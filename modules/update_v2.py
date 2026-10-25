# modules/update_v2.py
# ======================================================================
# Большое обновление:
# - кристаллы больше НЕ конвертируются в монеты;
# - отдельная редкая валюта;
# - "Кривая рука" падает с шансом 25% при открытии кейса;
# - "Прямые руки" стоят в 2 раза дороже ключа, который сломался;
# - роли можно продавать за кристаллы;
# - добавлены эффекты: щит, скидка, пассивный доход, критик, хранитель кристаллов, азарт;
# - добавлены мини-игры: лестница, кости PvP, чья карта выше, морской бой 3x3.
#
# Подключение в main.py:
# from modules import update_v2
# update_v2.register(bot)
# ======================================================================

import random
import time

import discord
from discord import app_commands, ui

from database import Database, db

V2_SCHEMA_DONE = False

# ===== Эффекты =====

EFFECTS = {
    "shield": {
        "name": "🛡️ Щит",
        "description": "Защищает от дебаффа «Кривая рука» при открытии кейсов."
    },
    "discount": {
        "name": "🏷️ Скидка",
        "description": "Скидка 10% на покупку кейсов и ключей."
    },
    "income": {
        "name": "💼 Пассивный доход",
        "description": "Раз в день можно получить 100 монет командой /daily."
    },
    "critic": {
        "name": "⚡ Критик",
        "description": "10% шанс увеличить выигрыш в мини-играх на 25%."
    },
    "crystal_guard": {
        "name": "💎 Хранитель кристаллов",
        "description": "15% шанс не потерять кристаллы при проигрыше."
    },
    "high_roller": {
        "name": "🔥 Азарт",
        "description": "Увеличивает максимальные ставки в мини-играх."
    },
}

EFFECT_PRICES = {
    "shield": 50,
    "discount": 40,
    "income": 60,
    "critic": 45,
    "crystal_guard": 55,
    "high_roller": 70,
}

EFFECT_ROLE_IDS = {
    "shield": 2001,
    "discount": 2002,
    "income": 2003,
    "critic": 2004,
    "crystal_guard": 2005,
    "high_roller": 2006,
}


# ===== Служебные функции =====

async def ensure_v2_schema():
    global V2_SCHEMA_DONE

    if V2_SCHEMA_DONE:
        return

    try:
        await db.db.execute("ALTER TABLE cases ADD COLUMN case_crystal_price INTEGER DEFAULT 0")
    except Exception:
        pass

    try:
        await db.db.execute("ALTER TABLE cases ADD COLUMN key_crystal_price INTEGER DEFAULT 0")
    except Exception:
        pass

    try:
        await db.db.execute("ALTER TABLE market_listings ADD COLUMN currency TEXT DEFAULT 'coins'")
    except Exception:
        pass

    try:
        await db.db.execute("ALTER TABLE users ADD COLUMN last_daily INTEGER DEFAULT 0")
    except Exception:
        pass

    await db.db.commit()
    V2_SCHEMA_DONE = True


async def safe_remove_role(guild: discord.Guild, user_id: int, role_id: int):
    role = guild.get_role(role_id)

    if not role:
        return

    member = guild.get_member(user_id)

    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except discord.HTTPException:
            return

    try:
        await member.remove_roles(role, reason="Действие в боте")
    except discord.HTTPException:
        pass


def format_currency(amount: int, currency: str) -> str:
    if currency == "crystals":
        return f"{amount} кристаллов"
    return f"{amount} монет"


async def spend_currency(user_id: int, guild_id: int, amount: int, currency: str) -> bool:
    amount = int(amount)

    if amount <= 0:
        return True

    await db.get_or_create_user(user_id, guild_id)

    if currency == "crystals":
        query = """
            UPDATE users
            SET crystals = crystals - ?
            WHERE user_id = ? AND guild_id = ? AND crystals >= ?
        """
    else:
        query = """
            UPDATE users
            SET coins = coins - ?
            WHERE user_id = ? AND guild_id = ? AND coins >= ?
        """

    async with db.db.execute(query, (amount, user_id, guild_id, amount)) as cursor:
        await db.db.commit()
        return cursor.rowcount > 0


async def award_currency(user_id: int, guild_id: int, amount: int, currency: str):
    amount = int(amount)

    if amount <= 0:
        return

    await db.get_or_create_user(user_id, guild_id)

    if currency == "crystals":
        query = """
            UPDATE users
            SET crystals = crystals + ?
            WHERE user_id = ? AND guild_id = ?
        """
    else:
        query = """
            UPDATE users
            SET coins = coins + ?
            WHERE user_id = ? AND guild_id = ?
        """

    await db.db.execute(query, (amount, user_id, guild_id))
    await db.db.commit()


async def apply_crit(user_id: int, guild_id: int, amount: int):
    try:
        has_crit = await db.has_effect(user_id, guild_id, "critic")
    except Exception:
        has_crit = False

    if has_crit and random.random() < 0.10:
        return int(amount * 1.25), True

    return amount, False


async def crystal_guard_refund(user_id: int, guild_id: int, amount: int, currency: str) -> bool:
    if currency != "crystals":
        return False

    try:
        has_guard = await db.has_effect(user_id, guild_id, "crystal_guard")
    except Exception:
        has_guard = False

    if has_guard and random.random() < 0.15:
        await award_currency(user_id, guild_id, amount, "crystals")
        return True

    return False


async def apply_discount(user_id: int, guild_id: int, price: int) -> int:
    try:
        has_discount = await db.has_effect(user_id, guild_id, "discount")
    except Exception:
        has_discount = False

    if has_discount and price > 0:
        return max(1, int(price * 0.90))

    return price


async def get_max_coin_bet(interaction: discord.Interaction) -> int:
    try:
        max_bet = await db.get_max_bet(interaction.user.id, interaction.guild.id)
    except Exception:
        max_bet = 1000

    try:
        if await db.has_effect(interaction.user.id, interaction.guild.id, "high_roller"):
            max_bet = int(max_bet * 1.5)
    except Exception:
        pass

    return max(10, int(max_bet))


