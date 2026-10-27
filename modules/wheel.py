# modules/wheel.py
# ======================================================================
# Почасовое колесо: /wheel (крутить раз в час) + /wheel_info (награды).
# - сначала defer, потом работа с БД (убирает "Unknown interaction");
# - атомарный захват вращения через UPDATE ... WHERE last_wheel_time <= now-3600;
# - pity-система: после 10 пустых гарантируется редкий ключ;
# - награды (монеты/кристаллы/кейсы/ключи) падают в инвентарь — используются там.
# Заменяет старый wheel.py и отдельный wheel_info.py.
# ======================================================================

import asyncio
import random
import time

import discord
from discord import ui

from database import db
from .shared import check_cooldown, get_rarity_name, safe_command, make_resilient
from .persistent_utils import make_id, edit_view

WHEEL_COOLDOWN = 3600  # 1 час
PITY_MAX = 10

WHEEL_REWARDS = [
    {"type": "empty", "weight": 300},
    {"type": "key", "tier": "common", "quantity": 1, "weight": 150},
    {"type": "coins", "amount": 50, "weight": 80},
    {"type": "coins", "amount": 100, "weight": 70},
    {"type": "key", "tier": "common", "quantity": 2, "weight": 60},
    {"type": "crystals", "amount": 1, "weight": 60},
    {"type": "key", "tier": "rare", "quantity": 1, "weight": 50},
    {"type": "coins", "amount": 200, "weight": 40},
    {"type": "key", "tier": "common", "quantity": 3, "weight": 35},
    {"type": "crystals", "amount": 2, "weight": 30},
    {"type": "coins", "amount": 300, "weight": 25},
    {"type": "key", "tier": "rare", "quantity": 2, "weight": 20},
    {"type": "case", "quantity": 1, "weight": 20},
    {"type": "crystals", "amount": 3, "weight": 15},
    {"type": "coins", "amount": 500, "weight": 10},
    {"type": "key", "tier": "epic", "quantity": 1, "weight": 10},
    {"type": "crystals", "amount": 5, "weight": 8},
    {"type": "coins", "amount": 1000, "weight": 5},
    {"type": "key", "tier": "epic", "quantity": 2, "weight": 4},
    {"type": "crystals", "amount": 10, "weight": 3},
    {"type": "coins", "amount": 2000, "weight": 5},
]

KEY_FALLBACK_VALUE = {"common": 50, "rare": 150, "epic": 500}

KEY_PREFERRED_RARITIES = {
    "common": ["common", "uncommon"],
    "rare": ["rare", "epic"],
    "epic": ["epic", "legendary", "secret", "secret+"],
}


def plural_keys(n: int) -> str:
    n = abs(n) % 100
    n1 = n % 10
    if 10 < n < 20:
        return "ключей"
    if 1 < n1 < 5:
        return "ключа"
    if n1 == 1:
        return "ключ"
    return "ключей"


def choose_case_for_key(active_cases, tier: str):
    preferred = KEY_PREFERRED_RARITIES.get(tier, [])
    candidates = [c for c in active_cases if c["case_rarity"] in preferred]
    return random.choice(candidates or active_cases)


async def _set_pity(user_id: int, guild_id: int, value: int):
    await db.db.execute(
        "UPDATE users SET wheel_pity = ? WHERE user_id = ? AND guild_id = ?",
        (value, user_id, guild_id),
    )
    await db.db.commit()


