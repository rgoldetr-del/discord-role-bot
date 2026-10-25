# modules/admin.py
# Единая админ-панель: команда /admin.
# Разделы: 🛠 Кейсы (открывает проверенную панель case_admin), 🎁 Выдать награды,
# 🔄 Сброс кулдаунов колеса/дейли.
# Все прежние разрозненные админ-команды (/give_*, /reset_*) свёрнуты в это меню.

import logging

import discord
from discord import ui

from database import db
from .shared import can_manage

log = logging.getLogger(__name__)


def find_member(guild: discord.Guild, interaction_msg, raw: str):
    """Найти участника по @mention / ID / имени."""
    raw = raw.strip()
    if interaction_msg and interaction_msg.mentions:
        for m in interaction_msg.mentions:
            if str(m.id) == raw or raw.lower() in (f"@{m.display_name.lower()}", f"<@{m.id}>"):
                return m
    try:
        member = guild.get_member(int(raw))
        if member:
            return member
    except ValueError:
        pass
    return discord.utils.get(guild.members, display_name=raw) \
        or discord.utils.get(guild.members, name=raw)


class GiveItemModal(ui.Modal, title="Выдать предмет"):
    """Модальное окно выдачи: пользователь + количество."""
    target = ui.TextInput(
        label="Пользователь",
        placeholder="@mention, ID или имя",
        max_length=100,
        required=True,
    )
    quantity = ui.TextInput(
        label="Количество",
        placeholder="1",
        max_length=6,
        required=True,
    )

    def __init__(self, guild: discord.Guild, kind: str, item_id: int = None):
        super().__init__()
        self.guild_ref = guild
        self.kind = kind          # coins | crystals | case | key | effect
        self.item_id = item_id    # case_id для case/key

    async def on_submit(self, interaction: discord.Interaction):
        member = find_member(interaction.guild, interaction.message, self.target.value)
        if member is None:
            await interaction.response.send_message("❌ Пользователь не найден.", ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message("❌ Нельзя выдать боту.", ephemeral=True)
            return

        # --- количество ---
        try:
            qty = max(1, min(1_000_000, int(self.quantity.value.strip())))
        except ValueError:
            await interaction.response.send_message("❌ Количество должно быть числом.", ephemeral=True)
            return

        await db.get_or_create_user(member.id, interaction.guild.id)

        if self.kind == "coins":
            new_bal = await db.update_coins(member.id, interaction.guild.id, qty)
            done = f"💰 **{qty}** монет → **{member.mention}** (баланс: {new_bal})"
        elif self.kind == "crystals":
            new_bal = await db.update_crystals(member.id, interaction.guild.id, qty)
            done = f"💎 **{qty}** кристаллов → **{member.mention}** (баланс: {new_bal})"
        elif self.kind == "case":
            await db.add_case(member.id, interaction.guild.id, self.item_id, qty)
            done = f"📦 **{qty}× кейс** → **{member.mention}**"
        elif self.kind == "key":
            await db.add_key(member.id, interaction.guild.id, self.item_id, qty)
            done = f"🔑 **{qty}× ключ** → **{member.mention}**"
        elif self.kind == "effect":
            await db.add_effect_to_inventory(member.id, interaction.guild.id, self.item_id)
            done = f"✨ Эффект → **{member.mention}**"
        else:
            done = "❌ Неизвестный тип."

        await interaction.response.send_message(f"✅ Выдано: {done}", ephemeral=True)


class GiveMenu(ui.View):
    """Подменю «Выдать»: кнопки валют + select кейсов/ключей/эффектов."""

    def __init__(self, user_id: int, guild_id: int, cases, effects: dict):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.cases_list = cases
        self.effects = effects

    def _check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id and can_manage(interaction)

    async def _open_modal(self, interaction: discord.Interaction, kind: str, item_id=None):
        if not self._check(interaction):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=True)
            return
        await interaction.response.send_modal(GiveItemModal(interaction.guild, kind, item_id))

    @ui.button(label="💰 Монеты", style=discord.ButtonStyle.success, custom_id="adm:give:coins")
    async def give_coins(self, interaction: discord.Interaction, button):
        await self._open_modal(interaction, "coins")

    @ui.button(label="💎 Кристаллы", style=discord.ButtonStyle.primary, custom_id="adm:give:crystals")
    async def give_crystals(self, interaction: discord.Interaction, button):
        await self._open_modal(interaction, "crystals")

    @ui.select(placeholder="📦 Выдать кейс…", custom_id="adm:give:case_sel")
    async def give_case_sel(self, interaction: discord.Interaction, select: ui.Select):
        await self._open_modal(interaction, "case", int(select.values[0]))

    @ui.select(placeholder="🔑 Выдать ключ…", custom_id="adm:give:key_sel")
    async def give_key_sel(self, interaction: discord.Interaction, select: ui.Select):
        await self._open_modal(interaction, "key", int(select.values[0]))

    @ui.select(placeholder="✨ Выдать эффект…", custom_id="adm:give:effect_sel")
    async def give_effect_sel(self, interaction: discord.Interaction, select: ui.Select):
        await self._open_modal(interaction, "effect", select.values[0])

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True


