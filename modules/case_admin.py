# modules/case_admin.py
# Админ-панель кейсов: создание, настройка, редкости, роли, удаление.

import uuid

import discord
from discord import ui

from database import db
from .shared import (
    deliver_message,
    resolve_role_by_input,
    get_rarity_emoji,
    get_rarity_name,
    get_role_name,
    RARITY_NAME
)


from .shared import can_manage as can_manage_cases


class CreateCaseModal(ui.Modal, title="Создать кейс"):
    name = ui.TextInput(
        label="Название кейса",
        placeholder="Например: Стартовый кейс",
        max_length=100,
        required=True
    )
    case_rarity = ui.TextInput(
        label="Редкость кейса",
        placeholder="common / uncommon / rare / epic / legendary / secret / secret+",
        max_length=20,
        required=True
    )
    case_price = ui.TextInput(
        label="Цена кейса (монеты, 0 = бесплатно / недоступно)",
        placeholder="Например: 100 или 0",
        max_length=12,
        required=True
    )
    key_price = ui.TextInput(
        label="Цена ключа (монеты, 0 = бесплатно / недоступно)",
        placeholder="Например: 50 или 0",
        max_length=12,
        required=True
    )
    case_crystal_price = ui.TextInput(
        label="Цена кейса (кристаллы, 0 = покупка за кристаллы выключена)",
        placeholder="Например: 10 или 0",
        max_length=12,
        required=True
    )
    key_crystal_price = ui.TextInput(
        label="Цена ключа (кристаллы, 0 = покупка за кристаллы выключена)",
        placeholder="Например: 5 или 0",
        max_length=12,
        required=True
    )

    def __init__(self, view):
        super().__init__(custom_id=f"create_case_modal_{uuid.uuid4().hex[:8]}")
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        rarity_key = self.case_rarity.value.strip().lower()

        if rarity_key not in RARITY_NAME:
            await interaction.response.send_message(
                "❌ Неверная редкость кейса. Доступны: " + ", ".join(RARITY_NAME.keys()),
                ephemeral=True
            )
            return

        try:
            case_price = int(self.case_price.value.strip())
            key_price = int(self.key_price.value.strip())
            case_crystal_price = int(self.case_crystal_price.value.strip())
            key_crystal_price = int(self.key_crystal_price.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Цены должны быть числами.", ephemeral=True)
            return

        if min(case_price, key_price, case_crystal_price, key_crystal_price) < 0:
            await interaction.response.send_message(
                "❌ Цены не могут быть отрицательными (0 — разрешено).", ephemeral=True)
            return

        await db.create_case_return_id(
            interaction.guild.id,
            self.name.value.strip(),
            rarity_key,
            case_price,
            key_price,
            case_crystal_price=case_crystal_price,
            key_crystal_price=key_crystal_price,
        )

        await interaction.response.send_message("✅ Кейс создан.", ephemeral=True)
        await self.view_ref.refresh(interaction)


class CaseSettingsModal(ui.Modal):
    def __init__(self, view, case):
        super().__init__(
            title="Настройки кейса",
            custom_id=f"case_settings_modal_{uuid.uuid4().hex[:8]}"
        )

        self.view_ref = view

        self.name_input = ui.TextInput(
            label="Название кейса",
            default=case["name"],
            max_length=100,
            required=True,
            custom_id=f"case_name_{uuid.uuid4().hex[:6]}"
        )

        self.case_price_input = ui.TextInput(
            label="Цена кейса (монеты, 0 = бесплатно / недоступно)",
            default=str(case["case_price"]),
            max_length=12,
            required=True,
            custom_id=f"case_price_{uuid.uuid4().hex[:6]}"
        )

        self.key_price_input = ui.TextInput(
            label="Цена ключа (монеты, 0 = бесплатно / недоступно)",
            default=str(case["key_price"]),
            max_length=12,
            required=True,
            custom_id=f"key_price_{uuid.uuid4().hex[:6]}"
        )

        self.case_crystal_input = ui.TextInput(
            label="Цена кейса (кристаллы, 0 = покупка за кристаллы выключена)",
            default=str(case.get("case_crystal_price") or 0),
            max_length=12,
            required=True,
            custom_id=f"case_cry_{uuid.uuid4().hex[:6]}"
        )

        self.key_crystal_input = ui.TextInput(
            label="Цена ключа (кристаллы, 0 = покупка за кристаллы выключена)",
            default=str(case.get("key_crystal_price") or 0),
            max_length=12,
            required=True,
            custom_id=f"key_cry_{uuid.uuid4().hex[:6]}"
        )

        self.add_item(self.name_input)
        self.add_item(self.case_price_input)
        self.add_item(self.key_price_input)
        self.add_item(self.case_crystal_input)
        self.add_item(self.key_crystal_input)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        try:
            case_price = int(self.case_price_input.value.strip())
            key_price = int(self.key_price_input.value.strip())
            case_crystal_price = int(self.case_crystal_input.value.strip())
            key_crystal_price = int(self.key_crystal_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Цены должны быть числами.", ephemeral=True)
            return

        if min(case_price, key_price, case_crystal_price, key_crystal_price) < 0:
            await interaction.response.send_message(
                "❌ Цены не могут быть отрицательными (0 — разрешено).", ephemeral=True)
            return

        success = await db.update_case_settings(
            self.view_ref.case_id,
            self.name_input.value.strip(),
            case_price,
            key_price,
            case_crystal_price=case_crystal_price,
            key_crystal_price=key_crystal_price,
        )

        if not success:
            await interaction.response.send_message("❌ Не удалось сохранить настройки.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Настройки кейса сохранены.", ephemeral=True)
        await self.view_ref.refresh(interaction)


class AddRarityModal(ui.Modal, title="Добавить редкость"):
    rarity = ui.TextInput(
        label="Редкость",
        placeholder="common / uncommon / rare / epic / legendary / secret / secret+",
        max_length=20,
        required=True
    )
    drop_chance = ui.TextInput(
        label="Шанс выпадения, %",
        placeholder="Например: 40",
        max_length=3,
        required=True
    )
    sell_price = ui.TextInput(
        label="Рыночная цена роли",
        placeholder="Например: 100",
        max_length=12,
        required=True
    )

    def __init__(self, view):
        super().__init__(custom_id=f"add_rarity_modal_{uuid.uuid4().hex[:8]}")
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        rarity_key = self.rarity.value.strip().lower()

        if rarity_key not in RARITY_NAME:
            await interaction.response.send_message(
                "❌ Неверная редкость. Доступны: " + ", ".join(RARITY_NAME.keys()),
                ephemeral=True
            )
            return

        try:
            chance = int(self.drop_chance.value.strip())
            sell_price = int(self.sell_price.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Шанс и цена должны быть числами.", ephemeral=True)
            return

        if chance < 0 or chance > 100:
            await interaction.response.send_message("❌ Шанс должен быть от 0 до 100.", ephemeral=True)
            return

        if sell_price < 0:
            await interaction.response.send_message("❌ Цена не может быть отрицательной.", ephemeral=True)
            return

        if await db.has_case_rarity(self.view_ref.case_id, rarity_key):
            await interaction.response.send_message("❌ Такая редкость уже есть в этом кейсе.", ephemeral=True)
            return

        await db.add_rarity_to_case(
            self.view_ref.case_id,
            rarity_key,
            chance,
            sell_price
        )

        await interaction.response.send_message("✅ Редкость добавлена.", ephemeral=True)
        await self.view_ref.refresh(interaction)


class RaritySettingsModal(ui.Modal):
    def __init__(self, view, rarity):
        super().__init__(
            title="Настройки редкости",
            custom_id=f"rarity_settings_modal_{uuid.uuid4().hex[:8]}"
        )

        self.view_ref = view

        self.drop_chance_input = ui.TextInput(
            label="Шанс выпадения, %",
            default=str(rarity["drop_chance"]),
            max_length=3,
            required=True,
            custom_id=f"rarity_chance_{uuid.uuid4().hex[:6]}"
        )

        self.sell_price_input = ui.TextInput(
            label="Рыночная цена роли",
            default=str(rarity["sell_price"]),
            max_length=12,
            required=True,
            custom_id=f"rarity_sell_price_{uuid.uuid4().hex[:6]}"
        )

        self.add_item(self.drop_chance_input)
        self.add_item(self.sell_price_input)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        try:
            chance = int(self.drop_chance_input.value.strip())
            sell_price = int(self.sell_price_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Шанс и цена должны быть числами.", ephemeral=True)
            return

        success = await db.update_case_rarity_settings(
            self.view_ref.case_rarity_id,
            chance,
            sell_price
        )

        if not success:
            await interaction.response.send_message("❌ Не удалось сохранить настройки редкости.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Настройки редкости сохранены.", ephemeral=True)
        await self.view_ref.refresh(interaction)


class AddRoleModal(ui.Modal, title="Добавить роль в редкость"):
    role_input = ui.TextInput(
        label="Роль",
        placeholder="@роль, имя роли или ID роли",
        max_length=100,
        required=True
    )

    def __init__(self, view):
        super().__init__(custom_id=f"add_role_modal_{uuid.uuid4().hex[:8]}")
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        role = resolve_role_by_input(interaction.guild, self.role_input.value)

        if not role:
            await interaction.response.send_message(
                "❌ Роль не найдена. Укажи @роль, точное имя роли или её ID.",
                ephemeral=True
            )
            return

        rarity = await db.get_case_rarity_details(self.view_ref.case_rarity_id)

        if not rarity:
            await interaction.response.send_message("❌ Редкость не найдена.", ephemeral=True)
            return

        if role.id in rarity["roles"]:
            await interaction.response.send_message("❌ Эта роль уже добавлена в данную редкость.", ephemeral=True)
            return

        await db.add_roles_to_case_rarity(self.view_ref.case_rarity_id, [role.id])
        await interaction.response.send_message(f"✅ Роль **{role.name}** добавлена.", ephemeral=True)
        await self.view_ref.refresh(interaction)


class DeleteCaseModal(ui.Modal, title="Удаление кейса"):
    confirm_input = ui.TextInput(
        label="Подтверждение",
        placeholder="Введи DELETE для удаления",
        required=True,
        max_length=10
    )

    def __init__(self, view):
        super().__init__(custom_id=f"delete_case_modal_{uuid.uuid4().hex[:8]}")
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        if self.confirm_input.value.strip().upper() != "DELETE":
            await interaction.response.send_message("❌ Удаление отменено.", ephemeral=True)
            return

        success = await db.delete_case(self.view_ref.case_id)

        if not success:
            await interaction.response.send_message("❌ Кейс не найден.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Кейс полностью удалён.", ephemeral=True)

        view = CaseAdminListView(self.view_ref.user_id, self.view_ref.guild_id, self.view_ref.guild)
        await view.refresh(interaction)


class CaseAdminListView(ui.View):
    def __init__(self, user_id: int, guild_id: int, guild: discord.Guild):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.guild = guild
        self.page = 0
        self.per_page = 8

    async def refresh(self, interaction: discord.Interaction):
        cases = await db.get_all_cases(self.guild_id, active_only=False)
        cases = [dict(case) for case in cases]
        cases.sort(key=lambda x: x["id"], reverse=True)

        embed = discord.Embed(
            title="📦 Управление кейсами",
            description="Нажми на кейс, чтобы настроить его.",
            color=0xFFD700
        )

        self.clear_items()

        create_btn = ui.Button(
            style=discord.ButtonStyle.success,
            label="➕ Создать кейс",
            custom_id=f"create_case_{uuid.uuid4().hex[:6]}"
        )
        create_btn.callback = self.create_callback
        self.add_item(create_btn)

        if not cases:
            embed.description = "Кейсов пока нет.\nНажми кнопку выше, чтобы создать первый кейс."
            await deliver_message(interaction, embed=embed, view=self)
            return

        pages = max(1, (len(cases) + self.per_page - 1) // self.per_page)
        self.page = max(0, min(self.page, pages - 1))

        start = self.page * self.per_page
        end = start + self.per_page
        page_cases = cases[start:end]

        for case in page_cases:
            status = "✅" if case["is_active"] else "📦"
            label = f"{status} {case['name']} #{case['id']}"[:80]

            button = ui.Button(
                style=discord.ButtonStyle.success if case["is_active"] else discord.ButtonStyle.secondary,
                label=label,
                custom_id=f"case_admin_{case['id']}_{uuid.uuid4().hex[:6]}"
            )
            button.callback = self.make_case_callback(case["id"])
            self.add_item(button)

        if pages > 1:
            if self.page > 0:
                prev_btn = ui.Button(style=discord.ButtonStyle.secondary, label="◀️ Назад")
                prev_btn.callback = self.prev_callback
                self.add_item(prev_btn)

            if self.page < pages - 1:
                next_btn = ui.Button(style=discord.ButtonStyle.secondary, label="Вперёд ▶️")
                next_btn.callback = self.next_callback
                self.add_item(next_btn)

        embed.set_footer(text=f"Страница {self.page + 1}/{pages}")
        await deliver_message(interaction, embed=embed, view=self)

    async def create_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        modal = CreateCaseModal(self)
        await interaction.response.send_modal(modal)

    async def prev_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        self.page -= 1
        await self.refresh(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        self.page += 1
        await self.refresh(interaction)

    @ui.button(label="⚡ Готовые пресеты", style=discord.ButtonStyle.primary, custom_id="ca:preset")
    async def preset_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Создать 7 готовых кейсов с редкостями и ролями (из старого /case_preset_full)."""
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ У бота нет права «Управлять ролями».", ephemeral=True)
            return

        from .auto_roles import PRESET_CASES, RARITY_COLORS
        await interaction.response.defer(ephemeral=True)

        lines = []
        existing_names = {r.name for r in interaction.guild.roles}

        for preset in PRESET_CASES:
            case_id = await db.create_case_return_id(
                interaction.guild.id, preset["name"], preset["case_rarity"],
                preset["case_price"], preset["key_price"])

            for rarity in preset["rarities"]:
                rarity_id = await db.add_rarity_return_id(
                    case_id, rarity["rarity"], rarity["chance"], rarity["price"])

                for role_name in rarity["roles"]:
                    final_name, counter = role_name, 2
                    while final_name in existing_names:
                        final_name = f"{role_name} {counter}"
                        counter += 1
                    try:
                        role = await interaction.guild.create_role(
                            name=final_name,
                            colour=discord.Colour(RARITY_COLORS.get(rarity["rarity"], 0x808080)),
                            permissions=discord.Permissions.none(),
                            hoist=False, mentionable=False,
                            reason="Автосоздание пресета кейсов")
                    except discord.Forbidden:
                        await interaction.followup.send(
                            "❌ У бота нет права создавать роли.", ephemeral=True)
                        return
                    except discord.HTTPException as e:
                        await interaction.followup.send(f"❌ Ошибка создания роли: {e}", ephemeral=True)
                        return
                    await db.add_roles_to_case_rarity(rarity_id, [role.id])
                    existing_names.add(final_name)

            act = await db.activate_case(case_id)
            if act["success"]:
                lines.append(f"✅ {preset['name']} — создан и активирован")
            else:
                lines.append(f"⚠️ {preset['name']} — создан, но не активирован:\n"
                             + "\n".join(act["details"]))

        await interaction.followup.send("Готово:\n" + "\n".join(lines), ephemeral=True)

    @ui.button(label="🤖 Роли для всех кейсов", style=discord.ButtonStyle.secondary, custom_id="ca:genall")
    async def gen_all_btn(self, button: discord.ui.Button, interaction: discord.Interaction):
        """Сгенерировать недостающие роли для всех кейсов (из старого /gen_all_case_roles)."""
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ У бота нет права «Управлять ролями».", ephemeral=True)
            return

        from .auto_roles import generate_roles_for_case
        await interaction.response.defer(ephemeral=True)

        cases = await db.get_all_cases(self.guild_id, active_only=False)
        total, errors = 0, []
        for case in cases:
            created, error = await generate_roles_for_case(interaction.guild, case["id"])
            total += created
            if error:
                errors.append(f"{case['name']}: {error}")

        msg = f"✅ Всего создано ролей: **{total}**"
        if errors:
            msg += "\n\n⚠️ Ошибки:\n" + "\n".join(errors)
        await interaction.followup.send(msg, ephemeral=True)

    def make_case_callback(self, case_id: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id or not can_manage_cases(interaction):
                await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
                return

            view = CaseAdminView(self.user_id, self.guild_id, self.guild, case_id)
            await view.refresh(interaction)

        return callback


class CaseAdminView(ui.View):
    def __init__(self, user_id: int, guild_id: int, guild: discord.Guild, case_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.guild = guild
        self.case_id = case_id

    async def refresh(self, interaction: discord.Interaction):
        case = await db.get_case_details(self.case_id)

        self.clear_items()

        if not case:
            embed = discord.Embed(
                title="❌ Кейс не найден",
                description="Вернись к списку кейсов.",
                color=0xFF0000
            )

            back_btn = ui.Button(style=discord.ButtonStyle.secondary, label="◀️ К списку кейсов")
            back_btn.callback = self.back_callback
            self.add_item(back_btn)

            await deliver_message(interaction, embed=embed, view=self)
            return

        case_rarity_info = get_rarity_emoji(case["case_rarity"])
        total_chance = sum(r["drop_chance"] for r in case["rarities"])
        total_roles = sum(len(r["roles"]) for r in case["rarities"])

        embed = discord.Embed(
            title=f"{case_rarity_info} Кейс: {case['name']}",
            description=(
                "Здесь можно настроить кейс:\n"
                "• цены кейса и ключа\n"
                "• редкости и шансы выпадения\n"
                "• рыночную цену ролей\n"
                "• роли внутри каждой редкости"
            ),
            color=0xFFD700
        )

        embed.add_field(name="ID кейса", value=str(case["id"]), inline=True)
        embed.add_field(name="Редкость кейса", value=get_rarity_name(case["case_rarity"]), inline=True)
        embed.add_field(name="Статус", value="✅ Активен" if case["is_active"] else "⏸️ Не активен", inline=True)
        embed.add_field(name="Цена кейса", value=f"{case['case_price']} монет", inline=True)
        embed.add_field(name="Цена ключа", value=f"{case['key_price']} монет", inline=True)
        embed.add_field(name="Всего ролей", value=str(total_roles), inline=True)

        chance_status = "✅" if total_chance == 100 else "⚠️"
        embed.add_field(name="Сумма шансов", value=f"{chance_status} {total_chance}%", inline=True)

        settings_btn = ui.Button(style=discord.ButtonStyle.primary, label="⚙️ Настройки кейса")
        settings_btn.callback = self.settings_callback
        self.add_item(settings_btn)

        add_rarity_btn = ui.Button(style=discord.ButtonStyle.success, label="➕ Добавить редкость")
        add_rarity_btn.callback = self.add_rarity_callback
        self.add_item(add_rarity_btn)

        rarities = sorted(case["rarities"], key=lambda x: x["id"])

        for rarity in rarities[:10]:
            rarity_emoji = get_rarity_emoji(rarity["rarity"])
            rarity_name = get_rarity_name(rarity["rarity"])

            label = (
                f"{rarity_emoji} {rarity_name} "
                f"{rarity['drop_chance']}% ({len(rarity['roles'])})"
            )[:80]

            button = ui.Button(
                style=discord.ButtonStyle.secondary,
                label=label,
                custom_id=f"case_rarity_{rarity['id']}_{uuid.uuid4().hex[:6]}"
            )
            button.callback = self.make_rarity_callback(rarity["id"])
            self.add_item(button)

        if case["is_active"]:
            deactivate_btn = ui.Button(style=discord.ButtonStyle.danger, label="⛔ Деактивировать")
            deactivate_btn.callback = self.deactivate_callback
            self.add_item(deactivate_btn)
        else:
            activate_btn = ui.Button(style=discord.ButtonStyle.success, label="✅ Активировать")
            activate_btn.callback = self.activate_callback
            self.add_item(activate_btn)

        delete_btn = ui.Button(style=discord.ButtonStyle.danger, label="🗑️ Удалить кейс")
        delete_btn.callback = self.delete_callback
        self.add_item(delete_btn)

        back_btn = ui.Button(style=discord.ButtonStyle.secondary, label="◀️ К списку кейсов")
        back_btn.callback = self.back_callback
        self.add_item(back_btn)

        await deliver_message(interaction, embed=embed, view=self)

    async def settings_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        case = await db.get_case_details(self.case_id)

        if not case:
            await interaction.response.send_message("❌ Кейс не найден.", ephemeral=True)
            return

        modal = CaseSettingsModal(self, case)
        await interaction.response.send_modal(modal)

    async def add_rarity_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        modal = AddRarityModal(self)
        await interaction.response.send_modal(modal)

    async def activate_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        result = await db.activate_case(self.case_id)

        if result["success"]:
            await interaction.response.send_message("✅ Кейс активирован.", ephemeral=True)
        else:
            details = "\n".join(result.get("details", []))
            await interaction.response.send_message(f"❌ {result['error']}\n{details}", ephemeral=True)

        await self.refresh(interaction)

    async def deactivate_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        await db.deactivate_case(self.case_id)
        await interaction.response.send_message("✅ Кейс деактивирован.", ephemeral=True)
        await self.refresh(interaction)

    async def delete_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        modal = DeleteCaseModal(self)
        await interaction.response.send_modal(modal)

    async def back_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        view = CaseAdminListView(self.user_id, self.guild_id, self.guild)
        await view.refresh(interaction)

    def make_rarity_callback(self, case_rarity_id: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id or not can_manage_cases(interaction):
                await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
                return

            view = RarityAdminView(
                self.user_id,
                self.guild_id,
                self.guild,
                self.case_id,
                case_rarity_id
            )
            await view.refresh(interaction)

        return callback


class RarityAdminView(ui.View):
    def __init__(
        self,
        user_id: int,
        guild_id: int,
        guild: discord.Guild,
        case_id: int,
        case_rarity_id: int
    ):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.guild = guild
        self.case_id = case_id
        self.case_rarity_id = case_rarity_id
        self.page = 0
        self.per_page = 8

    async def refresh(self, interaction: discord.Interaction):
        rarity = await db.get_case_rarity_details(self.case_rarity_id)

        if not rarity:
            view = CaseAdminView(self.user_id, self.guild_id, self.guild, self.case_id)
            await view.refresh(interaction)
            return

        case = await db.get_case_details(self.case_id)

        if not case:
            view = CaseAdminListView(self.user_id, self.guild_id, self.guild)
            await view.refresh(interaction)
            return

        rarity_emoji = get_rarity_emoji(rarity["rarity"])
        rarity_name = get_rarity_name(rarity["rarity"])

        embed = discord.Embed(
            title=f"{rarity_emoji} Редкость: {rarity_name}",
            description=(
                f"Кейс: **{case['name']}**\n\n"
                "Здесь можно настроить шанс выпадения, рыночную цену роли,\n"
                "а также добавлять и удалять роли."
            ),
            color=0xFFD700
        )

        embed.add_field(name="Шанс выпадения", value=f"{rarity['drop_chance']}%", inline=True)
        embed.add_field(name="Рыночная цена", value=f"{rarity['sell_price']} монет", inline=True)
        embed.add_field(name="Ролей внутри", value=str(len(rarity["roles"])), inline=True)

        self.clear_items()

        settings_btn = ui.Button(style=discord.ButtonStyle.primary, label="⚙️ Настройки редкости")
        settings_btn.callback = self.settings_callback
        self.add_item(settings_btn)

        add_role_btn = ui.Button(style=discord.ButtonStyle.success, label="➕ Добавить роль")
        add_role_btn.callback = self.add_role_callback
        self.add_item(add_role_btn)

        roles = rarity["roles"]

        pages = max(1, (len(roles) + self.per_page - 1) // self.per_page)
        self.page = max(0, min(self.page, pages - 1))

        start = self.page * self.per_page
        end = start + self.per_page
        page_roles = roles[start:end]

        for role_id in page_roles:
            role_name = get_role_name(self.guild, role_id)
            label = f"❌ {role_name}"[:80]

            button = ui.Button(
                style=discord.ButtonStyle.danger,
                label=label,
                custom_id=f"remove_role_{role_id}_{uuid.uuid4().hex[:6]}"
            )
            button.callback = self.make_remove_role_callback(role_id)
            self.add_item(button)

        if pages > 1:
            if self.page > 0:
                prev_btn = ui.Button(style=discord.ButtonStyle.secondary, label="◀️ Назад")
                prev_btn.callback = self.prev_callback
                self.add_item(prev_btn)

            if self.page < pages - 1:
                next_btn = ui.Button(style=discord.ButtonStyle.secondary, label="Вперёд ▶️")
                next_btn.callback = self.next_callback
                self.add_item(next_btn)

        delete_rarity_btn = ui.Button(style=discord.ButtonStyle.danger, label="🗑️ Удалить редкость")
        delete_rarity_btn.callback = self.delete_rarity_callback
        self.add_item(delete_rarity_btn)

        back_btn = ui.Button(style=discord.ButtonStyle.secondary, label="◀️ К настройкам кейса")
        back_btn.callback = self.back_callback
        self.add_item(back_btn)

        await deliver_message(interaction, embed=embed, view=self)

    async def settings_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        rarity = await db.get_case_rarity_details(self.case_rarity_id)

        if not rarity:
            await interaction.response.send_message("❌ Редкость не найдена.", ephemeral=True)
            return

        modal = RaritySettingsModal(self, rarity)
        await interaction.response.send_modal(modal)

    async def add_role_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        modal = AddRoleModal(self)
        await interaction.response.send_modal(modal)

    async def prev_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        self.page -= 1
        await self.refresh(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        self.page += 1
        await self.refresh(interaction)

    async def delete_rarity_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        await db.remove_rarity_from_case(self.case_rarity_id)
        await interaction.response.send_message("✅ Редкость удалена вместе со всеми ролями.", ephemeral=True)

        view = CaseAdminView(self.user_id, self.guild_id, self.guild, self.case_id)
        await view.refresh(interaction)

    async def back_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        view = CaseAdminView(self.user_id, self.guild_id, self.guild, self.case_id)
        await view.refresh(interaction)

    def make_remove_role_callback(self, role_id: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id or not can_manage_cases(interaction):
                await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
                return

            await db.remove_role_from_case_rarity(self.case_rarity_id, role_id)
            await interaction.response.send_message("✅ Роль удалена из редкости.", ephemeral=True)
            await self.refresh(interaction)

        return callback


def register(bot):
    @bot.tree.command(name="case_admin", description="Управление кейсами (владелец сервера / администратор)")
    async def case_admin(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return

        if not can_manage_cases(interaction):
            await interaction.response.send_message(
                "❌ Управление кейсами доступно только владельцу сервера или администратору.",
                ephemeral=True
            )
            return

        view = CaseAdminListView(interaction.user.id, interaction.guild.id, interaction.guild)
        await interaction.response.send_message("Загрузка панели кейсов...", ephemeral=True)
        await view.refresh(interaction)