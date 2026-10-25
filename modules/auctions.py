# modules/auctions.py
# Аукционы: просмотр (/auction), ставки через кнопки, авто-завершение.
# Создание аукциона — кнопкой «🔨 На аукцион» в инвентаре (role_actions.AuctionModal).
# Команда /auction_bid удалена: ставка делается кнопкой прямо из списка аукционов.

import time
import logging
from datetime import datetime

import discord
from discord import ui
from discord.ext import tasks

from database import db
from .shared import (
    check_cooldown,
    can_manage,
    get_rarity_emoji,
    get_role_name,
)

log = logging.getLogger(__name__)

# bot передаётся в register(); нужен фоновой задаче auction_loop
_active_bot = None


def fmt_time_left(end_ts: int) -> str:
    left = max(0, end_ts - int(time.time()))
    h, rem = divmod(left, 3600)
    m, _ = divmod(rem, 60)
    return f"<t:{end_ts}:R>" if left > 3600 else f"{h}ч {m}м"


class BidModal(ui.Modal, title="Сделать ставку"):
    amount = ui.TextInput(
        label="Ставка в монетах",
        placeholder="Например: 1500",
        max_length=12,
        required=True,
    )

    def __init__(self, auction_id: int):
        super().__init__()
        self.auction_id = auction_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Введи целое число монет.", ephemeral=True)
            return

        # defer до работы с БД — иначе долгий ответ вызывает 404 Unknown interaction
        await interaction.response.defer(ephemeral=True)
        result = await db.place_bid(interaction.user.id, self.auction_id, amount)

        if not result["success"]:
            await interaction.followup.send(f"❌ {result['error']}", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ Ставка **{result['bid_amount']}** монет принята!", ephemeral=True
        )
        # обновить список у всех, кто его смотрит
        try:
            await render_auctions(interaction.guild, interaction.channel)
        except Exception:
            pass


class AuctionBidButton(ui.Button):
    def __init__(self, auction_id: int):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="💰 Ставка",
            custom_id=f"auc:bid:{auction_id}",
        )
        self.auction_id = auction_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BidModal(self.auction_id))


class AuctionsView(ui.View):
    """Одна строка кнопок со ставками на первые аукционы."""

    def __init__(self, auctions):
        super().__init__(timeout=600)
        for a in auctions[:4]:
            self.add_item(AuctionBidButton(a["id"]))


async def build_auctions_payload(guild: discord.Guild):
    auctions = await db.get_active_auctions(guild.id)

    if not auctions:
        embed = discord.Embed(
            title="🔨 Активные аукционы",
            description="Пока пусто. Выстави роль из инвентаря: `/inventory` → 🔨 На аукцион.",
            color=0xFFA500,
        )
        return embed, None

    embed = discord.Embed(
        title="🔨 Активные аукционы",
        description="Жми **💰 Ставка** под нужным лотом. Шаг повышения — 100 монет.",
        color=0xFFA500,
    )
    for a in auctions[:8]:
        role_name = get_role_name(guild, a["role_id"])
        emoji = get_rarity_emoji(a["rarity"])
        current = a["current_bid"] or 0
        price_line = (
            f"**Ставка:** {current} монет" if current > 0
            else f"**Старт:** {'бесплатно' if a['start_price'] == 0 else str(a['start_price']) + ' монет'}"
        )
        seller = f"<@{a['seller_id']}>"
        embed.add_field(
            name=f"{emoji} {role_name} (ID: {a['id']})",
            value=f"{price_line}\n**До конца:** {fmt_time_left(a['end_time'])}\nПродавец: {seller}",
            inline=False,
        )
    return embed, AuctionsView(auctions)


async def render_auctions(guild: discord.Guild, channel: discord.TextChannel):
    """Обновить сообщение со списком аукционов в канале (или отправить новое)."""
    embed, view = await build_auctions_payload(guild)
    async for msg in channel.history(limit=50):
        if msg.author.id == guild.me.id and msg.embeds and \
                msg.embeds[0].title == "🔨 Активные аукционы":
            await msg.edit(embed=embed, view=view)
            return
    await channel.send(embed=embed, view=view)


