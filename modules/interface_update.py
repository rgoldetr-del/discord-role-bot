# modules/interface_update.py
# ======================================================================
# Обновление интерфейса:
# 1) Все мини-игры собираются под одной командой /games.
# 2) Цены кейса в кристаллах задаются сразу при создании кейса.
# 3) Админ/владелец может выдавать монеты, кристаллы, кейсы, ключи, эффекты.
# 4) Открытие кейса публичное, с лёгкой анимацией.
#
# Подключение: добавь "interface_update" В КОНЕЦ списка MODULES в main.py,
# чтобы модуль мог удалить старые команды и заменить их новыми.
# ======================================================================

import asyncio

import discord
from discord import app_commands, ui

from database import db

# Пытаемся импортировать старые и новые игры.
# Если какого-то модуля нет, команда просто не покажет этот раздел.
try:
    from modules.minigames import GamesMenuView
except Exception:
    GamesMenuView = None

try:
    from modules.update_v2 import NewGamesMenuView
except Exception:
    NewGamesMenuView = None

# Эффекты для выдачи.
# Если загружен update_v2, берём актуальный список оттуда.
try:
    from modules.update_v2 import EFFECTS
except Exception:
    EFFECTS = {
        "shield": {"name": "🛡️ Щит", "description": "Защита от Кривой руки."},
        "discount": {"name": "🏷️ Скидка", "description": "Скидка 10% в магазине."},
        "income": {"name": "💼 Доход", "description": "Ежедневный доход."},
        "critic": {"name": "⚡ Критик", "description": "Шанс критического выигрыша."},
        "crystal_guard": {"name": "💎 Хранитель кристаллов", "description": "Шанс не потерять кристаллы."},
        "high_roller": {"name": "🔥 Азарт", "description": "Увеличенные ставки."},
    }

try:
    from modules.update_v2 import EFFECT_ROLE_IDS
except Exception:
    EFFECT_ROLE_IDS = {
        "shield": 2001,
        "discount": 2002,
        "income": 2003,
        "critic": 2004,
        "crystal_guard": 2005,
        "high_roller": 2006,
    }

RARITY_KEYS = [
    "common",
    "uncommon",
    "rare",
    "epic",
    "legendary",
    "secret",
    "secret+"
]

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


