# modules/minigames.py
# Обновлённые мини-игры:
# - ставки монетами и кристаллами одновременно;
# - смешанные выплаты;
# - лёгкие интерфейсы на кнопках.

import random
import uuid

import discord
from discord import ui

from database import db
from .shared import (
from .shop import _safe_send
    BET_VALUE_EQUIV,
    mixed_value,
    try_spend_mixed,
    award_mixed,
    award_mixed_win,
    format_bet,
    format_reward
)

MIN_BET_VALUE = 10
MAX_BET_VALUE = 25000


async def allowed_max_value(interaction: discord.Interaction) -> int:
    try:
        db_max = await db.get_max_bet(interaction.user.id, interaction.guild.id)
    except Exception:
        db_max = 1000

    user = await db.get_or_create_user(interaction.user.id, interaction.guild.id)

    crystal_value = user["crystals"] * BET_VALUE_EQUIV

    return min(
        MAX_BET_VALUE,
        max(MIN_BET_VALUE, int(db_max) + int(crystal_value))
    )


def draw_card() -> int:
    return random.randint(1, 13)


def draw_cards(count: int):
    return [draw_card() for _ in range(count)]


def card_name(card: int) -> str:
    if card == 1:
        return "A"
    if card == 11:
        return "J"
    if card == 12:
        return "Q"
    if card == 13:
        return "K"
    return str(card)


def hand_value(hand):
    total = 0
    aces = 0

    for card in hand:
        if card == 1:
            total += 11
            aces += 1
        else:
            total += min(10, card)

    while total > 21 and aces > 0:
        total -= 10
        aces -= 1

    return total


def format_hand(hand):
    return ", ".join(card_name(card) for card in hand)


class BetModal(ui.Modal, title="Ставка"):
    coins_input = ui.TextInput(
        label="Монеты",
        placeholder="Например: 100",
        default="0",
        max_length=10,
        required=True,
        custom_id="bet_coins_input"
    )

    crystals_input = ui.TextInput(
        label="Кристаллы",
        placeholder="Например: 10",
        default="0",
        max_length=10,
        required=True,
        custom_id="bet_crystals_input"
    )

    def __init__(self, action: str):
        super().__init__(custom_id=f"bet_modal_{uuid.uuid4().hex[:8]}")
        self.action = action

    async def on_submit(self, interaction: discord.Interaction):
        try:
            coins = int(self.coins_input.value.strip() or "0")
            crystals = int(self.crystals_input.value.strip() or "0")
        except ValueError:
            await interaction.response.send_message("❌ Введи числа.", ephemeral=True)
            return

        if coins < 0 or crystals < 0:
            await interaction.response.send_message("❌ Ставка не может быть отрицательной.", ephemeral=True)
            return

        total_value = mixed_value(coins, crystals)

        if total_value < MIN_BET_VALUE:
            await interaction.response.send_message(
                f"❌ Минимальная ставка: {format_bet(MIN_BET_VALUE, 0)} (или эквивалент).",
                ephemeral=True
            )
            return

        max_value = await allowed_max_value(interaction)

        if total_value > max_value:
            await interaction.response.send_message(
                f"❌ Твоя максимальная ставка сейчас: {format_bet(max_value, 0)}.",
                ephemeral=True
            )
            return

        if self.action == "blackjack":
            await start_blackjack(interaction, coins, crystals)
            return

        if self.action == "mines":
            await start_mines(interaction, coins, crystals)
            return

        if self.action.startswith("roulette_"):
            color = self.action.split("_", 1)[1]
            await play_roulette(interaction, color, coins, crystals)
            return

        if self.action.startswith("dice_"):
            choice = self.action.split("_", 1)[1]
            await play_dice(interaction, choice, coins, crystals)
            return

        if self.action.startswith("coin_"):
            choice = self.action.split("_", 1)[1]
            await play_coin(interaction, choice, coins, crystals)
            return

        if self.action == "pvp_rps":
            await create_pvp_rps(interaction, coins, crystals)
            return

        if self.action == "pvp_blackjack":
            await create_pvp_blackjack(interaction, coins, crystals)
            return

        await interaction.response.send_message("❌ Неизвестная игра.", ephemeral=True)


