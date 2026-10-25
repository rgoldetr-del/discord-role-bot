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

import asyncio
import time

import discord
from discord import ui

from database import db, EFFECTS

from .persistent_utils import make_id
from .shared import get_rarity_emoji, get_rarity_name, safe_command

# защита от быстрых повторных кликов «Купить» (anti double-spend)
_pay_locks: dict[tuple, float] = {}


async def apply_discount(user_id: int, guild_id: int, price: int) -> int:
    """Возвращает цену с учётом эффекта «Скидка» (-10%). Скидка действует
    только на оплату монетами; цены в кристаллах не меняются.
    Округление вверх, чтобы нулевая цена осталась нулевой."""
    if price <= 0:
        return 0
    if await db.has_effect(user_id, guild_id, "discount"):
        return max(1, -(-price * 90 // 100))  # ceil(price * 0.9)
    return price


async def _acquire_pay_lock(user_id: int, guild_id: int) -> bool:
    key = (user_id, guild_id)
    now = time.monotonic()
    until = _pay_locks.get(key, 0)
    if now < until:
        return False
    _pay_locks[key] = now + 3.0
    # чистим протухшие записи
    if len(_pay_locks) > 512:
        for k in [k for k, v in _pay_locks.items() if v < now]:
            _pay_locks.pop(k, None)
    return True

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
        kind = item_value.split(":", 1)[0]
        if kind == "f":          # бесплатные товары (кейс раз в час)
            style = discord.ButtonStyle.secondary
            currency = "free"
        elif currency == "coins":
            style = discord.ButtonStyle.success
        elif currency == "crystals":
            style = discord.ButtonStyle.primary
        else:
            style = discord.ButtonStyle.danger   # «Забрать»
        super().__init__(
            style=style,
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
            # Кристальные цены задаются админом отдельно (0 = покупка за кристаллы недоступна).
            # Валюты не конвертируются — автоматического пересчёта нет.
            cases.append({
                "id": case["id"],
                "name": case["name"],
                "rarity": case["case_rarity"],
                "case_coins": coin_case,
                "case_crystals": int(case.get("case_crystal_price") or 0),
                "key_coins": coin_key,
                "key_crystals": int(case.get("key_crystal_price") or 0),
                "is_free": bool(case.get("is_free")),
            })
        # бесплатный кейс всегда показываем первым
        cases.sort(key=lambda c: (not c["is_free"], c["id"]))
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
            free_cd = await db.free_case_cooldown_left(self.user_id, self.guild_id)
            pages = max(1, (len(cases) + self.PER_PAGE - 1) // self.PER_PAGE)
            self.page = max(0, min(self.page, pages - 1))
            page_cases = cases[self.page * self.PER_PAGE:(self.page + 1) * self.PER_PAGE]

            lines = []
            for c in page_cases:
                emoji = get_rarity_emoji(c["rarity"])
                if self.tab == TAB_CASES:
                    if c["is_free"]:
                        status = "🆓 бесплатно!" if free_cd == 0 else f"<t:{int(time.time()) + free_cd}:R>"
                        lines.append(f"{emoji} **{c['name']}** — 🆓 {status} (кейс + ключ, 1 раз в час)")
                        continue
                    price = await apply_discount(self.user_id, self.guild_id, c["case_coins"])
                    cry = f" • 💎 {fmt(c['case_crystals'])}" if c["case_crystals"] > 0 else ""
                    zero = " 🆓" if price == 0 else ""
                    lines.append(f"{emoji} **{c['name']}** — 💰 {fmt(price)}{cry}{zero}")
                else:
                    price = await apply_discount(self.user_id, self.guild_id, c["key_coins"])
                    cry = f" • 💎 {fmt(c['key_crystals'])}" if c["key_crystals"] > 0 else ""
                    zero = " 🆓" if price == 0 else ""
                    lines.append(f"{emoji} 🔑 к **{c['name']}** — 💰 {fmt(price)}{cry}{zero}")

            embed.description = "\n".join(lines) if lines else "_Пусто: админ ещё не создал активных кейсов._"
            embed.set_footer(text=f"Страница {self.page + 1}/{pages} • Валюты не конвертируются: плати тем, что указано")

            if len(cases) > 1:
                options = []
                for c in cases[:25]:
                    emoji = get_rarity_emoji(c["rarity"])
                    if self.tab == TAB_CASES:
                        if c["is_free"]:
                            desc = "🆓 1 раз в час"
                        else:
                            desc = f"💰 {fmt(c['case_coins'])}" + (f" / 💎 {fmt(c['case_crystals'])}" if c["case_crystals"] > 0 else "")
                    else:
                        desc = f"💰 {fmt(c['key_coins'])}" + (f" / 💎 {fmt(c['key_crystals'])}" if c["key_crystals"] > 0 else "")
                    options.append(discord.SelectOption(
                        label=c["name"][:100], description=desc[:100],
                        value=self.item_value_for(self.tab, c["id"]), emoji=emoji,
                    ))
                self.add_item(ShopItemSelect(self, options))

            for index, c in enumerate(page_cases):
                iv = self.item_value_for(self.tab, c["id"])
                if self.tab == TAB_CASES and c["is_free"]:
                    label = "🎁 Забрать" if free_cd == 0 else f"⏳ {free_cd // 60} мин"
                    self.add_item(PayButton(self, f"f:{c['id']}", "free", label, disabled=free_cd != 0))
                    continue
                coins_price = await apply_discount(
                    self.user_id, self.guild_id,
                    c["case_coins"] if self.tab == TAB_CASES else c["key_coins"]
                )
                crystals_price = (
                    c["case_crystals"] if self.tab == TAB_CASES else c["key_crystals"]
                )
                coin_label = "🎁 Забрать" if coins_price == 0 else f"💰 {fmt(coins_price)}"
                self.add_item(PayButton(self, iv, "coins", coin_label))
                if crystals_price > 0:
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
                mark = "✅ активен" if key in owned else ""
                lines.append(
                    f"**{info['name']}** {mark}\n↳ {info['description']}"
                )
            embed.description = "\n\n".join(lines)
            embed.set_footer(text="💰 Эффекты покупаются за монеты и действуют 1 час • хранятся в /inventory")

            options = []
            for key, info in EFFECTS.items():
                options.append(discord.SelectOption(
                    label=info["name"][:100],
                    description=("активен ✅" if key in owned else f"💰 {fmt(info['price'])}")[:100],
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

        # защита от дабл-клика: одна покупка в 3 секунды на пользователя
        if not await _acquire_pay_lock(interaction.user.id, self.guild_id):
            await interaction.response.send_message("⏳ Подожди пару секунд между покупками.", ephemeral=True)
            return

        kind, _, arg = item_value.partition(":")
        guild_id = self.guild_id
        user_id = self.user_id

        if kind == "f":  # бесплатный кейс: 1 раз в час
            result = await db.claim_free_case(user_id, guild_id)
            if result["success"]:
                await interaction.response.send_message(
                    f"🎁 Ты получил бесплатный **{result['case_name']}** + 🔑 ключ к нему! "
                    f"Жди <t:{int(time.time()) + 3600}:R>.\n"
                    f"Открыть: /inventory → 📦 Кейсы",
                    ephemeral=True,
                )
                await self.refresh_after_purchase(interaction)
            elif result.get("cooldown_left"):
                left = int(result["cooldown_left"])
                await interaction.response.send_message(
                    f"⏳ Бесплатный кейс уже получен! Следующий через <t:{int(time.time()) + left}:R>.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(f"❌ {result.get('error', 'Не получилось.')}", ephemeral=True)
            return

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
            if not await db.try_spend_coins(user_id, guild_id, price):
                await interaction.response.send_message(
                    f"❌ Нужно 💰 {fmt(price)} монет, а у тебя меньше.", ephemeral=True)
                return

            await db.add_effect_to_inventory(user_id, guild_id, effect)
            await interaction.response.send_message(
                f"✅ Куплен эффект **{info['name']}** за 💰 {fmt(price)}. Активен 1 час — до <t:{int(time.time()) + 3600}:R>!",
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
        """Обновить исходное сообщение магазина после покупки.

        ВАЖНО: handle_pay всегда отвечает ephemeral-сообщением через
        interaction.response.send_message(...) — до этого метода. Поэтому
        edit_original_response/handle к этому же interaction НЕПРИМЕНИМЫ
        (Discord отвечает 404 Unknown interaction — именно эта ошибка была
        в логах хостинга). Правильно: редактировать исходное сообщение /shop
        напрямую через interaction.message.edit(...).
        """
        self.opened = None
        try:
            msg = getattr(interaction, "message", None)
            if msg is not None:
                await msg.edit(view=self)
        except discord.HTTPException:
            pass

    # ---------- Построение карточек ----------

    async def build_card(self, item_value: str):
        kind, _, arg = item_value.partition(":")

        if kind in ("c", "k", "f"):
            case_id = int(arg)
            cases = await self.load_cases()
            case = next((c for c in cases if c["id"] == case_id), None)
            if not case:
                return None

            emoji = get_rarity_emoji(case["rarity"])
            rarity_name = get_rarity_name(case["rarity"])

            if kind == "f":
                cd = await db.free_case_cooldown_left(self.user_id, self.guild_id)
                status = "🆓 можно забрать сейчас!" if cd == 0 else f"⏳ следующий через <t:{int(time.time()) + cd}:R>"
                return {
                    "title": f"🎁 {emoji} Бесплатный кейс «{case['name']}»",
                    "description": "Бесплатный кейс — **1 раз в час**. Ключ не нужен? Уточни у админа: "
                                   "обычно бесплатный кейс открывается без ключа из инвентаря.",
                    "fields": [("Редкость", get_rarity_name(case["rarity"])), ("Статус", status)],
                    "footer": "Открыть после получения: /inventory → 📦 Кейсы",
                    "buttons": ([PayButton(self, item_value, "free", "🎁 Забрать бесплатно")]
                                if cd == 0 else []),
                }

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
            ]
            if crystals_price > 0:
                fields.append(("💎 Цена", fmt(crystals_price)))

            coin_label = "🎁 Забрать бесплатно" if coins_price == 0 else f"Купить за 💰 {fmt(coins_price)}"
            buttons = [PayButton(self, item_value, "coins", coin_label)]
            if crystals_price > 0:
                buttons.append(PayButton(self, item_value, "crystals", f"Купить за 💎 {fmt(crystals_price)}"))
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
            buttons = [] if owned else [PayButton(self, item_value, "coins",
                                                  f"Купить за 💰 {fmt(info['price'])}")]
            return {
                "title": info["name"],
                "description": info["description"],
                "fields": [("Цена", f"💰 {fmt(info['price'])}"),
                           ("Действует", "1 час"),
                           ("Статус", "✅ активен" if owned else "не куплен")],
                "footer": "Эффекты покупаются за монеты и действуют ровно 1 час.",
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


UPGRADES_TABLE = UPGRADE_INFO  # единый справочник улучшений (без дублирования)


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
    @bot.tree.command(name="daily", description="Получить ежедневный доход 💼")
    @safe_command
    async def daily(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        await db.get_or_create_user(interaction.user.id, interaction.guild.id)

        # Бессрочная роль-улучшение «Богач»: +25 монет за уровень к ежедневной награде
        rich_lvl = await db.get_upgradeable_role_level(interaction.user.id, interaction.guild.id, "rich")
        amount = 100 + 25 * rich_lvl

        result = await db.claim_daily(interaction.user.id, interaction.guild.id, amount)
        if not result["success"]:
            remaining = int(result.get("cooldown_left") or result.get("remaining") or 0)
            until = int(time.time()) + remaining
            await interaction.response.send_message(
                f"⏳ Награда уже получена! Следующая через <t:{until}:R>.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="💼 Ежедневная награда",
            description=f"Ты получил **{amount}** 💰 монет!"
                        + (f"\n↳ бонус «Богач» lvl.{rich_lvl}: +{25 * rich_lvl}" if rich_lvl else "\n\nУлучши «💰 Богач» в /shop → ⚙️ Улучшения — +25 монет/уровень."),
            color=0x2ED573,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="shop", description="Магазин: кейсы, ключи, эффекты, улучшения")
    @safe_command
    async def shop(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        view = ShopView(interaction.user.id, interaction.guild.id)
        await view.refresh(interaction)
