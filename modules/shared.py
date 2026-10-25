# modules/shared.py
# Обновлённый общий модуль: редкости, кулдауны, доставка, роли, валюта.

import inspect
from datetime import datetime

import discord


def normalize_callback(func):
    """Совместимость коллбэков кнопок/селектов с разными сборками discord.py.

    Официальный discord.py вызывает callback(interaction), а форки (например,
    discord-ui-callbacks на хостинге) — callback(interaction, item).
    Возвращает обёртку, которая определяет Interaction по isinstance среди
    переданных аргументов и вызывает оригинал в нужной сигнатуре.
    """
    if getattr(func, "_norm_cb", False):
        return func
    sig = inspect.signature(func)
    accepts_item = len([p for p in sig.parameters.values()
                        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]) >= 2

    async def wrapper(*args):
        interaction = next((a for a in args if isinstance(a, discord.Interaction)), None)
        if interaction is None:
            raise TypeError("normalize_callback: среди аргументов нет Interaction")
        item = next((a for a in args if isinstance(a, discord.ui.Item)), None)
        if accepts_item:
            await func(interaction, item)
        else:
            await func(interaction)

    wrapper._norm_cb = True
    return wrapper


def safe_command(fn):
    """Обёртка slash-команд: перехватывает «Unknown interaction» (404).

    Возникает, когда бот медлит с ответом (>3 сек.) — Discord аннулирует
    interaction. Это не баг логики: молча игнорируем, чтобы не спамить в
    ERROR-лог. functools.wraps сохраняет сигнатуру и аннотации типов —
    tree.command() корректно разбирает параметры команды."""
    import functools

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            await fn(*args, **kwargs)
        except discord.NotFound:
            return
    # discord.py на некоторых хостингах — патченные сборки, где проверка
    # "это coroutine" идёт по __code__.co_flags напрямую (обёртка без await
    # внутри не имеет флага CO_COROUTINE). Восстанавливаем флаг вручную.
    wrapper.__code__ = wrapper.__code__.replace(co_flags=wrapper.__code__.co_flags | 0x100)
    wrapper.__annotations__ = getattr(fn, "__annotations__", {})
    return wrapper

from database import db

RARITY_EMOJI = {
    "common": "⚪",
    "uncommon": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟡",
    "secret": "🔴",
    "secret+": "⚫"
}

RARITY_NAME = {
    "common": "Обычная",
    "uncommon": "Необычная",
    "rare": "Редкая",
    "epic": "Эпическая",
    "legendary": "Легендарная",
    "secret": "Секретная",
    "secret+": "Абсолютная"
}

# Внутренний эквивалент нужен ТОЛЬКО для расчёта лимитов ставок в мини-играх.
# Это НЕ курс обмена: монеты и кристаллы не конвертируются друг в друга
# и обменять их между собой невозможно.
BET_VALUE_EQUIV = 10

MAX_PLAYER_CASES = 50   # максимум одинаковых кейсов в инвентаре
MAX_PLAYER_KEYS = 50    # максимум одинаковых ключей в инвентаре

cooldowns = {}


def get_rarity_emoji(rarity: str) -> str:
    return RARITY_EMOJI.get(rarity, "⚪")


def get_rarity_name(rarity: str) -> str:
    return RARITY_NAME.get(rarity, "Обычная")


def get_role_name(guild: discord.Guild, role_id: int) -> str:
    role = guild.get_role(role_id)
    return role.name if role else f"Роль {role_id}"


def can_manage(interaction: discord.Interaction) -> bool:
    """Владелец сервера или администратор."""
    if not interaction.guild:
        return False

    if interaction.user.id == interaction.guild.owner_id:
        return True

    try:
        return interaction.user.guild_permissions.administrator
    except Exception:
        return False


def mixed_value(coins: int, crystals: int) -> int:
    return max(0, coins) + max(0, crystals) * BET_VALUE_EQUIV


def format_bet(coins: int, crystals: int) -> str:
    coins = max(0, int(coins))
    crystals = max(0, int(crystals))

    if coins > 0 and crystals > 0:
        return f"{coins} монет и {crystals} кристаллов"

    if coins > 0:
        return f"{coins} монет"

    if crystals > 0:
        return f"{crystals} кристаллов"

    return "0 монет"


def format_reward(coins: int, crystals: int) -> str:
    return format_bet(coins, crystals)


async def check_cooldown(user_id: int, guild_id: int, seconds: int = 2) -> bool:
    key = f"{guild_id}:{user_id}"
    now = datetime.now().timestamp()

    if key in cooldowns and now - cooldowns[key] < seconds:
        return False

    cooldowns[key] = now
    return True


