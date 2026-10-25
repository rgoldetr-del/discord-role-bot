# main.py
# Точка входа Discord-бота: экономика, кейсы, колесо, мини-игры, маркет, аукционы.

import os
import logging
import importlib

import discord
from discord.ext import commands
from dotenv import load_dotenv

# --- Совместимость UI-коллбэков с разными сборками discord.py -----------------
# Официальный discord.py вызывает callback(interaction), форки на хостингах —
# callback(interaction, item). Шим определяет настоящий Interaction по типу
# аргументов и вызывает метод view в его сигнатуре (self, interaction[, button]).
import inspect as _inspect


def _compat_callback(cb, parent):
    try:
        params = [p for p in _inspect.signature(cb).parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    except (ValueError, TypeError):
        return cb

    async def wrapped(*args):
        interaction = next((a for a in args if type(a).__name__ == "Interaction"), None)
        n = len(params)
        if n >= 3:
            item = next((a for a in args if isinstance(a, __import__("discord.ui", fromlist=["Item"]).Item)), None)
            return await cb(parent, interaction, item)
        if n == 2:
            return await cb(parent, interaction)
        return await cb(interaction)

    return wrapped


try:
    from discord.ui.item import _ItemCallback as _IC

    _IC.__call__ = lambda self, *args: _compat_callback(self.callback, self.parent)(*args)
except Exception:  # на других сборках путь может отличаться — не критично
    pass
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
