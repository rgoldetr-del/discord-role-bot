# modules/gifts.py
# Подарки ролей.

import discord
from discord import app_commands

from database import db
from .shared import check_cooldown, safe_remove_role


def register(bot):
    @bot.tree.command(name="gift", description="Подарить роль другому игроку")
    @app_commands.describe(receiver="Получатель", inventory_id="ID роли из инвентаря")
    async def gift(interaction: discord.Interaction, receiver: discord.Member, inventory_id: int):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message("⏳ Подожди немного.", ephemeral=True)
            return

        if receiver.id == interaction.user.id:
            await interaction.response.send_message("Нельзя подарить роль самому себе.", ephemeral=True)
            return

        result = await db.gift_role(
            interaction.user.id,
            receiver.id,
            interaction.guild.id,
            inventory_id
        )

        if not result["success"]:
            await interaction.response.send_message(f"❌ {result['error']}", ephemeral=True)
            return

        if result.get("was_applied") and result.get("role_id"):
            await safe_remove_role(interaction.guild, interaction.user.id, result["role_id"])

        await interaction.response.send_message(
            f"✅ Ты подарил роль {receiver.mention}.",
            ephemeral=True
        )