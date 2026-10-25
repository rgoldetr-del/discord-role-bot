# modules/inventory.py

import discord
from discord import ui

from database import db
from .persistent_utils import (
    make_id, id_parts, notify, edit_view, defer,
    RARITY_EMOJI, role_label
)


class InvItemButton(ui.Button):
    def __init__(self, guild_id: int, user_id: int, item_id: int, label: str):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label=label[:80],
            custom_id=make_id("inv", "item", guild_id, user_id, item_id)
        )

    async def callback(self, interaction: discord.Interaction):
        _, gid, uid, item_id = id_parts(self.custom_id)

        if interaction.user.id != int(uid):
            await notify(interaction, "❌ Это не твой инвентарь.")
            return

        from .role_actions import RoleActionView

        await defer(interaction)
        view = RoleActionView()
        await view.render(interaction, int(gid), int(uid), int(item_id))


class InvPageButton(ui.Button):
    def __init__(self, guild_id: int, user_id: int, page: int, direction: str):
        self.direction = direction
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="◀️ Назад" if direction == "prev" else "Вперёд ▶️",
            custom_id=make_id("inv", "page", guild_id, user_id, page, direction)
        )

    async def callback(self, interaction: discord.Interaction):
        _, gid, uid, page, direction = id_parts(self.custom_id)

        if interaction.user.id != int(uid):
            await notify(interaction, "❌ Это не твой инвентарь.")
            return

        new_page = max(0, int(page) + (-1 if direction == "prev" else 1))

        await defer(interaction)
        view = InventoryView()
        await view.render(interaction, int(gid), int(uid), new_page)


class InventoryView(ui.View):
    __discord_ui_view__ = True

    def __init__(self, user_id=None, guild_id=None, guild=None, page=0):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.guild_id = guild_id
        self.guild = guild
        self.page = page

    async def render(self, interaction, guild_id: int, user_id: int, page: int = 0):
        guild = interaction.guild
        if guild is None:
            await notify(interaction, "❌ Только на сервере.")
            return

        rows = await db.get_user_inventory(user_id, guild_id)
        items = [dict(row) for row in rows]

        per_page = 8
        pages = max(1, (len(items) + per_page - 1) // per_page)
        page = max(0, min(page, pages - 1))

        try:
            effects = await db.get_player_effects(user_id, guild_id)
        except Exception:
            effects = {"coins": 0, "crystals": 0, "luck": 0, "rich": 0, "clumsy_hands": False}

        embed = discord.Embed(
            title=f"🎒 Инвентарь {interaction.user.display_name}",
            color=0x00BCD4
        )

        embed.add_field(
            name="💰 Баланс",
            value=f"Монеты: **{effects['coins']}**\nКристаллы: **{effects['crystals']}**",
            inline=False
        )

        buffs = []
        if effects.get("luck", 0) > 0:
            buffs.append(f"🍀 Удача lvl.{effects['luck']}")
        if effects.get("rich", 0) > 0:
            buffs.append(f"💎 Богач lvl.{effects['rich']}")

        try:
            extra = await db.get_user_effects(user_id, guild_id)
            buffs.extend(extra)
        except Exception:
            pass

        embed.add_field(name="✨ Бафы", value="\n".join(buffs) or "Нет", inline=True)
        debuff = "💀 Кривая рука" if effects.get("clumsy_hands") else "Нет"
        embed.add_field(name="☠️ Дебафы", value=debuff, inline=True)

        view = InventoryView(user_id, guild_id, guild, page)

        if not items:
            embed.description = "Инвентарь пуст."
            await edit_view(interaction, embed=embed, view=view)
            return

        start = page * per_page
        for item in items[start:start + per_page]:
            emoji = RARITY_EMOJI.get(item.get("rarity"), "⚪")
            status = "✅" if item.get("is_applied") else "⏸️"
            label = f"{status} {emoji} {role_label(guild, item)}"
            view.add_item(InvItemButton(guild_id, user_id, item["id"], label))

        if pages > 1:
            if page > 0:
                view.add_item(InvPageButton(guild_id, user_id, page, "prev"))
            if page < pages - 1:
                view.add_item(InvPageButton(guild_id, user_id, page, "next"))

        embed.set_footer(text=f"Страница {page + 1}/{pages} · Нажми на роль для действий")
        await edit_view(interaction, embed=embed, view=view)


def register(bot):
    @bot.tree.command(name="inventory", description="Инвентарь, баланс, бафы и дебафы")
    async def inventory(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        view = InventoryView()
        await view.render(interaction, interaction.guild.id, interaction.user.id, 0)