async def deliver_message(
    interaction: discord.Interaction,
    content: str = None,
    embed: discord.Embed = None,
    view=None
):
    try:
        if interaction.response.is_done():
            if interaction.message is not None:
                await interaction.message.edit(content=content, embed=embed, view=view)
            else:
                await interaction.edit_original_response(content=content, embed=embed, view=view)
        else:
            await interaction.response.edit_message(content=content, embed=embed, view=view)
    except discord.HTTPException:
        try:
            await interaction.edit_original_response(content=content, embed=embed, view=view)
        except Exception:
            pass


async def safe_remove_role(guild: discord.Guild, user_id: int, role_id: int):
    role = guild.get_role(role_id)

    if not role:
        return

    member = guild.get_member(user_id)

    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except discord.HTTPException:
            return

    try:
        await member.remove_roles(role, reason="Действие в боте")
    except discord.HTTPException:
        pass


def resolve_role_by_input(guild: discord.Guild, raw: str):
    raw = raw.strip()

    if not raw:
        return None

    if raw.startswith("<@&") and raw.endswith(">"):
        try:
            role_id = int(raw[3:-1])
            return guild.get_role(role_id)
        except ValueError:
            return None

    if raw.isdigit():
        return guild.get_role(int(raw))

    if raw.startswith("@"):
        raw = raw[1:].strip()

    role = discord.utils.get(guild.roles, name=raw)

    if role:
        return role

    lower_raw = raw.lower()

    for role in guild.roles:
        if role.name.lower() == lower_raw:
            return role

    for role in guild.roles:
        if lower_raw in role.name.lower():
            return role

    return None


# ===== Валюта: монеты + кристаллы =====

async def try_spend_mixed(user_id: int, guild_id: int, coins: int, crystals: int) -> bool:
    coins = max(0, int(coins))
    crystals = max(0, int(crystals))

    if coins == 0 and crystals == 0:
        return True

    await db.get_or_create_user(user_id, guild_id)

    async with db.db.execute(
        """
        UPDATE users
        SET coins = coins - ?, crystals = crystals - ?
        WHERE user_id = ? AND guild_id = ? AND coins >= ? AND crystals >= ?
        """,
        (coins, crystals, user_id, guild_id, coins, crystals)
    ) as cursor:
        await db.db.commit()
        return cursor.rowcount > 0


async def spend_coins(user_id: int, guild_id: int, amount: int) -> bool:
    return await try_spend_mixed(user_id, guild_id, amount, 0)


async def spend_crystals(user_id: int, guild_id: int, amount: int) -> bool:
    return await try_spend_mixed(user_id, guild_id, 0, amount)


async def award_mixed(user_id: int, guild_id: int, coins: int, crystals: int):
    coins = max(0, int(coins))
    crystals = max(0, int(crystals))

    if coins == 0 and crystals == 0:
        return

    await db.get_or_create_user(user_id, guild_id)

    await db.db.execute(
        """
        UPDATE users
        SET coins = coins + ?, crystals = crystals + ?
        WHERE user_id = ? AND guild_id = ?
        """,
        (coins, crystals, user_id, guild_id)
    )
    await db.db.commit()


async def award_mixed_win(
    user_id: int,
    guild_id: int,
    bet_coins: int,
    bet_crystals: int,
    multiplier: float,
    apply_rich_bonus: bool = True
):
    """
    Выплачивает выигрыш с комиссией 5%.
    Если ставка была смешанной, выплата сохраняется пропорционально.
    """
    bet_coins = max(0, int(bet_coins))
    bet_crystals = max(0, int(bet_crystals))
    bet_value = mixed_value(bet_coins, bet_crystals)

    if bet_value <= 0 or multiplier <= 0:
        return 0, 0, 0

    win_value = int(bet_value * multiplier * 0.95)
    profit = win_value - bet_value
    bonus_value = 0

    if apply_rich_bonus and profit > 0:
        try:
            rich_level = await db.get_upgradeable_role_level(user_id, guild_id, "rich")
        except Exception:
            rich_level = 0

        if rich_level > 0:
            bonus_value = int(profit * rich_level * 0.01)

    total_value = win_value + bonus_value

    if total_value <= 0:
        return 0, 0, 0

    if bet_crystals == 0:
        payout_coins = total_value
        payout_crystals = 0

    elif bet_coins == 0:
        payout_crystals = total_value // BET_VALUE_EQUIV
        payout_coins = total_value % BET_VALUE_EQUIV

    else:
        coin_share = bet_coins / bet_value
        payout_coins = int(total_value * coin_share)
        remaining_value = total_value - payout_coins

        payout_crystals = remaining_value // BET_VALUE_EQUIV
        payout_coins += remaining_value % BET_VALUE_EQUIV

    payout_coins = max(0, payout_coins)
    payout_crystals = max(0, payout_crystals)

    await award_mixed(user_id, guild_id, payout_coins, payout_crystals)

    return payout_coins, payout_crystals, bonus_value