async def _grant(reward: dict, user_id: int, guild_id: int, active_cases) -> str:
    """Выдаёт награду, возвращает текст результата."""
    rtype = reward["type"]

    if rtype == "coins":
        await db.update_coins(user_id, guild_id, reward["amount"])
        return f"💰 Выпало **{reward['amount']:,}** монет.".replace(",", " ")

    if rtype == "crystals":
        await db.update_crystals(user_id, guild_id, reward["amount"])
        return f"💎 Выпало **{reward['amount']}** кристаллов."

    if rtype == "case":
        case = random.choice(active_cases)
        await db.add_case(user_id, guild_id, case["id"], reward["quantity"])
        return (f"📦 Выпал бесплатный кейс **{case['name']}** "
                f"({get_rarity_name(case['case_rarity'])})! Лежит в /inventory.")

    if rtype == "key":
        quantity = reward["quantity"]
        if not active_cases:  # страховка: на сервере нет кейсов — компенсируем монетами
            amount = KEY_FALLBACK_VALUE.get(reward["tier"], 50) * quantity
            await db.update_coins(user_id, guild_id, amount)
            return (f"💰 На сервере пока нет кейсов — вместо ключей выпало "
                    f"**{amount:,}** монет.".replace(",", " "))
        case = choose_case_for_key(active_cases, reward["tier"])
        await db.add_key(user_id, guild_id, case["id"], quantity)
        return (f"🔑 Выпало **{quantity}** {plural_keys(quantity)} "
                f"от кейса **{case['name']}** ({get_rarity_name(case['case_rarity'])}) "
                f"— лежат в /inventory.")

    return "❌ Неизвестная награда."


class WheelSpinButton(ui.Button):
    def __init__(self, user_id: int):
        super().__init__(
            label="🎡 Крутить колесо",
            style=discord.ButtonStyle.primary,
            custom_id=make_id("wheel", "spin", user_id),
        )
        self.owner = user_id

    async def callback(self, interaction: discord.Interaction, item=None):
        if interaction.user.id != self.owner:
            await interaction.response.send_message("Колесо не твоё 🙂", ephemeral=True)
            return
        await run_spin(interaction)

def _wheel_view(user_id: int) -> ui.View:
    """Кнопку нужно класть внутрь View, иначе дискорд не примет её как компонент."""
    view = ui.View(timeout=None)
    view.add_item(WheelSpinButton(user_id))
    return view

async def run_spin(interaction: discord.Interaction):
    """Основная логика вращения. Используется и командой, и кнопкой."""
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("Только на сервере.", ephemeral=True)
        return

    user_id, guild_id = interaction.user.id, guild.id

    # Сначала подтверждаем взаимодействие — иначе Discord убьёт его таймаутом.
    try:
        await interaction.response.defer()
    except discord.HTTPException:
        return

    message = await interaction.original_response()

    if not await check_cooldown(user_id, guild_id):
        await edit_view(interaction, content="⏳ Слишком быстро, подожди пару секунд.")
        return

    check = await db.can_spin_wheel(user_id, guild_id)
    if not check["can_spin"]:
        until = int(time.time()) + int(check["time_left"])
        await edit_view(
            interaction,
            content=(
                f"⏰ Колесо уже крутили. Следующее вращение: <t:{until}:R>\n"
                f"Pity-счётчик: {check['pity']}/{PITY_MAX}"
            ),
            view=_wheel_view(user_id),
        )
        return

    # Атомарный захват вращения (защита от гонки двух кликов).
    now = int(time.time())
    async with db.db.execute(
        "UPDATE users SET last_wheel_time = ? "
        "WHERE user_id = ? AND guild_id = ? AND last_wheel_time <= ?",
        (now, user_id, guild_id, now - WHEEL_COOLDOWN),
    ) as cursor:
        await db.db.commit()
        if cursor.rowcount == 0:
            await edit_view(interaction, content="⏰ Ты уже крутил колесо.")
            return

    active_cases = await db.get_all_cases(guild_id, active_only=True)

    # Лёгкая анимация: несколько быстрых «секторов».
    sectors = ["🎡", "✨", "💰", "💎", "🔑", "📦"]
    for s in sectors[:4]:
        try:
            await message.edit(content=f"{s} Кручу колесо...")
        except discord.HTTPException:
            break
        await asyncio.sleep(0.35)

    pity = check["pity"]

    # Гарантированный ключ после PITY_MAX пустых.
    if pity >= PITY_MAX and active_cases:
        case = choose_case_for_key(active_cases, "rare")
        await db.add_key(user_id, guild_id, case["id"], 1)
        await _set_pity(user_id, guild_id, 0)
        result = (f"🎉 **Pity-сброс!** Выпал **1 ключ** от кейса "
                  f"**{case['name']}** ({get_rarity_name(case['case_rarity'])}).")
    else:
        weights = [r["weight"] for r in WHEEL_REWARDS]
        reward = random.choices(WHEEL_REWARDS, weights=weights, k=1)[0]
        if reward["type"] == "empty":
            await _set_pity(user_id, guild_id, pity + 1)
            result = f"💨 **Пусто.** Pity-счётчик: {pity + 1}/{PITY_MAX}"
        else:
            await _set_pity(user_id, guild_id, 0)
            result = await _grant(reward, user_id, guild_id, active_cases)

    next_time = int(time.time()) + WHEEL_COOLDOWN
    await edit_view(
        interaction,
        content=f"{result}\n⏱️ Следующее вращение: <t:{next_time}:R>",
        view=None,
    )


