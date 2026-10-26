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
    """Доставка/обновление ответа без падения на протухшем interaction.

    - если interaction ещё не отвечен -> edit_message (если message есть)
      иначе send_message ephemeral;
    - если отвечен и есть сообщение -> редактируем его;
    - при 404 Unknown interaction / прочем HTTPException -> followup.
    """
    kwargs = {"content": content, "embed": embed}
    if view is not None or kwargs["content"] is not None or kwargs["embed"] is not None:
        kwargs["view"] = view

    try:
        if interaction.response.is_done():
            if interaction.message is not None:
                await interaction.edit_original_response(**kwargs)
            else:
                await interaction.followup.send(**kwargs, ephemeral=True)
        elif interaction.message is not None:
            await interaction.response.edit_message(**kwargs)
        else:
            await interaction.response.send_message(**kwargs, ephemeral=True)
    except discord.HTTPException:
        try:
            await interaction.followup.send(**kwargs, ephemeral=True)
        except Exception:
            pass


# ===== Глобальный щит «неубиваемости» =====

def _is_ui_item(obj) -> bool:
    try:
        return isinstance(obj, discord.ui.Item)
    except Exception:
        return False


def make_resilient(fn):
    """Универсальная обёртка для ЛЮБЫХ хэндлеров (slash-команды, кнопки,
    селекты, модалки).

    Гарантии:
    1. Совместимость сигнатур: хэндлер получает корректные
       (interaction[, item]) независимо от того, как его вызвала конкретная
       сборка discord.py (official вызывает callback(interaction), форки —
       callback(interaction, item)); self/parent подставляется автоматически.
    2. Ни одно необработанное исключение не улетает в Discord: оно логируется
       с полным трейсбеком, а пользователю показывается дружелюбный ответ.
    3. Ошибки доставки (404 Unknown interaction) проглатываются молча —
       interaction уже мёртв, делать нечего.
    """
    import functools

    params = None
    try:
        params = [p for p in inspect.signature(fn).parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    except (TypeError, ValueError):
        pass

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        # --- нормализация аргументов под сигнатуру fn ---
        call_args = args
        if params is not None:
            n = len(params)
            has_self = getattr(fn, "__self__", None) is not None
            needs_item = any(p.name != "interaction" and p.default is inspect.Parameter.empty
                             for p in (params[1:] if has_self else params))
            inter = next((a for a in args if isinstance(a, discord.Interaction)), None)
            item = next((a for a in args if _is_ui_item(a)), None)
            if inter is not None:
                rebuilt = []
                if not has_self and n >= 2:
                    # несвязанная функция из View: первый параметр self
                    parent = getattr(item, "_view", None) or getattr(item, "_parent", None)
                    rebuilt.append(parent)
                rebuilt.append(inter)
                if needs_item:
                    rebuilt.append(item)
                call_args = tuple(rebuilt) + tuple(
                    a for a in args if a is not inter and not _is_ui_item(a))

        # --- выполнение с перехватом ошибок ---
        try:
            return await fn(*call_args, **kwargs)
        except discord.NotFound:
            return  # interaction истёк — штатная ситуация
        except (discord.Forbidden, discord.HTTPException) as e:
            log.warning("HTTP-ошибка в %s: %s", getattr(fn, "__qualname__", fn), e)
            try:
                if not (args and isinstance(args[0], discord.Interaction)):
                    return
                inter = next(a for a in args if isinstance(a, discord.Interaction))
                if not inter.response.is_done():
                    await inter.response.send_message(
                        "⚠️ Что-то пошло не так (недостаточно прав или боту не хватает доступа к каналу).",
                        ephemeral=True)
            except Exception:
                pass
        except Exception:
            log.exception("Необработанная ошибка в %s", getattr(fn, "__qualname__", fn))
            try:
                inter = next((a for a in args if isinstance(a, discord.Interaction)), None)
                if inter is not None:
                    msg = "💥 Внутренняя ошибка. Попробуй ещё раз позже — админы уже уведомлены логом."
                    if not inter.response.is_done():
                        await inter.response.send_message(msg, ephemeral=True)
                    else:
                        await inter.followup.send(msg, ephemeral=True)
            except Exception:
                pass
        return None

    # discord.py проверяет co_flags CO_COROUTINE напрямую — восстанавливаем флаг
    wrapper.__code__ = wrapper.__code__.replace(co_flags=wrapper.__code__.co_flags | 0x100)
    wrapper.__annotations__ = getattr(fn, "__annotations__", {})
    return wrapper


# Алиас: прежний safe_command теперь просто часть общего щита
safe_command = make_resilient


def _find_interaction(args):
    return next((a for a in args if isinstance(a, discord.Interaction)), None)


def install_global_handler_guard(logger=None):
    """Глобальный «неубиваемый» режим для ВСЕХ обработчиков взаимодействий.

    Патчит discord.ui.view.View._dispatch_interactions и
    discord.app_commands.tree.Tree.on_error (а также Interaction.on_error как
    запасной путь). Теперь, даже если какой-то хэндлер забыли обернуть в
    make_resilient или ошибка возникла внутри самой библиотеки до/после
    хэндлера — бот не роняет трейсбек в void и Discord не видит «бот не
    отвечает»: пользователь получает ephemeral-сообщение, ошибка пишется в лог.

    Идемпотентно: повторные вызовы не оборачивают повторно.
    """
    logr = logger or logging.getLogger("guard")

    # ---------- 1. View: кнопки / селекты / модалки ----------
    try:
        from discord.ui import view as _view_mod
    except Exception:
        _view_mod = None

    if _view_mod is not None and not getattr(_view_mod.View, "_guard_installed", False):
        orig_scheduled = _view_mod.View._scheduled_task

        async def guarded_scheduled(self, item, interaction):
            try:
                return await orig_scheduled(self, item, interaction)
            except discord.NotFound:
                pass
            except Exception:
                logr.exception("Guard: необработанная ошибка в view %s", type(self).__name__)
                try:
                    msg = "💥 Ошибка интерфейса. Попробуй ещё раз."
                    if not interaction.response.is_done():
                        await interaction.response.send_message(msg, ephemeral=True)
                    else:
                        await interaction.followup.send(msg, ephemeral=True)
                except Exception:
                    pass

        _view_mod.View._scheduled_task = guarded_scheduled
        _view_mod.View._guard_installed = True

    # ---------- 2. app_commands CommandTree: slash-команды ----------
    try:
        from discord.app_commands.tree import CommandTree as _Tree, CommandNotFound as _CNF
    except Exception:
        _Tree = None
        _CNF = None

    if _Tree is not None and not getattr(_Tree, "_guard_installed", False):
        orig_tree_error = _Tree.on_error

        async def on_tree_error(self, interaction, error, /):
            # стандартное поведение: лог + вызов error-хэндлеров команды
            try:
                await orig_tree_error(self, interaction, error)
            except Exception:
                logr.exception("Guard: ошибка в стандартном on_error")

            if _CNF is not None and isinstance(error, _CNF):
                return
            msg = "💥 Команда выполнилась с ошибкой. Попробуй ещё раз позже."
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
            except Exception:
                pass

        _Tree.on_error = on_tree_error
        _Tree._guard_installed = True

    # ---------- 3. Fallback: Interaction-level errors ----------
    try:
        if not getattr(discord.Interaction, "_guard_installed", False):

            async def on_interaction_error(self, error):
                logr.warning("Guard: interaction error: %s", error)

            discord.Interaction.on_error = on_interaction_error
            discord.Interaction._guard_installed = True
    except Exception:
        pass

    return True


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