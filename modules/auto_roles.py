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
    """Создаёт визуальные роли для всех пустых редкостей кейса.

    Существующие роли с тем же именем переиспользуются (дубликаты «Имя 2»
    не создаются никогда).
    """
    case = await db.get_case_details(case_id)

    if not case:
        return 0, "Кейс не найден."

    if case['guild_id'] != guild.id:
        return 0, "Кейс не с этого сервера."

    created = 0
    roles_by_name = {r.name: r for r in guild.roles}

    for rarity in case['rarities']:
        if rarity['roles']:
            continue

        rarity_name = RARITY_NAMES.get(rarity['rarity'], rarity['rarity'])
        rarity_color = RARITY_COLORS.get(rarity['rarity'], 0x808080)

        base_name = f"{case['name']} • {rarity_name}"
        role = roles_by_name.get(base_name)

        if role is None:
            try:
                role = await guild.create_role(
                    name=base_name,
                    colour=discord.Colour(rarity_color),
                    permissions=discord.Permissions.none(),
                    hoist=False,
                    mentionable=False,
                    reason=f"Автогенерация роли для кейса {case['name']}"
                )
                created += 1
            except discord.Forbidden:
                return created, "У бота нет права создавать роли."
            except discord.HTTPException as e:
                return created, f"Ошибка создания роли: {e}"
            roles_by_name[role.name] = role

        await db.add_roles_to_case_rarity(rarity['id'], [role.id])

    return created, None