def can_manage(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False

    is_owner = interaction.user.id == interaction.guild.owner_id

    try:
        is_admin = interaction.user.guild_permissions.administrator
    except Exception:
        is_admin = False

    return is_owner or is_admin


def parse_price_pair(raw: str):
    """
    Формат: монеты/кристаллы
    Примеры:
      100/10
      100 / 10
      100
    """
    raw = raw.strip().replace(",", "/").replace(" ", "")

    if "/" in raw:
        left, right = raw.split("/", 1)

        coins = int(left) if left else 0
        crystals = int(right) if right else 0
    else:
        coins = int(raw) if raw else 0
        crystals = 0

    if coins < 0 or crystals < 0:
        raise ValueError("Цены не могут быть отрицательными")

    return coins, crystals


async def ensure_case_currency_columns():
    try:
        await db.db.execute("ALTER TABLE cases ADD COLUMN case_crystal_price INTEGER DEFAULT 0")
    except Exception:
        pass

    try:
        await db.db.execute("ALTER TABLE cases ADD COLUMN key_crystal_price INTEGER DEFAULT 0")
    except Exception:
        pass

    await db.db.commit()


# ===== Создание и настройка кейсов с ценами в монетах и кристаллах =====

class CaseCreateFullModal(ui.Modal, title="Создать кейс"):
    name = ui.TextInput(
        label="Название кейса",
        placeholder="Например: Стартовый кейс",
        max_length=100,
        required=True,
        custom_id="case_create_name"
    )

    case_rarity = ui.TextInput(
        label="Редкость кейса",
        placeholder="common / uncommon / rare / epic / legendary / secret / secret+",
        max_length=20,
        required=True,
        custom_id="case_create_rarity"
    )

    case_prices = ui.TextInput(
        label="Цена кейса: монеты/кристаллы",
        placeholder="Например: 100/10",
        max_length=30,
        required=True,
        custom_id="case_create_case_prices"
    )

    key_prices = ui.TextInput(
        label="Цена ключа: монеты/кристаллы",
        placeholder="Например: 50/5",
        max_length=30,
        required=True,
        custom_id="case_create_key_prices"
    )

    def __init__(self, view=None):
        super().__init__(custom_id="case_create_full_modal")
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        if not can_manage(interaction):
            await interaction.response.send_message("❌ У тебя нет доступа.", ephemeral=True)
            return

        if self.view_ref is not None and hasattr(self.view_ref, "user_id"):
            if interaction.user.id != self.view_ref.user_id:
                await interaction.response.send_message("❌ У тебя нет доступа.", ephemeral=True)
                return

        rarity_key = self.case_rarity.value.strip().lower()

        if rarity_key not in RARITY_KEYS:
            await interaction.response.send_message(
                "❌ Неверная редкость кейса. Доступны: " + ", ".join(RARITY_KEYS),
                ephemeral=True
            )
            return

        try:
            case_coins, case_crystals = parse_price_pair(self.case_prices.value)
            key_coins, key_crystals = parse_price_pair(self.key_prices.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Цены нужно указывать в формате: монеты/кристаллы, например 100/10",
                ephemeral=True
            )
            return

        await ensure_case_currency_columns()

        await db.db.execute(
            """
            INSERT INTO cases (
                guild_id, name, case_rarity,
                case_price, case_crystal_price,
                key_price, key_crystal_price,
                is_active
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                interaction.guild.id,
                self.name.value.strip(),
                rarity_key,
                case_coins,
                case_crystals,
                key_coins,
                key_crystals
            )
        )
        await db.db.commit()

        message = (
            "✅ Кейс создан.\n"
            f"Цена кейса: {case_coins} монет / {case_crystals} кристаллов\n"
            f"Цена ключа: {key_coins} монет / {key_crystals} кристаллов"
        )

        if self.view_ref is not None and hasattr(self.view_ref, "refresh"):
            await interaction.response.send_message(message, ephemeral=True)
            await self.view_ref.refresh(interaction)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class CaseSettingsFullModal(ui.Modal):
    def __init__(self, view, case):
        super().__init__(
            title="Настройки кейса",
            custom_id="case_settings_full_modal"
        )

        self.view_ref = view
        self.case = case

        case_dict = dict(case) if not isinstance(case, dict) else case

        self.name_input = ui.TextInput(
            label="Название кейса",
            default=case_dict["name"],
            max_length=100,
            required=True,
            custom_id="case_settings_name"
        )

        self.case_prices_input = ui.TextInput(
            label="Цена кейса: монеты/кристаллы",
            default=f"{case_dict['case_price']}/{case_dict.get('case_crystal_price', 0)}",
            max_length=30,
            required=True,
            custom_id="case_settings_case_prices"
        )

        self.key_prices_input = ui.TextInput(
            label="Цена ключа: монеты/кристаллы",
            default=f"{case_dict['key_price']}/{case_dict.get('key_crystal_price', 0)}",
            max_length=30,
            required=True,
            custom_id="case_settings_key_prices"
        )

        self.add_item(self.name_input)
        self.add_item(self.case_prices_input)
        self.add_item(self.key_prices_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not can_manage(interaction):
            await interaction.response.send_message("❌ У тебя нет доступа.", ephemeral=True)
            return

        if self.view_ref is not None and hasattr(self.view_ref, "user_id"):
            if interaction.user.id != self.view_ref.user_id:
                await interaction.response.send_message("❌ У тебя нет доступа.", ephemeral=True)
                return

        try:
            case_coins, case_crystals = parse_price_pair(self.case_prices_input.value)
            key_coins, key_crystals = parse_price_pair(self.key_prices_input.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Цены нужно указывать в формате: монеты/кристаллы, например 100/10",
                ephemeral=True
            )
            return

        await ensure_case_currency_columns()

        await db.db.execute(
            """
            UPDATE cases
            SET name = ?, case_price = ?, case_crystal_price = ?, key_price = ?, key_crystal_price = ?
            WHERE id = ? AND guild_id = ?
            """,
            (
                self.name_input.value.strip(),
                case_coins,
                case_crystals,
                key_coins,
                key_crystals,
                self.view_ref.case_id,
                interaction.guild.id
            )
        )
        await db.db.commit()

        await interaction.response.send_message("✅ Настройки кейса сохранены.", ephemeral=True)

        if self.view_ref is not None and hasattr(self.view_ref, "refresh"):
            await self.view_ref.refresh(interaction)


# ===== Единый интерфейс мини-игр =====

class UnifiedGamesMenu(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id

        if GamesMenuView is not None:
            old_btn = ui.Button(
                style=discord.ButtonStyle.primary,
                label="🎮 Классические игры"
            )
            old_btn.callback = self.open_old_games
            self.add_item(old_btn)

        if NewGamesMenuView is not None:
            new_btn = ui.Button(
                style=discord.ButtonStyle.success,
                label="🕹️ Новые игры"
            )
            new_btn.callback = self.open_new_games
            self.add_item(new_btn)

    async def open_old_games(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не для тебя.", ephemeral=True)
            return

        view = GamesMenuView(self.user_id)
        await interaction.response.send_message("Выбери игру:", view=view, ephemeral=True)

    async def open_new_games(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не для тебя.", ephemeral=True)
            return

        view = NewGamesMenuView(self.user_id)
        await interaction.response.send_message("Выбери игру:", view=view, ephemeral=True)


# ===== Публичное открытие кейсов с лёгкой анимацией =====

class CaseOpenPublicView(ui.View):
    def __init__(self, user_id: int, guild_id: int, cases):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id

        options = []

        for case in cases[:25]:
            case_dict = dict(case)

            options.append(
                discord.SelectOption(
                    label=case_dict["name"][:100],
                    description="Нажми, чтобы открыть кейс",
                    value=str(case_dict["id"]),
                    emoji=RARITY_EMOJI.get(case_dict.get("case_rarity", "common"), "📦")
                )
            )

        select = ui.Select(
            placeholder="Выбери кейс для открытия",
            options=options,
            custom_id="case_open_public_select"
        )
        select.callback = self.on_case_selected
        self.add_item(select)

    async def on_case_selected(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Это не твой кейс.", ephemeral=True)
            return

        if not self.children or not self.children[0].values:
            await interaction.response.send_message("❌ Кейс не выбран.", ephemeral=True)
            return

        case_id = int(self.children[0].values[0])

        async with db.db.execute("SELECT * FROM cases WHERE id = ?", (case_id,)) as cursor:
            row = await cursor.fetchone()

        if not row:
            await interaction.response.edit_message(content="❌ Кейс не найден.", view=None)
            return

        case = dict(row)

        if not case["is_active"] or case["guild_id"] != interaction.guild.id:
            await interaction.response.edit_message(content="❌ Кейс не активен.", view=None)
            return

        # Лёгкая публичная анимация: одно редактирование + короткая пауза.
        await interaction.response.edit_message(
            content=f"🔑 {interaction.user.mention} открывает кейс **{case['name']}**...",
            view=None
        )
        await asyncio.sleep(0.7)

        result = await db.open_case(interaction.user.id, interaction.guild.id, case_id)

        if not result.get("success"):
            await interaction.edit_original_response(
                content=f"❌ {result.get('error', 'Не удалось открыть кейс.')}"
            )
            return

        role = interaction.guild.get_role(result["role_id"])
        role_name = role.name if role else f"Роль {result['role_id']}"

        rarity_key = result.get("rarity", "common")
        rarity_emoji = RARITY_EMOJI.get(rarity_key, "⚪")
        rarity_name = RARITY_NAME.get(rarity_key, rarity_key)

        embed = discord.Embed(
            title="🎉 Открытие кейса",
            description=(
                f"{interaction.user.mention} открывает кейс **{case['name']}**\n\n"
                f"Выпала роль: {rarity_emoji} **{role_name}**\n"
                f"Редкость: **{rarity_name}**"
            ),
            color=0x00BCD4
        )

        market_price = result.get("market_price")
        if market_price:
            embed.add_field(
                name="💰 Рыночная цена",
                value=f"{market_price} монет",
                inline=True
            )

        if result.get("duplicate"):
            embed.add_field(
                name="🔁 Повтор",
                value="Роль уже была у игрока. Копия добавлена в инвентарь.",
                inline=False
            )

        if result.get("debuff_applied"):
            embed.add_field(
                name="💀 Кривая рука",
                value="Игрок получил дебафф **Кривая рука**.",
                inline=False
            )

        await interaction.edit_original_response(content=None, embed=embed)

# ===== Быстрая генерация всех кейсов =====

PRESET_CASES = [
    {
        "name": "🌱 Стартовый", "case_rarity": "common",
        "case_coins": 50, "case_crystals": 5,
        "key_coins": 20, "key_crystals": 2,
        "rarities": [
            ("common", 55, 25),
            ("uncommon", 30, 60),
            ("rare", 12, 150),
            ("epic", 3, 400),
        ]
    },
    {
        "name": "🌿 Лесной", "case_rarity": "uncommon",
        "case_coins": 250, "case_crystals": 25,
        "key_coins": 100, "key_crystals": 10,
        "rarities": [
            ("common", 45, 80),
            ("uncommon", 30, 200),
            ("rare", 18, 500),
            ("epic", 6, 1500),
            ("legendary", 1, 8000),
        ]
    },
    {
        "name": "⚔️ Рыцарский", "case_rarity": "rare",
        "case_coins": 800, "case_crystals": 80,
        "key_coins": 300, "key_crystals": 30,
        "rarities": [
            ("common", 40, 200),
            ("uncommon", 30, 500),
            ("rare", 20, 1500),
            ("epic", 8, 4000),
            ("legendary", 18, 25000),  # 1.8 + 16.2 (secret + legendary)
            ("secret", 2, 150000),
        ]
    },
    {
        "name": "🏰 Королевский", "case_rarity": "epic",
        "case_coins": 2500, "case_crystals": 250,
        "key_coins": 1000, "key_crystals": 100,
        "rarities": [
            ("uncommon", 35, 800),
            ("rare", 30, 2500),
            ("epic", 20, 8000),
            ("legendary", 12, 25000),
            ("secret", 28, 150000),  # 2.8 + 25.2
            ("secret+", 2, 800000),
        ]
    },
    {
        "name": "🌌 Космический", "case_rarity": "legendary",
        "case_coins": 8000, "case_crystals": 800,
        "key_coins": 3000, "key_crystals": 300,
        "rarities": [
            ("rare", 35, 3500),
            ("epic", 30, 12000),
            ("legendary", 22, 40000),
            ("secret", 10, 200000),
            ("secret+", 3, 1500000),
        ]
    },
    {
        "name": "👑 Императорский", "case_rarity": "secret",
        "case_coins": 25000, "case_crystals": 2500,
        "key_coins": 10000, "key_crystals": 1000,
        "rarities": [
            ("epic", 40, 20000),
            ("legendary", 35, 60000),
            ("secret", 20, 300000),
            ("secret+", 5, 2500000),
        ]
    },
    {
        "name": "⚫ Абсолютный", "case_rarity": "secret+",
        "case_coins": 100000, "case_crystals": 10000,
        "key_coins": 40000, "key_crystals": 4000,
        "rarities": [
            ("legendary", 40, 50000),
            ("secret", 40, 400000),
            ("secret+", 20, 5000000),
        ]
    },
]


def add_preset_command(bot):
    @bot.tree.command(name="case_preset", description="Создать 7 готовых кейсов одной кнопкой")
    async def case_preset(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not can_manage(interaction):
            await interaction.response.send_message(
                "❌ Только владелец или администратор.",
                ephemeral=True
            )
            return

        await ensure_case_currency_columns()

        created = []

        for preset in PRESET_CASES:
            async with db.db.execute(
                """
                INSERT INTO cases (
                    guild_id, name, case_rarity,
                    case_price, case_crystal_price,
                    key_price, key_crystal_price,
                    is_active
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    interaction.guild.id,
                    preset["name"],
                    preset["case_rarity"],
                    preset["case_coins"],
                    preset["case_crystals"],
                    preset["key_coins"],
                    preset["key_crystals"],
                )
            ) as cursor:
                case_id = cursor.lastrowid

            for rarity, chance, sell_price in preset["rarities"]:
                async with db.db.execute(
                    """
                    INSERT INTO case_rarities
                    (case_id, rarity, drop_chance, sell_price)
                    VALUES (?, ?, ?, ?)
                    """,
                    (case_id, rarity, chance, sell_price)
                ) as cursor:
                    rarity_id = cursor.lastrowid

            created.append(f"✅ {preset['name']} (ID: {case_id})")

        await db.db.commit()

        embed = discord.Embed(
            title="🎁 7 готовых кейсов созданы!",
            description="\n".join(created) + "\n\n"
                       "**Что делать дальше:**\n"
                       "1. Зайди в `/case_admin`\n"
                       "2. Открой каждый кейс\n"
                       "3. Добавь Discord-роли в каждую редкость\n"
                       "4. Нажми '✅ Активировать кейс'",
            color=0x00FF00
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


# В функции register(bot) добавь в самом начале:
#     add_preset_command(bot)

# ===== Регистрация =====

def register(bot):
    add_preset_command(bot)
    # Удаляем старые команды, чтобы заменить их обновлёнными версиями.
    for command_name in ("games", "new_games", "set_case_crystal_prices", "case_open"):
        try:
            bot.tree.remove_command(command_name)
        except Exception:
            pass

    # Подменяем модальные окна в админ-панели кейсов, если она установлена.
    try:
        from modules import case_admin

        case_admin.CreateCaseModal = CaseCreateFullModal
        case_admin.CaseSettingsModal = CaseSettingsFullModal
    except Exception:
        pass

    # ===== Единая команда игр =====

    @bot.tree.command(name="games", description="Все мини-игры")
    async def games(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if GamesMenuView is None and NewGamesMenuView is None:
            await interaction.response.send_message("❌ Мини-игры не найдены.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎮 Мини-игры",
            description="Выбери раздел с играми.",
            color=0x5865F2
        )

        view = UnifiedGamesMenu(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ===== Создание кейса с монетами и кристаллами =====

    @bot.tree.command(name="case_create", description="Создать кейс (монеты и кристаллы)")
    async def case_create(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not can_manage(interaction):
            await interaction.response.send_message(
                "❌ Только владелец сервера или администратор может создавать кейсы.",
                ephemeral=True
            )
            return

        modal = CaseCreateFullModal(view=None)
        await interaction.response.send_modal(modal)

    # ===== Публичное открытие кейсов =====

    @bot.tree.command(name="case_open", description="Открыть кейс (видят все)")
    async def case_open(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        cases = await db.get_all_cases(interaction.guild.id, active_only=True)

        if not cases:
            await interaction.response.send_message("❌ Нет активных кейсов.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎰 Открытие кейса",
            description=(
                "Выбери кейс, который хочешь открыть.\n"
                "Открытие увидят все участники канала."
            ),
            color=0x9C27B0
        )

        view = CaseOpenPublicView(interaction.user.id, interaction.guild.id, cases)

        # Важно: отправка публичная, чтобы открытие видели все.
        await interaction.response.send_message(embed=embed, view=view)

    # ===== Админ-выдача =====

    give_group = app_commands.Group(
        name="give",
        description="Выдача наград (владелец/администратор)",
        guild_only=True
    )

    @give_group.command(name="coins", description="Выдать монеты")
    @app_commands.describe(user="Пользователь", amount="Количество монет")
    async def give_coins(interaction: discord.Interaction, user: discord.Member, amount: int):
        if not can_manage(interaction):
            await interaction.response.send_message("❌ У тебя нет доступа.", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Количество должно быть больше 0.", ephemeral=True)
            return

        await db.get_or_create_user(user.id, interaction.guild.id)
        await db.update_coins(user.id, interaction.guild.id, amount)

        await interaction.response.send_message(
            f"✅ Выдано **{amount} монет** → {user.mention}",
            ephemeral=True
        )

    @give_group.command(name="crystals", description="Выдать кристаллы")
    @app_commands.describe(user="Пользователь", amount="Количество кристаллов")
    async def give_crystals(interaction: discord.Interaction, user: discord.Member, amount: int):
        if not can_manage(interaction):
            await interaction.response.send_message("❌ У тебя нет доступа.", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Количество должно быть больше 0.", ephemeral=True)
            return

        await db.get_or_create_user(user.id, interaction.guild.id)
        await db.update_crystals(user.id, interaction.guild.id, amount)

        await interaction.response.send_message(
            f"✅ Выдано **{amount} кристаллов** → {user.mention}",
            ephemeral=True
        )

    @give_group.command(name="case", description="Выдать кейс")
    @app_commands.describe(user="Пользователь", case_id="ID кейса", quantity="Количество")
    async def give_case(interaction: discord.Interaction, user: discord.Member, case_id: int, quantity: int = 1):
        if not can_manage(interaction):
            await interaction.response.send_message("❌ У тебя нет доступа.", ephemeral=True)
            return

        if quantity <= 0:
            await interaction.response.send_message("❌ Количество должно быть больше 0.", ephemeral=True)
            return

        async with db.db.execute(
            "SELECT * FROM cases WHERE id = ? AND guild_id = ?",
            (case_id, interaction.guild.id)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            await interaction.response.send_message("❌ Кейс не найден.", ephemeral=True)
            return

        case = dict(row)
        await db.add_case(user.id, interaction.guild.id, case_id, quantity)

        await interaction.response.send_message(
            f"✅ Выдано **{quantity}** кейс(ов) **{case['name']}** → {user.mention}",
            ephemeral=True
        )

    @give_group.command(name="key", description="Выдать ключ")
    @app_commands.describe(user="Пользователь", case_id="ID кейса", quantity="Количество")
    async def give_key(interaction: discord.Interaction, user: discord.Member, case_id: int, quantity: int = 1):
        if not can_manage(interaction):
            await interaction.response.send_message("❌ У тебя нет доступа.", ephemeral=True)
            return

        if quantity <= 0:
            await interaction.response.send_message("❌ Количество должно быть больше 0.", ephemeral=True)
            return

        async with db.db.execute(
            "SELECT * FROM cases WHERE id = ? AND guild_id = ?",
            (case_id, interaction.guild.id)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            await interaction.response.send_message("❌ Кейс не найден.", ephemeral=True)
            return

        case = dict(row)
        await db.add_key(user.id, interaction.guild.id, case_id, quantity)

        await interaction.response.send_message(
            f"✅ Выдано **{quantity}** ключ(ей) к кейсу **{case['name']}** → {user.mention}",
            ephemeral=True
        )

    effect_choices = [
        app_commands.Choice(name=value["name"][:100], value=key)
        for key, value in EFFECTS.items()
    ]

    @give_group.command(name="effect", description="Выдать роль с эффектом")
    @app_commands.describe(user="Пользователь", effect="Эффект")
    @app_commands.choices(effect=effect_choices)
    async def give_effect(interaction: discord.Interaction, user: discord.Member, effect: app_commands.Choice[str]):
        if not can_manage(interaction):
            await interaction.response.send_message("❌ У тебя нет доступа.", ephemeral=True)
            return

        if effect.value not in EFFECTS:
            await interaction.response.send_message("❌ Неизвестный эффект.", ephemeral=True)
            return

        if hasattr(db, "has_effect"):
            if await db.has_effect(user.id, interaction.guild.id, effect.value):
                await interaction.response.send_message(
                    f"❌ У {user.mention} уже есть этот эффект.",
                    ephemeral=True
                )
                return

        if hasattr(db, "add_effect_to_inventory"):
            await db.add_effect_to_inventory(user.id, interaction.guild.id, effect.value)
        else:
            role_id = EFFECT_ROLE_IDS.get(effect.value, 2999)

            await db.db.execute(
                """
                INSERT INTO inventory
                (user_id, guild_id, role_id, role_type, rarity, level, is_applied)
                VALUES (?, ?, ?, 'effect', ?, 1, 1)
                """,
                (user.id, interaction.guild.id, role_id, effect.value)
            )
            await db.db.commit()

        await interaction.response.send_message(
            f"✅ Выдан эффект **{EFFECTS[effect.value]['name']}** → {user.mention}",
            ephemeral=True
        )

    bot.tree.add_command(give_group)