# modules/auto_roles.py
# Библиотека автогенерации ролей и пресетов кейсов.
# Используется панелью case_admin (кнопки «⚡ Готовые пресеты» и «🤖 Роли для всех кейсов»).
# Отдельных slash-команд здесь нет — всё свёрнуто в /admin → 🛠 Кейсы.

import discord

from database import db


RARITY_COLORS = {
    "common": 0x808080,
    "uncommon": 0x00FF00,
    "rare": 0x0000FF,
    "epic": 0x800080,
    "legendary": 0xFFD700,
    "secret": 0x8B0000,
    "secret+": 0x000000
}

RARITY_NAMES = {
    "common": "Обычная",
    "uncommon": "Необычная",
    "rare": "Редкая",
    "epic": "Эпическая",
    "legendary": "Легендарная",
    "secret": "Секретная",
    "secret+": "Абсолютная"
}


# Пресеты переехали в presets_data.py (Terraria-тематика). Здесь — алиас,
# чтобы не дублировать данные и не ломать импорты case_admin.
from .presets_data import PRESET_CASES  # noqa: F401

from .shared import can_manage


async def generate_roles_for_case(guild: discord.Guild, case_id: int):
    """Создаёт визуальные роли для всех пустых редкостей кейса."""
    case = await db.get_case_details(case_id)

    if not case:
        return 0, "Кейс не найден."

    if case['guild_id'] != guild.id:
        return 0, "Кейс не с этого сервера."

    created = 0
    existing_names = {r.name for r in guild.roles}

    for rarity in case['rarities']:
        if rarity['roles']:
            continue

        rarity_name = RARITY_NAMES.get(rarity['rarity'], rarity['rarity'])
        rarity_color = RARITY_COLORS.get(rarity['rarity'], 0x808080)

        base_name = f"{case['name']} • {rarity_name}"
        role_name = base_name
        counter = 2

        while role_name in existing_names:
            role_name = f"{base_name} {counter}"
            counter += 1

        try:
            role = await guild.create_role(
                name=role_name,
                colour=discord.Colour(rarity_color),
                permissions=discord.Permissions.none(),
                hoist=False,
                mentionable=False,
                reason=f"Автогенерация роли для кейса {case['name']}"
            )
        except discord.Forbidden:
            return created, "У бота нет права создавать роли."
        except discord.HTTPException as e:
            return created, f"Ошибка создания роли: {e}"

        await db.add_roles_to_case_rarity(rarity['id'], [role.id])
        existing_names.add(role_name)
        created += 1

    return created, None

