# modules/cases.py
# Обновлённые кейсы:
# - открытие видно всем в канале;
# - покупка кейсов/ключей за монеты и кристаллы;
# - кристаллы считаются по курсу 1 кристалл = 10 монет.

import asyncio

import discord
from discord import ui

from database import db
from .shared import (
    check_cooldown,
    get_rarity_emoji,
    get_rarity_name,
    get_role_name,
    crystal_price_from_coins,
    spend_coins,
    spend_crystals
)


async def build_case_select_view(user_id: int, guild_id: int, action: str):
    cases = await db.get_all_cases(guild_id, active_only=True)

    if not cases:
        return None

    return CaseSelectView(user_id, guild_id, action, cases)


class CaseSelectView(ui.View):
    def __init__(self, user_id: int, guild_id: int, action: str, cases):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id
        self.action = action

        options = []

        for case in cases[:25]:
            case_dict = dict(case)
            emoji = get_rarity_emoji(case_dict["case_rarity"])

            coin_price_case = case_dict["case_price"]
            crystal_price_case = crystal_price_from_coins(coin_price_case)

            coin_price_key = case_dict["key_price"]
            crystal_price_key = crystal_price_from_coins(coin_price_key)

            if action == "buy_case_coin":
                description = f"Цена кейса: {coin_price_case} монет"
            elif action == "buy_case_crystal":
                description = f"Цена кейса: {crystal_price_case} кристаллов"
            elif action == "buy_key_coin":
                description = f"Цена ключа: {coin_price_key} монет"
            elif action == "buy_key_crystal":
                description = f"Цена ключа: {crystal_price_key} кристаллов"
            else:
                description = (
                    f"Кейс: {coin_price_case}💰 / {crystal_price_case}💎 | "
                    f"Ключ: {coin_price_key}💰 / {crystal_price_key}💎"
                )

            options.append(
                discord.SelectOption(
                    label=case_dict["name"][:100],
                    description=description[:100],
                    value=str(case_dict["id"]),
                    emoji=emoji
                )
            )

        select = ui.Select(placeholder="Выбери кейс", options=options)
        select.callback = self.on_case_selected
        self.add_item(select)

    async def on_case_selected(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не для тебя.", ephemeral=True)
            return

        if not self.children or not self.children[0].values:
            await interaction.response.send_message("Кейс не выбран.", ephemeral=True)
            return

        case_id = int(self.children[0].values[0])
        case = await db.get_case_details(case_id)

        if not case or case["guild_id"] != interaction.guild.id or not case["is_active"]:
            await interaction.response.edit_message(content="❌ Кейс не найден или не активен.", view=None)
            return

        # ===== Покупка =====

        if self.action == "buy_case_coin":
            price = case["case_price"]

            if not await spend_coins(interaction.user.id, interaction.guild.id, price):
                await interaction.response.edit_message(content="❌ Недостаточно монет.", view=self)
                return

            await db.add_case(interaction.user.id, interaction.guild.id, case_id, 1)
            await interaction.response.edit_message(
                content=f"✅ Куплен кейс **{case['name']}** за **{price}** монет.",
                view=self
            )
            return

        if self.action == "buy_case_crystal":
            price = crystal_price_from_coins(case["case_price"])

            if not await spend_crystals(interaction.user.id, interaction.guild.id, price):
                await interaction.response.edit_message(content="❌ Недостаточно кристаллов.", view=self)
                return

            await db.add_case(interaction.user.id, interaction.guild.id, case_id, 1)
            await interaction.response.edit_message(
                content=f"✅ Куплен кейс **{case['name']}** за **{price}** кристаллов.",
                view=self
            )
            return

        if self.action == "buy_key_coin":
            price = case["key_price"]

            if not await spend_coins(interaction.user.id, interaction.guild.id, price):
                await interaction.response.edit_message(content="❌ Недостаточно монет.", view=self)
                return

            await db.add_key(interaction.user.id, interaction.guild.id, case_id, 1)
            await interaction.response.edit_message(
                content=f"✅ Куплен ключ к кейсу **{case['name']}** за **{price}** монет.",
                view=self
            )
            return

        if self.action == "buy_key_crystal":
            price = crystal_price_from_coins(case["key_price"])

            if not await spend_crystals(interaction.user.id, interaction.guild.id, price):
                await interaction.response.edit_message(content="❌ Недостаточно кристаллов.", view=self)
                return

            await db.add_key(interaction.user.id, interaction.guild.id, case_id, 1)
            await interaction.response.edit_message(
                content=f"✅ Куплен ключ к кейсу **{case['name']}** за **{price}** кристаллов.",
                view=self
            )
            return

        # ===== Открытие =====

        if self.action == "open":
            await interaction.response.edit_message(content="🔑 Открываю кейс...", view=None)
            await asyncio.sleep(0.45)

            result = await db.open_case(interaction.user.id, interaction.guild.id, case_id)

            if not result["success"]:
                await interaction.edit_original_response(content=f"❌ {result['error']}")
                return

            role_name = get_role_name(interaction.guild, result["role_id"])
            emoji = get_rarity_emoji(result["rarity"])
            rarity_name = get_rarity_name(result["rarity"])

            embed = discord.Embed(
                title="🎉 Кейс открыт!",
                description=(
                    f"Выпала роль: {emoji} **{role_name}**\n"
                    f"Редкость: **{rarity_name}**\n"
                    f"Рыночная цена: **{result['market_price']}** монет"
                ),
                color=0x00BCD4
            )

            if result["duplicate"]:
                embed.add_field(
                    name="🔁 Повтор",
                    value="Эта роль уже была у тебя. Копия добавлена в инвентарь.",
                    inline=False
                )

            if result["debuff_applied"]:
                embed.add_field(
                    name="💀 Кривая рука",
                    value="Ключ скользнул... Получен дебафф **Кривая рука**.",
                    inline=False
                )

            await interaction.edit_original_response(content=None, embed=embed)

            # Публичное объявление для всего канала.
            public_embed = discord.Embed(
                title="📦 Открытие кейса",
                description=(
                    f"{interaction.user.mention} открывает кейс **{result['case_name']}**\n"
                    f"Выпала роль: {emoji} **{role_name}** ({rarity_name})"
                ),
                color=0x00BCD4
            )

            if result["duplicate"]:
                public_embed.add_field(
                    name="🔁 Повтор",
                    value="Роль уже была у игрока. Копия добавлена в инвентарь.",
                    inline=False
                )

            if result["debuff_applied"]:
                public_embed.add_field(
                    name="💀 Кривая рука",
                    value="Игрок получил дебафф **Кривая рука**.",
                    inline=False
                )

            try:
                if interaction.channel:
                    await interaction.channel.send(
                        content=f"🎉 {interaction.user.mention} открыл кейс!",
                        embed=public_embed
                    )
            except discord.HTTPException:
                try:
                    await interaction.followup.send(
                        content=f"🎉 {interaction.user.mention} открыл кейс!",
                        embed=public_embed,
                        ephemeral=False
                    )
                except Exception:
                    pass


class CaseShopView(ui.View):
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.guild_id = guild_id

        buy_case_coin = ui.Button(style=discord.ButtonStyle.primary, label="📦 Кейс за монеты")
        buy_case_coin.callback = self.make_callback("buy_case_coin")
        self.add_item(buy_case_coin)

        buy_case_crystal = ui.Button(style=discord.ButtonStyle.primary, label="📦 Кейс за кристаллы")
        buy_case_crystal.callback = self.make_callback("buy_case_crystal")
        self.add_item(buy_case_crystal)

        buy_key_coin = ui.Button(style=discord.ButtonStyle.primary, label="🔑 Ключ за монеты")
        buy_key_coin.callback = self.make_callback("buy_key_coin")
        self.add_item(buy_key_coin)

        buy_key_crystal = ui.Button(style=discord.ButtonStyle.primary, label="🔑 Ключ за кристаллы")
        buy_key_crystal.callback = self.make_callback("buy_key_crystal")
        self.add_item(buy_key_crystal)

        view_cases = ui.Button(style=discord.ButtonStyle.secondary, label="👁️ Просмотр кейсов")
        view_cases.callback = self.view_cases_callback
        self.add_item(view_cases)

    def make_callback(self, action: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Это не для тебя.", ephemeral=True)
                return

            view = await build_case_select_view(self.user_id, self.guild_id, action)

            if not view:
                await interaction.response.send_message("❌ Нет активных кейсов.", ephemeral=True)
                return

            titles = {
                "buy_case_coin": "Выбери кейс для покупки за монеты:",
                "buy_case_crystal": "Выбери кейс для покупки за кристаллы:",
                "buy_key_coin": "Выбери ключ для покупки за монеты:",
                "buy_key_crystal": "Выбери ключ для покупки за кристаллы:",
            }

            await interaction.response.send_message(
                titles.get(action, "Выбери кейс:"),
                view=view,
                ephemeral=True
            )

        return callback

    async def view_cases_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Это не для тебя.", ephemeral=True)
            return

        cases = await db.get_all_cases(self.guild_id, active_only=True)

        if not cases:
            await interaction.response.send_message("❌ Нет активных кейсов.", ephemeral=True)
            return

        embed = discord.Embed(title="📦 Доступные кейсы", color=0xFFD700)

        for case in cases[:10]:
            case_details = await db.get_case_details(case["id"])

            if not case_details:
                continue

            emoji = get_rarity_emoji(case_details["case_rarity"])
            rarity_name = get_rarity_name(case_details["case_rarity"])

            crystal_case_price = crystal_price_from_coins(case_details["case_price"])
            crystal_key_price = crystal_price_from_coins(case_details["key_price"])

            lines = [
                f"**Цена кейса:** {case_details['case_price']} монет / {crystal_case_price} кристаллов",
                f"**Цена ключа:** {case_details['key_price']} монет / {crystal_key_price} кристаллов",
                f"**Редкость кейса:** {rarity_name}",
                "**Редкости:**"
            ]

            for rarity in case_details["rarities"]:
                r_emoji = get_rarity_emoji(rarity["rarity"])
                r_name = get_rarity_name(rarity["rarity"])
                lines.append(f"  {r_emoji} {r_name}: {rarity['drop_chance']}%")

            embed.add_field(
                name=f"{emoji} {case_details['name']} (ID: {case_details['id']})",
                value="\n".join(lines)[:1024],
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class CaseInfoView(ui.View):
    def __init__(self, guild_id: int, guild: discord.Guild, cases):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.guild = guild

        options = []

        for case in cases[:25]:
            case_dict = dict(case)
            options.append(
                discord.SelectOption(
                    label=case_dict["name"][:100],
                    description="Награды и шансы",
                    value=str(case_dict["id"]),
                    emoji=get_rarity_emoji(case_dict["case_rarity"])
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

        if not case or case["guild_id"] != self.guild_id:
            await interaction.response.send_message("❌ Кейс не найден.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📦 Награды кейса: {case['name']}",
            description="Шансы и роли внутри кейса:",
            color=0xFFD700
        )

        for rarity in case["rarities"]:
            emoji = get_rarity_emoji(rarity["rarity"])
            name = get_rarity_name(rarity["rarity"])

            role_names = []

            for role_id in rarity["roles"][:15]:
                role_names.append(get_role_name(self.guild, role_id))

            if len(rarity["roles"]) > 15:
                role_names.append(f"... и ещё {len(rarity['roles']) - 15}")

            value = (
                f"**Шанс:** {rarity['drop_chance']}%\n"
                f"**Рыночная цена:** {rarity['sell_price']} монет\n"
                f"**Роли:**\n" + ("\n".join(role_names) if role_names else "Нет ролей")
            )

            embed.add_field(
                name=f"{emoji} {name}",
                value=value[:1024],
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


def register(bot):
    @bot.tree.command(name="case_open", description="Открыть кейс")
    async def case_open(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        view = await build_case_select_view(interaction.user.id, interaction.guild.id, "open")

        if not view:
            await interaction.response.send_message("❌ Нет активных кейсов.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🎰 Открытие кейса",
            description="Выбери кейс. Для открытия нужны кейс и ключ.\nРезультат увидят все в канале.",
            color=0x9C27B0
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @bot.tree.command(name="case_shop", description="Купить кейс или ключ")
    async def case_shop(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not await check_cooldown(interaction.user.id, interaction.guild.id):
            await interaction.response.send_message("⏳ Подожди немного.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🏪 Магазин кейсов",
            description=(
                "Можно покупать за монеты или кристаллы.\n"
                "Курс: **1 кристалл = 10 монет**."
            ),
            color=0xFFD700
        )

        view = CaseShopView(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @bot.tree.command(name="case_info", description="Посмотреть награды и шансы кейсов")
    async def case_info(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        cases = await db.get_all_cases(interaction.guild.id, active_only=True)

        if not cases:
            await interaction.response.send_message("❌ Нет активных кейсов.", ephemeral=True)
            return

        view = CaseInfoView(interaction.guild.id, interaction.guild, cases)

        embed = discord.Embed(
            title="ℹ️ Награды кейсов",
            description="Выбери кейс, чтобы посмотреть роли и шансы.",
            color=0x00BCD4
        )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)