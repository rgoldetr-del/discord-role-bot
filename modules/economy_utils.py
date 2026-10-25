# modules/economy_utils.py
# Единые вспомогательные функции экономики для всех модулей:
# - mixed-ставки (монеты + кристаллы) и лимиты ставок;
# - payout с учётом эффектов «Критик», «Богач», «Хранитель кристаллов»;
# - скидка 10% на покупки;
# - лимиты кейсов и ключей (защита от "раздувания" экономики);
# - единый курс валют.

import random
import time

from database import db
from .shared import award_mixed, award_mixed_win

COIN_PER_CRYSTAL = 10

MIN_BET_VALUE = 10
MAX_BET_VALUE = 25000


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))


async def has_effect(user_id: int, guild_id: int, effect: str) -> bool:
    try:
        return await db.has_effect(user_id, guild_id, effect)
    except Exception:
        return False


async def get_max_bet_value(user_id: int, guild_id: int) -> int:
    """
    Максимальная ставка в монетном эквиваленте:
    10% богатства игрока, потолок по лучшей редкости, + стоимость кристаллов.
    Эффект «Азарт» увеличивает лимит в 1.5 раза.
    """
    try:
        base = await db.get_max_bet(user_id, guild_id)
    except Exception:
        base = 1000

    user = await db.get_or_create_user(user_id, guild_id)
    crystal_value = (user["crystals"] or 0) * COIN_PER_CRYSTAL

    limit = max(MIN_BET_VALUE, int(base) + crystal_value)

    if await has_effect(user_id, guild_id, "high_roller"):
        limit = int(limit * 1.5)

    return clamp(limit, MIN_BET_VALUE, MAX_BET_VALUE)


async def validate_mixed_bet(user_id: int, guild_id: int, coins: int, crystals: int):
    """Возвращает (ok, message)."""
    coins = max(0, int(coins))
    crystals = max(0, int(crystals))

    total = coins + crystals * COIN_PER_CRYSTAL

    if total < MIN_BET_VALUE:
        return False, f"❌ Минимальная ставка: {MIN_BET_VALUE} монет по курсу."

    max_bet = await get_max_bet_value(user_id, guild_id)

    if total > max_bet:
        return False, f"❌ Максимальная ставка для тебя сейчас: {max_bet} монет по курсу."

    return True, None


async def payout_with_effects(
    user_id: int,
    guild_id: int,
    bet_coins: int,
    bet_crystals: int,
    multiplier: float,
    rich_bonus: bool = True,
    allow_crit: bool = True,
):
    """
    Выплата выигрыша:
    - комиссия дома 5%;
    - бонус «Богач» (+1% за уровень к прибыли);
    - шанс крита «Критик»: 10% → +25% к выплате;
    - смешанная ставка возвращается пропорционально.
    Возвращает (coins, crystals, crit, bonus_value).
    """
    bet_coins = max(0, int(bet_coins))
    bet_crystals = max(0, int(bet_crystals))
    bet_value = bet_coins + bet_crystals * COIN_PER_CRYSTAL

    if bet_value <= 0 or multiplier <= 0:
        return 0, 0, False, 0

    win_value = int(bet_value * multiplier * 0.95)
    profit = win_value - bet_value
    bonus_value = 0

    if rich_bonus and profit > 0:
        try:
            rich_level = await db.get_upgradeable_role_level(user_id, guild_id, "rich")
        except Exception:
            rich_level = 0

        if rich_level > 0:
            bonus_value = int(profit * rich_level * 0.01)

    total_value = win_value + bonus_value

    crit = False

    if allow_crit and total_value > 0 and await has_effect(user_id, guild_id, "critic"):
        if random.random() < 0.10:
            total_value = int(total_value * 1.25)
            crit = True

    if total_value <= 0:
        return 0, 0, crit, bonus_value

    # Пропорциональная выдача: кристаллы возвращаем кристаллами, монеты — монетами.
    if bet_crystals == 0:
        payout_coins, payout_crystals = total_value, 0
    elif bet_coins == 0:
        payout_crystals = total_value // COIN_PER_CRYSTAL
        payout_coins = total_value % COIN_PER_CRYSTAL
    else:
        coin_share = bet_coins / bet_value
        payout_coins = int(total_value * coin_share)
        remaining = total_value - payout_coins
        payout_crystals = remaining // COIN_PER_CRYSTAL
        payout_coins += remaining % COIN_PER_CRYSTAL

    await award_mixed(user_id, guild_id, max(0, payout_coins), max(0, payout_crystals))

    return payout_coins, payout_crystals, crit, bonus_value


