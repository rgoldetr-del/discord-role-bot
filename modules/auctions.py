# modules/auctions.py
# Аукционы: просмотр, создание, ставки.

from datetime import datetime

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
    @bot.tree.command(name="auction", description="Посмотреть активные аукционы")
    async def auction(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message("⏳ Подожди немного.", ephemeral=True)
            return

        auctions = await db.get_active_auctions(interaction.guild.id)

        if not auctions:
            await interaction.response.send_message("🔨 Нет активных аукционов.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔨 Активные аукционы",
            description="Используй `/auction_bid auction_id:X amount:Y` для ставки.",
            color=0xFFA500
        )

        now = datetime.now()

        for auction_item in auctions[:10]:
            role_name = get_role_name(interaction.guild, auction_item["role_id"])
            emoji = get_rarity_emoji(auction_item["rarity"])

            end_time = datetime.fromtimestamp(auction_item["end_time"])
            time_left = max(0, int((end_time - now).total_seconds()))

            hours, remainder = divmod(time_left, 3600)
            minutes, _ = divmod(remainder, 60)

            current_bid = auction_item["current_bid"] if auction_item["current_bid"] > 0 else auction_item["start_price"]

            embed.add_field(
                name=f"{emoji} {role_name} (ID: {auction_item['id']})",
                value=f"**Текущая ставка:** {current_bid} монет\n**Осталось:** {hours}ч {minutes}м",
                inline=True
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="auction_create", description="Создать аукцион")
    @app_commands.describe(
        inventory_id="ID роли из инвентаря",
        start_price="Начальная цена",
        duration_hours="Длительность в часах (макс 24)"
    )
    async def auction_create(
        interaction: discord.Interaction,
        inventory_id: int,
        start_price: int,
        duration_hours: int = 24
    ):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        result = await db.create_auction(
            interaction.user.id,
            interaction.guild.id,
            inventory_id,
            start_price,
            duration_hours
        )

        if not result["success"]:
            await interaction.response.send_message(f"❌ {result['error']}", ephemeral=True)
            return

        if result.get("was_applied") and result.get("role_id"):
            await safe_remove_role(interaction.guild, interaction.user.id, result["role_id"])

        await interaction.response.send_message(
            f"✅ Аукцион создан.\n"
            f"ID аукциона: `{result['auction_id']}`\n"
            f"Начальная цена: {start_price} монет\n"
            f"Длительность: {duration_hours} часов",
            ephemeral=True
        )

    @bot.tree.command(name="auction_bid", description="Сделать ставку на аукционе")
    @app_commands.describe(auction_id="ID аукциона", amount="Ставка в монетах")
    async def auction_bid(interaction: discord.Interaction, auction_id: int, amount: int):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message("⏳ Подожди немного.", ephemeral=True)
            return

        result = await db.place_bid(interaction.user.id, auction_id, amount)

        if not result["success"]:
            await interaction.response.send_message(f"❌ {result['error']}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"✅ Ставка **{result['bid_amount']}** монет принята.",
            ephemeral=True
        )