async def get_max_crystal_bet(interaction: discord.Interaction) -> int:
    max_bet = 25

    try:
        if await db.has_effect(interaction.user.id, interaction.guild.id, "high_roller"):
            max_bet = 50
    except Exception:
        pass

    return max_bet


# ===== Патчи Database =====

async def has_effect(self, user_id: int, guild_id: int, effect: str) -> bool:
    async with self.db.execute(
        """
        SELECT COUNT(*) AS count
        FROM inventory
        WHERE user_id = ? AND guild_id = ? AND role_type = 'effect'
          AND rarity = ? AND is_applied = 1
        """,
        (user_id, guild_id, effect)
    ) as cursor:
        row = await cursor.fetchone()
        return bool(row and row["count"] > 0)


Database.has_effect = has_effect


async def add_effect_to_inventory(self, user_id: int, guild_id: int, effect: str) -> int:
    if await self.has_effect(user_id, guild_id, effect):
        return -1

    role_id = EFFECT_ROLE_IDS.get(effect, 2999)

    async with self.db.execute(
        """
        INSERT INTO inventory
        (user_id, guild_id, role_id, role_type, rarity, level, is_applied)
        VALUES (?, ?, ?, 'effect', ?, 1, 1)
        """,
        (user_id, guild_id, role_id, effect)
    ) as cursor:
        await self.db.commit()
        return cursor.lastrowid


Database.add_effect_to_inventory = add_effect_to_inventory


async def get_user_effects(self, user_id: int, guild_id: int):
    async with self.db.execute(
        """
        SELECT rarity
        FROM inventory
        WHERE user_id = ? AND guild_id = ? AND role_type = 'effect' AND is_applied = 1
        ORDER BY id
        """,
        (user_id, guild_id)
    ) as cursor:
        rows = await cursor.fetchall()
        return [row["rarity"] for row in rows]


Database.get_user_effects = get_user_effects


async def open_case_v2(self, user_id: int, guild_id: int, case_id: int):
    async with self.db.execute(
        "SELECT * FROM cases WHERE id = ?",
        (case_id,)
    ) as cursor:
        case_row = await cursor.fetchone()

    if not case_row:
        return {"success": False, "error": "Кейс не найден."}

    case = dict(case_row)

    if case["guild_id"] != guild_id:
        return {"success": False, "error": "Кейс не найден."}

    if not case["is_active"]:
        return {"success": False, "error": "Кейс не активен."}

    async with self.db.execute(
        "SELECT quantity FROM player_cases WHERE user_id = ? AND guild_id = ? AND case_id = ?",
        (user_id, guild_id, case_id)
    ) as cursor:
        row = await cursor.fetchone()
        case_amount = row["quantity"] if row else 0

    async with self.db.execute(
        "SELECT quantity FROM player_keys WHERE user_id = ? AND guild_id = ? AND case_id = ?",
        (user_id, guild_id, case_id)
    ) as cursor:
        row = await cursor.fetchone()
        key_amount = row["quantity"] if row else 0

    if case_amount < 1:
        return {"success": False, "error": "У тебя нет этого кейса."}

    if key_amount < 1:
        return {"success": False, "error": "У тебя нет ключа для этого кейса."}

    reward = await self.get_random_role_from_case(case_id)

    if not reward:
        return {"success": False, "error": "В кейсе нет доступных ролей."}

    if not await self.use_case(user_id, guild_id, case_id):
        return {"success": False, "error": "Не удалось использовать кейс."}

    if not await self.use_key(user_id, guild_id, case_id):
        await self.add_case(user_id, guild_id, case_id, 1)
        return {"success": False, "error": "Не удалось использовать ключ."}

    debuff_applied = False

    has_shield = await self.has_effect(user_id, guild_id, "shield")

    if not has_shield and random.random() < 0.25:
        debuff_result = await self.add_debuff_to_inventory(user_id, guild_id, "clumsy_hands")

        if debuff_result != -1:
            await self.update_broken_key_cost(user_id, guild_id, case["key_price"])
            debuff_applied = True

    async with self.db.execute(
        """
        SELECT COUNT(*) AS count
        FROM inventory
        WHERE user_id = ? AND guild_id = ? AND role_id = ?
        """,
        (user_id, guild_id, reward["role_id"])
    ) as cursor:
        row = await cursor.fetchone()
        duplicate = bool(row and row["count"] > 0)

    try:
        inventory_id = await self.add_role_to_inventory(
            user_id,
            guild_id,
            reward["role_id"],
            "visual",
            reward["rarity"],
            1,
            reward.get("sell_price", 0)
        )
    except TypeError:
        inventory_id = await self.add_role_to_inventory(
            user_id,
            guild_id,
            reward["role_id"],
            "visual",
            reward["rarity"],
            1
        )

    if inventory_id == -1:
        async with self.db.execute(
            """
            SELECT COUNT(*) AS count
            FROM inventory
            WHERE user_id = ? AND guild_id = ? AND role_id = ?
            """,
            (user_id, guild_id, reward["role_id"])
        ) as cursor:
            row = await cursor.fetchone()
            new_level = (row["count"] if row else 0) + 1

        async with self.db.execute(
            """
            INSERT INTO inventory
            (user_id, guild_id, role_id, role_type, rarity, level, is_applied)
            VALUES (?, ?, ?, 'visual', ?, ?, 0)
            """,
            (user_id, guild_id, reward["role_id"], reward["rarity"], new_level)
        ) as cursor:
            await self.db.commit()
            inventory_id = cursor.lastrowid

    return {
        "success": True,
        "duplicate": duplicate,
        "debuff_applied": debuff_applied,
        "rarity": reward["rarity"],
        "role_id": reward["role_id"],
        "market_price": reward.get("sell_price", 0),
        "case_name": case["name"]
    }


Database.open_case = open_case_v2