async def resolve_loss(
    user_id: int,
    guild_id: int,
    bet_coins: int,
    bet_crystals: int,
):
    """Обрабатывает «Хранителя кристаллов» при проигрыше. Возвращает True, если кристаллы вернулись."""
    if bet_crystals <= 0:
        return False

    if await has_effect(user_id, guild_id, "crystal_guard"):
        if random.random() < 0.15:
            await award_mixed(user_id, guild_id, 0, bet_crystals)
            return True

    return False


async def apply_discount(user_id: int, guild_id: int, price: int) -> int:
    """Скидка 10% на покупки (эффект «Скидка»)."""
    if price > 0 and await has_effect(user_id, guild_id, "discount"):
        return max(1, int(price * 0.9))

    return price


# ===== Лимиты кейсов и ключей (защита экономики) =====

CASE_COOLDOWN_SECONDS = 30      # не чаще одного открытия каждые 30 секунд
MAX_CASES_PER_HOUR = 40         # максимум открытий в час
MAX_CASES_PER_DAY = 120         # максимум открытий в сутки
MAX_CASE_PRICE = 1000000        # цена кейса не выше 1 млн монет
MAX_KEY_PRICE = 400000          # цена ключа не выше 400 тыс. монет
MAX_PLAYER_CASES = 50           # нельзя хранить больше 50 одинаковых кейсов
MAX_PLAYER_KEYS = 50            # нельзя хранить больше 50 одинаковых ключей


async def check_case_open_limits(user_id: int, guild_id: int):
    """Возвращает (ok, message). Считает открытия по последним покупкам/открытиям."""
    now = int(time.time())

    last = await db._fetchone(
        """
        SELECT MAX(opened_at) AS last_open
        FROM case_open_history
        WHERE user_id = ? AND guild_id = ?
        """,
        (user_id, guild_id)
    )

    if last and last["last_open"]:
        elapsed = now - last["last_open"]

        if elapsed < CASE_COOLDOWN_SECONDS:
            wait = CASE_COOLDOWN_SECONDS - elapsed
            return False, f"⏳ Слишком быстро! Следующее открытие через {wait} сек."

    hour_row = await db._fetchone(
        """
        SELECT COUNT(*) AS count FROM case_open_history
        WHERE user_id = ? AND guild_id = ? AND opened_at > ?
        """,
        (user_id, guild_id, now - 3600)
    )

    if hour_row and hour_row["count"] >= MAX_CASES_PER_HOUR:
        return False, "🚫 Достигнут лимит: 40 кейсов в час."

    day_row = await db._fetchone(
        """
        SELECT COUNT(*) AS count FROM case_open_history
        WHERE user_id = ? AND guild_id = ? AND opened_at > ?
        """,
        (user_id, guild_id, now - 86400)
    )

    if day_row and day_row["count"] >= MAX_CASES_PER_DAY:
        return False, "🚫 Достигнут дневной лимит: 120 кейсов."

    return True, None


async def log_case_open(user_id: int, guild_id: int, case_id: int):
    await db.db.execute(
        "INSERT INTO case_open_history (user_id, guild_id, case_id) VALUES (?, ?, ?)",
        (user_id, guild_id, case_id)
    )
    await db.db.commit()


def format_mixed(coins: int, crystals: int) -> str:
    parts = []

    if coins:
        parts.append(f"{coins} 💰")

    if crystals:
        parts.append(f"{crystals} 💎")

    return " + ".join(parts) if parts else "0 💰"
