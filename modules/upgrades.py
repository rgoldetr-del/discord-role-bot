# modules/upgrades.py
# Магазин улучшений: удача, богач, прямые руки.

import discord
from discord import app_commands

from database import db
from .shared import check_cooldown


def register(bot):
    @bot.tree.command(name="shop_upgrade", description="Магазин прокачиваемых улучшений")
    async def shop_upgrade(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message("⏳ Подожди немного.", ephemeral=True)
            return

        user = await db.get_or_create_user(interaction.user.id, interaction.guild.id)

        luck_level = await db.get_upgradeable_role_level(interaction.user.id, interaction.guild.id, "luck")
        rich_level = await db.get_upgradeable_role_level(interaction.user.id, interaction.guild.id, "rich")

        next_luck_price = int(500 * (3 ** luck_level))
        next_rich_price = int(500 * (3 ** rich_level))

        straight_hands_price = user["broken_key_cost"] * 2 if user["broken_key_cost"] > 0 else 100

        embed = discord.Embed(
            title="🛒 Магазин улучшений",
            color=0x9C27B0
        )

        embed.add_field(
            name="🍀 Удача",
            value=(
                f"**Текущий уровень:** {luck_level}\n"
                f"**Следующий уровень:** {next_luck_price} монет\n"
                f"**Эффект:** +{luck_level}% к шансу выпадения ролей"
            ),
            inline=False
        )

        embed.add_field(
            name="💰 Богач",
            value=(
                f"**Текущий уровень:** {rich_level}\n"
                f"**Следующий уровень:** {next_rich_price} монет\n"
                f"**Эффект:** +{rich_level}% к монетам в мини-играх"
            ),
            inline=False
        )

        embed.add_field(
            name="🔧 Прямые руки",
            value=(
                f"**Цена:** {straight_hands_price} монет\n"
                f"**Эффект:** Снимает дебафф 'Кривая рука'"
            ),
            inline=False
        )

        embed.set_footer(text="Используй /buy_upgrade для покупки")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="buy_upgrade", description="Купить улучшение")
    @app_commands.describe(upgrade_type="Тип улучшения")
    @app_commands.choices(upgrade_type=[
        app_commands.Choice(name="Удача", value="luck"),
        app_commands.Choice(name="Богач", value="rich"),
        app_commands.Choice(name="Прямые руки", value="straight_hands"),
    ])
    async def buy_upgrade(interaction: discord.Interaction, upgrade_type: app_commands.Choice[str]):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message("⏳ Подожди немного.", ephemeral=True)
            return

        user = await db.get_or_create_user(interaction.user.id, interaction.guild.id)

        if upgrade_type.value == "luck":
            current_level = await db.get_upgradeable_role_level(interaction.user.id, interaction.guild.id, "luck")
            price = int(500 * (3 ** current_level))

            success = await db.buy_upgradeable_role(
                interaction.user.id,
                interaction.guild.id,
                "luck",
                current_level + 1,
                price
            )

            if not success:
                await interaction.response.send_message(f"❌ Недостаточно монет. Нужно: {price}", ephemeral=True)
                return

            await interaction.response.send_message(
                f"✅ Куплена **Удача lvl.{current_level + 1}** за {price} монет.",
                ephemeral=True
            )

        elif upgrade_type.value == "rich":
            current_level = await db.get_upgradeable_role_level(interaction.user.id, interaction.guild.id, "rich")
            price = int(500 * (3 ** current_level))

            success = await db.buy_upgradeable_role(
                interaction.user.id,
                interaction.guild.id,
                "rich",
                current_level + 1,
                price
            )

            if not success:
                await interaction.response.send_message(f"❌ Недостаточно монет. Нужно: {price}", ephemeral=True)
                return

            await interaction.response.send_message(
                f"✅ Куплен **Богач lvl.{current_level + 1}** за {price} монет.",
                ephemeral=True
            )

        elif upgrade_type.value == "straight_hands":
            price = user["broken_key_cost"] * 2 if user["broken_key_cost"] > 0 else 100

            has_debuff = await db.has_debuff(interaction.user.id, interaction.guild.id, "clumsy_hands")

            if not has_debuff:
                await interaction.response.send_message("❌ У тебя нет дебаффа 'Кривая рука'.", ephemeral=True)
                return

            if not await db.try_spend_coins(interaction.user.id, interaction.guild.id, price):
                await interaction.response.send_message(f"❌ Недостаточно монет. Нужно: {price}", ephemeral=True)
                return

            await db.remove_debuff(interaction.user.id, interaction.guild.id, "clumsy_hands")

            await interaction.response.send_message(
                f"✅ Куплены **Прямые руки** за {price} монет.\nДебафф 'Кривая рука' снят.",
                ephemeral=True
            )