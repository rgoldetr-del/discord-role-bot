# modules/auto_roles.py

import discord
from discord import app_commands

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


PRESET_CASES = [
    {
        "name": "🌱 Стартовый",
        "case_rarity": "common",
        "case_price": 50,
        "key_price": 20,
        "rarities": [
            {"rarity": "common", "chance": 55, "price": 25, "roles": ["🌱 Саженец"]},
            {"rarity": "uncommon", "chance": 30, "price": 60, "roles": ["🌿 Росток"]},
            {"rarity": "rare", "chance": 12, "price": 150, "roles": ["🌳 Дуб"]},
            {"rarity": "epic", "chance": 3, "price": 400, "roles": ["🌲 Мировое дерево"]},
        ]
    },
    {
        "name": "🌿 Лесной",
        "case_rarity": "uncommon",
        "case_price": 250,
        "key_price": 100,
        "rarities": [
            {"rarity": "common", "chance": 45, "price": 80, "roles": ["🌻 Подсолнух"]},
            {"rarity": "uncommon", "chance": 30, "price": 200, "roles": ["🌸 Цветущая вишня"]},
            {"rarity": "rare", "chance": 18, "price": 500, "roles": ["🍁 Клён"]},
            {"rarity": "epic", "chance": 6, "price": 1500, "roles": ["🌺 Орхидея"]},
            {"rarity": "legendary", "chance": 1, "price": 8000, "roles": ["🌲 Древний лес"]},
        ]
    },
    {
        "name": "⚔️ Рыцарский",
        "case_rarity": "rare",
        "case_price": 800,
        "key_price": 300,
        "rarities": [
            {"rarity": "common", "chance": 40, "price": 200, "roles": ["🗡️ Оруженосец"]},
            {"rarity": "uncommon", "chance": 30, "price": 500, "roles": ["🏹 Лучник"]},
            {"rarity": "rare", "chance": 20, "price": 1500, "roles": ["⚔️ Рыцарь"]},
            {"rarity": "epic", "chance": 8, "price": 4000, "roles": ["🛡️ Паладин"]},
            {"rarity": "legendary", "chance": 2, "price": 25000, "roles": ["👑 Король рыцарей"]},
        ]
    },
    {
        "name": "🏰 Королевский",
        "case_rarity": "epic",
        "case_price": 2500,
        "key_price": 1000,
        "rarities": [
            {"rarity": "uncommon", "chance": 35, "price": 800, "roles": ["🏰 Лорд"]},
            {"rarity": "rare", "chance": 30, "price": 2500, "roles": ["👑 Принц"]},
            {"rarity": "epic", "chance": 20, "price": 8000, "roles": ["🏛️ Герцог"]},
            {"rarity": "legendary", "chance": 12, "price": 25000, "roles": ["⚜️ Император"]},
            {"rarity": "secret", "chance": 3, "price": 150000, "roles": ["🦅 Грифон"]},
        ]
    },
    {
        "name": "🌌 Космический",
        "case_rarity": "legendary",
        "case_price": 8000,
        "key_price": 3000,
        "rarities": [
            {"rarity": "rare", "chance": 35, "price": 3500, "roles": ["🌙 Луна"]},
            {"rarity": "epic", "chance": 30, "price": 12000, "roles": ["🪐 Сатурн"]},
            {"rarity": "legendary", "chance": 22, "price": 40000, "roles": ["☀️ Солнце"]},
            {"rarity": "secret", "chance": 10, "price": 200000, "roles": ["🌌 Млечный путь"]},
            {"rarity": "secret+", "chance": 3, "price": 1500000, "roles": ["🕳️ Чёрная дыра"]},
        ]
    },
    {
        "name": "👑 Императорский",
        "case_rarity": "secret",
        "case_price": 25000,
        "key_price": 10000,
        "rarities": [
            {"rarity": "epic", "chance": 40, "price": 20000, "roles": ["👼 Архангел"]},
            {"rarity": "legendary", "chance": 35, "price": 60000, "roles": ["😈 Архидемон"]},
            {"rarity": "secret", "chance": 20, "price": 300000, "roles": ["🐉 Древний дракон"]},
            {"rarity": "secret+", "chance": 5, "price": 2500000, "roles": ["⚡ Зевс"]},
        ]
    },
    {
        "name": "⚫ Абсолютный",
        "case_rarity": "secret+",
        "case_price": 100000,
        "key_price": 40000,
        "rarities": [
            {"rarity": "legendary", "chance": 40, "price": 50000, "roles": ["🌟 Созвездие"]},
            {"rarity": "secret", "chance": 40, "price": 400000, "roles": ["🌀 Сингулярность"]},
            {"rarity": "secret+", "chance": 20, "price": 5000000, "roles": ["🌌✨ Творец вселенной"]},
        ]
    },
]


