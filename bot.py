import os
import io
import json
import random
import asyncio
import logging
import time

import discord
from discord import app_commands
from dotenv import load_dotenv

from wheel import Segment, make_wheel_gif, make_wheel_png

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DEV_GUILD_ID = os.getenv("DEV_GUILD_ID", "").strip()
DATA_FILE = "data.json"

FREE_VISUAL_INTERVAL_SECONDS = 60 * 60  # 1 час

if not TOKEN:
    raise SystemExit("Укажи DISCORD_TOKEN в файле .env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("role-wheel")

# ==================== ВАЛЮТЫ И НАСТРОЙКИ ====================
TOP_VISUAL_ROLE_ID = 1553819177741975733
EMPTY_COLOR = "#2A3350"

# Все варианты визуального колеса.
# Порядок важен: этот же индекс используется при выборе победителя.
VISUAL_OUTCOMES = [
    {"role_id": 1560109884228239410, "weight": 3000, "color": "#475569"},  # самая плохая визуал роль
    {"role_id": 1559965196535992411, "weight": 1500, "color": "#06B6D4"},
    {"role_id": 1559965097948872714, "weight": 1000, "color": "#10B981"},
    {"role_id": 1559961941269553262, "weight": 700,  "color": "#84CC16"},
    {"role_id": 1559960655472107551, "weight": 500,  "color": "#EAB308"},
    {"role_id": 1559960565449887784, "weight": 300,  "color": "#F59E0B"},
    {"role_id": 1554524369857019904, "weight": 80,   "color": "#EF4444"},
    {"role_id": 1559936940059660469, "weight": 40,   "color": "#A855F7"},
    {"role_id": 1553819177741975733, "weight": 15,   "color": "#FFD700"},  # ТОП визуал
    {"role_id": None, "weight": 500, "color": EMPTY_COLOR, "label": "ПУСТО", "is_empty": True},
]

# Все варианты админского колеса.
ADMIN_OUTCOMES = [
    {"role_id": 1553836651984199850, "weight": 2000, "color": "#64748B"},
    {"role_id": 1554503215561580574, "weight": 1200, "color": "#7C3AED"},
    {"role_id": 1553834047514476624, "weight": 600,  "color": "#DB2777"},
    {"role_id": 1553064131903496313, "weight": 150,  "color": "#DC2626"},
    {"role_id": 1553834837570228305, "weight": 20,   "color": "#F59E0B"},  # главная админка
    {"role_id": None, "weight": 6030, "color": EMPTY_COLOR, "label": "ПУСТО", "is_empty": True},
]

WHEELS = {
    "visual": {
        "title": "КОЛЕСО ФОРТУНЫ",
        "subtitle": "Визуальное колесо · 1 крутка",
        "outcomes": VISUAL_OUTCOMES,
    },
    "admin": {
        "title": "КОЛЕСО ФОРТУНЫ",
        "subtitle": "Админское колесо · 1 админская крутка",
        "outcomes": ADMIN_OUTCOMES,
    },
}

VISUAL_ROLE_IDS = {
    o["role_id"] for o in VISUAL_OUTCOMES if o.get("role_id") is not None
}
ADMIN_ROLE_IDS = {
    o["role_id"] for o in ADMIN_OUTCOMES if o.get("role_id") is not None
}

# Продажа:
# - все визуальные роли, кроме ТОП визуал, дают 1 визуальную крутку;
# - ТОП визуал даёт 1 админскую крутку;
# - все админские роли дают 1 админскую крутку.
SELL_VISUAL_IDS = VISUAL_ROLE_IDS - {TOP_VISUAL_ROLE_ID}
SELL_ADMIN_IDS = ADMIN_ROLE_IDS | {TOP_VISUAL_ROLE_ID}

# ==================== КЛИЕНТ ====================
intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

DATA_LOCK = asyncio.Lock()
BUSY = set()
RENDER_SEM = asyncio.Semaphore(2)


def can_manage(guild: discord.Guild, role: discord.Role) -> bool:
    return guild.me.top_role > role


# ==================== ХРАНИЛИЩЕ ====================
def load_data():
    default_data = {
        "visual_spins": {},
        "admin_spins": {},
        "free_claims": {},
    }

    if not os.path.exists(DATA_FILE):
        return default_data

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return default_data

        data.setdefault("visual_spins", {})
        data.setdefault("admin_spins", {})
        data.setdefault("free_claims", {})
        return data

    except Exception:
        log.exception("Не удалось прочитать data.json")
        return default_data


def save_data(data):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def key(guild_id: int, user_id: int) -> str:
    return f"{guild_id}:{user_id}"


def get_spins(data, guild_id: int, user_id: int, kind: str) -> int:
    try:
        return int(data.get(f"{kind}_spins", {}).get(key(guild_id, user_id), 0))
    except (TypeError, ValueError):
        return 0


def add_spins(data, guild_id: int, user_id: int, kind: str, amount: int) -> int:
    store = data.setdefault(f"{kind}_spins", {})
    k = key(guild_id, user_id)
    store[k] = max(0, get_spins(data, guild_id, user_id, kind) + int(amount))
    return store[k]


async def refund(guild_id: int, user_id: int, kind: str):
    async with DATA_LOCK:
        data = load_data()
        add_spins(data, guild_id, user_id, kind, 1)
        save_data(data)


def get_last_free_claim(data, guild_id: int, user_id: int) -> float:
    try:
        return float(data.get("free_claims", {}).get(key(guild_id, user_id), 0.0))
    except (TypeError, ValueError):
        return 0.0


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []

    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    if not parts or secs:
        parts.append(f"{secs} сек")

    return " ".join(parts)


# ==================== КОЛЕСО ====================
def build_segments(guild: discord.Guild, kind: str):
    cfg = WHEELS[kind]
    segments = []

    for i, outcome in enumerate(cfg["outcomes"]):
        role_id = outcome.get("role_id")
        is_empty = bool(outcome.get("is_empty", role_id is None))

        if role_id is None:
            label = outcome.get("label", "ПУСТО")
        else:
            role = guild.get_role(role_id)
            label = role.name if role else outcome.get("label", f"Приз {i + 1}")

        segments.append(
            Segment(
                label=label,
                color=outcome["color"],
                weight=float(outcome["weight"]),
                role_id=role_id,
                is_empty=is_empty,
            )
        )

    return segments


def choose_winner(kind: str) -> int:
    outcomes = WHEELS[kind]["outcomes"]
    weights = [float(o["weight"]) for o in outcomes]
    return random.choices(range(len(outcomes)), weights=weights, k=1)[0]


async def render_wheel_gif(guild: discord.Guild, kind: str, winner_index: int) -> bytes:
    cfg = WHEELS[kind]
    segments = build_segments(guild, kind)

    async with RENDER_SEM:
        return await asyncio.to_thread(
            make_wheel_gif,
            segments,
            winner_index,
            cfg["title"],
            cfg["subtitle"],
            random.randrange(1, 1_000_000_000),
        )


# ==================== СТАРТ ====================
@client.event
async def on_ready():
    try:
        if DEV_GUILD_ID:
            guild = discord.Object(id=int(DEV_GUILD_ID))
            tree.copy_global_to(guild=guild)
            await tree.sync(guild=guild)
        else:
            await tree.sync()
    except Exception:
        log.exception("Не удалось синхронизировать команды")

    log.info("Бот запущен как %s", client.user)

    # Предупреждения об иерархии ролей
    for guild in client.guilds:
        for kind, cfg in WHEELS.items():
            for outcome in cfg["outcomes"]:
                role_id = outcome.get("role_id")
                if role_id is None:
                    continue

                role = guild.get_role(role_id)
                if role is None:
                    log.warning(
                        "[%s] В колесе %s указан несуществующий role_id: %s",
                        guild.name,
                        kind,
                        role_id,
                    )
                elif not can_manage(guild, role):
                    log.warning(
                        "[%s] Бот не может управлять ролью %s. Подними роль бота выше неё.",
                        guild.name,
                        role.name,
                    )


# ==================== ПРОДАЖА РОЛИ ====================
@tree.command(name="sell_role", description="Продать свою роль и получить крутки")
@app_commands.describe(role="Роль, которую хочешь продать")
async def sell_role(interaction: discord.Interaction, role: discord.Role):
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Только на сервере.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    member = interaction.user

    if role.is_default():
        await interaction.followup.send("Роль @everyone нельзя продать.", ephemeral=True)
        return

    if role not in member.roles:
        await interaction.followup.send("У тебя нет этой роли.", ephemeral=True)
        return

    if not can_manage(interaction.guild, role):
        await interaction.followup.send(
            "Бот не может управлять этой ролью. Роль бота должна быть выше.",
            ephemeral=True,
        )
        return

    if role.id in SELL_VISUAL_IDS:
        kind = "visual"
        reward_text = "визуальную крутку"
    elif role.id in SELL_ADMIN_IDS:
        kind = "admin"
        reward_text = "админскую крутку"
    else:
        await interaction.followup.send("Эту роль нельзя продать.", ephemeral=True)
        return

    try:
        await member.remove_roles(role, reason=f"Продажа роли {role.name}")
    except discord.HTTPException:
        await interaction.followup.send("Не удалось снять роль.", ephemeral=True)
        return

    async with DATA_LOCK:
        data = load_data()
        balance = add_spins(data, interaction.guild.id, member.id, kind, 1)
        save_data(data)

    await interaction.followup.send(
        f"✅ Ты продал роль **{role.name}** и получил 1 {reward_text}.\n"
        f"Баланс: **{balance}**.",
        ephemeral=True,
    )


# ==================== ПОКУПКА ТОП ВИЗУАЛ ====================
@tree.command(name="buy_top_visual", description="Купить ТОП визуальную роль за 1 админскую крутку")
async def buy_top_visual(interaction: discord.Interaction):
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Только на сервере.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    member = interaction.user
    role = interaction.guild.get_role(TOP_VISUAL_ROLE_ID)

    if role is None:
        await interaction.followup.send("ТОП визуальная роль не найдена.", ephemeral=True)
        return

    if not can_manage(interaction.guild, role):
        await interaction.followup.send(
            "Бот не может выдать эту роль. Подними роль бота выше неё.",
            ephemeral=True,
        )
        return

    if role in member.roles:
        await interaction.followup.send("У тебя уже есть эта роль.", ephemeral=True)
        return

    async with DATA_LOCK:
        data = load_data()
        if get_spins(data, interaction.guild.id, member.id, "admin") < 1:
            await interaction.followup.send(
                "Нужна 1 админская крутка.",
                ephemeral=True,
            )
            return

        add_spins(data, interaction.guild.id, member.id, "admin", -1)
        save_data(data)

    try:
        await member.add_roles(role, reason="Покупка ТОП визуальной роли")
    except discord.HTTPException:
        await refund(interaction.guild.id, member.id, "admin")
        await interaction.followup.send(
            "Не удалось выдать роль. Админская крутка возвращена.",
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        f"🎉 Ты получил роль **{role.name}** за 1 админскую крутку!",
        ephemeral=True,
    )


# ==================== БЕСПЛАТНАЯ ВИЗУАЛЬНАЯ КРУТКА РАЗ В ЧАС ====================
@tree.command(
    name="free_visual",
    description="Получить 1 бесплатную визуальную крутку раз в час"
)
async def free_visual(interaction: discord.Interaction):
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Только на сервере.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    member = interaction.user
    now = time.time()

    allowed = False
    remaining = 0.0
    balance = 0

    async with DATA_LOCK:
        data = load_data()
        claims = data.setdefault("free_claims", {})
        k = key(guild.id, member.id)

        last_claim = get_last_free_claim(data, guild.id, member.id)
        elapsed = now - last_claim

        if elapsed < FREE_VISUAL_INTERVAL_SECONDS:
            remaining = FREE_VISUAL_INTERVAL_SECONDS - elapsed
        else:
            balance = add_spins(data, guild.id, member.id, "visual", 1)
            claims[k] = now
            save_data(data)
            allowed = True

    if not allowed:
        await interaction.followup.send(
            f"⏳ Бесплатная визуальная крутка будет доступна через **{format_duration(remaining)}**.",
            ephemeral=True,
        )
        return

    await interaction.followup.send(
        f"🎁 Ты получил **1 бесплатную визуальную крутку**!\n"
        f"Текущий баланс визуальных круток: **{balance}**.\n"
        f"Следующая бесплатная крутка будет доступна через 1 час.",
        ephemeral=True,
    )


# ==================== КРУЧЕНИЕ ====================
async def run_spin(interaction: discord.Interaction, kind: str):
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Только на сервере.", ephemeral=True)
        return

    guild = interaction.guild
    member = interaction.user
    busy_key = (guild.id, member.id)

    if busy_key in BUSY:
        await interaction.response.send_message(
            "⏳ Ты уже крутишь колесо. Подожди пару секунд.",
            ephemeral=True,
        )
        return

    async with DATA_LOCK:
        data = load_data()
        if get_spins(data, guild.id, member.id, kind) < 1:
            await interaction.response.send_message(
                "❌ У тебя нет круток. Продай роль через `/sell_role` или получи бесплатную через `/free_visual`.",
                ephemeral=True,
            )
            return

    cfg = WHEELS[kind]
    wheel_name = cfg["subtitle"].split(" ·")[0].lower()

    # Отвечаем сразу, чтобы Discord не отвалился по таймауту.
    await interaction.response.send_message(
        f"🎰 {member.mention} запускает **{wheel_name}** колесо..."
    )
    message = await interaction.original_response()

    BUSY.add(busy_key)
    spent = False
    gif_bytes = None

    try:
        # Списываем крутку.
        async with DATA_LOCK:
            data = load_data()
            add_spins(data, guild.id, member.id, kind, -1)
            save_data(data)
        spent = True

        # Выбираем победителя ДО рендера.
        winner_index = choose_winner(kind)

        # Рендерим колесо специально под этого победителя.
        gif_bytes = await render_wheel_gif(guild, kind, winner_index)

        outcome = cfg["outcomes"][winner_index]
        role_id = outcome.get("role_id")

        if role_id is None:
            result = (
                f"💨 **Пусто!** {member.mention} крутил колесо, но приз не выпал. "
                f"Крутка сгорела."
            )

        else:
            role = guild.get_role(role_id)

            if role is None:
                log.error(
                    "[%s] Выпавшая роль не найдена: %s",
                    guild.name,
                    role_id,
                )
                result = (
                    f"🎡 Выпала роль **{outcome.get('label', 'неизвестная роль')}**, "
                    f"но такой роли нет на сервере. Крутка сгорела."
                )

            elif role in member.roles:
                result = (
                    f"🎡 Выпала роль **{role.name}**, но она у тебя уже есть. "
                    f"Крутка сгорела."
                )

            else:
                try:
                    await member.add_roles(role, reason="Приз колеса фортуны")
                    result = f"🎉 **{member.display_name}** выбивает **{role.name}**!"
                except discord.HTTPException:
                    log.exception(
                        "[%s] Не удалось выдать роль %s пользователю %s",
                        guild.name,
                        role.name,
                        member,
                    )
                    result = (
                        f"🎡 Выпала роль **{role.name}**, но бот не смог её выдать. "
                        f"Крутка сгорела. Проверь иерархию ролей."
                    )

        await message.edit(
            content=result,
            attachments=[
                discord.File(
                    io.BytesIO(gif_bytes),
                    filename="wheel.gif",
                )
            ],
        )

    except Exception:
        log.exception("Ошибка при кручении")

        # Если колесо ещё не было отрендерено, возвращаем крутку.
        # Если GIF уже готов — считаем, что спин состоялся.
        if spent and gif_bytes is None:
            await refund(guild.id, member.id, kind)
            err = "⚠️ Произошла техническая ошибка до прокрутки. Крутка возвращена."
        else:
            err = "⚠️ Произошла техническая ошибка. Обратись к администратору."

        try:
            await message.edit(content=err)
        except discord.HTTPException:
            pass

    finally:
        BUSY.discard(busy_key)


@tree.command(name="spin_visual", description="Крутить визуальное колесо за 1 визуальную крутку")
async def spin_visual(interaction: discord.Interaction):
    await run_spin(interaction, "visual")


@tree.command(name="spin_admin", description="Крутить админское колесо за 1 админскую крутку")
async def spin_admin(interaction: discord.Interaction):
    await run_spin(interaction, "admin")


# ==================== БАЛАНС ====================
@tree.command(name="balance", description="Показать количество круток")
async def balance(interaction: discord.Interaction):
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Только на сервере.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    member = interaction.user
    now = time.time()

    async with DATA_LOCK:
        data = load_data()
        v = get_spins(data, guild.id, member.id, "visual")
        a = get_spins(data, guild.id, member.id, "admin")

        last_claim = get_last_free_claim(data, guild.id, member.id)
        elapsed = now - last_claim
        remaining = max(0.0, FREE_VISUAL_INTERVAL_SECONDS - elapsed)

    if remaining <= 0:
        free_status = "✅ Доступна сейчас: `/free_visual`"
    else:
        free_status = f"⏳ Будет доступна через {format_duration(remaining)}"

    embed = discord.Embed(title="🎟 Твой баланс", color=0x5865F2)
    embed.add_field(name="Визуальные крутки", value=f"**{v}**", inline=False)
    embed.add_field(name="Админские крутки", value=f"**{a}**", inline=False)
    embed.add_field(name="Бесплатная визуальная крутка", value=free_status, inline=False)
    embed.set_footer(text="/spin_visual · /spin_admin · /free_visual")

    await interaction.followup.send(embed=embed, ephemeral=True)


# ==================== ИНФО О КОЛЁСАХ ====================
@tree.command(name="wheel", description="Показать колёса, шансы и индексы исходов")
async def wheel_info(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Только на сервере.", ephemeral=True)
        return

    await interaction.response.defer()

    files = []
    embeds = []

    for kind, cfg in WHEELS.items():
        segments = build_segments(interaction.guild, kind)
        png = await asyncio.to_thread(
            make_wheel_png,
            segments,
            cfg["title"],
            cfg["subtitle"],
            None,
        )
        files.append(
            discord.File(
                io.BytesIO(png),
                filename=f"{kind}_wheel.png",
            )
        )

        total = sum(float(o["weight"]) for o in cfg["outcomes"]) or 1.0
        lines = []

        for idx, outcome in enumerate(cfg["outcomes"]):
            pct = float(outcome["weight"]) / total * 100.0
            role_id = outcome.get("role_id")

            if role_id is None:
                label = outcome.get("label", "ПУСТО")
            else:
                role = interaction.guild.get_role(role_id)
                label = role.name if role else outcome.get("label", f"Приз {idx + 1}")

            lines.append(f"`{idx:>2}` `{pct:6.2f}%` {label}")

        embed = discord.Embed(
            title=cfg["subtitle"],
            description="\n".join(lines),
            color=0xFFD66E,
        )
        embed.set_footer(
            text="Индексы нужны для /preview_spin. Шансы реальные, секторы честные."
        )
        embeds.append(embed)

    await interaction.followup.send(files=files, embeds=embeds)


# ==================== ПРЕДПРОСМОТР ВСЕХ ВАРИАНТОВ ====================
@tree.command(
    name="preview_spin",
    description="Админ: показать конкретный вариант колеса без выдачи роли"
)
@app_commands.describe(
    kind="Какое колесо",
    outcome_index="Индекс исхода из команды /wheel"
)
@app_commands.choices(kind=[
    app_commands.Choice(name="Визуальное", value="visual"),
    app_commands.Choice(name="Админское", value="admin"),
])
@app_commands.default_permissions(administrator=True)
async def preview_spin(
    interaction: discord.Interaction,
    kind: app_commands.Choice[str],
    outcome_index: int,
):
    if not interaction.guild:
        await interaction.response.send_message("Только на сервере.", ephemeral=True)
        return

    if not (
        interaction.user.guild_permissions.administrator
        or interaction.user.id == interaction.guild.owner_id
    ):
        await interaction.response.send_message("Недостаточно прав.", ephemeral=True)
        return

    cfg = WHEELS[kind.value]

    if outcome_index < 0 or outcome_index >= len(cfg["outcomes"]):
        await interaction.response.send_message(
            f"Неверный индекс. Допустимо: `0 ... {len(cfg['outcomes']) - 1}`.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    message = await interaction.original_response()

    try:
        gif_bytes = await render_wheel_gif(
            interaction.guild,
            kind.value,
            outcome_index,
        )

        segments = build_segments(interaction.guild, kind.value)
        label = segments[outcome_index].label

        await message.edit(
            content=f"🧪 Предпросмотр варианта `{outcome_index}`: **{label}**",
            attachments=[
                discord.File(
                    io.BytesIO(gif_bytes),
                    filename="preview.gif",
                )
            ],
        )

    except Exception:
        log.exception("Ошибка предпросмотра колеса")
        await message.edit(content="⚠️ Не удалось отрендерить предпросмотр.")


# ==================== АДМИН: ВЫДАТЬ КРУТКИ ====================
@tree.command(name="give_spins", description="Админ: выдать крутки пользователю")
@app_commands.describe(
    user="Пользователь",
    amount="Количество",
    kind="Тип круток"
)
@app_commands.choices(kind=[
    app_commands.Choice(name="Визуальные", value="visual"),
    app_commands.Choice(name="Админские", value="admin"),
])
@app_commands.default_permissions(administrator=True)
async def give_spins(
    interaction: discord.Interaction,
    user: discord.Member,
    amount: int,
    kind: app_commands.Choice[str],
):
    if not interaction.guild:
        await interaction.response.send_message("Только на сервере.", ephemeral=True)
        return

    if not (
        interaction.user.guild_permissions.administrator
        or interaction.user.id == interaction.guild.owner_id
    ):
        await interaction.response.send_message("Недостаточно прав.", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message(
            "Количество должно быть больше нуля.",
            ephemeral=True,
        )
        return

    async with DATA_LOCK:
        data = load_data()
        new_balance = add_spins(
            data,
            interaction.guild.id,
            user.id,
            kind.value,
            amount,
        )
        save_data(data)

    await interaction.response.send_message(
        f"✅ Выдано **{amount}** {kind.name.lower()} круток пользователю {user.mention}.\n"
        f"Баланс: **{new_balance}**.",
        ephemeral=True,
    )


if __name__ == "__main__":
    client.run(TOKEN)