def _rewards_text() -> str:
    total = sum(r["weight"] for r in WHEEL_REWARDS)

    def pct(w):
        return f"{w / total * 100:.1f}%"

    icons = {"coins": "💰", "crystals": "💎", "key": "🔑", "case": "📦", "empty": "💨"}
    lines = []
    for r in sorted(WHEEL_REWARDS, key=lambda x: -x["weight"]):
        if r["type"] == "coins":
            name = f"{r['amount']:,} монет".replace(",", " ")
        elif r["type"] == "crystals":
            name = f"{r['amount']} кр."
        elif r["type"] == "key":
            name = f"{r['quantity']} {plural_keys(r['quantity'])} ({r['tier']})"
        elif r["type"] == "case":
            name = "кейс"
        else:
            name = "пусто"
        lines.append(f"{icons[r['type']]} {pct(r['weight'])} — {name}")
    return "\n".join(lines)


def register(bot):
    @bot.tree.command(name="wheel", description="Крутить почасовое колесо 🎡")
    @safe_command
    async def wheel(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        check = await db.can_spin_wheel(interaction.user.id, interaction.guild.id)
        if check["can_spin"]:
            await run_spin(interaction)
            return

        until = int(time.time()) + int(check["time_left"])
        embed = discord.Embed(
            title="🎡 Почасовое колесо",
            description=(
                f"⏰ Следующее вращение доступно: <t:{until}:R>\n"
                f"Pity-счётчик: **{check['pity']}/{PITY_MAX}** "
                f"(после {PITY_MAX} пустых — гарантированный редкий ключ)."
            ),
            color=0x9C27B0,
        )
        await interaction.response.send_message(
            embed=embed, view=_wheel_view(interaction.user.id), ephemeral=True,
        )

    @bot.tree.command(name="wheel_info", description="Посмотреть награды почасового колеса")
    @safe_command
    async def wheel_info(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎡 Награды почасового колеса",
            description="Крутить можно **раз в час**. Все выигрыши падают в /inventory.\n\n",
            color=0x9C27B0,
        )
        embed.add_field(name="Шансы выпадения", value=_rewards_text(), inline=False)
        embed.set_footer(text="Валюты не конвертируются. Pity: после 10 пустых — редкий ключ.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


    # --- Автозащита всех UI-коллбэков модуля (кнопки/селекты/модалки) ---
    # make_resilient перехватывает любые исключения (в т.ч. 404 Unknown
    # interaction) и подстраивает сигнатуру под стиль вызова библиотеки.
    for _cls in list(globals().values()):
        try:
            if not (isinstance(_cls, type) and (
                    issubclass(_cls, discord.ui.View) or issubclass(_cls, discord.ui.Item))):
                continue
        except TypeError:
            continue
        for _name, _attr in list(vars(_cls).items()):
            if _name == "callback" and callable(_attr) and not getattr(_attr, "_wrapped_by_guard", False):
                setattr(_cls, _name, make_resilient(_attr))
