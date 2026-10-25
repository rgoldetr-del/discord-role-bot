# modules/role_actions.py

import asyncio
import time

import discord
from discord import ui

from database import db
from .shared import get_rarity_emoji, get_rarity_name, get_role_name


FALLBACK_PRICES = {
    "common": 200,
    "uncommon": 800,
    "rare": 2000,
    "epic": 5000,
    "legendary": 15000,
    "secret": 50000,
    "secret+": 200000
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


# ===== Вспомогательные функции =====

async def get_item(guild_id: int, user_id: int, item_id: int):
    async with db.db.execute(
        "SELECT * FROM inventory WHERE id = ? AND user_id = ? AND guild_id = ?",
        (item_id, user_id, guild_id)
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def is_locked(item_id: int) -> bool:
    async with db.db.execute(
        "SELECT COUNT(*) AS count FROM market_listings WHERE inventory_id = ? AND is_sold = 0",
        (item_id,)
    ) as cursor:
        row = await cursor.fetchone()
        if row and row["count"] > 0:
            return True

    now = int(time.time())

    async with db.db.execute(
        "SELECT COUNT(*) AS count FROM auctions WHERE inventory_id = ? AND end_time > ?",
        (item_id, now)
    ) as cursor:
        row = await cursor.fetchone()
        return bool(row and row["count"] > 0)


def get_price(item: dict) -> int:
    price = item.get("market_price", 0) or 0

    if price <= 0:
        price = FALLBACK_PRICES.get(item.get("rarity"), 0)

    return int(price or 0)


def get_item_name(guild: discord.Guild, item: dict) -> str:
    if item.get("role_type") == "upgradeable":
        names = {"luck": "Удача", "rich": "Богач"}
        base = names.get(item.get("rarity"), item.get("rarity"))
        return f"{base} lvl.{item.get('level', 1)}"

    if item.get("role_type") == "debuff":
        return "💀 Кривая рука"

    if item.get("role_type") == "effect":
        names = {
            "shield": "🛡️ Щит",
            "discount": "🏷️ Скидка",
            "income": "💼 Доход",
            "critic": "⚡ Критик",
            "crystal_guard": "💎 Хранитель кристаллов",
            "high_roller": "🔥 Азарт"
        }
        return names.get(item.get("rarity"), "✨ Эффект")

    role = guild.get_role(item.get("role_id"))
    return role.name if role else f"Роль {item.get('role_id')}"


async def deliver(interaction: discord.Interaction, content=None, embed=None, view=None):
    try:
        if interaction.response.is_done():
            if interaction.message is not None:
                await interaction.message.edit(content=content, embed=embed, view=view)
            else:
                await interaction.edit_original_response(content=content, embed=embed, view=view)
        else:
            await interaction.response.edit_message(content=content, embed=embed, view=view)
    except discord.HTTPException:
        pass


async def render_inventory(interaction: discord.Interaction, guild_id: int, user_id: int):
    """Возврат в инвентарь после действия (использует inventory_v2)."""
    try:
        from .inventory_v2 import InventoryV2View

        view = InventoryV2View(int(user_id), int(guild_id))
        await view.refresh(interaction)
    except Exception:
        try:
            await interaction.message.edit(content=None, embed=None, view=None)
        except Exception:
            pass


class CaseOpenButton(ui.Button):
    """Кнопка «🔓 Открыть» для кейса из инвентаря (custom_id: ra:opencase:...)."""

    def __init__(self, guild_id: int, user_id: int, case_id: int):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="🔓 Открыть",
            custom_id=f"ra:opencase:{guild_id}:{user_id}:{case_id}",
        )

    async def callback(self, interaction: discord.Interaction):
        parts = self.custom_id.split(":")
        _, action, raw_guild, raw_user, raw_case = parts

        guild_id, user_id, case_id = int(raw_guild), int(raw_user), int(raw_case)

        if interaction.user.id != user_id:
            await interaction.response.send_message("❌ Это не твой инвентарь.", ephemeral=True)
            return

        try:
            await interaction.response.defer()
        except discord.HTTPException:
            return

        message = await interaction.original_response()

        # лёгкая анимация открытия
        for emoji in ("🔑", "✨", "📦"):
            try:
                await message.edit(content=f"{emoji} Открываю кейс...")
            except discord.HTTPException:
                break
            await asyncio.sleep(0.4)

        result = await db.open_case(user_id, guild_id, case_id)

        if not result["success"]:
            await message.edit(content=f"❌ {result['error']}")
            return

        role_name = get_role_name(interaction.guild, result["role_id"])
        emoji = get_rarity_emoji(result["rarity"])
        rarity_name = get_rarity_name(result["rarity"])

        embed = discord.Embed(
            title="🎉 Кейс открыт!",
            description=(
                f"Выпала роль: {emoji} **{role_name}**\n"
                f"Редкость: **{rarity_name}**\n"
                f"Рыночная цена: **{result['market_price']:,}** монет".replace(",", " ")
            ),
            color=0x00BCD4,
        )

        if result["duplicate"]:
            embed.add_field(name="🔁 Повтор", value="Эта роль уже была у тебя. Копия добавлена в инвентарь.", inline=False)
        if result["debuff_applied"]:
            embed.add_field(name="💀 Кривая рука", value="Ключ скользнул... Получен дебафф «Кривая рука». Лечится в /shop.", inline=False)

        embed.set_footer(text="Новая роль — во вкладке 🎭 Роли в /inventory")

        try:
            await message.edit(content=None, embed=embed, view=None)
        except discord.HTTPException:
            pass

        # публичное объявление о крупном дропе (эпик+)
        if result["rarity"] in ("epic", "legendary", "secret", "secret+"):
            try:
                if interaction.channel:
                    await interaction.channel.send(
                        content=f"🎉 {interaction.user.mention} выбил {emoji} **{rarity_name}** из кейса **{result['case_name']}**!"
                    )
            except discord.HTTPException:
                pass


async def remove_role_if_applied(interaction: discord.Interaction, item: dict):
    if not item.get("is_applied"):
        return

    if item.get("role_type") not in ("visual", "admin"):
        return

    role = interaction.guild.get_role(item.get("role_id"))

    if not role:
        return

    try:
        await interaction.user.remove_roles(role, reason="Действие с ролью в боте")
    except discord.HTTPException:
        pass


# ===== Кнопки =====

class RoleActionButton(ui.Button):
    def __init__(self, action: str, guild_id: int, user_id: int, item_id: int, label: str):
        style = discord.ButtonStyle.secondary

        if action in ("apply", "sell_now"):
            style = discord.ButtonStyle.success
        elif action in ("sell", "gift", "auction"):
            style = discord.ButtonStyle.primary
        elif action == "unapply":
            style = discord.ButtonStyle.danger

        super().__init__(
            style=style,
            label=label[:80],
            custom_id=f"ra:{action}:{guild_id}:{user_id}:{item_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        parts = self.custom_id.split(":")

        if len(parts) != 5:
            return

        _, action, raw_guild, raw_user, raw_item = parts

        guild_id = int(raw_guild)
        user_id = int(raw_user)
        item_id = int(raw_item)

        if interaction.user.id != user_id:
            await interaction.response.send_message("❌ Это не твой инвентарь.", ephemeral=True)
            return

        if action == "back":
            await render_inventory(interaction, guild_id, user_id)
            return

        item = await get_item(guild_id, user_id, item_id)

        if not item:
            await deliver(interaction, content="❌ Роль не найдена.", view=None)
            return

        locked = await is_locked(item_id)

        if action in ("apply", "unapply"):
            if item["role_type"] not in ("visual", "admin"):
                await deliver(interaction, content="❌ Эту роль нельзя применить или снять.", view=None)
                return

            if locked:
                await deliver(interaction, content="🔒 Роль участвует в рынке или аукционе.", view=None)
                return

            role = interaction.guild.get_role(item["role_id"])

            if action == "apply":
                if not role:
                    await deliver(interaction, content="❌ Discord-роль не найдена.", view=None)
                    return

                try:
                    await interaction.user.add_roles(role, reason="Применение роли из инвентаря")
                except discord.Forbidden:
                    await deliver(interaction, content="❌ У бота нет прав выдать эту роль.", view=None)
                    return

                await db.apply_role(user_id, guild_id, item_id)
            else:
                if role:
                    try:
                        await interaction.user.remove_roles(role, reason="Снятие роли из инвентаря")
                    except discord.HTTPException:
                        pass

                await db.unapply_role(user_id, guild_id, item_id)

            view = RoleActionView()
            await view.render(interaction, guild_id, user_id, item_id)
            return

        if locked:
            await deliver(interaction, content="🔒 Роль участвует в рынке или аукционе.", view=None)
            return

        if action == "sell_now":
            if item["role_type"] == "debuff":
                await deliver(interaction, content="❌ Дебафф нельзя продать.", view=None)
                return

            price = get_price(item)

            if price <= 0:
                await deliver(interaction, content="❌ У этой роли нет рыночной цены.", view=None)
                return

            await remove_role_if_applied(interaction, item)

            await db.db.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
            await db.db.commit()

            await db.update_coins(user_id, guild_id, price)

            await render_inventory(interaction, guild_id, user_id)
            return

        if action == "sell":
            if item["role_type"] == "debuff":
                await deliver(interaction, content="❌ Дебафф нельзя продать.", view=None)
                return

            modal = SellModal(guild_id, user_id, item_id, item)
            await interaction.response.send_modal(modal)
            return

        if action == "gift":
            if item["role_type"] != "visual":
                await deliver(interaction, content="❌ Подарить можно только визуальные роли.", view=None)
                return

            modal = GiftModal(guild_id, user_id, item_id)
            await interaction.response.send_modal(modal)
            return

        if action == "auction":
            if item["role_type"] == "debuff":
                await deliver(interaction, content="❌ Дебафф нельзя выставлять на аукцион.", view=None)
                return

            modal = AuctionModal(guild_id, user_id, item_id, item)
            await interaction.response.send_modal(modal)
            return


# ===== View =====

class RoleActionView(ui.View):
    __discord_ui_view__ = True

    def __init__(self):
        super().__init__(timeout=None)

    async def refresh(self, interaction, guild_id: int, user_id: int, item_id: int):
        await self.render(interaction, guild_id, user_id, item_id)

    async def render(self, interaction: discord.Interaction, guild_id: int, user_id: int, item_id: int):
        item = await get_item(guild_id, user_id, item_id)

        if not item:
            await deliver(interaction, content="❌ Роль не найдена.", view=None)
            return

        locked = await is_locked(item_id)
        name = get_item_name(interaction.guild, item)
        price = get_price(item)

        embed = discord.Embed(title=f"🎒 {name}", color=0x00BCD4)

        embed.add_field(
            name="Редкость",
            value=RARITY_NAMES.get(item.get("rarity"), "Обычная"),
            inline=True
        )

        embed.add_field(
            name="Тип",
            value=item.get("role_type", "unknown"),
            inline=True
        )

        embed.add_field(
            name="💰 Рыночная цена",
            value=f"{price} монет",
            inline=True
        )

        status = "✅ Применена" if item.get("is_applied") else "⏸️ Не применена"
        embed.add_field(name="Статус", value=status, inline=False)

        if locked:
            embed.add_field(
                name="🔒 Заблокировано",
                value="Роль участвует в рынке или аукционе.",
                inline=False
            )

        view = RoleActionView()

        if not locked:
            if item["role_type"] in ("visual", "admin"):
                if item.get("is_applied"):
                    view.add_item(RoleActionButton("unapply", guild_id, user_id, item_id, "❌ Снять"))
                else:
                    view.add_item(RoleActionButton("apply", guild_id, user_id, item_id, "✅ Применить"))

            if item["role_type"] != "debuff" and price > 0:
                view.add_item(RoleActionButton("sell_now", guild_id, user_id, item_id, f"💰 Продать сразу за {price}"))

            if item["role_type"] != "debuff":
                view.add_item(RoleActionButton("sell", guild_id, user_id, item_id, "🏪 Продать игрокам"))
                view.add_item(RoleActionButton("auction", guild_id, user_id, item_id, "🔨 На аукцион"))

            if item["role_type"] == "visual":
                view.add_item(RoleActionButton("gift", guild_id, user_id, item_id, "🎁 Подарить"))

        view.add_item(RoleActionButton("back", guild_id, user_id, item_id, "◀️ Назад в инвентарь"))

        await deliver(interaction, embed=embed, view=view)


# ===== Модальные окна =====

class SellModal(ui.Modal):
    def __init__(self, guild_id: int, user_id: int, item_id: int, item: dict):
        super().__init__(
            title="Продажа игрокам",
            custom_id=f"ram:sell:{guild_id}:{user_id}:{item_id}"
        )

        default_price = get_price(item)

        self.price_input = ui.TextInput(
            label="Цена",
            default=str(default_price) if default_price > 0 else "1",
            max_length=12,
            required=True
        )

        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction):
        _, _, raw_guild, raw_user, raw_item = self.custom_id.split(":")

        guild_id = int(raw_guild)
        user_id = int(raw_user)
        item_id = int(raw_item)

        try:
            price = int(self.price_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Цена должна быть числом.", ephemeral=True)
            return

        if price <= 0:
            await interaction.response.send_message("❌ Цена должна быть больше 0.", ephemeral=True)
            return

        item = await get_item(guild_id, user_id, item_id)

        if not item:
            await interaction.response.send_message("❌ Роль не найдена.", ephemeral=True)
            return

        if await is_locked(item_id):
            await interaction.response.send_message("🔒 Роль участвует в рынке или аукционе.", ephemeral=True)
            return

        market_price = get_price(item)
        min_price = market_price if market_price > 0 else 1

        if price < min_price:
            await interaction.response.send_message(
                f"❌ Нельзя выставить дешевле рыночной цены. Минимум: {min_price} монет.",
                ephemeral=True
            )
            return

        # defer до работы с БД и ролями — защита от 404 Unknown interaction
        await interaction.response.defer(ephemeral=True)

        await remove_role_if_applied(interaction, item)

        if item.get("is_applied"):
            await db.unapply_role(user_id, guild_id, item_id)

        await db.db.execute(
            """
            INSERT INTO market_listings (seller_id, guild_id, inventory_id, price, is_sold)
            VALUES (?, ?, ?, ?, 0)
            """,
            (user_id, guild_id, item_id, price)
        )
        await db.db.commit()

        await deliver(
            interaction,
            content=f"✅ Роль выставлена на продажу за **{price}** монет.",
            view=None
        )

        await render_inventory(interaction, guild_id, user_id)


class GiftModal(ui.Modal):
    def __init__(self, guild_id: int, user_id: int, item_id: int):
        super().__init__(
            title="Подарить роль",
            custom_id=f"ram:gift:{guild_id}:{user_id}:{item_id}"
        )

        self.recipient_input = ui.TextInput(
            label="ID или упоминание получателя",
            max_length=64,
            required=True
        )

        self.add_item(self.recipient_input)

    async def on_submit(self, interaction: discord.Interaction):
        _, _, raw_guild, raw_user, raw_item = self.custom_id.split(":")

        guild_id = int(raw_guild)
        user_id = int(raw_user)
        item_id = int(raw_item)

        raw = self.recipient_input.value.strip()

        for prefix in ("<@!", "<@"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):]

        raw = raw.rstrip(">")

        try:
            recipient_id = int(raw)
        except ValueError:
            await interaction.response.send_message("❌ Неверный ID получателя.", ephemeral=True)
            return

        if recipient_id == user_id:
            await interaction.response.send_message("❌ Нельзя подарить роль самому себе.", ephemeral=True)
            return

        member = interaction.guild.get_member(recipient_id)

        if member is None:
            try:
                member = await interaction.guild.fetch_member(recipient_id)
            except discord.HTTPException:
                await interaction.response.send_message("❌ Получатель не найден на сервере.", ephemeral=True)
                return

        # defer до работы с БД и ролями — иначе 404 Unknown interaction при долгой обработке
        await interaction.response.defer(ephemeral=True)

        item = await get_item(guild_id, user_id, item_id)

        if not item:
            await deliver(interaction, content="❌ Роль не найдена.", view=None)
            return

        if await is_locked(item_id):
            await deliver(interaction, content="🔒 Роль участвует в рынке или аукционе.", view=None)
            return

        await remove_role_if_applied(interaction, item)

        await db.db.execute(
            "UPDATE inventory SET user_id = ?, is_applied = 0 WHERE id = ?",
            (recipient_id, item_id)
        )
        await db.db.commit()

        await interaction.response.send_message(
            f"✅ Роль подарена {member.mention}.",
            ephemeral=True
        )

        await render_inventory(interaction, guild_id, user_id)


class AuctionModal(ui.Modal):
    def __init__(self, guild_id: int, user_id: int, item_id: int, item: dict):
        super().__init__(
            title="Создать аукцион",
            custom_id=f"ram:auction:{guild_id}:{user_id}:{item_id}"
        )

        default_price = get_price(item)

        self.start_price_input = ui.TextInput(
            label="Начальная цена",
            default=str(default_price) if default_price > 0 else "100",
            max_length=12,
            required=True
        )

        self.duration_input = ui.TextInput(
            label="Длительность в часах (1-24)",
            default="24",
            max_length=2,
            required=True
        )

        self.add_item(self.start_price_input)
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        _, _, raw_guild, raw_user, raw_item = self.custom_id.split(":")

        guild_id = int(raw_guild)
        user_id = int(raw_user)
        item_id = int(raw_item)

        try:
            start_price = int(self.start_price_input.value.strip())
            duration = int(self.duration_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Введи числа.", ephemeral=True)
            return

        if start_price < 0:
            await interaction.response.send_message("❌ Начальная цена не может быть отрицательной.", ephemeral=True)
            return

        if duration < 1 or duration > 24:
            await interaction.response.send_message("❌ Длительность должна быть от 1 до 24 часов.", ephemeral=True)
            return

        # defer до работы с БД и ролями — иначе 404 Unknown interaction при долгой обработке
        await interaction.response.defer(ephemeral=True)

        item = await get_item(guild_id, user_id, item_id)

        if not item:
            await deliver(interaction, content="❌ Роль не найдена.", view=None)
            return

        if await is_locked(item_id):
            await deliver(interaction, content="🔒 Роль участвует в рынке или аукционе.", view=None)
            return

        await remove_role_if_applied(interaction, item)

        if item.get("is_applied"):
            await db.unapply_role(user_id, guild_id, item_id)

        end_time = int(time.time() + duration * 3600)

        await db.db.execute(
            """
            INSERT INTO auctions (seller_id, guild_id, inventory_id, start_price, current_bid, end_time)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (user_id, guild_id, item_id, start_price, end_time)
        )
        await db.db.commit()

        price_text = "бесплатно (первая ставка от 1 монеты)" if start_price == 0 else f"**{start_price}** монет"
        await deliver(
            interaction,
            content=f"✅ Аукцион создан. Начальная цена: {price_text}.\nУправлять ставками: /auction",
            view=None
        )

        await render_inventory(interaction, guild_id, user_id)


def register(bot):
    pass