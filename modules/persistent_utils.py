# modules/persistent_utils.py

import discord


def make_id(*parts) -> str:
    return "pw2:" + ":".join(str(part) for part in parts)


def id_parts(custom_id: str):
    return custom_id.split(":")[2:]


def can_manage(interaction: discord.Interaction) -> bool:
    if not interaction.guild:
        return False

    if interaction.user.id == interaction.guild.owner_id:
        return True

    try:
        return interaction.user.guild_permissions.administrator
    except Exception:
        return False


async def notify(interaction: discord.Interaction, text: str):
    try:
        if interaction.response.is_done():
            await interaction.followup.send(text, ephemeral=True)
        else:
            await interaction.response.send_message(text, ephemeral=True)
    except discord.HTTPException:
        pass


async def edit_view(
    interaction: discord.Interaction,
    *,
    content=None,
    embed=None,
    view=None
):
    try:
        if interaction.response.is_done():
            await interaction.edit_original_response(
                content=content, embed=embed, view=view
            )
        else:
            await interaction.response.edit_message(
                content=content, embed=embed, view=view
            )
    except discord.HTTPException:
        pass


async def defer(interaction: discord.Interaction):
    try:
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
    except discord.HTTPException:
        pass


RARITY_EMOJI = {
    "common": "⚪", "uncommon": "🟢", "rare": "🔵", "epic": "🟣",
    "legendary": "🟡", "secret": "🔴", "secret+": "⚫"
}

RARITY_NAME = {
    "common": "Обычная", "uncommon": "Необычная", "rare": "Редкая",
    "epic": "Эпическая", "legendary": "Легендарная",
    "secret": "Секретная", "secret+": "Абсолютная"
}

FALLBACK_PRICES = {
    "common": 200, "uncommon": 800, "rare": 2000, "epic": 5000,
    "legendary": 15000, "secret": 50000, "secret+": 200000
}


def role_label(guild, item: dict) -> str:
    if item.get("role_type") == "upgradeable":
        names = {"luck": "Удача", "rich": "Богач"}
        return f"{names.get(item.get('rarity'), item.get('rarity'))} lvl.{item.get('level', 1)}"

    if item.get("role_type") == "debuff":
        return "💀 Кривая рука"

    if item.get("role_type") == "effect":
        names = {
            "shield": "🛡️ Щит", "discount": "🏷️ Скидка",
            "income": "💼 Доход", "critic": "⚡ Критик",
            "crystal_guard": "💎 Хранитель", "high_roller": "🔥 Азарт"
        }
        return names.get(item.get("rarity"), "✨ Эффект")

    role = guild.get_role(item.get("role_id"))
    return role.name if role else f"Роль {item.get('role_id')}"


async def rows_to_dicts(rows):
    return [dict(row) for row in rows]