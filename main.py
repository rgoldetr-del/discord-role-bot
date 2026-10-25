# main.py
# Точка входа Discord-бота: экономика, кейсы, колесо, мини-игры, маркет, аукционы.

import os
import logging
import importlib

import discord
from discord.ext import commands
from dotenv import load_dotenv

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
    "inventory",
    "cases",
    "case_admin",
    "wheel",
    "wheel_info",
    "market",
    "auctions",
    "gifts",
    "upgrades",
    "minigames",
    "update_v2",
    "interface_update",
    "auto_roles",
    "case_shop_fix",
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


bot.setup_hook = setup_hook


@bot.event
async def on_ready():
    log.info("Бот запущен как %s", bot.user)


if __name__ == "__main__":
    bot.run(TOKEN)