async def list_role_for_sale_currency(
    self,
    seller_id: int,
    guild_id: int,
    inventory_id: int,
    price: int,
    currency: str
):
    if price <= 0:
        return {"success": False, "error": "Цена должна быть больше 0."}

    if currency not in ("coins", "crystals"):
        return {"success": False, "error": "Неверная валюта."}

    async with self.db.execute(
        "SELECT * FROM inventory WHERE id = ? AND user_id = ? AND guild_id = ?",
        (inventory_id, seller_id, guild_id)
    ) as cursor:
        item_row = await cursor.fetchone()

    if not item_row:
        return {"success": False, "error": "Роль не найдена в твоём инвентаре."}

    item = dict(item_row)

    if item["role_type"] == "debuff":
        return {"success": False, "error": "Дебаффы нельзя продавать."}

    async with self.db.execute(
        "SELECT COUNT(*) AS count FROM market_listings WHERE inventory_id = ? AND is_sold = 0",
        (inventory_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if row and row["count"] > 0:
            return {"success": False, "error": "Роль уже выставлена на рынок."}

    now = int(time.time())

    async with self.db.execute(
        "SELECT COUNT(*) AS count FROM auctions WHERE inventory_id = ? AND end_time > ?",
        (inventory_id, now)
    ) as cursor:
        row = await cursor.fetchone()
        if row and row["count"] > 0:
            return {"success": False, "error": "Роль участвует в аукционе."}

    was_applied = bool(item["is_applied"])

    if was_applied:
        await self.unapply_role(seller_id, guild_id, inventory_id)

    async with self.db.execute(
        """
        INSERT INTO market_listings
        (seller_id, guild_id, inventory_id, price, currency)
        VALUES (?, ?, ?, ?, ?)
        """,
        (seller_id, guild_id, inventory_id, price, currency)
    ) as cursor:
        await self.db.commit()
        listing_id = cursor.lastrowid

    return {
        "success": True,
        "listing_id": listing_id,
        "was_applied": was_applied,
        "role_id": item["role_id"]
    }


Database.list_role_for_sale_currency = list_role_for_sale_currency


async def buy_from_market_v2(self, buyer_id: int, listing_id: int):
    async with self.db.execute(
        "SELECT * FROM market_listings WHERE id = ?",
        (listing_id,)
    ) as cursor:
        listing_row = await cursor.fetchone()

    if not listing_row or listing_row["is_sold"]:
        return {"success": False, "error": "Лот не найден или уже продан."}

    listing = dict(listing_row)
    currency = listing.get("currency", "coins") or "coins"

    async with self.db.execute(
        "SELECT * FROM inventory WHERE id = ?",
        (listing["inventory_id"],)
    ) as cursor:
        item_row = await cursor.fetchone()

    if not item_row:
        return {"success": False, "error": "Роль уже недоступна."}

    item = dict(item_row)

    if listing["seller_id"] == buyer_id:
        return {"success": False, "error": "Нельзя купить свою собственную роль."}

    await self.get_or_create_user(buyer_id, listing["guild_id"])
    await self.get_or_create_user(listing["seller_id"], listing["guild_id"])

    if currency == "crystals":
        spend_query = """
            UPDATE users
            SET crystals = crystals - ?
            WHERE user_id = ? AND guild_id = ? AND crystals >= ?
        """
    else:
        spend_query = """
            UPDATE users
            SET coins = coins - ?
            WHERE user_id = ? AND guild_id = ? AND coins >= ?
        """

    async with db.db.execute(
        spend_query,
        (listing["price"], buyer_id, listing["guild_id"], listing["price"])
    ) as cursor:
        await db.db.commit()

        if cursor.rowcount == 0:
            return {"success": False, "error": "Недостаточно средств."}

    async with self.db.execute(
        "UPDATE market_listings SET is_sold = 1 WHERE id = ? AND is_sold = 0",
        (listing_id,)
    ) as cursor:
        if cursor.rowcount == 0:
            await award_currency(buyer_id, listing["guild_id"], listing["price"], currency)
            await self.db.commit()
            return {"success": False, "error": "Лот уже продан."}

    commission = int(listing["price"] * 0.05)
    seller_revenue = listing["price"] - commission

    await award_currency(listing["seller_id"], listing["guild_id"], seller_revenue, currency)

    was_applied = bool(item["is_applied"])

    await self.db.execute(
        "UPDATE inventory SET user_id = ?, is_applied = 0 WHERE id = ?",
        (buyer_id, listing["inventory_id"])
    )
    await self.db.commit()

    listing["role_id"] = item["role_id"]

    return {
        "success": True,
        "listing": listing,
        "commission": commission,
        "seller_revenue": seller_revenue,
        "was_applied": was_applied,
        "role_id": item["role_id"],
        "currency": currency
    }


Database.buy_from_market = buy_from_market_v2


# ===== Магазин кейсов за монеты и кристаллы =====

class CaseBuySelectView(ui.View):
    def __init__(self, user_id: int, guild_id: int, action: str, cases):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.action = action

        options = []

        for case in cases[:25]:
            case_dict = dict(case)

            if action == "buy_case_coin":
                description = f"Цена: {case_dict['case_price']} монет"
            elif action == "buy_case_crystal":
                description = f"Цена: {case_dict.get('case_crystal_price', 0)} кристаллов"
            elif action == "buy_key_coin":
                description = f"Цена: {case_dict['key_price']} монет"
            else:
                description = f"Цена: {case_dict.get('key_crystal_price', 0)} кристаллов"

            options.append(
                discord.SelectOption(
                    label=case_dict["name"][:100],
                    description=description[:100],
                    value=str(case_dict["id"])
                )
            )

        select = ui.Select(placeholder="Выбери кейс", options=options)
        select.callback = self.on_case_selected
        self.add_item(select)

    async def on_case_selected(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не для тебя.", ephemeral=True)
            return

        if not self.children or not self.children[0].values:
            await interaction.response.send_message("Кейс не выбран.", ephemeral=True)
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

        if self.action == "buy_case_coin":
            price = case["case_price"]
            currency = "coins"
            item = "кейс"
        elif self.action == "buy_case_crystal":
            price = case.get("case_crystal_price", 0)
            currency = "crystals"
            item = "кейс"
        elif self.action == "buy_key_coin":
            price = case["key_price"]
            currency = "coins"
            item = "ключ"
        else:
            price = case.get("key_crystal_price", 0)
            currency = "crystals"
            item = "ключ"

        if price <= 0:
            await interaction.response.edit_message(
                content="❌ Этот товар нельзя купить за выбранную валюту.",
                view=self
            )
            return

        price = await apply_discount(interaction.user.id, interaction.guild.id, price)

        if not await spend_currency(interaction.user.id, interaction.guild.id, price, currency):
            await interaction.response.edit_message(
                content=f"❌ Недостаточно средств. Нужно: {format_currency(price, currency)}.",
                view=self
            )
            return

        if self.action.startswith("buy_case"):
            await db.add_case(interaction.user.id, interaction.guild.id, case_id, 1)
        else:
            await db.add_key(interaction.user.id, interaction.guild.id, case_id, 1)

        await interaction.response.edit_message(
            content=f"✅ Куплен {item} **{case['name']}** за {format_currency(price, currency)}.",
            view=self
        )


class CaseShopV2View(ui.View):
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id

        buttons = [
            ("📦 Кейс за монеты", "buy_case_coin", discord.ButtonStyle.primary),
            ("📦 Кейс за кристаллы", "buy_case_crystal", discord.ButtonStyle.primary),
            ("🔑 Ключ за монеты", "buy_key_coin", discord.ButtonStyle.secondary),
            ("🔑 Ключ за кристаллы", "buy_key_crystal", discord.ButtonStyle.secondary),
        ]

        for label, action, style in buttons:
            button = ui.Button(style=style, label=label)
            button.callback = self.make_callback(action)
            self.add_item(button)

    def make_callback(self, action: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Это не для тебя.", ephemeral=True)
                return

            cases = await db.get_all_cases(self.guild_id, active_only=True)

            if not cases:
                await interaction.response.send_message("❌ Нет активных кейсов.", ephemeral=True)
                return

            view = CaseBuySelectView(self.user_id, self.guild_id, action, cases)
            await interaction.response.send_message("Выбери кейс:", view=view, ephemeral=True)

        return callback


# ===== Новые мини-игры =====

class AmountModal(ui.Modal, title="Ставка"):
    amount_input = ui.TextInput(
        label="Сумма",
        placeholder="Например: 100",
        max_length=10,
        required=True
    )

    def __init__(self, game: str, currency: str):
        super().__init__()
        self.game = game
        self.currency = currency

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Введи число.", ephemeral=True)
            return

        if amount <= 0:
            await interaction.response.send_message("❌ Ставка должна быть больше 0.", ephemeral=True)
            return

        if self.currency == "coins":
            if amount < 10:
                await interaction.response.send_message("❌ Минимальная ставка: 10 монет.", ephemeral=True)
                return

            max_bet = await get_max_coin_bet(interaction)

            if amount > max_bet:
                await interaction.response.send_message(f"❌ Максимальная ставка: {max_bet} монет.", ephemeral=True)
                return
        else:
            if amount < 1:
                await interaction.response.send_message("❌ Минимальная ставка: 1 кристалл.", ephemeral=True)
                return

            max_bet = await get_max_crystal_bet(interaction)

            if amount > max_bet:
                await interaction.response.send_message(f"❌ Максимальная ставка: {max_bet} кристаллов.", ephemeral=True)
                return

        if self.game == "ladder":
            await start_ladder(interaction, self.currency, amount)
            return

        if self.game == "dice_pvp":
            await create_dice_pvp(interaction, self.currency, amount)
            return

        if self.game == "high_card":
            await create_high_card(interaction, self.currency, amount)
            return

        if self.game == "battleship":
            await create_battleship(interaction, self.currency, amount)
            return

        await interaction.response.send_message("❌ Неизвестная игра.", ephemeral=True)


class CurrencyChoiceView(ui.View):
    def __init__(self, game: str):
        super().__init__(timeout=120)
        self.game = game

        coins = ui.Button(style=discord.ButtonStyle.primary, label="💰 Монеты")
        coins.callback = self.make_callback("coins")
        self.add_item(coins)

        crystals = ui.Button(style=discord.ButtonStyle.success, label="💎 Кристаллы")
        crystals.callback = self.make_callback("crystals")
        self.add_item(crystals)

    def make_callback(self, currency: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.send_modal(AmountModal(self.game, currency))

        return callback


class NewGamesMenuView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id

        games = [
            ("🪜 Лестница", "ladder"),
            ("🎲 Кости PvP", "dice_pvp"),
            ("🃏 Чья карта выше", "high_card"),
            ("🚢 Морской бой 3x3", "battleship"),
        ]

        for label, game in games:
            button = ui.Button(style=discord.ButtonStyle.primary, label=label)
            button.callback = self.make_callback(game)
            self.add_item(button)

    def make_callback(self, game: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Это не для тебя.", ephemeral=True)
                return

            view = CurrencyChoiceView(game)
            await interaction.response.send_message(
                "Выбери валюту ставки:",
                view=view,
                ephemeral=True
            )

        return callback


# ===== Лестница =====

class LadderView(ui.View):
    def __init__(self, user_id: int, guild_id: int, currency: str, bet: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.guild_id = guild_id
        self.currency = currency
        self.bet = bet
        self.step = 0
        self.active = True

        self.up_button = ui.Button(style=discord.ButtonStyle.primary, label="⬆️ Подняться")
        self.up_button.callback = self.up_callback
        self.add_item(self.up_button)

        self.cashout_button = ui.Button(style=discord.ButtonStyle.success, label="💰 Забрать")
        self.cashout_button.callback = self.cashout_callback
        self.add_item(self.cashout_button)

        self.refresh_buttons()

    def multiplier(self):
        return round(1 + self.step * 0.35, 2)

    def success_chance(self):
        return max(35, 90 - self.step * 7)

    def refresh_buttons(self):
        self.cashout_button.disabled = self.step == 0 or not self.active
        self.up_button.disabled = not self.active

    def make_embed(self):
        embed = discord.Embed(title="🪜 Лестница", color=0x00BCD4)
        embed.description = (
            f"Ступень: **{self.step}**\n"
            f"Множитель: **x{self.multiplier()}**\n"
            f"Шанс подняться: **{self.success_chance()}%**"
        )
        embed.set_footer(text=f"Ставка: {format_currency(self.bet, self.currency)}")
        return embed

    async def up_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не твоя игра.", ephemeral=True)
            return

        if not self.active:
            await interaction.response.edit_message(embed=self.make_embed(), view=self)
            return

        if random.randint(1, 100) > self.success_chance():
            self.active = False
            self.clear_items()

            refunded = await crystal_guard_refund(
                self.user_id,
                self.guild_id,
                self.bet,
                self.currency
            )

            embed = self.make_embed()
            embed.description = f"💥 Ты сорвался! Проигрыш: {format_currency(self.bet, self.currency)}."

            if refunded:
                embed.description += "\n💎 Хранитель кристаллов вернул ставку!"

            await interaction.response.edit_message(embed=embed, view=self)
            return

        self.step += 1

        if self.step >= 10:
            await self.cashout(interaction, auto=True)
            return

        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def cashout_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не твоя игра.", ephemeral=True)
            return

        if self.step == 0:
            await interaction.response.send_message("Сначала поднимись хотя бы на одну ступень.", ephemeral=True)
            return

        await self.cashout(interaction, auto=False)

    async def cashout(self, interaction: discord.Interaction, auto: bool):
        if not self.active:
            return

        self.active = False
        self.clear_items()

        winnings = int(self.bet * self.multiplier() * 0.95)
        winnings, crit = await apply_crit(self.user_id, self.guild_id, winnings)

        await award_currency(self.user_id, self.guild_id, winnings, self.currency)

        embed = self.make_embed()
        embed.description = f"✅ Забрано: {format_currency(winnings, self.currency)}."

        if auto:
            embed.description += "\n🎉 Лестница пройдена полностью!"

        if crit:
            embed.description += "\n⚡ Сработал критический эффект!"

        await interaction.response.edit_message(embed=embed, view=self)


async def start_ladder(interaction: discord.Interaction, currency: str, amount: int):
    if not await spend_currency(interaction.user.id, interaction.guild.id, amount, currency):
        await interaction.response.send_message("❌ Недостаточно средств.", ephemeral=True)
        return

    view = LadderView(interaction.user.id, interaction.guild.id, currency, amount)
    await interaction.response.send_message(embed=view.make_embed(), view=view, ephemeral=True)


# ===== Кости PvP =====

class DicePvPInviteView(ui.View):
    def __init__(self, creator_id: int, guild_id: int, currency: str, bet: int):
        super().__init__(timeout=180)
        self.creator_id = creator_id
        self.guild_id = guild_id
        self.currency = currency
        self.bet = bet

        join = ui.Button(style=discord.ButtonStyle.success, label="🎮 Принять вызов")
        join.callback = self.join_callback
        self.add_item(join)

    async def join_callback(self, interaction: discord.Interaction):
        if interaction.user.id == self.creator_id:
            await interaction.response.send_message("Ты уже участник.", ephemeral=True)
            return

        if interaction.user.bot:
            await interaction.response.send_message("Боты не могут играть.", ephemeral=True)
            return

        if not await spend_currency(self.creator_id, self.guild_id, self.bet, self.currency):
            await interaction.response.send_message("❌ У создателя игры недостаточно средств.", ephemeral=True)
            return

        if not await spend_currency(interaction.user.id, self.guild_id, self.bet, self.currency):
            await award_currency(self.creator_id, self.guild_id, self.bet, self.currency)
            await interaction.response.send_message("❌ У тебя недостаточно средств.", ephemeral=True)
            return

        game_view = DicePvPGameView(
            self.creator_id,
            interaction.user.id,
            self.guild_id,
            self.currency,
            self.bet
        )

        await interaction.response.edit_message(
            content=(
                f"🎲 Кости!\n"
                f"<@{self.creator_id}> против <@{interaction.user.id}>\n"
                f"Ставка каждого: {format_currency(self.bet, self.currency)}\n"
                f"Оба игрока должны бросить кости."
            ),
            view=game_view
        )


class DicePvPGameView(ui.View):
    def __init__(self, player1: int, player2: int, guild_id: int, currency: str, bet: int):
        super().__init__(timeout=180)
        self.player1 = player1
        self.player2 = player2
        self.guild_id = guild_id
        self.currency = currency
        self.bet = bet
        self.rolls = {}
        self.done = False

        p1 = ui.Button(style=discord.ButtonStyle.primary, label="Игрок 1: бросить")
        p1.callback = self.make_callback(player1)
        self.add_item(p1)

        p2 = ui.Button(style=discord.ButtonStyle.primary, label="Игрок 2: бросить")
        p2.callback = self.make_callback(player2)
        self.add_item(p2)

    def make_callback(self, player_id: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != player_id:
                await interaction.response.send_message("Это не твоя кнопка.", ephemeral=True)
                return

            if self.done or player_id in self.rolls:
                await interaction.response.edit_message(view=self)
                return

            self.rolls[player_id] = random.randint(1, 6)

            if len(self.rolls) < 2:
                await interaction.response.edit_message(
                    content=(
                        f"🎲 <@{player_id}> бросил: **{self.rolls[player_id]}**\n"
                        f"Ожидание второго игрока..."
                    ),
                    view=self
                )
                return

            self.done = True
            self.clear_items()

            r1 = self.rolls[self.player1]
            r2 = self.rolls[self.player2]

            if r1 > r2:
                winner = self.player1
            elif r2 > r1:
                winner = self.player2
            else:
                winner = None

            text = (
                f"🎲 <@{self.player1}> выбросил **{r1}**\n"
                f"🎲 <@{self.player2}> выбросил **{r2}**\n\n"
            )

            if winner is None:
                await award_currency(self.player1, self.guild_id, self.bet, self.currency)
                await award_currency(self.player2, self.guild_id, self.bet, self.currency)
                text += "🤝 Ничья! Ставки возвращены."
            else:
                winnings = int(self.bet * 2 * 0.95)
                winnings, crit = await apply_crit(winner, self.guild_id, winnings)
                await award_currency(winner, self.guild_id, winnings, self.currency)

                text += f"🏆 Победитель: <@{winner}>!\nВыигрыш: {format_currency(winnings, self.currency)}."

                if crit:
                    text += "\n⚡ Сработал критический эффект!"

            await interaction.response.edit_message(content=text, view=self)

        return callback


async def create_dice_pvp(interaction: discord.Interaction, currency: str, amount: int):
    view = DicePvPInviteView(interaction.user.id, interaction.guild.id, currency, amount)

    await interaction.response.send_message(
        content=(
            f"🎲 <@{interaction.user.id}> ищет соперника на кости!\n"
            f"Ставка: {format_currency(amount, currency)}."
        ),
        view=view
    )


# ===== Чья карта выше =====

class HighCardInviteView(ui.View):
    def __init__(self, creator_id: int, guild_id: int, currency: str, bet: int):
        super().__init__(timeout=180)
        self.creator_id = creator_id
        self.guild_id = guild_id
        self.currency = currency
        self.bet = bet

        join = ui.Button(style=discord.ButtonStyle.success, label="🎮 Принять вызов")
        join.callback = self.join_callback
        self.add_item(join)

    async def join_callback(self, interaction: discord.Interaction):
        if interaction.user.id == self.creator_id:
            await interaction.response.send_message("Ты уже участник.", ephemeral=True)
            return

        if interaction.user.bot:
            await interaction.response.send_message("Боты не могут играть.", ephemeral=True)
            return

        if not await spend_currency(self.creator_id, self.guild_id, self.bet, self.currency):
            await interaction.response.send_message("❌ У создателя игры недостаточно средств.", ephemeral=True)
            return

        if not await spend_currency(interaction.user.id, self.guild_id, self.bet, self.currency):
            await award_currency(self.creator_id, self.guild_id, self.bet, self.currency)
            await interaction.response.send_message("❌ У тебя недостаточно средств.", ephemeral=True)
            return

        game_view = HighCardGameView(
            self.creator_id,
            interaction.user.id,
            self.guild_id,
            self.currency,
            self.bet
        )

        await interaction.response.edit_message(
            content=(
                f"🃏 Чья карта выше!\n"
                f"<@{self.creator_id}> против <@{interaction.user.id}>\n"
                f"Ставка каждого: {format_currency(self.bet, self.currency)}"
            ),
            view=game_view
        )


def high_card_value(card: int) -> int:
    if card == 1:
        return 14
    return card


def high_card_name(card: int) -> str:
    names = {1: "Туз", 11: "Валет", 12: "Дама", 13: "Король"}
    return names.get(card, str(card))


class HighCardGameView(ui.View):
    def __init__(self, player1: int, player2: int, guild_id: int, currency: str, bet: int):
        super().__init__(timeout=180)
        self.player1 = player1
        self.player2 = player2
        self.guild_id = guild_id
        self.currency = currency
        self.bet = bet
        self.cards = {}
        self.done = False

        p1 = ui.Button(style=discord.ButtonStyle.primary, label="Игрок 1: вытянуть карту")
        p1.callback = self.make_callback(player1)
        self.add_item(p1)

        p2 = ui.Button(style=discord.ButtonStyle.primary, label="Игрок 2: вытянуть карту")
        p2.callback = self.make_callback(player2)
        self.add_item(p2)

    def make_callback(self, player_id: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != player_id:
                await interaction.response.send_message("Это не твоя кнопка.", ephemeral=True)
                return

            if self.done or player_id in self.cards:
                await interaction.response.edit_message(view=self)
                return

            self.cards[player_id] = random.randint(1, 13)

            if len(self.cards) < 2:
                await interaction.response.edit_message(
                    content=(
                        f"🃏 <@{player_id}> вытянул карту: **{high_card_name(self.cards[player_id])}**\n"
                        f"Ожидание второго игрока..."
                    ),
                    view=self
                )
                return

            self.done = True
            self.clear_items()

            c1 = self.cards[self.player1]
            c2 = self.cards[self.player2]

            v1 = high_card_value(c1)
            v2 = high_card_value(c2)

            text = (
                f"🃏 <@{self.player1}>: **{high_card_name(c1)}**\n"
                f"🃏 <@{self.player2}>: **{high_card_name(c2)}**\n\n"
            )

            if v1 > v2:
                winner = self.player1
            elif v2 > v1:
                winner = self.player2
            else:
                winner = None

            if winner is None:
                await award_currency(self.player1, self.guild_id, self.bet, self.currency)
                await award_currency(self.player2, self.guild_id, self.bet, self.currency)
                text += "🤝 Ничья! Ставки возвращены."
            else:
                winnings = int(self.bet * 2 * 0.95)
                winnings, crit = await apply_crit(winner, self.guild_id, winnings)
                await award_currency(winner, self.guild_id, winnings, self.currency)

                text += f"🏆 Победитель: <@{winner}>!\nВыигрыш: {format_currency(winnings, self.currency)}."

                if crit:
                    text += "\n⚡ Сработал критический эффект!"

            await interaction.response.edit_message(content=text, view=self)

        return callback


async def create_high_card(interaction: discord.Interaction, currency: str, amount: int):
    view = HighCardInviteView(interaction.user.id, interaction.guild.id, currency, amount)

    await interaction.response.send_message(
        content=(
            f"🃏 <@{interaction.user.id}> ищет соперника на игру 'Чья карта выше'!\n"
            f"Ставка: {format_currency(amount, currency)}."
        ),
        view=view
    )


# ===== Морской бой 3x3 =====

class BattleshipInviteView(ui.View):
    def __init__(self, creator_id: int, guild_id: int, currency: str, bet: int):
        super().__init__(timeout=180)
        self.creator_id = creator_id
        self.guild_id = guild_id
        self.currency = currency
        self.bet = bet

        join = ui.Button(style=discord.ButtonStyle.success, label="🎮 Принять вызов")
        join.callback = self.join_callback
        self.add_item(join)

    async def join_callback(self, interaction: discord.Interaction):
        if interaction.user.id == self.creator_id:
            await interaction.response.send_message("Ты уже участник.", ephemeral=True)
            return

        if interaction.user.bot:
            await interaction.response.send_message("Боты не могут играть.", ephemeral=True)
            return

        if not await spend_currency(self.creator_id, self.guild_id, self.bet, self.currency):
            await interaction.response.send_message("❌ У создателя игры недостаточно средств.", ephemeral=True)
            return

        if not await spend_currency(interaction.user.id, self.guild_id, self.bet, self.currency):
            await award_currency(self.creator_id, self.guild_id, self.bet, self.currency)
            await interaction.response.send_message("❌ У тебя недостаточно средств.", ephemeral=True)
            return

        game_view = BattleshipGameView(
            self.creator_id,
            interaction.user.id,
            self.guild_id,
            self.currency,
            self.bet
        )

        await interaction.response.edit_message(
            content=(
                f"🚢 Морской бой 3x3!\n"
                f"<@{self.creator_id}> против <@{interaction.user.id}>\n"
                f"Ставка каждого: {format_currency(self.bet, self.currency)}\n"
                f"Первым ходит <@{self.creator_id}>."
            ),
            view=game_view
        )


class BattleshipGameView(ui.View):
    def __init__(self, player1: int, player2: int, guild_id: int, currency: str, bet: int):
        super().__init__(timeout=300)
        self.player1 = player1
        self.player2 = player2
        self.guild_id = guild_id
        self.currency = currency
        self.bet = bet
        self.turn = player1
        self.ship1 = random.randint(0, 8)
        self.ship2 = random.randint(0, 8)
        self.missed = set()
        self.done = False

        self.refresh_buttons()

    def refresh_buttons(self):
        self.clear_items()

        if self.done:
            return

        for i in range(9):
            button = ui.Button(
                style=discord.ButtonStyle.secondary,
                label=str(i + 1),
                disabled=i in self.missed
            )
            button.callback = self.make_shot_callback(i)
            self.add_item(button)

    def make_shot_callback(self, cell: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.turn:
                await interaction.response.send_message("Сейчас не твой ход.", ephemeral=True)
                return

            if self.done or cell in self.missed:
                await interaction.response.edit_message(view=self)
                return

            target_ship = self.ship2 if self.turn == self.player1 else self.ship1

            if cell == target_ship:
                self.done = True
                self.clear_items()

                winnings = int(self.bet * 2 * 0.95)
                winnings, crit = await apply_crit(self.turn, self.guild_id, winnings)
                await award_currency(self.turn, self.guild_id, winnings, self.currency)

                text = (
                    f"💥 <@{self.turn}> попал в корабль!\n"
                    f"🏆 Победитель: <@{self.turn}>!\n"
                    f"Выигрыш: {format_currency(winnings, self.currency)}."
                )

                if crit:
                    text += "\n⚡ Сработал критический эффект!"

                await interaction.response.edit_message(content=text, view=self)
                return

            self.missed.add(cell)

            if len(self.missed) >= 9:
                self.done = True
                self.clear_items()

                await award_currency(self.player1, self.guild_id, self.bet, self.currency)
                await award_currency(self.player2, self.guild_id, self.bet, self.currency)

                await interaction.response.edit_message(
                    content="🤝 Все клетки обстреляны. Ничья! Ставки возвращены.",
                    view=self
                )
                return

            self.turn = self.player2 if self.turn == self.player1 else self.player1

            await interaction.response.edit_message(
                content=(
                    f"🚢 Морской бой 3x3\n"
                    f"Промах: клетка **{cell + 1}**\n"
                    f"Ходит: <@{self.turn}>"
                ),
                view=self
            )

        return callback


async def create_battleship(interaction: discord.Interaction, currency: str, amount: int):
    view = BattleshipInviteView(interaction.user.id, interaction.guild.id, currency, amount)

    await interaction.response.send_message(
        content=(
            f"🚢 <@{interaction.user.id}> ищет соперника на морской бой 3x3!\n"
            f"Ставка: {format_currency(amount, currency)}."
        ),
        view=view
    )


# ===== Регистрация команд =====

def register(bot):
    @bot.listen("on_ready")
    async def _update_v2_ready():
        await ensure_v2_schema()

    @bot.tree.command(name="effects", description="Посмотреть свои активные эффекты")
    async def effects(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        await ensure_v2_schema()

        user_effects = await db.get_user_effects(interaction.user.id, interaction.guild.id)

        if not user_effects:
            await interaction.response.send_message("❌ У тебя нет активных эффектов.", ephemeral=True)
            return

        embed = discord.Embed(title="✨ Активные эффекты", color=0x9C27B0)

        for effect_key in user_effects:
            effect = EFFECTS.get(effect_key)

            if not effect:
                continue

            embed.add_field(
                name=effect["name"],
                value=effect["description"],
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="effect_shop", description="Магазин ролей с эффектами")
    async def effect_shop(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        await ensure_v2_schema()

        embed = discord.Embed(
            title="🧬 Магазин эффектов",
            description="Эффекты покупаются за кристаллы и не конвертируются в монеты.",
            color=0x9C27B0
        )

        for key, effect in EFFECTS.items():
            price = EFFECT_PRICES[key]

            embed.add_field(
                name=effect["name"],
                value=f"{effect['description']}\nЦена: **{price} кристаллов**",
                inline=False
            )

        embed.set_footer(text="Используй /buy_effect для покупки")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="buy_effect", description="Купить роль с эффектом")
    @app_commands.describe(effect="Эффект")
    @app_commands.choices(effect=[
        app_commands.Choice(name=value["name"], value=key)
        for key, value in EFFECTS.items()
    ])
    async def buy_effect(interaction: discord.Interaction, effect: app_commands.Choice[str]):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        await ensure_v2_schema()

        price = EFFECT_PRICES.get(effect.value, 50)

        if await db.has_effect(interaction.user.id, interaction.guild.id, effect.value):
            await interaction.response.send_message("❌ Этот эффект уже куплен.", ephemeral=True)
            return

        if not await spend_currency(interaction.user.id, interaction.guild.id, price, "crystals"):
            await interaction.response.send_message(
                f"❌ Недостаточно кристаллов. Нужно: {price}.",
                ephemeral=True
            )
            return

        await db.add_effect_to_inventory(interaction.user.id, interaction.guild.id, effect.value)

        await interaction.response.send_message(
            f"✅ Куплен эффект **{EFFECTS[effect.value]['name']}** за {price} кристаллов.",
            ephemeral=True
        )

    @bot.tree.command(name="daily", description="Получить ежедневный доход")
    async def daily(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        await ensure_v2_schema()

        if not await db.has_effect(interaction.user.id, interaction.guild.id, "income"):
            await interaction.response.send_message(
                "❌ У тебя нет роли «Пассивный доход».",
                ephemeral=True
            )
            return

        now = int(time.time())
        user = await db.get_or_create_user(interaction.user.id, interaction.guild.id)
        last_daily = user.get("last_daily", 0) or 0

        if now - last_daily < 86400:
            hours = int((86400 - (now - last_daily)) // 3600)
            minutes = int(((86400 - (now - last_daily)) % 3600) // 60)

            await interaction.response.send_message(
                f"⏰ Следующий доход через: **{hours}ч {minutes}м**.",
                ephemeral=True
            )
            return

        async with db.db.execute(
            """
            UPDATE users
            SET last_daily = ?
            WHERE user_id = ? AND guild_id = ? AND last_daily <= ?
            """,
            (now, interaction.user.id, interaction.guild.id, now - 86400)
        ) as cursor:
            await db.db.commit()

            if cursor.rowcount == 0:
                await interaction.response.send_message("⏳ Ты уже получил доход.", ephemeral=True)
                return

        await award_currency(interaction.user.id, interaction.guild.id, 100, "coins")

        await interaction.response.send_message(
            "✅ Получено **100 монет** пассивного дохода.",
            ephemeral=True
        )

    @bot.tree.command(name="set_case_crystal_prices", description="[Админ] Установить цены кейса в кристаллах")
    @app_commands.describe(
        case_id="ID кейса",
        case_crystal_price="Цена кейса в кристаллах",
        key_crystal_price="Цена ключа в кристаллах"
    )
    async def set_case_crystal_prices(
        interaction: discord.Interaction,
        case_id: int,
        case_crystal_price: int,
        key_crystal_price: int
    ):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        is_owner = interaction.user.id == interaction.guild.owner_id

        try:
            is_admin = interaction.user.guild_permissions.administrator
        except Exception:
            is_admin = False

        if not is_owner and not is_admin:
            await interaction.response.send_message("❌ Только владелец или администратор.", ephemeral=True)
            return

        await ensure_v2_schema()

        if case_crystal_price < 0 or key_crystal_price < 0:
            await interaction.response.send_message("❌ Цены не могут быть отрицательными.", ephemeral=True)
            return

        async with db.db.execute(
            """
            UPDATE cases
            SET case_crystal_price = ?, key_crystal_price = ?
            WHERE id = ? AND guild_id = ?
            """,
            (case_crystal_price, key_crystal_price, case_id, interaction.guild.id)
        ) as cursor:
            await db.db.commit()

            if cursor.rowcount == 0:
                await interaction.response.send_message("❌ Кейс не найден.", ephemeral=True)
                return

        await interaction.response.send_message(
            f"✅ Цены в кристаллах обновлены.\n"
            f"Кейс: {case_crystal_price} кристаллов\n"
            f"Ключ: {key_crystal_price} кристаллов",
            ephemeral=True
        )

    @bot.tree.command(name="case_shop_v2", description="Магазин кейсов за монеты и кристаллы")
    async def case_shop_v2(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        await ensure_v2_schema()

        embed = discord.Embed(
            title="🏪 Магазин кейсов",
            description=(
                "Монеты и кристаллы — отдельные валюты.\n"
                "Кристаллы нельзя конвертировать в монеты."
            ),
            color=0xFFD700
        )

        view = CaseShopV2View(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @bot.tree.command(name="market_sell_crystals", description="Выставить роль на продажу за кристаллы")
    @app_commands.describe(inventory_id="ID роли из инвентаря", price="Цена в кристаллах")
    async def market_sell_crystals(interaction: discord.Interaction, inventory_id: int, price: int):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        await ensure_v2_schema()

        result = await db.list_role_for_sale_currency(
            interaction.user.id,
            interaction.guild.id,
            inventory_id,
            price,
            "crystals"
        )

        if not result["success"]:
            await interaction.response.send_message(f"❌ {result['error']}", ephemeral=True)
            return

        if result.get("was_applied") and result.get("role_id"):
            await safe_remove_role(interaction.guild, interaction.user.id, result["role_id"])

        await interaction.response.send_message(
            f"✅ Роль выставлена на продажу за **{price} кристаллов**.",
            ephemeral=True
        )

    @bot.tree.command(name="new_games", description="Новые мини-игры")
    async def new_games(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        await ensure_v2_schema()

        embed = discord.Embed(
            title="🎮 Новые мини-игры",
            description=(
                "Ставки принимаются отдельно в монетах или кристаллах.\n"
                "Валюты не конвертируются."
            ),
            color=0x5865F2
        )

        view = NewGamesMenuView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)