class GamesMenuView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id

        games = [
            ("🃏 Блэкджек", "blackjack"),
            ("🎡 Рулетка", "roulette"),
            ("🎲 Кости", "dice"),
            ("🪙 Монетка", "coin"),
            ("💣 Мины", "mines"),
            ("✊ PvP КНБ", "pvp_rps"),
            ("🃏 PvP Блэкджек", "pvp_blackjack"),
        ]

        for label, game in games:
            button = ui.Button(
                style=discord.ButtonStyle.primary,
                label=label,
                custom_id=f"game_{game}_{uuid.uuid4().hex[:6]}"
            )
            button.callback = self.make_callback(game)
            self.add_item(button)

    def make_callback(self, game: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Это не для тебя.", ephemeral=True)
                return

            if game in ("blackjack", "mines", "pvp_rps", "pvp_blackjack"):
                await interaction.response.send_modal(BetModal(game))
                return

            if game == "roulette":
                view = RouletteView(self.user_id)
                await interaction.response.send_message(
                    "Выбери цвет. После нажатия нужно ввести ставку.",
                    view=view,
                    ephemeral=True
                )
                return

            if game == "dice":
                view = DiceView(self.user_id)
                await interaction.response.send_message(
                    "Больше или меньше 50? После нажатия нужно ввести ставку.",
                    view=view,
                    ephemeral=True
                )
                return

            if game == "coin":
                view = CoinView(self.user_id)
                await interaction.response.send_message(
                    "Орёл или решка? После нажатия нужно ввести ставку.",
                    view=view,
                    ephemeral=True
                )
                return

        return callback


class RouletteView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

        options = [
            ("🔴 Красное", "roulette_red", discord.ButtonStyle.danger),
            ("⚫ Чёрное", "roulette_black", discord.ButtonStyle.secondary),
            ("🟢 Зелёное", "roulette_green", discord.ButtonStyle.success),
        ]

        for label, action, style in options:
            button = ui.Button(
                style=style,
                label=label,
                custom_id=f"roulette_{uuid.uuid4().hex[:6]}"
            )
            button.callback = self.make_callback(action)
            self.add_item(button)

    def make_callback(self, action: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Это не для тебя.", ephemeral=True)
                return

            await interaction.response.send_modal(BetModal(action))

        return callback


class DiceView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

        high = ui.Button(
            style=discord.ButtonStyle.primary,
            label="📈 Больше 50",
            custom_id=f"dice_high_{uuid.uuid4().hex[:6]}"
        )
        high.callback = self.make_callback("dice_high")
        self.add_item(high)

        low = ui.Button(
            style=discord.ButtonStyle.primary,
            label="📉 Меньше 50",
            custom_id=f"dice_low_{uuid.uuid4().hex[:6]}"
        )
        low.callback = self.make_callback("dice_low")
        self.add_item(low)

    def make_callback(self, action: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Это не для тебя.", ephemeral=True)
                return

            await interaction.response.send_modal(BetModal(action))

        return callback


class CoinView(ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id

        heads = ui.Button(
            style=discord.ButtonStyle.primary,
            label="🪙 Орёл",
            custom_id=f"coin_heads_{uuid.uuid4().hex[:6]}"
        )
        heads.callback = self.make_callback("coin_heads")
        self.add_item(heads)

        tails = ui.Button(
            style=discord.ButtonStyle.secondary,
            label="🌀 Решка",
            custom_id=f"coin_tails_{uuid.uuid4().hex[:6]}"
        )
        tails.callback = self.make_callback("coin_tails")
        self.add_item(tails)

    def make_callback(self, action: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Это не для тебя.", ephemeral=True)
                return

            await interaction.response.send_modal(BetModal(action))

        return callback


async def play_roulette(interaction: discord.Interaction, color: str, bet_coins: int, bet_crystals: int):
    if not await try_spend_mixed(interaction.user.id, interaction.guild.id, bet_coins, bet_crystals):
        await interaction.response.send_message("❌ Недостаточно средств.", ephemeral=True)
        return

    number = random.randint(0, 36)
    red_numbers = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}

    if number == 0:
        result_color = "green"
    elif number in red_numbers:
        result_color = "red"
    else:
        result_color = "black"

    color_names = {
        "red": "🔴 красное",
        "black": "⚫ чёрное",
        "green": "🟢 зелёное"
    }

    if result_color == color:
        multiplier = 36 if color == "green" else 2
        payout_coins, payout_crystals, bonus = await award_mixed_win(
            interaction.user.id,
            interaction.guild.id,
            bet_coins,
            bet_crystals,
            multiplier
        )

        text = (
            f"Выпало **{number}** {color_names[result_color]}.\n"
            f"✅ Выигрыш: **{format_reward(payout_coins, payout_crystals)}**."
        )

        if bonus > 0:
            text += f"\n💎 Бонус Богача: +{bonus} ценности."
    else:
        text = (
            f"Выпало **{number}** {color_names[result_color]}.\n"
            f"❌ Проигрыш: **{format_bet(bet_coins, bet_crystals)}**."
        )

    await interaction.response.send_message(text, ephemeral=True)


async def play_dice(interaction: discord.Interaction, choice: str, bet_coins: int, bet_crystals: int):
    if not await try_spend_mixed(interaction.user.id, interaction.guild.id, bet_coins, bet_crystals):
        await interaction.response.send_message("❌ Недостаточно средств.", ephemeral=True)
        return

    roll = random.randint(1, 100)
    win = False

    if choice == "high" and roll > 50:
        win = True

    if choice == "low" and roll < 50:
        win = True

    if win:
        payout_coins, payout_crystals, bonus = await award_mixed_win(
            interaction.user.id,
            interaction.guild.id,
            bet_coins,
            bet_crystals,
            1.95
        )

        text = (
            f"🎲 Выпало: **{roll}**\n"
            f"✅ Выигрыш: **{format_reward(payout_coins, payout_crystals)}**."
        )

        if bonus > 0:
            text += f"\n💎 Бонус Богача: +{bonus} ценности."
    else:
        text = (
            f"🎲 Выпало: **{roll}**\n"
            f"❌ Проигрыш: **{format_bet(bet_coins, bet_crystals)}**."
        )

    await interaction.response.send_message(text, ephemeral=True)


async def play_coin(interaction: discord.Interaction, choice: str, bet_coins: int, bet_crystals: int):
    if not await try_spend_mixed(interaction.user.id, interaction.guild.id, bet_coins, bet_crystals):
        await interaction.response.send_message("❌ Недостаточно средств.", ephemeral=True)
        return

    result = "heads" if random.random() < 0.5 else "tails"

    if result == choice:
        payout_coins, payout_crystals, bonus = await award_mixed_win(
            interaction.user.id,
            interaction.guild.id,
            bet_coins,
            bet_crystals,
            1.95
        )

        result_name = "Орёл" if result == "heads" else "Решка"

        text = (
            f"🪙 Выпало: **{result_name}**\n"
            f"✅ Выигрыш: **{format_reward(payout_coins, payout_crystals)}**."
        )

        if bonus > 0:
            text += f"\n💎 Бонус Богача: +{bonus} ценности."
    else:
        result_name = "Орёл" if result == "heads" else "Решка"

        text = (
            f"🪙 Выпало: **{result_name}**\n"
            f"❌ Проигрыш: **{format_bet(bet_coins, bet_crystals)}**."
        )

    await interaction.response.send_message(text, ephemeral=True)


class BlackjackView(ui.View):
    def __init__(self, user_id: int, guild_id: int, bet_coins: int, bet_crystals: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.bet_coins = bet_coins
        self.bet_crystals = bet_crystals
        self.player_hand = draw_cards(2)
        self.dealer_hand = draw_cards(2)
        self.finished = False

        hit = ui.Button(
            style=discord.ButtonStyle.primary,
            label="➕ Ещё",
            custom_id=f"bj_hit_{uuid.uuid4().hex[:6]}"
        )
        hit.callback = self.hit_callback
        self.add_item(hit)

        stand = ui.Button(
            style=discord.ButtonStyle.success,
            label="✋ Хватит",
            custom_id=f"bj_stand_{uuid.uuid4().hex[:6]}"
        )
        stand.callback = self.stand_callback
        self.add_item(stand)

    async def _edit(self, interaction: discord.Interaction, embed: discord.Embed):
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    def make_embed(self):
        embed = discord.Embed(title="🃏 Блэкджек", color=0x00BCD4)

        embed.add_field(
            name=f"Твои карты: {hand_value(self.player_hand)}",
            value=format_hand(self.player_hand),
            inline=False
        )

        if self.finished:
            embed.add_field(
                name=f"Карты дилера: {hand_value(self.dealer_hand)}",
                value=format_hand(self.dealer_hand),
                inline=False
            )
        else:
            embed.add_field(
                name="Карты дилера",
                value=f"{card_name(self.dealer_hand[0])}, ❔",
                inline=False
            )

        embed.set_footer(text=f"Ставка: {format_bet(self.bet_coins, self.bet_crystals)}")
        return embed

    async def hit_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не твоя игра.", ephemeral=True)
            return

        if self.finished:
            await self._edit(interaction, self.make_embed())
            return

        self.player_hand.append(draw_card())

        if hand_value(self.player_hand) > 21:
            await self.finish(interaction, "bust")
            return

        await self._edit(interaction, self.make_embed())

    async def stand_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не твоя игра.", ephemeral=True)
            return

        if self.finished:
            await self._edit(interaction, self.make_embed())
            return

        await self.finish(interaction, "stand")

    async def finish(self, interaction: discord.Interaction, reason: str):
        if self.finished:
            return

        self.finished = True
        self.clear_items()

        player_value = hand_value(self.player_hand)

        if reason == "bust":
            embed = self.make_embed()
            embed.description = f"💥 Перебор! Проигрыш: **{format_bet(self.bet_coins, self.bet_crystals)}**."
            await self._edit(interaction, embed)
            return

        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(draw_card())

        dealer_value = hand_value(self.dealer_hand)

        if dealer_value > 21 or player_value > dealer_value:
            multiplier = 2.5 if player_value == 21 and len(self.player_hand) == 2 else 2

            payout_coins, payout_crystals, bonus = await award_mixed_win(
                self.user_id,
                self.guild_id,
                self.bet_coins,
                self.bet_crystals,
                multiplier
            )

            embed = self.make_embed()
            embed.description = f"🏆 Победа! Выигрыш: **{format_reward(payout_coins, payout_crystals)}**."

            if bonus > 0:
                embed.description += f"\n💎 Бонус Богача: +{bonus} ценности."

        elif player_value == dealer_value:
            await award_mixed(self.user_id, self.guild_id, self.bet_coins, self.bet_crystals)

            embed = self.make_embed()
            embed.description = "🤝 Ничья. Ставка возвращена."
        else:
            embed = self.make_embed()
            embed.description = f"❌ Дилер сильнее. Проигрыш: **{format_bet(self.bet_coins, self.bet_crystals)}**."

        await self._edit(interaction, embed)


async def start_blackjack(interaction: discord.Interaction, bet_coins: int, bet_crystals: int):
    if not await try_spend_mixed(interaction.user.id, interaction.guild.id, bet_coins, bet_crystals):
        await interaction.response.send_message("❌ Недостаточно средств.", ephemeral=True)
        return

    view = BlackjackView(interaction.user.id, interaction.guild.id, bet_coins, bet_crystals)
    await interaction.response.send_message(embed=view.make_embed(), view=view, ephemeral=True)


class MinesView(ui.View):
    def __init__(self, user_id: int, guild_id: int, bet_coins: int, bet_crystals: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.guild_id = guild_id
        self.bet_coins = bet_coins
        self.bet_crystals = bet_crystals
        self.bombs = set(random.sample(range(9), 3))
        self.revealed = set()
        self.active = True

        self.refresh_buttons()

    def multiplier(self):
        return round(1 + len(self.revealed) * 0.25, 2)

    def refresh_buttons(self):
        self.clear_items()

        for i in range(9):
            if i in self.revealed:
                label = "💎"
                disabled = True
            elif not self.active and i in self.bombs:
                label = "💣"
                disabled = True
            else:
                label = "❔"
                disabled = not self.active

            button = ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                disabled=disabled,
                custom_id=f"mine_{i}_{uuid.uuid4().hex[:6]}"
            )
            button.callback = self.make_cell_callback(i)
            self.add_item(button)

        if self.active:
            cashout = ui.Button(
                style=discord.ButtonStyle.success,
                label=f"💰 Забрать x{self.multiplier()}",
                disabled=len(self.revealed) == 0,
                custom_id=f"mine_cashout_{uuid.uuid4().hex[:6]}"
            )
            cashout.callback = self.cashout_callback
            self.add_item(cashout)

    def make_embed(self):
        embed = discord.Embed(title="💣 Мины", color=0x00BCD4)
        embed.description = (
            f"Открыто безопасных клеток: **{len(self.revealed)}**\n"
            f"Текущий множитель: **x{self.multiplier()}**"
        )
        embed.set_footer(text=f"Ставка: {format_bet(self.bet_coins, self.bet_crystals)}")
        return embed

    async def _edit(self, interaction: discord.Interaction, embed: discord.Embed):
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    def make_cell_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Это не твоя игра.", ephemeral=True)
                return

            if not self.active or index in self.revealed:
                await self._edit(interaction, self.make_embed())
                return

            if index in self.bombs:
                self.active = False
                self.refresh_buttons()

                embed = self.make_embed()
                embed.description = f"💥 Бум! Проигрыш: **{format_bet(self.bet_coins, self.bet_crystals)}**."
                await self._edit(interaction, embed)
                return

            self.revealed.add(index)

            if len(self.revealed) >= 6:
                await self.cashout(interaction, auto=True)
                return

            self.refresh_buttons()
            await self._edit(interaction, self.make_embed())

        return callback

    async def cashout_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не твоя игра.", ephemeral=True)
            return

        if len(self.revealed) == 0:
            await interaction.response.send_message("Сначала открой хотя бы одну клетку.", ephemeral=True)
            return

        await self.cashout(interaction, auto=False)

    async def cashout(self, interaction: discord.Interaction, auto: bool):
        if not self.active:
            return

        self.active = False

        payout_coins, payout_crystals, bonus = await award_mixed_win(
            self.user_id,
            self.guild_id,
            self.bet_coins,
            self.bet_crystals,
            self.multiplier()
        )

        self.refresh_buttons()

        embed = self.make_embed()
        embed.description = f"✅ Забрано: **{format_reward(payout_coins, payout_crystals)}**."

        if auto:
            embed.description += "\n🎉 Все безопасные клетки открыты!"

        if bonus > 0:
            embed.description += f"\n💎 Бонус Богача: +{bonus} ценности."

        await self._edit(interaction, embed)


async def start_mines(interaction: discord.Interaction, bet_coins: int, bet_crystals: int):
    if not await try_spend_mixed(interaction.user.id, interaction.guild.id, bet_coins, bet_crystals):
        await interaction.response.send_message("❌ Недостаточно средств.", ephemeral=True)
        return

    view = MinesView(interaction.user.id, interaction.guild.id, bet_coins, bet_crystals)
    await interaction.response.send_message(embed=view.make_embed(), view=view, ephemeral=True)


class RPSInviteView(ui.View):
    def __init__(self, creator_id: int, guild_id: int, bet_coins: int, bet_crystals: int):
        super().__init__(timeout=180)
        self.creator_id = creator_id
        self.guild_id = guild_id
        self.bet_coins = bet_coins
        self.bet_crystals = bet_crystals

        join = ui.Button(
            style=discord.ButtonStyle.success,
            label="🎮 Принять вызов",
            custom_id=f"rps_join_{uuid.uuid4().hex[:6]}"
        )
        join.callback = self.join_callback
        self.add_item(join)

    async def join_callback(self, interaction: discord.Interaction):
        if interaction.user.id == self.creator_id:
            await interaction.response.send_message("Ты уже участник.", ephemeral=True)
            return

        if interaction.user.bot:
            await interaction.response.send_message("Боты не могут играть.", ephemeral=True)
            return

        if not await try_spend_mixed(interaction.user.id, self.guild_id, self.bet_coins, self.bet_crystals):
            await interaction.response.send_message(
                f"❌ Нужно иметь ставку: {format_bet(self.bet_coins, self.bet_crystals)}.",
                ephemeral=True
            )
            return

        game_view = RPSGameView(
            self.creator_id,
            interaction.user.id,
            self.guild_id,
            self.bet_coins,
            self.bet_crystals
        )

        await interaction.response.edit_message(
            content=(
                f"✊ Камень-ножницы-бумага!\n"
                f"<@{self.creator_id}> против <@{interaction.user.id}>\n"
                f"Ставка каждого: **{format_bet(self.bet_coins, self.bet_crystals)}**\n"
                f"Выберите свои варианты ниже."
            ),
            view=game_view
        )


class RPSGameView(ui.View):
    def __init__(self, player1: int, player2: int, guild_id: int, bet_coins: int, bet_crystals: int):
        super().__init__(timeout=180)
        self.player1 = player1
        self.player2 = player2
        self.guild_id = guild_id
        self.bet_coins = bet_coins
        self.bet_crystals = bet_crystals
        self.choices = {}

        options = [
            ("🪨 Камень", "rock"),
            ("✂️ Ножницы", "scissors"),
            ("📄 Бумага", "paper"),
        ]

        for label, value in options:
            button = ui.Button(
                style=discord.ButtonStyle.primary,
                label=label,
                custom_id=f"rps_{value}_{uuid.uuid4().hex[:6]}"
            )
            button.callback = self.make_choice_callback(value)
            self.add_item(button)

    def make_choice_callback(self, value: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id not in (self.player1, self.player2):
                await interaction.response.send_message("Ты не участник.", ephemeral=True)
                return

            if interaction.user.id in self.choices:
                await interaction.response.send_message("Выбор уже сделан.", ephemeral=True)
                return

            self.choices[interaction.user.id] = value

            ready1 = "✅" if self.player1 in self.choices else "⏳"
            ready2 = "✅" if self.player2 in self.choices else "⏳"

            if len(self.choices) < 2:
                await interaction.response.send_message("✅ Выбор сохранён.", ephemeral=True)

                await interaction.message.edit(
                    content=(
                        f"✊ Камень-ножницы-бумага!\n"
                        f"<@{self.player1}> {ready1}\n"
                        f"<@{self.player2}> {ready2}"
                    ),
                    view=self
                )
                return

            winner = self.get_winner()
            self.clear_items()

            if winner is None:
                await award_mixed(self.player1, self.guild_id, self.bet_coins, self.bet_crystals)
                await award_mixed(self.player2, self.guild_id, self.bet_coins, self.bet_crystals)

                await interaction.message.edit(
                    content="🤝 Ничья! Ставки возвращены.",
                    view=self
                )
                return

            win_coins = int(self.bet_coins * 2 * 0.95)
            win_crystals = int(self.bet_crystals * 2 * 0.95)

            await award_mixed(winner, self.guild_id, win_coins, win_crystals)

            await interaction.message.edit(
                content=(
                    f"🏆 Победитель: <@{winner}>!\n"
                    f"Выигрыш: **{format_reward(win_coins, win_crystals)}**."
                ),
                view=self
            )

        return callback

    def get_winner(self):
        c1 = self.choices[self.player1]
        c2 = self.choices[self.player2]

        if c1 == c2:
            return None

        if (
            (c1 == "rock" and c2 == "scissors") or
            (c1 == "scissors" and c2 == "paper") or
            (c1 == "paper" and c2 == "rock")
        ):
            return self.player1

        return self.player2


async def create_pvp_rps(interaction: discord.Interaction, bet_coins: int, bet_crystals: int):
    if not await try_spend_mixed(interaction.user.id, interaction.guild.id, bet_coins, bet_crystals):
        await interaction.response.send_message("❌ Недостаточно средств.", ephemeral=True)
        return

    view = RPSInviteView(interaction.user.id, interaction.guild.id, bet_coins, bet_crystals)

    await interaction.response.send_message(
        content=(
            f"✊ <@{interaction.user.id}> ищет соперника на камень-ножницы-бумагу!\n"
            f"Ставка: **{format_bet(bet_coins, bet_crystals)}**."
        ),
        view=view
    )


class PvPBlackjackInviteView(ui.View):
    def __init__(self, creator_id: int, guild_id: int, bet_coins: int, bet_crystals: int):
        super().__init__(timeout=180)
        self.creator_id = creator_id
        self.guild_id = guild_id
        self.bet_coins = bet_coins
        self.bet_crystals = bet_crystals

        join = ui.Button(
            style=discord.ButtonStyle.success,
            label="🎮 Принять вызов",
            custom_id=f"pvpbj_join_{uuid.uuid4().hex[:6]}"
        )
        join.callback = self.join_callback
        self.add_item(join)

    async def join_callback(self, interaction: discord.Interaction):
        if interaction.user.id == self.creator_id:
            await interaction.response.send_message("Ты уже участник.", ephemeral=True)
            return

        if interaction.user.bot:
            await interaction.response.send_message("Боты не могут играть.", ephemeral=True)
            return

        if not await try_spend_mixed(interaction.user.id, self.guild_id, self.bet_coins, self.bet_crystals):
            await interaction.response.send_message(
                f"❌ Нужно иметь ставку: {format_bet(self.bet_coins, self.bet_crystals)}.",
                ephemeral=True
            )
            return

        game_view = PvPBlackjackView(
            self.creator_id,
            interaction.user.id,
            self.guild_id,
            self.bet_coins,
            self.bet_crystals
        )

        await interaction.response.edit_message(
            content=(
                f"🃏 Блэкджек 2 игроков против дилера!\n"
                f"<@{self.creator_id}> против <@{interaction.user.id}>\n"
                f"Ставка каждого: **{format_bet(self.bet_coins, self.bet_crystals)}**"
            ),
            view=game_view
        )


class PvPBlackjackView(ui.View):
    def __init__(self, player1: int, player2: int, guild_id: int, bet_coins: int, bet_crystals: int):
        super().__init__(timeout=300)
        self.player1 = player1
        self.player2 = player2
        self.guild_id = guild_id
        self.bet_coins = bet_coins
        self.bet_crystals = bet_crystals

        self.hands = {
            player1: draw_cards(2),
            player2: draw_cards(2)
        }

        self.finished = {
            player1: False,
            player2: False
        }

        self.dealer_hand = draw_cards(2)
        self.done = False
        self.results = {}

        self.refresh_buttons()

    def refresh_buttons(self):
        self.clear_items()

        if self.done:
            return

        p1_hit = ui.Button(
            style=discord.ButtonStyle.primary,
            label="Игрок 1: Ещё",
            custom_id=f"pvpbj_p1_hit_{uuid.uuid4().hex[:6]}"
        )
        p1_hit.callback = self.make_callback(self.player1, "hit")
        self.add_item(p1_hit)

        p1_stand = ui.Button(
            style=discord.ButtonStyle.success,
            label="Игрок 1: Хватит",
            custom_id=f"pvpbj_p1_stand_{uuid.uuid4().hex[:6]}"
        )
        p1_stand.callback = self.make_callback(self.player1, "stand")
        self.add_item(p1_stand)

        p2_hit = ui.Button(
            style=discord.ButtonStyle.primary,
            label="Игрок 2: Ещё",
            custom_id=f"pvpbj_p2_hit_{uuid.uuid4().hex[:6]}"
        )
        p2_hit.callback = self.make_callback(self.player2, "hit")
        self.add_item(p2_hit)

        p2_stand = ui.Button(
            style=discord.ButtonStyle.success,
            label="Игрок 2: Хватит",
            custom_id=f"pvpbj_p2_stand_{uuid.uuid4().hex[:6]}"
        )
        p2_stand.callback = self.make_callback(self.player2, "stand")
        self.add_item(p2_stand)

    def make_callback(self, player_id: int, action: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != player_id:
                await interaction.response.send_message("Это не твоя кнопка.", ephemeral=True)
                return

            if self.done or self.finished[player_id]:
                await interaction.response.edit_message(embed=self.make_embed(), view=self)
                return

            if action == "hit":
                self.hands[player_id].append(draw_card())

                if hand_value(self.hands[player_id]) > 21:
                    self.finished[player_id] = True
            else:
                self.finished[player_id] = True

            if all(self.finished.values()):
                await self.resolve()

            self.refresh_buttons()
            await interaction.response.edit_message(embed=self.make_embed(), view=self)

        return callback

    def make_embed(self):
        embed = discord.Embed(title="🃏 PvP Блэкджек", color=0x00BCD4)

        for player_id in (self.player1, self.player2):
            hand = self.hands[player_id]
            status = "✅ Готов" if self.finished[player_id] else "⏳ Играет"

            embed.add_field(
                name=f"<@{player_id}> — {hand_value(hand)} {status}",
                value=format_hand(hand),
                inline=False
            )

        if self.done:
            embed.add_field(
                name=f"Дилер — {hand_value(self.dealer_hand)}",
                value=format_hand(self.dealer_hand),
                inline=False
            )

            if self.results:
                lines = []

                for player_id, result in self.results.items():
                    lines.append(f"<@{player_id}>: {result}")

                embed.add_field(name="Результаты", value="\n".join(lines), inline=False)
        else:
            embed.add_field(
                name="Дилер",
                value=f"{card_name(self.dealer_hand[0])}, ❔",
                inline=False
            )

        embed.set_footer(text=f"Ставка каждого: {format_bet(self.bet_coins, self.bet_crystals)}")
        return embed

    async def resolve(self):
        self.done = True

        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(draw_card())

        dealer_value = hand_value(self.dealer_hand)

        for player_id in (self.player1, self.player2):
            player_value = hand_value(self.hands[player_id])

            if player_value > 21:
                self.results[player_id] = f"💥 Перебор. Проигрыш {format_bet(self.bet_coins, self.bet_crystals)}."
                continue

            if dealer_value > 21 or player_value > dealer_value:
                payout_coins, payout_crystals, bonus = await award_mixed_win(
                    player_id,
                    self.guild_id,
                    self.bet_coins,
                    self.bet_crystals,
                    2
                )

                text = f"🏆 Победа! Выигрыш {format_reward(payout_coins, payout_crystals)}."

                if bonus > 0:
                    text += f" Бонус: +{bonus} ценности."

                self.results[player_id] = text

            elif player_value == dealer_value:
                await award_mixed(player_id, self.guild_id, self.bet_coins, self.bet_crystals)
                self.results[player_id] = "🤝 Ничья. Ставка возвращена."
            else:
                self.results[player_id] = f"❌ Дилер сильнее. Проигрыш {format_bet(self.bet_coins, self.bet_crystals)}."


async def create_pvp_blackjack(interaction: discord.Interaction, bet_coins: int, bet_crystals: int):
    if not await try_spend_mixed(interaction.user.id, interaction.guild.id, bet_coins, bet_crystals):
        await interaction.response.send_message("❌ Недостаточно средств.", ephemeral=True)
        return

    view = PvPBlackjackInviteView(interaction.user.id, interaction.guild.id, bet_coins, bet_crystals)

    await interaction.response.send_message(
        content=(
            f"🃏 <@{interaction.user.id}> ищет второго игрока в блэкджек против дилера!\n"
            f"Ставка каждого: **{format_bet(bet_coins, bet_crystals)}**."
        ),
        view=view
    )


def register(bot):
    @bot.tree.command(name="games", description="Все мини-игры")
    @_safe_send
    async def games(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎮 Мини-игры",
            description=(
                "Выбери игру.\n"
                "Ставить можно монеты, кристаллы или и то, и другое сразу.\n"
                "Валюты не конвертируются: монеты — это монеты, кристаллы — кристаллы."
            ),
            color=0x5865F2
        )

        view = GamesMenuView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)