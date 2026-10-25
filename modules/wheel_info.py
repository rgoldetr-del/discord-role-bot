# modules/wheel_info.py
# Просмотр наград колеса.

import discord

from .shared import get_rarity_name


def register(bot):
    @bot.tree.command(name="wheel_info", description="Посмотреть награды почасового колеса")
    async def wheel_info(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎡 Награды почасового колеса",
            description=(
                "Колесо можно крутить раз в час.\n"
                "После 10 пустых результатов гарантируется редкий ключ.\n\n"
                "Ключи всегда показывают редкость кейса, который они открывают."
            ),
            color=0x9C27B0
        )

        embed.add_field(
            name="Основные награды",
            value=(
                "💨 30% — пусто\n"
                "🔑 15% — 1 обычный ключ\n"
                "💰 8% — 50 монет\n"
                "💰 7% — 100 монет\n"
                "🔑 6% — 2 обычных ключа\n"
                "💎 6% — 1 кристалл"
            ),
            inline=False
        )

        embed.add_field(
            name="Редкие награды",
            value=(
                "🔑 5% — 1 редкий ключ\n"
                "💰 4% — 200 монет\n"
                "🔑 3.5% — 3 обычных ключа\n"
                "💎 3% — 2 кристалла\n"
                "💰 2.5% — 300 монет\n"
                "🔑 2% — 2 редких ключа"
            ),
            inline=False
        )

        embed.add_field(
            name="Очень редкие награды",
            value=(
                "📦 2% — бесплатный кейс\n"
                "💎 1.5% — 3 кристалла\n"
                "💰 1% — 500 монет\n"
                "🔑 1% — 1 эпический ключ\n"
                "💎 0.8% — 5 кристаллов\n"
                "💰 0.5% — 1000 монет"
            ),
            inline=False
        )

        embed.add_field(
            name="Редчайшие награды",
            value=(
                "🔑 0.4% — 2 эпических ключа\n"
                "💎 0.3% — 10 кристаллов\n"
                "💰 0.5% — 2000 монет"
            ),
            inline=False
        )

        embed.set_footer(text="Кейсы и ключи можно использовать в /case_open")

        await interaction.response.send_message(embed=embed, ephemeral=True)