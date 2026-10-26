# modules/admin.py
# Единая админ-панель: команда /admin.
# Разделы: 🛠 Кейсы (открывает проверенную панель case_admin), 🎁 Выдать награды,
# 🔄 Сброс кулдаунов колеса/дейли.
# Все прежние разрозненные админ-команды (/give_*, /reset_*) свёрнуты в это меню.

import logging

import discord
from discord import ui

from database import db, EFFECTS
from .shared import can_manage, make_resilient

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
            await _safe_send(interaction, "❌ Нет доступа.")
            return
        try:
            await interaction.response.send_modal(GiveItemModal(interaction.guild, kind, item_id))
        except discord.NotFound:
            log.warning("Интеракция устарела (404) — модалка не открыта")

    # Коллбэки кнопок/селектов: официальный discord.py вызывает callback(interaction),
    # форки на хостингах — callback(interaction, item). Шим в main.py приводит оба
    # варианта к сигнатуре метода, поэтому здесь канонический вид (self, interaction).
    @ui.button(label="💰 Монеты", style=discord.ButtonStyle.success, custom_id="adm:give:coins")
    async def give_coins(self, interaction: discord.Interaction):
        await self._open_modal(interaction, "coins")

    @ui.button(label="💎 Кристаллы", style=discord.ButtonStyle.primary, custom_id="adm:give:crystals")
    async def give_crystals(self, interaction: discord.Interaction):
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
        "🔄 **Сброс** — сбросить кулдаун колеса или дейли-награды игроку\n"
        "🧹 **Уборка ролей** — удалить все роли сервера без участников\n\n"
        "⬅ Кнопка «Назад» возвращает в это меню из любого раздела."
    )


async def delete_empty_roles(interaction: discord.Interaction):
    """Удалить все роли гильдии, у которых 0 участников.

    Безопасно: пропускаем @everyone, управляющие (managed) роли ботов/интеграций,
    административные роли и роли выше ранга бота (их мы всё равно не удалим).
    """
    guild = interaction.guild
    me = guild.me

    if not me.guild_permissions.manage_roles:
        await interaction.followup.send(
            "❌ У бота нет разрешения **Управлять ролями**.", ephemeral=True)
        return

    protected_names = {"Admin", "Administrator", "Админ", "Модер", "Moderator"}

    candidates = [
        r for r in guild.roles
        if not r.is_default()                      # @everyone
        and not r.managed                          # роли ботов/вебхуков/интеграций
        and len(r.members) == 0                    # нет участников
        and r.name not in protected_names          # не админ-роли
        and r < me.top_role                        # ниже ранга бота
        and r.id != guild.id
    ]

    if not candidates:
        await interaction.followup.send("🧹 Пустых ролей не найдено.", ephemeral=True)
        return

    if len(candidates) > 200:
        candidates = candidates[:200]  # защита от rate limit за один вызов

    deleted, failed = [], []
    for role in candidates:
        try:
            await role.delete(reason=f"Очистка пустых ролей ({interaction.user})")
            deleted.append(role.name)
        except discord.Forbidden:
            failed.append(f"{role.name} (нет прав)")
        except discord.HTTPException as e:
            failed.append(f"{role.name} ({e})")

    lines = [f"✅ Удалено пустых ролей: **{len(deleted)}**"]
    if deleted:
        names = ", ".join(f"`{n}`" for n in deleted[:15])
        more = f" …и ещё {len(deleted) - 15}" if len(deleted) > 15 else ""
        lines.append(names + more)
    if failed:
        lines.append(f"⚠️ Не удалось: {'; '.join(failed[:10])}")

    text = "\n".join(lines)
    for i in range(0, len(text), 1900):
        await interaction.followup.send(text[i:i + 1900], ephemeral=True)


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

    @staticmethod
    def _opt(label: str, value: str, emoji: str = None, description: str = None):
        """discord.ui.SelectOption не существует — только discord.SelectOption."""
        return discord.SelectOption(label=label[:100], value=value,
                                   emoji=emoji, description=(description or "")[:100] or None)

    @ui.button(label="🛠 Кейсы", style=discord.ButtonStyle.primary, custom_id="adm:cases")
    async def cases_btn(self, interaction: discord.Interaction):
        if not self._is_owner(self.user_id, interaction):
            await _safe_send(interaction, "❌ Нет доступа.")
            return
        from .case_admin import CaseAdminListView
        panel = CaseAdminListView(self.user_id, self.guild_id, interaction.guild)
        # добавим кнопку возврата в меню /admin
        panel.add_item(_BackToAdminButton(self.user_id, self.guild_id))
        await _safe_edit(interaction, content=None, embed=None, view=panel)

    @ui.button(label="🎁 Выдать", style=discord.ButtonStyle.success, custom_id="adm:give")
    async def give_btn(self, interaction: discord.Interaction):
        if not self._is_owner(self.user_id, interaction):
            await _safe_send(interaction, "❌ Нет доступа.")
            return
        cases = [dict(c) for c in await db.get_all_cases(self.guild_id, active_only=False)]
        case_opts = [self._opt(c["name"], str(c["id"])) for c in cases[:25]] \
            or [self._opt("— нет кейсов —", "0")]
        eff_opts = [
            self._opt(name, name, emoji=info.get("emoji"))
            for name, info in EFFECTS.items()
        ]
        view = GiveMenu(self.user_id, self.guild_id, cases, EFFECTS)
        view.give_case_sel.options = case_opts
        view.give_key_sel.options = list(case_opts)
        view.give_effect_sel.options = eff_opts
        await _safe_edit(interaction,
                         content="🎁 **Что выдать?** Кнопки — валюта, списки — предметы.",
                         embed=None, view=view)

    @ui.button(label="🔄 Сброс", style=discord.ButtonStyle.danger, custom_id="adm:reset")
    async def reset_btn(self, interaction: discord.Interaction):
        if not self._is_owner(self.user_id, interaction):
            await _safe_send(interaction, "❌ Нет доступа.")
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

        await _safe_modal(interaction, ResetModal())

    @ui.button(label="🧹 Уборка ролей", style=discord.ButtonStyle.secondary, custom_id="adm:cleanroles")
    async def clean_roles_btn(self, interaction: discord.Interaction):
        if not self._is_owner(self.user_id, interaction):
            await _safe_send(interaction, "❌ Нет доступа.")
            return

        class ConfirmClean(ui.Modal, title="Удаление пустых ролей"):
            # label TextInput ограничен 45 символами (Discord API error 50035)
            confirm = ui.TextInput(
                label="Введи DELETE для подтверждения",
                placeholder="Удалятся ВСЕ роли сервера без участников",
                max_length=10, required=True)

            async def on_submit(self, inter: discord.Interaction):
                if self.confirm.value.strip().upper() != "DELETE":
                    await inter.response.send_message("⚠️ Отменено.", ephemeral=True)
                    return
                await inter.response.defer(ephemeral=True, thinking=True)
                await delete_empty_roles(inter)

        await _safe_modal(interaction, ConfirmClean())


