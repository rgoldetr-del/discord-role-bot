# modules/inventory_v2.py
# ======================================================================
# Обновлённый инвентарь v2:
# - вкладки (страницы): Роли, Кейсы и ключи, Улучшения, Эффекты;
# - сортировка по редкости/новизне/цене;
# - фильтр по редкости;
# - пагинация по 6 предметов;
# - красивая карточка предмета с действиями;
# - экономика: лимиты кейсов/ключей, скидка «Скидка», защита от дублирования.
#
# Подключение: добавь "inventory_v2" В КОНЕЦ списка MODULES в main.py
# (после inventory, role_actions и interface_update), чтобы команда /inventory
# была заменена новой версией.
# ======================================================================

import time

import discord
from discord import app_commands, ui

from database import db
from .economy_utils import (
    COIN_PER_CRYSTAL,
    MAX_PLAYER_CASES,
    MAX_PLAYER_KEYS,
    apply_discount,
)
from .shared import (
    check_cooldown,
    get_rarity_emoji,
    get_rarity_name,
    deliver_message,
)
from .persistent_utils import make_id, id_parts

TAB_ROLES = "roles"
TAB_CASES = "cases"
TAB_UPGRADES = "upgrades"
TAB_EFFECTS = "effects"

TABS = [
    (TAB_ROLES, "🎭 Роли"),
    (TAB_CASES, "📦 Кейсы"),
    (TAB_UPGRADES, "⚙️ Улучшения"),
    (TAB_EFFECTS, "✨ Эффекты"),
]

SORT_OPTIONS = [
    ("rarity", "🌈 По редкости"),
    ("new", "🆕 Сначала новые"),
    ("price", "💰 По цене"),
]

RARITY_ORDER = {
    "common": 0, "uncommon": 1, "rare": 2, "epic": 3,
    "legendary": 4, "secret": 5, "secret+": 6,
    # служебные типы — в конец
    "luck": 7, "rich": 8, "shield": 9, "discount": 10,
    "income": 11, "critic": 12, "crystal_guard": 13,
    "high_roller": 14, "clumsy_hands": 15,
}

EFFECT_INFO = {
    "shield": ("🛡️ Щит", "Защищает от дебаффа «Кривая рука» при открытии кейсов."),
    "discount": ("🏷️ Скидка", "Скидка 10% на покупку кейсов и ключей."),
    "income": ("💼 Пассивный доход", "Раз в день можно получить 100 монет командой /daily."),
    "critic": ("⚡ Критик", "10% шанс увеличить выигрыш в мини-играх на 25%."),
    "crystal_guard": ("💎 Хранитель кристаллов", "15% шанс не потерять кристаллы при проигрыше."),
    "high_roller": ("🔥 Азарт", "Увеличивает максимальные ставки в мини-играх в 1.5 раза."),
}

UPGRADE_INFO = {
    "luck": ("🍀 Удача", "+1% к шансу редких выпадений за уровень в колесе и кейсах."),
    "rich": ("💰 Богач", "+1% к выигрышу в мини-играх за уровень."),
}


def rarity_weight(item: dict) -> int:
    return RARITY_ORDER.get(item.get("rarity", "common"), 0)


def sort_items(items: list, sort_key: str) -> list:
    if sort_key == "new":
        return sorted(items, key=lambda x: (-(x.get("obtained_at") or 0), -(x.get("id") or 0)))

    if sort_key == "price":
        return sorted(items, key=lambda x: (-(x.get("market_price") or 0), rarity_weight(x)))

    # по умолчанию — по редкости (сначала самые редкие)
    return sorted(items, key=lambda x: (-rarity_weight(x), -(x.get("market_price") or 0)))


def item_title(guild: discord.Guild, item: dict) -> str:
    from .role_actions import get_item_name
    return get_item_name(guild, item)


async def count_active_effects(user_id: int, guild_id: int) -> int:
    row = await db._fetchone(
        """
        SELECT COUNT(*) AS count FROM inventory
        WHERE user_id = ? AND guild_id = ? AND role_type = 'effect' AND is_applied = 1
        """,
        (user_id, guild_id)
    )
    return row["count"] if row else 0


