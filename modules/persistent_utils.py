# modules/persistent_utils.py
# Мини-утилиты для persistent view и генерации custom_id.

import discord


def make_id(*parts) -> str:
    return "pw2:" + ":".join(str(part) for part in parts)


def id_parts(custom_id: str):
    return custom_id.split(":")[2:]


def can_manage(interaction: discord.Interaction) -> bool:
    """Владелец сервера или администратор."""
    if not interaction.guild:
        return False

    if interaction.user.id == interaction.guild.owner_id:
        return True

    try:
        return interaction.user.guild_permissions.administrator
    except Exception:
        return False


async def edit_view(interaction: discord.Interaction, content=None, embed=None, view=None):
    """Безопасное редактирование ответа (после defer)."""
    try:
        await interaction.edit_original_response(content=content, embed=embed, view=view)
    except discord.HTTPException:
        pass