def _modal_ok(func):
    """Обёртка коллбэков кнопок/селектов: защищает отSignatureMismatch на разных версиях discord.py.

    Официальный discord.py вызывает callback(self, interaction), форк с хостинга —
    callback(interaction, item). Функция принимает (self, interaction) и сама определяет,
    какой из аргументов настоящий Interaction; внутри — чистый async код без ui-декораторов.
    Возвращает готовый коллбэк для присваивания button.callback / select.callback.
    """
    async def wrapper(a, b=None):
        inter = a if isinstance(a, discord.Interaction) else b
        if inter is None:
            log.error("Коллбэк вызван без Interaction")
            return
        await func(inter)
    return wrapper


async def _safe_modal(interaction: discord.Interaction, modal: ui.Modal):
    try:
        if interaction.response.is_done():
            await interaction.followup.send("⚠️ Интеракция устарела, повтори команду.", ephemeral=True)
        else:
            await interaction.response.send_modal(modal)
    except discord.NotFound:
        log.warning("Интеракция устарела (404) — модалка не открыта")


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
    @make_resilient
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


# ===== Автообёртка всех UI-коллбэков модуля =====
# make_resilient перехватывает исключения и учитывает оба стиля вызова
# коллбэков (official / форк хостинга). Применяем ко ВСЕМ методам callback
# классов View/Item этого модуля — кнопки защищены без ручного декора каждой.
for _cls in list(globals().values()):
    try:
        if isinstance(_cls, type) and issubclass(_cls, discord.ui.View):
            pass
        elif isinstance(_cls, type) and issubclass(_cls, discord.ui.Item):
            pass
        else:
            continue
    except TypeError:
        continue
    for _name, _attr in list(vars(_cls).items()):
        if _name == "callback" and callable(_attr):
            setattr(_cls, _name, make_resilient(_attr))
