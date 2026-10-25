# modules/shop.py
# ======================================================================
# Единый магазин бота: команда /shop.
# Вкладки: 📦 Кейсы | 🔑 Ключи | ✨ Эффекты | ⚙️ Улучшения.
# - оплата монетами (💰) или кристаллами (💎) — валюты НЕ конвертируются;
# - эффект «Скидка» даёт -10% на кейсы и ключи;
# - все покупки падают в инвентарь (/inventory): кейсы, ключи, эффекты, улучшения.
# Заменяет собой старые /case_shop, /effect_shop, /buy_effect,
# /shop_upgrade, /buy_upgrade — их больше нет.
# ======================================================================

import discord
from discord import ui

from database import db, EFFECTS
from .economy_utils import apply_discount
from .persistent_utils import make_id
from .shared import get_rarity_emoji, get_rarity_name, crystal_price_from_coins

TAB_CASES = "cases"
TAB_KEYS = "keys"
TAB_EFFECTS = "effects"
TAB_UPGRADES = "upgrades"

TABS = [
    (TAB_CASES, "📦 Кейсы"),
    (TAB_KEYS, "🔑 Ключи"),
    (TAB_EFFECTS, "✨ Эффекты"),
    (TAB_UPGRADES, "⚙️ Улучшения"),
]

UPGRADE_INFO = {
    "luck": ("🍀 Удача", "+1% к шансу редких выпадений за уровень", 500),
    "rich": ("💰 Богач", "+1% к выигрышу в мини-играх за уровень", 500),
}

UPGRADE_STEP = 3  # каждая следующая покупка дороже в 3 раза