async def finalize_due_auctions(bot):
    """Авто-завершение истёкших аукционов: победа/возврат + уведомления."""
    finished = await db.get_finished_auctions()
    for a in finished:
        if not await db.finalize_auction(a["id"]):
            continue
        item = await db._fetchone(
            "SELECT * FROM inventory WHERE id = ?", (a["inventory_id"],)
        )
        role_name = str(a["role_id"])
        if item:
            g = bot.get_guild(a["guild_id"])
            if g:
                r = g.get_role(item["role_id"])
                if r:
                    role_name = r.name
        guild = bot.get_guild(a["guild_id"])
        if not guild:
            continue
        if a["highest_bidder"] and a["current_bid"]:
            buyer = guild.get_member(a["highest_bidder"])
            seller = guild.get_member(a["seller_id"])
            if buyer:
                await deliver_to_user(bot, buyer, guild,
                    f"🎉 Ты выиграл аукцион **{role_name}** за **{a['current_bid']}** монет! Роль в твоём инвентаре.")
            if seller:
                await deliver_to_user(bot, seller, guild,
                    f"💸 Твой аукцион **{role_name}** продан за **{a['current_bid']}** монет.")
        elif a["seller_id"]:
            seller = guild.get_member(a["seller_id"])
            if seller:
                await deliver_to_user(bot, seller, guild,
                    f"↩️ Аукцион **{role_name}** завершился без ставок — роль вернулась в инвентарь.")


async def deliver_to_user(bot, member, guild, text):
    try:
        dm = await member.create_dm()
        await dm.send(text)
    except discord.HTTPException:
        ch = guild.text_channels and guild.text_channels[0]
        if ch:
            await ch.send(f"{member.mention} {text}", allowed_mentions=discord.AllowedMentions.none())


# Фоновая задача авто-завершения аукционов (запускается из main.py в setup_hook).
# Объявлена на уровне модуля, чтобы import auction_loop работал без вызова register().
@tasks.loop(hours=1)
async def auction_loop(bot=None):
    bot = bot or _active_bot
    if bot is None:
        return
    try:
        await finalize_due_auctions(bot)
    except Exception:
        log.warning("Ошибка авто-завершения аукционов", exc_info=True)


class AuctionRefreshButton(ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="🔄 Обновить",
                         custom_id="auc:refresh")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed, view = await build_auctions_payload(interaction.guild)
        await interaction.message.edit(embed=embed, view=view)


def register(bot):
    global _active_bot
    _active_bot = bot

    # Старая команда ставок больше не нужна — ставки делаются кнопкой.
    try:
        bot.tree.remove_command("auction_bid")
    except KeyError:
        pass

    @bot.tree.command(name="auction", description="Посмотреть активные аукционы")
    async def auction(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message("⏳ Подожди немного.", ephemeral=True)
            return

        # defer до работы с БД — иначе долгий ответ вызывает 404 Unknown interaction
        await interaction.response.defer(ephemeral=True)
        embed, view = await build_auctions_payload(interaction.guild)
        if view is None:
            view = AuctionsView([])
        view.add_item(AuctionRefreshButton())
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    
    @bot.tree.command(name="auction_finish", description="[Админ] Проверить и завершить истёкшие аукционы")
    async def auction_finish(interaction: discord.Interaction):
        if not interaction.guild or not can_manage(interaction):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        before = len(await db.get_active_auctions(interaction.guild.id))
        await finalize_due_auctions(bot)
        after = len(await db.get_active_auctions(interaction.guild.id))
        await interaction.followup.send(
            f"✅ Завершено аукционов: {before - after}. Активных осталось: {after}.",
            ephemeral=True,
        )

