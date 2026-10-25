# modules/case_shop_fix.py

import discord


def register(bot):
    try:
        bot.tree.remove_command("case_shop")
    except Exception:
        pass

    @bot.tree.command(name="case_shop", description="Открыть магазин кейсов")
    async def case_shop(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        view = None

        try:
            from modules import cases as cases_module

            view_cls = getattr(cases_module, "CaseShopView", None)

            if view_cls is None:
                view_cls = getattr(cases_module, "CaseShopV2View", None)

            if view_cls is not None:
                try:
                    view = view_cls(interaction.user.id, interaction.guild.id)
                except TypeError:
                    try:
                        view = view_cls(interaction.user.id, interaction.guild.id, interaction.guild)
                    except TypeError:
                        view = view_cls()
        except Exception:
            view = None

        embed = discord.Embed(
            title="🏪 Магазин кейсов",
            description="Выбери действие:",
            color=0xFFD700
        )

        if view is None:
            await interaction.followup.send(
                "❌ Не удалось загрузить магазин кейсов. Проверь `modules/cases.py`.",
                ephemeral=True
            )
            return

        await interaction.followup.send(embed=embed, view=view, ephemeral=True)