async def build_summary_embed(
    interaction: discord.Interaction,
    tab: str,
    page: int,
    pages: int,
    counts: dict,
):
    user = await db.get_or_create_user(interaction.user.id, interaction.guild.id)

    embed = discord.Embed(
        title="🎒 Инвентарь",
        color=0x5865F2,
        timestamp=discord.utils.utcnow()
    )

    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    embed.add_field(name="💰 Монеты", value=f"{user['coins']:,}".replace(",", " "), inline=True)
    embed.add_field(name="💎 Кристаллы", value=f"{user['crystals']:,}".replace(",", " "), inline=True)
    embed.add_field(name="ℹ️ Курс", value=f"1 💎 = {COIN_PER_CRYSTAL} 💰", inline=True)

    footer_counts = (
        f"🎭 Роли: {counts['roles']}   📦 Кейсы: {counts['cases']}   "
        f"🔑 Ключи: {counts['keys']}   ✨ Эффекты: {counts['effects']}"
    )

    if page > 1 or pages > 1:
        embed.set_footer(text=f"{footer_counts}  •  Страница {page}/{pages}")
    else:
        embed.set_footer(text=footer_counts)

    return embed


class InventoryTabSelect(ui.Select):
    def __init__(self, view: "InventoryV2View"):
        options = []

        for key, label in TABS:
            options.append(
                discord.SelectOption(
                    label=label,
                    value=key,
                    default=(key == view.tab)
                )
            )

        super().__init__(
            placeholder="Вкладка инвентаря",
            options=options,
            custom_id=make_id("inv2", "tab", view.user_id)
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("Это не твой инвентарь.", ephemeral=True)
            return

        self.view_ref.tab = self.values[0]
        self.view_ref.page = 0
        await self.view_ref.refresh(interaction)


class InventorySortSelect(ui.Select):
    def __init__(self, view: "InventoryV2View"):
        options = [
            discord.SelectOption(label=label, value=key, default=(key == view.sort))
            for key, label in SORT_OPTIONS
        ]

        super().__init__(
            placeholder="Сортировка",
            options=options,
            custom_id=make_id("inv2", "sort", view.user_id)
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("Это не твой инвентарь.", ephemeral=True)
            return

        self.view_ref.sort = self.values[0]
        self.view_ref.page = 0
        await self.view_ref.refresh(interaction)


class InventoryRaritySelect(ui.Select):
    def __init__(self, view: "InventoryV2View", available_rarities: list):
        options = [discord.SelectOption(label="⚡ Все редкости", value="all", default=(view.rarity_filter == "all"))]

        for rarity in available_rarities:
            options.append(
                discord.SelectOption(
                    label=f"{get_rarity_emoji(rarity)} {get_rarity_name(rarity)}",
                    value=rarity,
                    default=(rarity == view.rarity_filter)
                )
            )

        super().__init__(
            placeholder="Фильтр по редкости",
            options=options[:25],
            custom_id=make_id("inv2", "rar", view.user_id)
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("Это не твой инвентарь.", ephemeral=True)
            return

        self.view_ref.rarity_filter = self.values[0]
        self.view_ref.page = 0
        await self.view_ref.refresh(interaction)


class InventoryPageButton(ui.Button):
    def __init__(self, view: "InventoryV2View", delta: int, label: str, style=discord.ButtonStyle.secondary):
        super().__init__(style=style, label=label, custom_id=make_id("inv2", f"pg{delta}", view.user_id))
        self.view_ref = view
        self.delta = delta

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("Это не твой инвентарь.", ephemeral=True)
            return

        self.view_ref.page += self.delta
        await self.view_ref.refresh(interaction)


class InventoryItemButton(ui.Button):
    def __init__(self, view: "InventoryV2View", index: int, label: str, style=discord.ButtonStyle.secondary):
        super().__init__(style=style, label=label[:80], custom_id=make_id("inv2", f"it{index}", view.user_id))
        self.view_ref = view
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("Это не твой инвентарь.", ephemeral=True)
            return

        items = self.view_ref.current_items()

        if not (0 <= self.index < len(items)):
            await self.view_ref.refresh(interaction)
            return

        await self.view_ref.open_item(interaction, items[self.index])


class InventoryRefreshButton(ui.Button):
    def __init__(self, view: "InventoryV2View"):
        super().__init__(
            style=discord.ButtonStyle.primary,
            emoji="🔄",
            custom_id=make_id("inv2", "refresh", view.user_id)
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("Это не твой инвентарь.", ephemeral=True)
            return

        await self.view_ref.refresh(interaction)


class InventoryBackButton(ui.Button):
    def __init__(self, view: "InventoryV2View"):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="◀️ Назад",
            custom_id=make_id("inv2", "back", view.user_id)
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("Это не твой инвентарь.", ephemeral=True)
            return

        self.view_ref.opened_item = None
        await self.view_ref.refresh(interaction)


class InventoryV2View(ui.View):
    PER_PAGE = 6

    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.tab = TAB_ROLES
        self.sort = "rarity"
        self.rarity_filter = "all"
        self.page = 0
        self.opened_item = None  # dict | None
        self._items_cache = []

    # ===== Данные =====

    async def load_data(self, guild: discord.Guild):
        data = {"roles": [], "cases": [], "case_groups": {}, "keys": {}, "upgrades": [], "effects": []}

        rows = await db.get_user_inventory(self.user_id, self.guild_id)
        items = [dict(row) for row in rows]

        data["roles"] = [i for i in items if i["role_type"] in ("visual", "admin", "debuff")]
        data["upgrades"] = [i for i in items if i["role_type"] == "upgradeable"]
        data["effects"] = [i for i in items if i["role_type"] == "effect"]

        async with db.db.execute(
            """
            SELECT case_id, SUM(quantity) AS total
            FROM player_cases WHERE user_id = ? AND guild_id = ?
            GROUP BY case_id
            """,
            (self.user_id, self.guild_id)
        ) as cursor:
            for row in await cursor.fetchall():
                data["case_groups"][row["case_id"]] = row["total"]

        async with db.db.execute(
            """
            SELECT case_id, SUM(quantity) AS total
            FROM player_keys WHERE user_id = ? AND guild_id = ?
            GROUP BY case_id
            """,
            (self.user_id, self.guild_id)
        ) as cursor:
            for row in await cursor.fetchall():
                data["keys"][row["case_id"]] = row["total"]

        case_ids = list(data["case_groups"].keys())
        cases_list = []

        for case_id in case_ids:
            case = await db.get_case_details(case_id)
            if case:
                cases_list.append({
                    "case": case,
                    "amount": data["case_groups"][case_id],
                    "keys": data["keys"].get(case_id, 0),
                })

        cases_list.sort(key=lambda x: x["case"]["name"])
        data["cases"] = cases_list

        self._data = data
        return data

    def current_items(self) -> list:
        return self._items_cache

    # ===== Отрисовка =====

    async def refresh(self, interaction: discord.Interaction):
        guild = interaction.guild

        if guild is None:
            await deliver_message(interaction, content="❌ Только на сервере.", view=None)
            return

        data = await self.load_data(guild)

        counts = {
            "roles": len(data["roles"]),
            "cases": sum(c["amount"] for c in data["cases"]),
            "keys": sum(c["keys"] for c in data["cases"]),
            "effects": await count_active_effects(self.user_id, self.guild_id),
        }

        if self.opened_item is not None:
            await self.render_item_card(interaction, data, counts)
            return

        self.clear_items()

        # Список элементов текущей вкладки
        if self.tab == TAB_ROLES:
            base = list(data["roles"])

            if self.rarity_filter != "all":
                base = [i for i in base if i["rarity"] == self.rarity_filter]

            base = sort_items(base, self.sort)
            available_rarities = sorted(
                {i["rarity"] for i in data["roles"]},
                key=rarity_weight,
                reverse=True
            )
        elif self.tab == TAB_CASES:
            base = data["cases"]
            available_rarities = []
        elif self.tab == TAB_UPGRADES:
            base = sorted(data["upgrades"], key=rarity_weight)
            available_rarities = []
        else:
            base = sorted(data["effects"], key=lambda x: x["id"])
            available_rarities = []

        pages = max(1, (len(base) + self.PER_PAGE - 1) // self.PER_PAGE)
        self.page = max(0, min(self.page, pages - 1))

        start = self.page * self.PER_PAGE
        page_items = base[start:start + self.PER_PAGE]
        self._items_cache = page_items

        embed = await build_summary_embed(interaction, self.tab, self.page + 1, pages, counts)

        if self.tab == TAB_CASES:
            embed.description = self.render_cases_block(page_items) if page_items else "_Здесь пока пусто. Загляни в магазин кейсов!_"
        elif self.tab == TAB_UPGRADES:
            embed.description = self.render_upgrades_block(guild, page_items)
        elif self.tab == TAB_EFFECTS:
            embed.description = self.render_effects_block(page_items)
        else:
            embed.description = self.render_roles_block(guild, page_items)

        # Селектор вкладок всегда доступен
        self.add_item(InventoryTabSelect(self))

        if self.tab == TAB_ROLES:
            if len(data["roles"]) > 1:
                self.add_item(InventorySortSelect(self))

            if available_rarities:
                self.add_item(InventoryRaritySelect(self, available_rarities))

        for index, item in enumerate(page_items):
            if self.tab == TAB_CASES:
                entry = item
                case = entry["case"]
                label = f"📦 {case['name']} ×{entry['amount']} 🔑{entry['keys']}"
            elif self.tab == TAB_UPGRADES:
                name, _ = UPGRADE_INFO.get(item["rarity"], (item["rarity"], ""))
                label = f"{name} lvl.{item['level']}"
            elif self.tab == TAB_EFFECTS:
                name, _ = EFFECT_INFO.get(item["rarity"], ("✨ Эффект", ""))
                status = "✅" if item["is_applied"] else "⏸️"
                label = f"{status} {name}"
            else:
                emoji = get_rarity_emoji(item["rarity"])
                status = "🟢" if item["is_applied"] else "⚪"
                label = f"{status} {emoji} {item_title(guild, item)}"

            style = discord.ButtonStyle.success if (
                self.tab == TAB_ROLES and item.get("is_applied")
            ) else discord.ButtonStyle.secondary

            self.add_item(InventoryItemButton(self, index, label, style))

        # Навигация
        if pages > 1:
            if self.page > 0:
                self.add_item(InventoryPageButton(self, -1, "◀️"))
            if self.page < pages - 1:
                self.add_item(InventoryPageButton(self, +1, "▶️"))

        self.add_item(InventoryRefreshButton(self))

        await deliver_message(interaction, embed=embed, view=self)

    def render_roles_block(self, guild, items) -> str:
        if not items:
            return "_Список пуст. Открой кейс командой `/case_open`!_"

        lines = ["**🎭 Роли — нажми кнопку, чтобы посмотреть детали:**", ""]

        for item in items:
            emoji = get_rarity_emoji(item["rarity"])
            status = "🟢 надета" if item["is_applied"] else "⚪ снята"
            price = item.get("market_price") or 0
            price_part = f" • 💰 {price}" if price else ""
            lock = " 🔒" if item.get("locked") else ""
            lines.append(f"{emoji} **{item_title(guild, item)}** — {status}{price_part}` #{item['id']}`{lock}")

        return "\n".join(lines)

    def render_cases_block(self, entries) -> str:
        if not entries:
            return ""

        lines = ["**📦 Кейсы и ключи** (хранение до {mc} шт. каждого):".format(mc=MAX_PLAYER_CASES), ""]

        for entry in entries:
            case = entry["case"]
            lines.append(
                f"📦 **{case['name']}** — кейсов: **{entry['amount']}**, ключей: **{entry['keys']}** `ID {case['id']}`"
            )

        lines.append("")
        lines.append("_Открыть: `/case_open` • Купить: `/case_shop`_")
        return "\n".join(lines)

    def render_upgrades_block(self, guild, items) -> str:
        lines = ["**⚙️ Прокачиваемые улучшения:**", ""]

        levels = {item["rarity"]: item["level"] for item in items}
        luck = levels.get("luck", 0)
        rich = levels.get("rich", 0)

        next_luck = int(500 * (3 ** luck))
        next_rich = int(500 * (3 ** rich))

        lines.append(f"🍀 **Удача** — уровень **{luck}** (+{luck}% к шансам колеса)")
        lines.append(f"   Следующий уровень: **{next_luck} 💰**")
        lines.append(f"💰 **Богач** — уровень **{rich}** (+{rich}% к выигрышам)")
        lines.append(f"   Следующий уровень: **{next_rich} 💰**")
        lines.append("")
        lines.append("_Купить: `/buy_upgrade`_")
        return "\n".join(lines)

    def render_effects_block(self, items) -> str:
        if not items:
            return (
                "**✨ Эффекты** дают пассивные бонусы.\n"
                "Магазин эффектов: `/effect_shop` (покупка за кристаллы)."
            )

        lines = ["**✨ Активные эффекты:**", ""]

        for item in items:
            name, desc = EFFECT_INFO.get(item["rarity"], ("✨ Эффект", ""))
            status = "✅ включён" if item["is_applied"] else "⏸️ выключен"
            lines.append(f"{name} — {status}\n↳ {desc}")

        return "\n".join(lines)

    # ===== Карточка предмета =====

    async def open_item(self, interaction: discord.Interaction, item):
        self.opened_item = item
        await self.render_item_card(interaction, getattr(self, "_data", {}), {})

    async def render_case_card(self, interaction: discord.Interaction, entry: dict):
        """Карточка кейса из инвентаря: количество, ключи, кнопка открытия."""
        from .role_actions import CaseOpenButton

        case = entry["case"]
        self.clear_items()

        emoji = get_rarity_emoji(case["case_rarity"])
        can_open = entry["amount"] >= 1 and entry["keys"] >= 1

        embed = discord.Embed(
            title=f"📦 {emoji} Кейс «{case['name']}»",
            color=self.rarity_color(case["case_rarity"]),
        )
        embed.add_field(name="Кейсов у тебя", value=f"**{entry['amount']}**", inline=True)
        embed.add_field(name="Ключей у тебя", value=f"**{entry['keys']}**", inline=True)
        embed.add_field(name="Редкость", value=get_rarity_name(case["case_rarity"]), inline=True)

        if not can_open:
            embed.description = "Нужен **кейс + ключ**. Купить: /shop → вкладка 📦 Кейсы / 🔑 Ключи."

        lines = [f"{get_rarity_emoji(r['rarity'])} {get_rarity_name(r['rarity'])} — {r['drop_chance']}%"
                 for r in case.get("rarities", [])]
        if lines:
            embed.add_field(name="Шансы редкостей", value="\n".join(lines), inline=False)

        if can_open:
            self.add_item(CaseOpenButton(self.guild_id, self.user_id, case["id"]))
        self.add_item(InventoryBackButton(self))

        await deliver_message(interaction, embed=embed, view=self)

    async def render_item_card(self, interaction: discord.Interaction, data: dict, counts: dict):
        guild = interaction.guild
        item = self.opened_item

        # кейс из player_cases (dict с ключами "case"/"amount"/"keys")
        if isinstance(item, dict) and "case" in item:
            await self.render_case_card(interaction, item)
            return

        self.clear_items()

        if item.get("role_type") == "visual":
            locked = await db.is_item_locked(item["id"]) if hasattr(db, "is_item_locked") else False
        else:
            locked = False

        item["locked"] = locked

        emoji = get_rarity_emoji(item["rarity"])
        embed = discord.Embed(
            title=f"{emoji} {item_title(guild, item)}",
            color=self.rarity_color(item["rarity"])
        )

        embed.add_field(name="Редкость", value=get_rarity_name(item["rarity"]), inline=True)
        embed.add_field(name="Статус", value="🟢 Надета" if item["is_applied"] else "⚪ Снята", inline=True)
        embed.add_field(name="ID", value=f"`#{item['id']}`", inline=True)

        market_price = item.get("market_price") or 0
        if market_price:
            embed.add_field(name="Рыночная цена", value=f"{market_price} 💰", inline=True)

        if item["role_type"] == "debuff":
            embed.add_field(
                name="💀 Дебафф",
                value="«Кривая рука»: ключ может сломаться при открытии кейса. Лечится улучшением «Прямые руки».",
                inline=False
            )
        elif item["role_type"] == "effect":
            _, desc = EFFECT_INFO.get(item["rarity"], ("✨ Эффект", ""))
            embed.add_field(name="Эффект", value=desc, inline=False)

        if locked:
            embed.set_footer(text="🔒 Предмет участвует на рынке или аукционе — действия недоступны.")

        # Кнопки действий через существующий роутер role_actions (ra:...)
        from .role_actions import RoleActionButton

        user_id = self.user_id
        guild_id = self.guild_id
        item_id = item["id"]

        if not locked and item["role_type"] in ("visual", "admin"):
            if item["is_applied"]:
                self.add_item(RoleActionButton("unapply", guild_id, user_id, item_id, "⏸️ Снять"))
            else:
                self.add_item(RoleActionButton("apply", guild_id, user_id, item_id, "▶️ Надеть"))

            self.add_item(RoleActionButton("sell", guild_id, user_id, item_id, "💰 Продать"))
            self.add_item(RoleActionButton("auction", guild_id, user_id, item_id, "🔨 Аукцион"))

            if item["role_type"] == "visual":
                self.add_item(RoleActionButton("gift", guild_id, user_id, item_id, "🎁 Подарить"))

        self.add_item(InventoryBackButton(self))

        await deliver_message(interaction, embed=embed, view=self)

    @staticmethod
    def rarity_color(rarity: str) -> int:
        colors = {
            "common": 0x808080, "uncommon": 0x2ED573, "rare": 0x1E90FF,
            "epic": 0x9B59B6, "legendary": 0xFFD700, "secret": 0xE74C3C,
            "secret+": 0x000000, "clumsy_hands": 0x111111,
        }
        return colors.get(rarity, 0x5865F2)


def register(bot):
    # Удаляем старую команду /inventory, если она есть.
    try:
        bot.tree.remove_command("inventory")
    except Exception:
        pass

    @bot.tree.command(name="inventory", description="Инвентарь: роли, кейсы, улучшения, эффекты")
    @app_commands.describe(user="Посмотреть чужой инвентарь (только просмотр)")
    async def inventory_v2(interaction: discord.Interaction, user: discord.Member = None):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        target = user or interaction.user

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message("⏳ Подожди немного.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if target.id != interaction.user.id:
            # Чужой инвентарь — только просмотр без кнопок действий
            rows = await db.get_user_inventory(target.id, interaction.guild.id)
            items = [dict(row) for row in rows]
            roles = sort_items([i for i in items if i["role_type"] in ("visual", "admin")], "rarity")

            embed = discord.Embed(title=f"🎒 Инвентарь: {target.display_name}", color=0x5865F2)
            embed.set_thumbnail(url=target.display_avatar.url)

            if not roles:
                embed.description = "_Пусто_"
            else:
                lines = []
                for item in roles[:15]:
                    emoji = get_rarity_emoji(item["rarity"])
                    status = "🟢" if item["is_applied"] else "⚪"
                    lines.append(f"{status} {emoji} {item_title(interaction.guild, item)}` #{item['id']}`")
                embed.description = "\n".join(lines)

                if len(roles) > 15:
                    embed.set_footer(text=f"...и ещё {len(roles) - 15}")

            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        view = InventoryV2View(interaction.user.id, interaction.guild.id)
        await view.refresh(interaction)