async def _safe_send(interaction: discord.Interaction, content=None, *, embed=None, view=None, ephemeral=True):
    """Ответ на интеракцию с защитой от 404 Unknown interaction (просроченный токен)."""
    try:
        if interaction.response.is_done():
            await interaction.followup.send(content=content, embed=embed, view=view, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(content=content, embed=embed, view=view, ephemeral=ephemeral)
    except discord.NotFound:
        log.warning("Интеракция устарела (404) — ответ пропущен")
    except discord.HTTPException:
        log.warning("Не удалось отправить ответ", exc_info=True)


async def _safe_edit(interaction: discord.Interaction, *, content=None, embed=None, view=None):
    try:
        if interaction.response.is_done():
            await interaction.message.edit(content=content, embed=embed, view=view)
        else:
            await interaction.response.edit_message(content=content, embed=embed, view=view)
    except discord.NotFound:
        log.warning("Интеракция устарела (404) — редактирование пропущено")
    except discord.HTTPException:
        log.warning("Не удалось отредактировать сообщение", exc_info=True)

async def show_main_menu(interaction: discord.Interaction):
    embed = discord.Embed(title="🛡 Панель администратора", color=0xE74C3C, description=_main_desc())
    await _safe_edit(interaction, content=None, embed=embed,
                     view=AdminMainView(interaction.user.id, interaction.guild.id))


def _main_desc():
    return (
        "Выбери раздел:\n\n"
        "🛠 **Кейсы** — создание и настройка кейсов (награды, редкости, цены)\n"
        "🎁 **Выдать** — монеты, кристаллы, кейсы, ключи, эффекты любому игроку\n"
        "🔄 **Сброс** — сбросить кулдаун колеса или дейли-награды игроку\n\n"
        "⬅ Кнопка «Назад» возвращает в это меню из любого раздела."
    )


class AdminMainView(ui.View):
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id

    @staticmethod
    def _is_owner(user_id: int, interaction: discord.Interaction) -> bool:
        return interaction.user.id == user_id and can_manage(interaction)

    async def _respond_denied(self, interaction: discord.Interaction, button=None):
        try:
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=True)
        except discord.HTTPException:
            pass

    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        # защитный обработчик: не «глушить» view при ошибке кнопки
        log.exception("Ошибка кнопки админ-панели", exc_info=error)

    @ui.button(label="🛠 Кейсы", style=discord.ButtonStyle.primary, custom_id="adm:cases")
    async def cases_btn(self, interaction: discord.Interaction, button):
        if not self._is_owner(self.user_id, interaction):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=True)
            return
        from .case_admin import CaseAdminListView
        panel = CaseAdminListView(self.user_id, self.guild_id, interaction.guild)
        # добавим кнопку возврата в меню /admin
        panel.add_item(_BackToAdminButton(self.user_id, self.guild_id))
        await interaction.response.edit_message(content=None, embed=None, view=panel)

    @ui.button(label="🎁 Выдать", style=discord.ButtonStyle.success, custom_id="adm:give")
    async def give_btn(self, interaction: discord.Interaction, button):
        if not self._is_owner(self.user_id, interaction):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=True)
            return
        cases = [dict(c) for c in await db.get_all_cases(self.guild_id, active_only=False)]
        case_opts = [ui.SelectOption(label=c["name"][:100], value=str(c["id"])) for c in cases[:25]] \
            or [ui.SelectOption(label="— нет кейсов —", value="0")]
        eff_opts = [
            ui.SelectOption(label=f"{info.get('emoji', '✨')} {name}"[:100], value=name)
            for name, info in db.EFFECTS.items()
        ]
        view = GiveMenu(self.user_id, self.guild_id, cases, db.EFFECTS)
        view.give_case_sel.options = case_opts
        view.give_key_sel.options = case_opts
        view.give_effect_sel.options = eff_opts
        await _safe_edit(interaction,
                         content="🎁 **Что выдать?** Кнопки — валюта, списки — предметы.",
                         embed=None, view=view)

    @ui.button(label="🔄 Сброс", style=discord.ButtonStyle.danger, custom_id="adm:reset")
    async def reset_btn(self, interaction: discord.Interaction, button):
        if not self._is_owner(self.user_id, interaction):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=True)
            return

        class ResetModal(ui.Modal, title="Сброс кулдаунов"):
            target = ui.TextInput(label="Пользователь (@mention / ID / имя)", max_length=100, required=True)
            what = ui.TextInput(label="Что сбросить: wheel / daily / all", max_length=10, required=True)

            async def on_submit(self, inter: discord.Interaction):
                member = find_member(inter.guild, inter.message, self.target.value)
                if member is None:
                    await inter.response.send_message("❌ Пользователь не найден.", ephemeral=True)
                    return

                what = self.what.value.strip().lower()
                done = []
                if what in ("wheel", "all"):
                    await db.reset_wheel_cooldown(member.id, inter.guild.id)
                    done.append("🎡 колесо")
                if what in ("daily", "all"):
                    await db.reset_daily(member.id, inter.guild.id)
                    done.append("💼 дейли")
                if not done:
                    await inter.response.send_message("❌ Укажи: wheel / daily / all.", ephemeral=True)
                    return
                await inter.response.send_message(
                    f"✅ Сброшено {', '.join(done)} для {member.mention}.", ephemeral=True)

        await interaction.response.send_modal(ResetModal())


class _BackToAdminButton(ui.Button):
    """Кнопка возврата из встроенной панели кейсов в главное меню /admin."""

    def __init__(self, user_id: int, guild_id: int):
        super().__init__(label="⬅ В меню /admin", style=discord.ButtonStyle.secondary,
                         custom_id="adm:back_main")
        self.user_id = user_id
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or not can_manage(interaction):
            await interaction.response.send_message("❌ Нет доступа.", ephemeral=True)
            return
        await show_main_menu(interaction)


def register(bot):
    # /admin заменяет собой старую команду /case_admin:
    # панель кейсов открывается из меню, отдельная команда не нужна.
    try:
        bot.tree.remove_command("case_admin")
    except Exception:
        pass

    @bot.tree.command(name="admin", description="Единая админ-панель: кейсы, выдача, сбросы")
    async def admin(interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
            return
        if not can_manage(interaction):
            await interaction.response.send_message(
                "❌ Доступно только владельцу сервера или администратору.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🛡 Панель администратора",
            description=_main_desc(),
            color=0xE74C3C,
        )
        embed.set_footer(text=f"Запросил: {interaction.user.display_name}")
        await _safe_send(interaction, embed=embed,
                         view=AdminMainView(interaction.user.id, interaction.guild.id))
