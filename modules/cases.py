# modules/cases.py
# ======================================================================
# Публичные кейсы: только просмотр наград (/case_info).
# - покупка кейсов и ключей переехала в /shop;
# - открытие кейса — из /inventory (кнопка «🔓 Открыть»);
# - администрирование кейсов — в /admin.
# ======================================================================

import discord
from discord import ui

from database import db
from .shared import get_rarity_emoji, get_rarity_name, check_cooldown, safe_command


class CaseInfoView(ui.View):
    """Выбор кейса -> embed со списком ролей и шансами редкостей."""

    def __init__(self, guild_id: int, guild: discord.Guild, cases):
        super().__init__(timeout=180)
        self.guild = guild

        options = []
        for case in cases[:25]:
            case_dict = dict(case)
            options.append(
                discord.SelectOption(
                    label=case_dict["name"][:100],
                    description=f"Редкость: {get_rarity_name(case_dict['case_rarity'])}"[:100],
                    value=str(case_dict["id"]),
                    emoji=get_rarity_emoji(case_dict["case_rarity"]),
                )
            )

        select = ui.Select(placeholder="Выбери кейс", options=options)
        select.callback = self.on_case_selected
        self.add_item(select)

    async def on_case_selected(self, interaction: discord.Interaction):
        if not self.children or not self.children[0].values:
            await interaction.response.send_message("Кейс не выбран.", ephemeral=True)
            return

        case_id = int(self.children[0].values[0])
        case = await db.get_case_details(case_id)

        if not case or case["guild_id"] != interaction.guild.id or not case["is_active"]:
            await interaction.response.edit_message(content="❌ Кейс не найден или не активен.", view=None)
            return

        lines = [f"{get_rarity_emoji(r['rarity'])} **{get_rarity_name(r['rarity'])}** — "
                 f"{r['drop_chance']}% (продажа ~{r['sell_price']:,} 💰)".replace(",", " ")
                 for r in case.get("rarities", [])]

        role_names = []
        for rarity in case.get("rarities", []):
            for role_id in rarity.get("role_ids", []):
                role = self.guild.get_role(role_id)
                if role:
                    role_names.append(f"{get_rarity_emoji(rarity['rarity'])} {role.name}")

        embed = discord.Embed(
            title=f"📦 Кейс «{case['name']}»",
            description="\n".join(lines) or "_Настроек редкостей нет_",
            color=0x00BCD4,
        )
        if role_names:
            text = "\n".join(role_names[:20])
            if len(role_names) > 20:
                text += f"\n…и ещё {len(role_names) - 20}"
            embed.add_field(name="Возможные роли", value=text, inline=False)
        embed.set_footer(text="Купить: /shop • Открыть: /inventory → вкладка 📦 Кейсы")

        await interaction.response.edit_message(embed=embed, view=self)


def register(bot):
    @bot.tree.command(name="case_info", description="Посмотреть награды и шансы кейсов")
    @safe_command
    async def case_info(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message("⏳ Подожди немного.", ephemeral=True)
            return

        cases = await db.get_all_cases(interaction.guild.id, active_only=True)

        if not cases:
            await interaction.response.send_message("Нет активных кейсов.", ephemeral=True)
            return

        await interaction.response.send_message(
            view=CaseInfoView(interaction.guild.id, interaction.guild, cases),
            ephemeral=True,
        )