def fmt(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def currency_emoji(currency: str) -> str:
    return "💎" if currency == "crystals" else "💰"


# ===== Кнопка оплаты =====

class PayButton(ui.Button):
    def __init__(self, view: "ShopView", item_value: str, currency: str, label: str, disabled=False):
        super().__init__(
            style=discord.ButtonStyle.success if currency == "coins" else discord.ButtonStyle.primary,
            label=label[:80],
            disabled=disabled,
            custom_id=make_id("shop", "pay", view.user_id, item_value, currency),
        )
        self.view_ref = view
        self.item_value = item_value
        self.currency = currency

    async def callback(self, interaction: discord.Interaction):
        await self.view_ref.handle_pay(interaction, self.item_value, self.currency)


class ShopTabSelect(ui.Select):
    def __init__(self, view: "ShopView"):
        options = [
            discord.SelectOption(label=label, value=key, default=(key == view.tab))
            for key, label in TABS
        ]
        super().__init__(
            placeholder="Раздел магазина",
            options=options,
            custom_id=make_id("shop", "tab", view.user_id),
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("Это не твой магазин.", ephemeral=True)
            return
        self.view_ref.tab = self.values[0]
        self.view_ref.page = 0
        await self.view_ref.refresh(interaction)


class ShopPageButton(ui.Button):
    def __init__(self, view: "ShopView", delta: int, label: str):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=label,
            custom_id=make_id("shop", f"pg{delta}", view.user_id),
        )
        self.view_ref = view
        self.delta = delta

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("Это не твой магазин.", ephemeral=True)
            return
        self.view_ref.page += self.delta
        await self.view_ref.refresh(interaction)


class ShopBackButton(ui.Button):
    def __init__(self, view: "ShopView"):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="◀️ Назад",
            custom_id=make_id("shop", "back", view.user_id),
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("Это не твой магазин.", ephemeral=True)
            return
        self.view_ref.opened = None
        await self.view_ref.refresh(interaction)


# ===== Основной view =====

class ShopView(ui.View):
    PER_PAGE = 5

    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.tab = TAB_CASES
        self.page = 0
        self.opened = None  # dict карточки товара | None
        self._page_items = []

    # ---------- Данные ----------

    async def load_cases(self):
        rows = await db.get_all_cases(self.guild_id, active_only=True)
        cases = []
        for row in rows:
            case = dict(row)
            coin_case = int(case["case_price"] or 0)
            coin_key = int(case["key_price"] or 0)
            cases.append({
                "id": case["id"],
                "name": case["name"],
                "rarity": case["case_rarity"],
                "case_coins": coin_case,
                "case_crystals": int(case.get("case_crystal_price") or 0) or crystal_price_from_coins(coin_case),
                "key_coins": coin_key,
                "key_crystals": int(case.get("key_crystal_price") or 0) or crystal_price_from_coins(coin_key),
            })
        return cases

    @staticmethod
    def item_value_for(tab: str, case_id: int) -> str:
        """value для select/pay: 'c:<id>' кейс, 'k:<id>' ключ."""
        prefix = "c" if tab == TAB_CASES else "k"
        return f"{prefix}:{case_id}"

    # ---------- Отрисовка ----------

    async def refresh(self, interaction: discord.Interaction):
        if self.opened is not None:
            await self.render_card(interaction)
            return

        self.clear_items()

        user = await db.get_or_create_user(self.user_id, self.guild_id)
        has_discount = await db.has_effect(self.user_id, self.guild_id, "discount")

        embed = discord.Embed(title="🛒 Магазин", color=0x5865F2, timestamp=discord.utils.utcnow())
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(name="💰 Монеты", value=fmt(user["coins"]), inline=True)
        embed.add_field(name="💎 Кристаллы", value=fmt(user["crystals"]), inline=True)
        embed.add_field(
            name="🏷️ Скидка",
            value="-10% активна ✅" if has_discount else "нет (купи в ✨ Эффекты)",
            inline=True,
        )

        if self.tab in (TAB_CASES, TAB_KEYS):
            cases = await self.load_cases()
            pages = max(1, (len(cases) + self.PER_PAGE - 1) // self.PER_PAGE)
            self.page = max(0, min(self.page, pages - 1))
            page_cases = cases[self.page * self.PER_PAGE:(self.page + 1) * self.PER_PAGE]

            lines = []
            for c in page_cases:
                emoji = get_rarity_emoji(c["rarity"])
                if self.tab == TAB_CASES:
                    price = await apply_discount(self.user_id, self.guild_id, c["case_coins"])
                    lines.append(f"{emoji} **{c['name']}** — 💰 {fmt(price)} • 💎 {fmt(c['case_crystals'])}")
                else:
                    price = await apply_discount(self.user_id, self.guild_id, c["key_coins"])
                    lines.append(f"{emoji} 🔑 к **{c['name']}** — 💰 {fmt(price)} • 💎 {fmt(c['key_crystals'])}")

            embed.description = "\n".join(lines) if lines else "_Пусто: админ ещё не создал активных кейсов._"
            embed.set_footer(text=f"Страница {self.page + 1}/{pages} • Валюты не конвертируются: плати тем, что указано")

            if len(cases) > 1:
                options = []
                for c in cases[:25]:
                    emoji = get_rarity_emoji(c["rarity"])
                    if self.tab == TAB_CASES:
                        desc = f"💰 {fmt(c['case_coins'])} / 💎 {fmt(c['case_crystals'])}"
                    else:
                        desc = f"💰 {fmt(c['key_coins'])} / 💎 {fmt(c['key_crystals'])}"
                    options.append(discord.SelectOption(
                        label=c["name"][:100], description=desc[:100],
                        value=self.item_value_for(self.tab, c["id"]), emoji=emoji,
                    ))
                self.add_item(ShopItemSelect(self, options))

            for index, c in enumerate(page_cases):
                iv = self.item_value_for(self.tab, c["id"])
                coins_price = await apply_discount(
                    self.user_id, self.guild_id,
                    c["case_coins"] if self.tab == TAB_CASES else c["key_coins"]
                )
                crystals_price = (
                    c["case_crystals"] if self.tab == TAB_CASES else c["key_crystals"]
                )
                self.add_item(PayButton(self, iv, "coins", f"💰 {fmt(coins_price)}"))
                self.add_item(PayButton(self, iv, "crystals", f"💎 {fmt(crystals_price)}"))

            if pages > 1:
                if self.page > 0:
                    self.add_item(ShopPageButton(self, -1, "◀️"))
                if self.page < pages - 1:
                    self.add_item(ShopPageButton(self, +1, "▶️"))

        elif self.tab == TAB_EFFECTS:
            owned = set(await db.get_user_effects(self.user_id, self.guild_id))
            lines = []
            for key, info in EFFECTS.items():
                mark = "✅ у тебя" if key in owned else ""
                lines.append(
                    f"**{info['name']}** {mark}\n↳ {info['description']}\n"
                    f"   Цена: 💎 {fmt(info['price'])}"
                )
            embed.description = "\n\n".join(lines)
            embed.set_footer(text="Эффекты покупаются за кристаллы и хранятся в /inventory")

            options = []
            for key, info in EFFECTS.items():
                options.append(discord.SelectOption(
                    label=info["name"][:100],
                    description=("уже куплен ✅" if key in owned else f"💎 {fmt(info['price'])}")[:100],
                    value=f"e:{key}",
                    default=(f"e:{key}" == (self.opened or {}).get("value")),
                ))
            self.add_item(ShopItemSelect(self, options))

        else:  # TAB_UPGRADES
            luck = await db.get_upgradeable_role_level(self.user_id, self.guild_id, "luck")
            rich = await db.get_upgradeable_role_level(self.user_id, self.guild_id, "rich")
            has_debuff = await db.has_debuff(self.user_id, self.guild_id, "clumsy_hands")
            sh_price = (user["broken_key_cost"] * 2) if has_debuff and user["broken_key_cost"] else 100

            embed.description = (
                f"🍀 **Удача** — lvl.{luck} (+{luck}% к шансам)\n"
                f"   Следующий уровень: 💰 {fmt(UPGRADE_INFO['luck'][2] * UPGRADE_STEP ** luck)}\n\n"
                f"💰 **Богач** — lvl.{rich} (+{rich}% к выигрышам)\n"
                f"   Следующий уровень: 💰 {fmt(UPGRADE_INFO['rich'][2] * UPGRADE_STEP ** rich)}\n\n"
                f"🔧 **Прямые руки** — снимает дебафф «Кривая рука»\n"
                f"   {'Цена: 💰 ' + fmt(sh_price) if has_debuff else 'Дебаффа нет — покупать не нужно ✅'}"
            )
            embed.set_footer(text="Улучшения покупаются только за монеты")

            options = [
                discord.SelectOption(label="🍀 Удача", value="u:luck",
                                     description=f"lvl.{luck} → {luck + 1}"),
                discord.SelectOption(label="💰 Богач", value="u:rich",
                                     description=f"lvl.{rich} → {rich + 1}"),
            ]
            if has_debuff:
                options.append(discord.SelectOption(label="🔧 Прямые руки", value="u:straight",
                                                   description=f"💰 {fmt(sh_price)}"))
            self.add_item(ShopItemSelect(self, options))

        self.add_item(ShopTabSelect(self))

        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
        except discord.HTTPException:
            pass

    # ---------- Карточка товара ----------

    async def render_card(self, interaction: discord.Interaction):
        card = self.opened
        self.clear_items()

        embed = discord.Embed(title=card["title"], description=card["description"], color=0x5865F2)

        for name, value in card.get("fields", []):
            embed.add_field(name=name, value=value, inline=True)

        if card.get("footer"):
            embed.set_footer(text=card["footer"])

        for btn in card["buttons"]:
            self.add_item(btn)

        self.add_item(ShopBackButton(self))
        self.add_item(ShopTabSelect(self))

        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
        except discord.HTTPException:
            pass

    # ---------- Покупка ----------

    async def handle_pay(self, interaction: discord.Interaction, item_value: str, currency: str):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не твой магазин.", ephemeral=True)
            return

        kind, _, arg = item_value.partition(":")
        guild_id = self.guild_id
        user_id = self.user_id

        if kind in ("c", "k"):
            case_id = int(arg)
            cases = await self.load_cases()
            case = next((c for c in cases if c["id"] == case_id), None)

            if not case:
                await interaction.response.send_message("❌ Кейс не найден или не активен.", ephemeral=True)
                return

            if kind == "c":
                base_price = case["case_coins"] if currency == "coins" else case["case_crystals"]
                add_fn = db.add_case
                what = f"кейс **{case['name']}**"
            else:
                base_price = case["key_coins"] if currency == "coins" else case["key_crystals"]
                add_fn = db.add_key
                what = f"ключ к кейсу **{case['name']}**"

            price = await apply_discount(user_id, guild_id, base_price) if currency == "coins" else base_price

            if not await db.try_spend(user_id, guild_id, price, currency):
                bal = await db.get_or_create_user(user_id, guild_id)
                have = bal["coins"] if currency == "coins" else bal["crystals"]
                await interaction.response.send_message(
                    f"❌ Недостаточно {('монет', 'кристаллов')[currency == 'crystals']}:"
                    f" нужно {fmt(price)}, у тебя {fmt(have)}.",
                    ephemeral=True,
                )
                return

            ok = await add_fn(user_id, guild_id, case_id, 1)
            if not ok:
                # лимит хранилища — вернуть деньги
                await db.award_currency(user_id, guild_id, price, currency)
                await interaction.response.send_message("❌ Достигнут лимит хранения (50 шт.).", ephemeral=True)
                return

            discount_note = " (скидка -10% 🏷️)" if currency == "coins" and price < base_price else ""
            await interaction.response.send_message(
                f"✅ Куплен {what} за **{fmt(price)}** {currency_emoji(currency)}. "
                f"Загляни в /inventory!{discount_note}",
                ephemeral=True,
            )
            await self.refresh_after_purchase(interaction)

        elif kind == "e":
            effect = arg
            info = EFFECTS.get(effect)
            if not info:
                await interaction.response.send_message("❌ Эффект не найден.", ephemeral=True)
                return

            if await db.has_effect(user_id, guild_id, effect):
                await interaction.response.send_message("✅ Такой эффект уже у тебя.", ephemeral=True)
                return

            price = info["price"]
            if not await db.try_spend_crystals(user_id, guild_id, price):
                await interaction.response.send_message(
                    f"❌ Нужно 💎 {fmt(price)}, а у тебя меньше.", ephemeral=True)
                return

            await db.add_effect_to_inventory(user_id, guild_id, effect)
            await interaction.response.send_message(
                f"✅ Куплен эффект **{info['name']}** за 💎 {fmt(price)}. Он сразу активен!",
                ephemeral=True,
            )
            await self.refresh_after_purchase(interaction)

        elif kind == "u":
            if arg in ("luck", "rich"):
                name, desc, base = UPGRADES_TABLE[arg]
                level = await db.get_upgradeable_role_level(user_id, guild_id, arg)
                price = base * UPGRADE_STEP ** level

                if await db.buy_upgradeable_role(user_id, guild_id, arg, level + 1, price):
                    await interaction.response.send_message(
                        f"✅ **{name}** улучшена до lvl.{level + 1} за 💰 {fmt(price)}.",
                        ephemeral=True,
                    )
                    await self.refresh_after_purchase(interaction)
                else:
                    await interaction.response.send_message(
                        f"❌ Нужно 💰 {fmt(price)} монет.", ephemeral=True)
            else:  # straight_hands
                if not await db.has_debuff(user_id, guild_id, "clumsy_hands"):
                    await interaction.response.send_message("❌ Дебаффа «Кривая рука» нет.", ephemeral=True)
                    return
                user = await db.get_or_create_user(user_id, guild_id)
                price = user["broken_key_cost"] * 2 if user["broken_key_cost"] else 100
                if await db.try_spend_coins(user_id, guild_id, price):
                    await db.remove_debuff(user_id, guild_id, "clumsy_hands")
                    await interaction.response.send_message(
                        f"✅ «Прямые руки» куплены за 💰 {fmt(price)}. Дебафф снят!", ephemeral=True)
                    await self.refresh_after_purchase(interaction)
                else:
                    await interaction.response.send_message(f"❌ Нужно 💰 {fmt(price)} монет.", ephemeral=True)

    async def refresh_after_purchase(self, interaction: discord.Interaction):
        self.opened = None
        try:
            await self.refresh(interaction)
        except discord.HTTPException:
            pass

    # ---------- Построение карточек ----------

    async def build_card(self, item_value: str):
        kind, _, arg = item_value.partition(":")

        if kind in ("c", "k"):
            case_id = int(arg)
            cases = await self.load_cases()
            case = next((c for c in cases if c["id"] == case_id), None)
            if not case:
                return None

            emoji = get_rarity_emoji(case["rarity"])
            rarity_name = get_rarity_name(case["rarity"])

            if kind == "c":
                title = f"📦 {emoji} Кейс «{case['name']}»"
                field_name = "Редкость"
                coins_price = await apply_discount(self.user_id, self.guild_id, case["case_coins"])
                crystals_price = case["case_crystals"]
            else:
                title = f"🔑 Ключ к кейсу «{case['name']}»"
                field_name = "Редкость кейса"
                coins_price = await apply_discount(self.user_id, self.guild_id, case["key_coins"])
                crystals_price = case["key_crystals"]

            fields = [
                (field_name, rarity_name),
                ("💰 Цена", fmt(coins_price)),
                ("💎 Цена", fmt(crystals_price)),
            ]

            buttons = [
                PayButton(self, item_value, "coins", f"Купить за 💰 {fmt(coins_price)}"),
                PayButton(self, item_value, "crystals", f"Купить за 💎 {fmt(crystals_price)}"),
            ]
            return {
                "title": title,
                "description": "Открывается из инвентаря (нужен кейс + ключ).",
                "fields": fields,
                "footer": "Валюты не конвертируются: плати монетами ИЛИ кристаллами.",
                "buttons": buttons,
            }

        if kind == "e":
            info = EFFECTS.get(arg)
            if not info:
                return None
            owned = arg in set(await db.get_user_effects(self.user_id, self.guild_id))
            buttons = [] if owned else [PayButton(self, item_value, "crystals",
                                                  f"Купить за 💎 {fmt(info['price'])}")]
            return {
                "title": info["name"],
                "description": info["description"],
                "fields": [("Цена", f"💎 {fmt(info['price'])}"), ("Статус", "✅ куплен" if owned else "не куплен")],
                "footer": "Эффекты покупаются только за кристаллы.",
                "buttons": buttons,
            }

        if kind == "u":
            user = await db.get_or_create_user(self.user_id, self.guild_id)
            if arg in ("luck", "rich"):
                name, desc, base = UPGRADES_TABLE[arg]
                level = await db.get_upgradeable_role_level(self.user_id, self.guild_id, arg)
                price = base * UPGRADE_STEP ** level
                return {
                    "title": name,
                    "description": desc,
                    "fields": [("Текущий уровень", str(level)), ("Цена след. уровня", f"💰 {fmt(price)}")],
                    "footer": "Улучшения покупаются только за монеты.",
                    "buttons": [PayButton(self, item_value, "coins", f"Купить за 💰 {fmt(price)}")],
                }
            has_debuff = await db.has_debuff(self.user_id, self.guild_id, "clumsy_hands")
            price = user["broken_key_cost"] * 2 if has_debuff and user["broken_key_cost"] else 100
            return {
                "title": "🔧 Прямые руки",
                "description": "Снимает дебафф «Кривая рука» (ключ может ломаться при открытии кейсов).",
                "fields": [("Дебафф", "есть 💀" if has_debuff else "нет ✅"), ("Цена", f"💰 {fmt(price)}")],
                "footer": "Покупается только за монеты.",
                "buttons": ([PayButton(self, item_value, "coins", f"Купить за 💰 {fmt(price)}")]
                            if has_debuff else []),
            }

        return None


UPGRADES_TABLE = {
    key: (name, desc, base) for key, (name, desc, base) in UPGRADE_INFO.items()
}


class ShopItemSelect(ui.Select):
    def __init__(self, view: "ShopView", options: list):
        super().__init__(
            placeholder="Выбери товар",
            options=options,
            custom_id=make_id("shop", "sel", view.user_id),
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("Это не твой магазин.", ephemeral=True)
            return
        card = await self.view_ref.build_card(self.values[0])
        if card is None:
            await interaction.response.send_message("❌ Товар недоступен.", ephemeral=True)
            return
        card["value"] = self.values[0]
        self.view_ref.opened = card
        await self.view_ref.render_card(interaction)


def register(bot):
    @bot.tree.command(name="shop", description="Магазин: кейсы, ключи, эффекты, улучшения")
    async def shop(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        view = ShopView(interaction.user.id, interaction.guild.id)
        await view.refresh(interaction)
