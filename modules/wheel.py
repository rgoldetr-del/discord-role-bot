# modules/wheel.py
# Оптимизированное колесо:
# - сначала отвечаем на взаимодействие;
# - потом делаем проверки БД;
# - это убирает ошибку "Unknown interaction".

import asyncio
import random
import time

import discord

from database import db
from .shared import check_cooldown, get_rarity_name

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

KEY_FALLBACK_VALUE = {
    "common": 50,
    "rare": 150,
    "epic": 500
}

KEY_PREFERRED_RARITIES = {
    "common": ["common", "uncommon"],
    "rare": ["rare", "epic"],
    "epic": ["epic", "legendary", "secret", "secret+"]
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

    candidates = [
        case for case in active_cases
        if case["case_rarity"] in preferred
    ]

    if candidates:
        return random.choice(candidates)

    return random.choice(active_cases)


async def reset_pity(user_id: int, guild_id: int):
    await db.db.execute(
        "UPDATE users SET wheel_pity = 0 WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id)
    )
    await db.db.commit()


async def add_pity(user_id: int, guild_id: int):
    await db.db.execute(
        "UPDATE users SET wheel_pity = wheel_pity + 1 WHERE user_id = ? AND guild_id = ?",
        (user_id, guild_id)
    )
    await db.db.commit()


def register(bot):
    @bot.tree.command(name="wheel", description="Крутить почасовое колесо")
    async def wheel(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        # СНАЧАЛА подтверждаем взаимодействие.
        # Это обязательно, иначе Discord может убить взаимодействие с ошибкой
        # "Unknown interaction", если база отвечает дольше 3 секунд.
        try:
            await interaction.response.defer(ephemeral=False)
        except discord.HTTPException:
            return

        message = await interaction.original_response()

        try:
            await message.edit(content="🎰 Кручу колесо...")
        except discord.HTTPException:
            return

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await message.edit(content="⏳ Подожди немного.")
            return

        check = await db.can_spin_wheel(interaction.user.id, interaction.guild.id)

        if not check["can_spin"]:
            hours = int(check["time_left"] // 3600)
            minutes = int((check["time_left"] % 3600) // 60)
            seconds = int(check["time_left"] % 60)

            await message.edit(
                content=(
                    f"⏰ Ты уже крутил колесо.\n"
                    f"Следующее вращение через: **{hours}ч {minutes}м {seconds}с**\n"
                    f"Pity-счётчик: {check['pity']}/10"
                )
            )
            return

        active_cases = await db.get_all_cases(interaction.guild.id, active_only=True)

        if not active_cases:
            await message.edit(content="❌ Нет активных кейсов.")
            return

        # Лёгкая анимация.
        # Одна короткая пауза и одно редактирование, без тяжёлых циклов.
        await asyncio.sleep(0.45)

        user = await db.get_or_create_user(interaction.user.id, interaction.guild.id)
        now = int(time.time())

        async with db.db.execute(
            """
            UPDATE users
            SET last_wheel_time = ?
            WHERE user_id = ? AND guild_id = ? AND last_wheel_time <= ?
            """,
            (now, interaction.user.id, interaction.guild.id, now - 3600)
        ) as cursor:
            await db.db.commit()

            if cursor.rowcount == 0:
                await message.edit(content="⏰ Ты уже крутил колесо.")
                return

        pity = user["wheel_pity"]

        # Гарантированный ключ после 10 пустых.
        if pity >= 10:
            case = choose_case_for_key(active_cases, "rare")
            await db.add_key(interaction.user.id, interaction.guild.id, case["id"], 1)
            await reset_pity(interaction.user.id, interaction.guild.id)

            rarity_name = get_rarity_name(case["case_rarity"])

            await message.edit(
                content=(
                    f"🎉 **Pity-сброс!**\n"
                    f"🔑 Выпал **1 ключ** от кейса **{case['name']}** ({rarity_name})."
                )
            )
            return

        weights = [reward["weight"] for reward in WHEEL_REWARDS]
        reward = random.choices(WHEEL_REWARDS, weights=weights, k=1)[0]

        if reward["type"] == "empty":
            await add_pity(interaction.user.id, interaction.guild.id)

            await message.edit(
                content=(
                    f"💨 **Пусто.**\n"
                    f"Pity-счётчик: {pity + 1}/10"
                )
            )
            return

        await reset_pity(interaction.user.id, interaction.guild.id)

        if reward["type"] == "coins":
            amount = reward["amount"]
            await db.update_coins(interaction.user.id, interaction.guild.id, amount)

            await message.edit(
                content=f"💰 Выпало **{amount}** монет."
            )
            return

        if reward["type"] == "crystals":
            amount = reward["amount"]
            await db.update_crystals(interaction.user.id, interaction.guild.id, amount)

            await message.edit(
                content=f"💎 Выпало **{amount}** кристаллов."
            )
            return

        if reward["type"] == "case":
            case = random.choice(active_cases)
            await db.add_case(interaction.user.id, interaction.guild.id, case["id"], reward["quantity"])

            rarity_name = get_rarity_name(case["case_rarity"])

            await message.edit(
                content=(
                    f"📦 Выпал бесплатный кейс **{case['name']}** ({rarity_name})."
                )
            )
            return

        if reward["type"] == "key":
            tier = reward["tier"]
            quantity = reward["quantity"]

            if not active_cases:
                amount = KEY_FALLBACK_VALUE.get(tier, 50) * quantity
                await db.update_coins(interaction.user.id, interaction.guild.id, amount)

                await message.edit(
                    content=f"💰 Ключи закончились. Выпало **{amount}** монет."
                )
                return

            case = choose_case_for_key(active_cases, tier)
            await db.add_key(interaction.user.id, interaction.guild.id, case["id"], quantity)

            rarity_name = get_rarity_name(case["case_rarity"])
            key_word = plural_keys(quantity)

            await message.edit(
                content=(
                    f"🔑 Выпал **{quantity}** {key_word} "
                    f"от кейса **{case['name']}** ({rarity_name})."
                )
            )
            return

        await message.edit(content="❌ Неизвестная награда.")