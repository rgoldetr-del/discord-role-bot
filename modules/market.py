# modules/market.py
# Маркетплейс: просмотр, продажа, покупка, отмена.

import discord
from discord import app_commands

from database import db
from .shared import (
    check_cooldown,
    safe_remove_role,
    get_rarity_emoji,
    get_role_name
)


def register(bot):
    @bot.tree.command(name="market", description="Посмотреть маркетплейс")
    async def market(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message("⏳ Подожди немного.", ephemeral=True)
            return

        listings = await db.get_market_listings(interaction.guild.id)

        if not listings:
            await interaction.response.send_message("🏪 Маркетплейс пуст.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🏪 Маркетплейс ролей",
            description="Используй `/market_sell` или инвентарь, чтобы продать.\n`/market_buy listing_id:X` — купить.",
            color=0x00FF00
        )

        for listing in listings[:10]:
            role_name = get_role_name(interaction.guild, listing["role_id"])
            emoji = get_rarity_emoji(listing["rarity"])

            seller = interaction.guild.get_member(listing["seller_id"])
            seller_name = seller.display_name if seller else f"ID:{listing['seller_id']}"

            embed.add_field(
                name=f"{emoji} {role_name} (ID лота: {listing['id']})",
                value=f"**Продавец:** {seller_name}\n**Цена:** {listing['price']} монет",
                inline=True
            )

        if len(listings) > 10:
            embed.set_footer(text=f"... и ещё {len(listings) - 10} лотов")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="market_sell", description="Выставить роль на продажу")
    @app_commands.describe(inventory_id="ID роли из инвентаря", price="Цена в монетах")
    async def market_sell(interaction: discord.Interaction, inventory_id: int, price: int):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message("⏳ Подожди немного.", ephemeral=True)
            return

        result = await db.list_role_for_sale(
            interaction.user.id,
            interaction.guild.id,
            inventory_id,
            price
        )

        if not result["success"]:
            await interaction.response.send_message(f"❌ {result['error']}", ephemeral=True)
            return

        if result.get("was_applied") and result.get("role_id"):
            await safe_remove_role(interaction.guild, interaction.user.id, result["role_id"])

        await interaction.response.send_message(
            f"✅ Роль выставлена на продажу за **{price}** монет.\nКомиссия сервера: 5%",
            ephemeral=True
        )

    @bot.tree.command(name="market_buy", description="Купить роль с маркетплейса")
    @app_commands.describe(listing_id="ID лота")
    async def market_buy(interaction: discord.Interaction, listing_id: int):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message("⏳ Подожди немного.", ephemeral=True)
            return

        result = await db.buy_from_market(interaction.user.id, listing_id)

        if not result["success"]:
            await interaction.response.send_message(f"❌ {result['error']}", ephemeral=True)
            return

        if result.get("was_applied") and result.get("role_id"):
            await safe_remove_role(
                interaction.guild,
                result["listing"]["seller_id"],
                result["role_id"]
            )

        role_name = get_role_name(interaction.guild, result["role_id"])

        await interaction.response.send_message(
            f"✅ Ты купил роль **{role_name}** за **{result['listing']['price']}** монет.\n"
            f"Комиссия: {result['commission']} монет",
            ephemeral=True
        )

    @bot.tree.command(name="market_cancel", description="Отменить продажу роли")
    @app_commands.describe(listing_id="ID лота")
    async def market_cancel(interaction: discord.Interaction, listing_id: int):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        success = await db.cancel_market_listing(interaction.user.id, listing_id)

        if not success:
            await interaction.response.send_message("❌ Лот не найден или уже продан.", ephemeral=True)
            return

        await interaction.response.send_message(
            "✅ Лот отменён. Роль возвращена в инвентарь.",
            ephemeral=True
        )