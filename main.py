# main.py
# Точка входа Discord-бота: экономика, кейсы, колесо, мини-игры, маркет, аукционы.

import os
import logging
import importlib

import discord
from discord.ext import commands
from dotenv import load_dotenv

# --- Совместимость UI-коллбэков с разными сборками discord.py -----------------
# Разные сборки по-разному вызывают коллбэк кнопки/селекта:
#   официальный discord.py : item.callback(interaction), метод (self, inter[, item])
#   форк хостинга           : item.callback(interaction, item) — без self!
# Если библиотека передаёт (interaction, item), а метод объявлен как
# (self, interaction), то в `self` попадает Button — отсюда падения вида
# AttributeError: 'Button' object has no attribute 'user'.
# Шим нормализует вызовы: методы всегда получают корректные
# (self, interaction[, item]), независимо от порядка/состава аргументов.
import inspect as _inspect
from discord.ui.item import Item as _UIItem


def _normalize_args(cb, default_parent, default_item, args):
    """Привести args к сигнатуре метода коллбэка (self, interaction[, item])."""
    try:
        params = [p for p in _inspect.signature(cb).parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    except (ValueError, TypeError):
        return args
    n = len(params)
    inter = next((a for a in args if isinstance(a, discord.Interaction)), None)
    item = next((a for a in args if isinstance(a, _UIItem)), default_item)

    bound_self = getattr(cb, "__self__", None)
    if bound_self is not None:      # bound method — self уже внутри
        if n >= 3:
            return (bound_self, inter, item)
        if n == 2:
            return (bound_self, inter)
        return (inter,)

    # несвязанная функция из класса View: первый параметр self = parent view
    if n >= 3:
        return (default_parent, inter, item)
    if n == 2:
        return (default_parent, inter)
    return (inter,)


class _CompatItemCallback:
    """Обёртка коллбэка Item (для сборок без _ItemCallback)."""

    __slots__ = ("_cb", "_item")

    def __init__(self, cb, item):
        self._cb = cb
        self._item = item

    async def __call__(self, *args):
        parent = self._item._view if self._item._view is not None else self._item._parent
        real_args = _normalize_args(self._cb, parent, self._item, args)
        return await self._cb(*real_args)


# Патч вызова коллбэков. В discord.py 2.5+ для @ui.button/@ui.select коллбэк
# хранится в item.callback как объект _ItemCallback, чей __call__ вызывает
# метод с (parent, interaction, item) — лишние аргументы ломают методы,
# объявленные как (self, interaction). Патчим __call__ этого класса: он теперь
# сам подбирает аргументы под сигнатуру метода и принимает оба стиля вызова —
# official: callback(interaction), форк: callback(interaction, item).
try:
    from discord.ui.item import _ItemCallback as _IC

    def _ic_call(self, *args):
        real_args = _normalize_args(self.callback, self.parent, self.item, args)
        return self.callback(*real_args)

    _IC.__call__ = _ic_call
except ImportError:
    # старые сборки: коллбэк лежит в item.callback напрямую — патчим setattr
    _orig_setattr = _UIItem.__setattr__

    def _item_setattr(self, name, value):
        if name == "callback" and callable(value) and not isinstance(value, _CompatItemCallback):
            value = _CompatItemCallback(value, self)
        _orig_setattr(self, name, value)

    _UIItem.__setattr__ = _item_setattr


# Функция для ручного вызова (не используется автоматически):
# -----------------------------------------------------------------------------

from database import db

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DEV_GUILD_ID = os.getenv("DEV_GUILD_ID", "").strip()

if not TOKEN:
    raise SystemExit("Укажи DISCORD_TOKEN в .env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("main")

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Список модулей бота. Если файла нет — предупреждение, бот продолжает запуск.
MODULES = [
    "cases",        # /case_info — просмотр наград кейсов
    "shop",         # /shop + /daily — единый магазин (кейсы/ключи/эффекты/улучшения)
    "wheel",        # /wheel + /wheel_info — почасовое колесо
    "inventory_v2", # /inventory — инвентарь с вкладками (заменяет старый inventory.py)
    "role_actions", # кнопки действий над предметами инвентаря (применить/открыть/продать/подарить)
    "market",       # /market — маркетплейс
    "auctions",     # /auction — аукционы
    "minigames",    # /games — все мини-игры
    "admin",        # /admin — единая админ-панель (кейсы, выдача, сбросы)
    "case_admin",   # панели управления кейсами (открываются из /admin; auto_roles — её библиотека)
]

for module_name in MODULES:
    try:
        module = importlib.import_module(f"modules.{module_name}")
    except ModuleNotFoundError:
        log.warning("Модуль modules/%s.py не найден. Пропускаю.", module_name)
        continue
    except Exception:
        log.exception("Ошибка импорта модуля modules/%s.py", module_name)
        continue

    try:
        if hasattr(module, "register"):
            module.register(bot)
            log.info("Модуль %s зарегистрирован", module_name)
        else:
            log.warning("В модуле modules/%s.py нет функции register().", module_name)
    except Exception:
        log.exception("Ошибка регистрации модуля modules/%s.py", module_name)


async def setup_hook():
    await db.connect()
    log.info("База данных подключена")

    try:
        if DEV_GUILD_ID:
            guild = discord.Object(id=int(DEV_GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            log.info("Команды синхронизированы для DEV-сервера")
        else:
            await bot.tree.sync()
            log.info("Команды синхронизированы глобально")
    except ValueError:
        log.warning("DEV_GUILD_ID указан неправильно, пробую глобальную синхронизацию")
        await bot.tree.sync()
    except Exception:
        log.exception("Не удалось синхронизировать команды")

    # фоновые задачи модулей (авто-завершение аукционов раз в час)
    try:
        from modules.auctions import auction_loop
        if not auction_loop.is_running():
            auction_loop.start(bot)
    except Exception:
        log.exception("Не удалось запустить auction_loop")


# ВАЖНО: назначаем setup_hook ДО регистрации @bot.event.
# Декоратор event() оборачивает коллбэк и при присваивании bot.setup_hook
# перезаписывает оригинальный setup_hook — иначе база не подключается,
# а Discord отвечает 404 Unknown interaction на все команды.
bot.setup_hook = setup_hook


if __name__ == "__main__":
    bot.run(TOKEN)