def can_manage(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False

    if interaction.user.id == interaction.guild.owner_id:
        return True

    try:
        return interaction.user.guild_permissions.administrator
    except Exception:
        return False


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


def register(bot):
    @bot.tree.command(name="gen_case_roles", description="Создать роли для конкретного кейса")
    @app_commands.describe(case_id="ID кейса")
    @app_commands.default_permissions(administrator=True)
    async def gen_case_roles(interaction: discord.Interaction, case_id: int):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not can_manage(interaction):
            await interaction.response.send_message("❌ Только владелец или администратор.", ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ У бота нет права «Управлять ролями».", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        created, error = await generate_roles_for_case(interaction.guild, case_id)

        if error:
            await interaction.followup.send(f"❌ {error}", ephemeral=True)
            return

        if created == 0:
            await interaction.followup.send("ℹ️ Все редкости этого кейса уже содержат роли.", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ Создано ролей: **{created}**\nОни автоматически привязаны к кейсу.",
            ephemeral=True
        )

    @bot.tree.command(name="gen_all_case_roles", description="Создать роли для всех кейсов")
    @app_commands.default_permissions(administrator=True)
    async def gen_all_case_roles(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not can_manage(interaction):
            await interaction.response.send_message("❌ Только владелец или администратор.", ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ У бота нет права «Управлять ролями».", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        cases = await db.get_all_cases(interaction.guild.id, active_only=False)

        total_created = 0
        errors = []

        for case in cases:
            created, error = await generate_roles_for_case(interaction.guild, case['id'])
            total_created += created

            if error:
                errors.append(f"{case['name']}: {error}")

        message = f"✅ Всего создано ролей: **{total_created}**"

        if errors:
            message += "\n\n⚠️ Ошибки:\n" + "\n".join(errors)

        await interaction.followup.send(message, ephemeral=True)

    @bot.tree.command(name="activate_case", description="Активировать кейс")
    @app_commands.describe(case_id="ID кейса")
    @app_commands.default_permissions(administrator=True)
    async def activate_case(interaction: discord.Interaction, case_id: int):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not can_manage(interaction):
            await interaction.response.send_message("❌ Только владелец или администратор.", ephemeral=True)
            return

        result = await db.activate_case(case_id)

        if result['success']:
            await interaction.response.send_message("✅ Кейс активирован.", ephemeral=True)
            return

        details = "\n".join(result['details']) if result['details'] else ""
        await interaction.response.send_message(
            f"❌ {result['error']}\n{details}",
            ephemeral=True
        )

    @bot.tree.command(name="deactivate_case", description="Деактивировать кейс")
    @app_commands.describe(case_id="ID кейса")
    @app_commands.default_permissions(administrator=True)
    async def deactivate_case(interaction: discord.Interaction, case_id: int):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not can_manage(interaction):
            await interaction.response.send_message("❌ Только владелец или администратор.", ephemeral=True)
            return

        await db.deactivate_case(case_id)
        await interaction.response.send_message("✅ Кейс деактивирован.", ephemeral=True)

    @bot.tree.command(name="case_preset_full", description="Создать 7 готовых кейсов + редкости + роли")
    @app_commands.default_permissions(administrator=True)
    async def case_preset_full(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not can_manage(interaction):
            await interaction.response.send_message("❌ Только владелец или администратор.", ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message("❌ У бота нет права «Управлять ролями».", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        lines = []
        existing_names = {r.name for r in interaction.guild.roles}

        for preset in PRESET_CASES:
            case_id = await db.create_case_return_id(
                interaction.guild.id,
                preset['name'],
                preset['case_rarity'],
                preset['case_price'],
                preset['key_price']
            )

            for rarity in preset['rarities']:
                rarity_id = await db.add_rarity_return_id(
                    case_id,
                    rarity['rarity'],
                    rarity['chance'],
                    rarity['price']
                )

                for role_name in rarity['roles']:
                    final_name = role_name
                    counter = 2

                    while final_name in existing_names:
                        final_name = f"{role_name} {counter}"
                        counter += 1

                    rarity_color = RARITY_COLORS.get(rarity['rarity'], 0x808080)

                    try:
                        role = await interaction.guild.create_role(
                            name=final_name,
                            colour=discord.Colour(rarity_color),
                            permissions=discord.Permissions.none(),
                            hoist=False,
                            mentionable=False,
                            reason="Автосоздание пресета кейсов"
                        )
                    except discord.Forbidden:
                        await interaction.followup.send(
                            "❌ У бота нет права создавать роли.",
                            ephemeral=True
                        )
                        return
                    except discord.HTTPException as e:
                        await interaction.followup.send(
                            f"❌ Ошибка создания роли: {e}",
                            ephemeral=True
                        )
                        return

                    await db.add_roles_to_case_rarity(rarity_id, [role.id])
                    existing_names.add(final_name)

            activate_result = await db.activate_case(case_id)

            if activate_result['success']:
                lines.append(f"✅ {preset['name']} — создан и активирован")
            else:
                details = "\n".join(activate_result['details'])
                lines.append(f"⚠️ {preset['name']} — создан, но не активирован:\n{details}")

        await interaction.followup.send(
            "Готово:\n" + "\n".join(lines),
            ephemeral=True
        )