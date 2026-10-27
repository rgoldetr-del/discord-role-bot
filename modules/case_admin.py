# modules/case_admin.py
# Админ-панель кейсов: создание, настройка, редкости, роли, удаление.
# Версия без декорированных @ui.button кнопок в списке кейсов.
# Все кнопки создаются вручную внутри refresh(), чтобы избежать проблем
# с форком discord.py и 404 Unknown interaction.

import uuid

import asyncio
import time
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
from .shared import can_manage as can_manage_cases, make_resilient

async def _preset_safe_create_role(
    guild: discord.Guild,
    roles_by_name: dict,
    base_name: str,
    color_hex: int,
    reason: str,
    prefix: str,
    progress
):
    base_name = base_name[:100]

    role = roles_by_name.get(base_name)
    if role is not None:
        print(f"[preset] reuse role: {base_name}")
        return role, None, False

    final_name = base_name
    counter = 2
    while final_name in roles_by_name:
        final_name = f"{base_name} {counter}"[:100]
        counter += 1

    for attempt in range(6):
        try:
            print(f"[preset] create role attempt {attempt + 1}: {final_name}")
            # ВАЖНО: без asyncio.wait_for. Раньше он обрывал внутреннее ожидание
            # рейт-лимита дискорда на 25-й секунде, и все следующие роли висли.
            # Теперь даём библиотеке самой дождаться конца кулдауна.
            role = await guild.create_role(
                name=final_name,
                colour=discord.Colour(color_hex),
                permissions=discord.Permissions.none(),
                hoist=False,
                mentionable=False,
                reason=reason
            )
            roles_by_name[role.name] = role
            print(f"[preset] created role: {role.name} ({role.id})")
            return role, None, True

        except discord.Forbidden:
            print("[preset] Forbidden: нет прав на создание роли")
            return None, "нет прав", False

        except discord.HTTPException as e:
            status = getattr(e, "status", None)
            retry_after = getattr(e, "retry_after", None)

            # 429 = дискорд сам сказал, сколько ждать
            if status == 429 or retry_after is not None:
                try:
                    delay = float(retry_after) + 1.0
                except Exception:
                    delay = 15.0
                delay = min(max(delay, 3.0), 120.0)
                print(f"[preset] 429 rate limit, sleeping {delay:.1f}s")
                try:
                    await progress(f"{prefix}\n⏳ Лимит ролей, жду {int(delay)} сек...")
                except Exception:
                    pass
                await asyncio.sleep(delay)
                continue

            # прочая ошибка — увеличивающийся откат
            delay = 5.0 + attempt * 5.0
            print(f"[preset] HTTPException {status}: {e}, retry in {delay:.0f}s")
            await asyncio.sleep(delay)

        except Exception as e:
            print(f"[preset] unexpected error: {e!r}")
            await asyncio.sleep(5.0)

    return None, "роль не создана", False

async def _install_presets_safe(interaction: discord.Interaction):
    """Безопасная установка пресета кейсов.

    - делает паузы между созданием ролей;
    - повторяет попытку при rate limit;
    - пропускает кейсы, которые уже существуют;
    - повторно использует роли с теми же именами;
    - не убивает всю установку из-за одной ошибки роли.
    """
    if not interaction.guild:
        try:
            await interaction.response.send_message("Только на сервере.", ephemeral=True)
        except discord.HTTPException:
            pass
        return

    if not can_manage_cases(interaction):
        try:
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
        except discord.HTTPException:
            pass
        return

    if not interaction.guild.me.guild_permissions.manage_roles:
        try:
            await interaction.response.send_message(
                "❌ У бота нет права «Управлять ролями».",
                ephemeral=True
            )
        except discord.HTTPException:
            pass
        return

    from .auto_roles import PRESET_CASES, RARITY_COLORS

    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                "⏳ Начинаю установку пресета. Это может занять 1-3 минуты.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "⏳ Начинаю установку пресета. Это может занять 1-3 минуты.",
                ephemeral=True
            )
    except discord.HTTPException:
        return

    async def progress(text: str):
        try:
            await interaction.edit_original_response(content=text[:2000])
        except discord.HTTPException:
            pass

    async def finish(text: str):
        try:
            await interaction.edit_original_response(content=text[:2000])
        except discord.HTTPException:
            try:
                await interaction.followup.send(text[:2000], ephemeral=True)
            except discord.HTTPException:
                pass

        if len(text) > 2000:
            for i in range(2000, len(text), 1900):
                try:
                    await interaction.followup.send(text[i:i + 1900], ephemeral=True)
                except discord.HTTPException:
                    break

    if not PRESET_CASES:
        await finish("❌ В файле presets_data.py нет PRESET_CASES.")
        return

    if len(PRESET_CASES) <= 2:
        await progress(
            f"⚠️ В пресете только {len(PRESET_CASES)} кейсов. "
            "Похоже, файл presets_data.py сохранён не полностью. Продолжаю..."
        )

    guild = interaction.guild
    roles_by_name = {r.name: r for r in guild.roles}

    existing_cases = {
        c["name"]
        for c in [dict(row) for row in await db.get_all_cases(guild.id, active_only=False)]
    }

    async def get_or_create_role(base_name: str, color_hex: int, reason: str):
        base_name = base_name[:100]

        role = roles_by_name.get(base_name)
        if role is not None:
            return role, None

        final_name = base_name
        counter = 2
        while final_name in roles_by_name:
            final_name = f"{base_name} {counter}"[:100]
            counter += 1

        for attempt in range(8):
            try:
                role = await guild.create_role(
                    name=final_name,
                    colour=discord.Colour(color_hex),
                    permissions=discord.Permissions.none(),
                    hoist=False,
                    mentionable=False,
                    reason=reason
                )
                roles_by_name[role.name] = role
                return role, None
            except discord.Forbidden:
                return None, "нет прав"
            except discord.HTTPException as e:
                retry_after = getattr(e, "retry_after", None)
                try:
                    delay = float(retry_after) + 0.25 if retry_after else 1.2 + attempt
                except Exception:
                    delay = 1.2 + attempt
                await asyncio.sleep(min(max(delay, 0.5), 30.0))

        return None, "rate limit"

    created_cases = 0
    skipped_cases = 0
    linked_roles = 0
    errors = []

    for index, preset in enumerate(PRESET_CASES, start=1):
        name = preset.get("name", f"Кейс {index}")

        if name in existing_cases:
            skipped_cases += 1
            await progress(f"⏳ {index}/{len(PRESET_CASES)} • {name} пропущен, уже существует")
            continue

        rarities = []
        for r in preset.get("rarities", []):
            rr = dict(r)
            rr["roles"] = list(r.get("roles", []))
            rarities.append(rr)

        total_chance = sum(int(rr.get("chance", 0)) for rr in rarities)
        if total_chance != 100:
            for rr in rarities:
                if rr.get("rarity") == "common":
                    rr["chance"] = max(0, int(rr.get("chance", 0)) + (100 - total_chance))
                    break

        case_id = await db.create_case_return_id(
            guild.id,
            name,
            preset.get("case_rarity", "common"),
            int(preset.get("case_price", 0)),
            int(preset.get("key_price", 0)),
            case_crystal_price=int(preset.get("case_crystal_price", 0)),
            key_crystal_price=int(preset.get("key_crystal_price", 0)),
            is_free=1 if preset.get("free") else 0,
            active=False
        )

        forbidden_stop = False

        for rr in rarities:
            rarity_id = await db.add_rarity_return_id(
                case_id,
                rr.get("rarity", "common"),
                int(rr.get("chance", 0)),
                int(rr.get("price", 0))
            )

            for role_name in rr.get("roles", []):
                role, err = await get_or_create_role(
                    role_name,
                    RARITY_COLORS.get(rr.get("rarity", "common"), 0x808080),
                    f"Пресет кейса {name}"
                )

                if role is None:
                    errors.append(f"{name} / {rr.get('rarity')} / {role_name}: {err}")

                    if err == "нет прав":
                        forbidden_stop = True
                        break

                    continue

                await db.add_roles_to_case_rarity(rarity_id, [role.id])
                linked_roles += 1

                # Пауза от rate limit Discord.
                await asyncio.sleep(0.75)

            if forbidden_stop:
                break

        if forbidden_stop:
            await finish("❌ У бота нет права создавать роли. Установка остановлена.")
            return

        act = await db.activate_case(case_id)
        created_cases += 1

        if act["success"]:
            await progress(
                f"⏳ {index}/{len(PRESET_CASES)} • создано кейсов: {created_cases}, "
                f"ролей: {linked_roles}"
            )
        else:
            errors.append(f"{name}: кейс не активирован")
            await progress(f"⚠️ {index}/{len(PRESET_CASES)} • {name} не активирован")

    lines = [
        "🎉 Установка пресета завершена.",
        f"Всего кейсов в пресете: {len(PRESET_CASES)}",
        f"Создано новых кейсов: {created_cases}",
        f"Пропущено существующих: {skipped_cases}",
        f"Ролей создано/привязано: {linked_roles}",
    ]

    if errors:
        lines.append(f"Ошибок: {len(errors)}")
        lines.extend(errors[:10])
        if len(errors) > 10:
            lines.append(f"... и ещё {len(errors) - 10}")

    await finish("\n".join(lines))

# ======================================================================
# МОДАЛКИ
# ======================================================================

class CreateCaseModal(ui.Modal, title="Создать кейс"):
    def __init__(self, view):
        super().__init__(custom_id=f"create_case_modal_{uuid.uuid4().hex[:8]}")
        self.view_ref = view

        self.name_input = ui.TextInput(
            label="Название кейса",
            placeholder="Например: 👑 Король Слизней",
            max_length=100,
            required=True
        )
        self.rarity_input = ui.TextInput(
            label="Редкость кейса",
            placeholder="common / uncommon / rare / epic / legendary / secret / secret+",
            max_length=20,
            required=True
        )
        self.case_price_input = ui.TextInput(
            label="Цена кейса (монеты)",
            placeholder="0 = бесплатно",
            max_length=12,
            required=True
        )
        self.key_price_input = ui.TextInput(
            label="Цена ключа (монеты)",
            placeholder="0 = бесплатно",
            max_length=12,
            required=True
        )

        self.add_item(self.name_input)
        self.add_item(self.rarity_input)
        self.add_item(self.case_price_input)
        self.add_item(self.key_price_input)

    async def on_submit(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.view_ref.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        rarity_key = self.rarity_input.value.strip().lower()
        if rarity_key not in RARITY_NAME:
            await interaction.response.send_message(
                "❌ Неверная редкость кейса. Доступны: " + ", ".join(RARITY_NAME.keys()),
                ephemeral=True
            )
            return

        try:
            case_price = int(self.case_price_input.value.strip())
            key_price = int(self.key_price_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Цены должны быть числами.", ephemeral=True)
            return

        if case_price < 0 or key_price < 0:
            await interaction.response.send_message(
                "❌ Цены не могут быть отрицательными (0 — разрешено).",
                ephemeral=True
            )
            return

        await db.create_case_return_id(
            interaction.guild.id,
            self.name_input.value.strip(),
            rarity_key,
            case_price,
            key_price,
            case_crystal_price=0,
            key_crystal_price=0,
            is_free=0,
            active=False
        )

        await interaction.response.send_message(
            "✅ Кейс создан.\n"
            "Кристальные цены, редкость и признак бесплатного кейса можно изменить в настройках кейса.",
            ephemeral=True
        )
        await self.view_ref.refresh_message(getattr(interaction, "message", None))


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
            label="Цена кейса (монеты)",
            placeholder="0 = бесплатно / недоступно",
            default=str(case["case_price"]),
            max_length=12,
            required=True,
            custom_id=f"case_price_{uuid.uuid4().hex[:6]}"
        )
        self.key_price_input = ui.TextInput(
            label="Цена ключа (монеты)",
            placeholder="0 = бесплатно / недоступно",
            default=str(case["key_price"]),
            max_length=12,
            required=True,
            custom_id=f"key_price_{uuid.uuid4().hex[:6]}"
        )
        self.case_crystal_input = ui.TextInput(
            label="Цена кейса (кристаллы)",
            placeholder="0 = кристаллы выключены",
            default=str(case.get("case_crystal_price") or 0),
            max_length=12,
            required=True,
            custom_id=f"case_cry_{uuid.uuid4().hex[:6]}"
        )
        self.key_crystal_input = ui.TextInput(
            label="Цена ключа (кристаллы)",
            placeholder="0 = кристаллы выключены",
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

    async def on_submit(self, interaction: discord.Interaction, *_):
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
                "❌ Цены не могут быть отрицательными (0 — разрешено).",
                ephemeral=True
            )
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
        await self.view_ref.refresh_message(getattr(interaction, "message", None))


class CaseMetaModal(ui.Modal, title="Редкость и тип кейса"):
    def __init__(self, view, case):
        super().__init__(custom_id=f"case_meta_modal_{uuid.uuid4().hex[:8]}")
        self.view_ref = view

        self.rarity_input = ui.TextInput(
            label="Редкость кейса",
            default=case["case_rarity"],
            placeholder="common / uncommon / rare / epic / legendary / secret / secret+",
            max_length=20,
            required=True
        )
        self.free_input = ui.TextInput(
            label="Бесплатный кейс? (0 или 1)",
            default=str(case.get("is_free") or 0),
            max_length=1,
            required=True
        )

        self.add_item(self.rarity_input)
        self.add_item(self.free_input)

    async def on_submit(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.view_ref.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        rarity = self.rarity_input.value.strip().lower()
        if rarity not in RARITY_NAME:
            await interaction.response.send_message(
                "❌ Неверная редкость. Доступны: " + ", ".join(RARITY_NAME.keys()),
                ephemeral=True
            )
            return

        try:
            is_free = int(self.free_input.value.strip())
            if is_free not in (0, 1):
                raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Бесплатный кейс: введи 0 или 1.", ephemeral=True)
            return

        try:
            await db.db.execute(
                "UPDATE cases SET case_rarity = ?, is_free = ? WHERE id = ?",
                (rarity, is_free, self.view_ref.case_id)
            )
            await db.db.commit()
        except Exception:
            await interaction.response.send_message("❌ Не удалось сохранить изменения.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Редкость и тип кейса сохранены.", ephemeral=True)
        await self.view_ref.refresh_message(getattr(interaction, "message", None))


class AddRarityModal(ui.Modal, title="Добавить редкость"):
    def __init__(self, view):
        super().__init__(custom_id=f"add_rarity_modal_{uuid.uuid4().hex[:8]}")
        self.view_ref = view

        self.rarity_input = ui.TextInput(
            label="Редкость",
            placeholder="common / uncommon / rare / epic / legendary / secret / secret+",
            max_length=20,
            required=True
        )
        self.drop_chance_input = ui.TextInput(
            label="Шанс выпадения, %",
            placeholder="Например: 40",
            max_length=3,
            required=True
        )
        self.sell_price_input = ui.TextInput(
            label="Рыночная цена роли",
            placeholder="Например: 100",
            max_length=12,
            required=True
        )

        self.add_item(self.rarity_input)
        self.add_item(self.drop_chance_input)
        self.add_item(self.sell_price_input)

    async def on_submit(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.view_ref.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        rarity_key = self.rarity_input.value.strip().lower()
        if rarity_key not in RARITY_NAME:
            await interaction.response.send_message(
                "❌ Неверная редкость. Доступны: " + ", ".join(RARITY_NAME.keys()),
                ephemeral=True
            )
            return

        try:
            chance = int(self.drop_chance_input.value.strip())
            sell_price = int(self.sell_price_input.value.strip())
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
        await self.view_ref.refresh_message(getattr(interaction, "message", None))


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

    async def on_submit(self, interaction: discord.Interaction, *_):
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
        await self.view_ref.refresh_message(getattr(interaction, "message", None))


class AddRoleModal(ui.Modal, title="Добавить роль в редкость"):
    def __init__(self, view):
        super().__init__(custom_id=f"add_role_modal_{uuid.uuid4().hex[:8]}")
        self.view_ref = view

        self.role_input = ui.TextInput(
            label="Роль",
            placeholder="@роль, имя роли или ID роли",
            max_length=100,
            required=True
        )
        self.add_item(self.role_input)

    async def on_submit(self, interaction: discord.Interaction, *_):
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
        await self.view_ref.refresh_message(getattr(interaction, "message", None))


class DeleteCaseModal(ui.Modal, title="Удаление кейса"):
    def __init__(self, view):
        super().__init__(custom_id=f"delete_case_modal_{uuid.uuid4().hex[:8]}")
        self.view_ref = view

        self.confirm_input = ui.TextInput(
            label="Подтверждение",
            placeholder="Введи DELETE для удаления",
            required=True,
            max_length=10
        )
        self.add_item(self.confirm_input)

    async def on_submit(self, interaction: discord.Interaction, *_):
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

        view = CaseAdminListView(
            self.view_ref.user_id,
            self.view_ref.guild_id,
            self.view_ref.guild
        )
        await view.refresh_message(getattr(interaction, "message", None))


PRESET_INSTALL_LOCKS: dict[int, float] = {}


class DeleteAllCasesModal(ui.Modal, title="Удалить все кейсы"):
    def __init__(self, view):
        super().__init__(custom_id=f"delete_all_cases_modal_{uuid.uuid4().hex[:8]}")
        self.view_ref = view

        self.confirm_input = ui.TextInput(
            label="Введи DELETEALL",
            placeholder="Удалятся ВСЕ кейсы сервера",
            max_length=20,
            required=True
        )
        self.add_item(self.confirm_input)

    async def on_submit(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.view_ref.user_id or not can_manage_cases(interaction):
            try:
                await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            except discord.HTTPException:
                pass
            return

        if self.confirm_input.value.strip().upper() != "DELETEALL":
            try:
                await interaction.response.send_message("❌ Удаление отменено.", ephemeral=True)
            except discord.HTTPException:
                pass
            return

        try:
            await interaction.response.send_message("⏳ Удаляю все кейсы...", ephemeral=True)
        except discord.HTTPException:
            return

        cases = await db.get_all_cases(self.view_ref.guild_id, active_only=False)
        deleted = 0
        errors = 0

        for case in cases:
            try:
                if await db.delete_case(case["id"]):
                    deleted += 1
                else:
                    errors += 1
            except Exception:
                errors += 1

        try:
            await interaction.edit_original_response(
                content=f"✅ Удалено кейсов: **{deleted}**.\nОшибок: **{errors}**."
            )
        except discord.HTTPException:
            pass

        await self.view_ref.refresh_message(getattr(interaction, "message", None))


async def _install_presets_background(interaction: discord.Interaction):
    """Безопасная установка пресета кейсов."""
    guild = interaction.guild
    if guild is None:
        return

    if not can_manage_cases(interaction):
        try:
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
        except discord.HTTPException:
            pass
        return

    if not guild.me.guild_permissions.manage_roles:
        try:
            await interaction.response.send_message(
                "❌ У бота нет права «Управлять ролями».",
                ephemeral=True
            )
        except discord.HTTPException:
            pass
        return

    now = time.time()
    started = PRESET_INSTALL_LOCKS.get(guild.id)

    if started is not None and now - started < 1800:
        try:
            await interaction.response.send_message(
                "⏳ Установка пресета уже запущена. Подожди завершения.",
                ephemeral=True
            )
        except discord.HTTPException:
            pass
        return

    PRESET_INSTALL_LOCKS[guild.id] = now
    finish = None

    try:
        try:
            await interaction.response.send_message(
                "⏳ Запускаю установку пресета. Статус будет в канале.",
                ephemeral=True
            )
        except discord.HTTPException:
            pass

        status = None
        channel = interaction.channel

        if channel is not None:
            try:
                status = await channel.send("⏳ Устанавливаю пресет кейсов...")
            except discord.HTTPException:
                status = None

        async def progress(text: str):
            nonlocal status

            if status is not None:
                try:
                    await status.edit(content=text[:2000])
                    return
                except discord.HTTPException:
                    status = None

            if channel is not None:
                try:
                    status = await channel.send(text[:2000])
                except discord.HTTPException:
                    pass

        async def finish(text: str):
            nonlocal status

            if status is not None:
                try:
                    await status.edit(content=text[:2000])
                    if len(text) <= 2000:
                        return
                except discord.HTTPException:
                    status = None

            start = 2000 if status is not None else 0

            if channel is not None:
                for i in range(start, len(text), 1900):
                    try:
                        await channel.send(text[i:i + 1900])
                    except discord.HTTPException:
                        break
            else:
                for i in range(0, len(text), 1900):
                    try:
                        await interaction.followup.send(text[i:i + 1900], ephemeral=True)
                    except discord.HTTPException:
                        break

        from .auto_roles import PRESET_CASES, RARITY_COLORS

        if not PRESET_CASES:
            await finish("❌ В presets_data.py нет PRESET_CASES.")
            return

        roles_by_name = {r.name: r for r in guild.roles}

        existing_cases = {
            c["name"]: c
            for c in [dict(row) for row in await db.get_all_cases(guild.id, active_only=False)]
        }

        async def get_or_create_role(base_name: str, color_hex: int, reason: str, prefix: str):
            return await _preset_safe_create_role(
                guild,
                roles_by_name,
                base_name,
                color_hex,
                reason,
                prefix,
                progress
            )

        created_cases = 0
        skipped_cases = 0
        linked_roles = 0
        errors = []
        total_presets = len(PRESET_CASES)

        for index, preset in enumerate(PRESET_CASES, start=1):
            name = preset.get("name", f"Кейс {index}")

            if name in existing_cases:
                skipped_cases += 1
                await progress(f"⏳ {index}/{total_presets} • {name} пропущен, уже существует")
                continue

            rarities = []
            for r in preset.get("rarities", []):
                rr = dict(r)
                rr["roles"] = list(r.get("roles", []))
                rarities.append(rr)

            total_chance = sum(int(rr.get("chance", 0)) for rr in rarities)
            if total_chance != 100:
                for rr in rarities:
                    if rr.get("rarity") == "common":
                        rr["chance"] = max(
                            0,
                            int(rr.get("chance", 0)) + (100 - total_chance)
                        )
                        break

            await progress(f"⏳ {index}/{total_presets} • создаю кейс {name}")

            case_id = await db.create_case_return_id(
                guild.id,
                name,
                preset.get("case_rarity", "common"),
                int(preset.get("case_price", 0)),
                int(preset.get("key_price", 0)),
                case_crystal_price=int(preset.get("case_crystal_price", 0)),
                key_crystal_price=int(preset.get("key_crystal_price", 0)),
                is_free=1 if preset.get("free") else 0,
                active=False
            )

            existing_cases[name] = {"id": case_id, "is_active": True}

            roles_total = sum(len(rr.get("roles", [])) for rr in rarities)
            roles_done = 0
            forbidden_stop = False

            for rr in rarities:
                rarity_id = await db.add_rarity_return_id(
                    case_id,
                    rr.get("rarity", "common"),
                    int(rr.get("chance", 0)),
                    int(rr.get("price", 0))
                )

                for role_name in rr.get("roles", []):
                    roles_done += 1

                    prefix = (
                        f"⏳ {index}/{total_presets} • {name}\n"
                        f"Роль {roles_done}/{roles_total}: {role_name}"
                    )

                    await progress(prefix)

                    role, err, created = await get_or_create_role(
                        role_name,
                        RARITY_COLORS.get(rr.get("rarity", "common"), 0x808080),
                        f"Пресет кейса {name}",
                        prefix
                    )

                    if role is None:
                        errors.append(f"{name} / {rr.get('rarity')} / {role_name}: {err}")

                        if err == "нет прав":
                            forbidden_stop = True
                            break

                        continue

                    await db.add_roles_to_case_rarity(rarity_id, [role.id])
                    linked_roles += 1

                    if created:
                        await asyncio.sleep(0.8)

                if forbidden_stop:
                    break

            if forbidden_stop:
                await finish("❌ У бота нет права создавать роли. Установка остановлена.")
                return

            print(f"[preset] case {name}: roles done, activating")
            act = await db.activate_case(case_id)
            print(f"[preset] case {name}: activate success={act.get('success')}")
            created_cases += 1

            if act["success"]:
                await progress(f"✅ {index}/{total_presets} • {name} создан и активирован")
            else:
                errors.append(f"{name}: не активирован")
                await progress(f"⚠️ {index}/{total_presets} • {name} создан, но не активирован")

        lines = [
            "🎉 Установка пресета завершена.",
            f"Всего кейсов в пресете: {total_presets}",
            f"Создано новых кейсов: {created_cases}",
            f"Пропущено существующих: {skipped_cases}",
            f"Ролей создано/привязано: {linked_roles}",
        ]

        if errors:
            lines.append(f"Ошибок: {len(errors)}")
            lines.extend(errors[:10])
            if len(errors) > 10:
                lines.append(f"... и ещё {len(errors) - 10}")

        await finish("\n".join(lines))

    except Exception as e:
        try:
            if finish is not None:
                await finish(f"❌ Установка прервалась ошибкой: {e!r}")
        except Exception:
            pass
    finally:
        PRESET_INSTALL_LOCKS.pop(guild.id, None)



# ======================================================================
# СПИСОК КЕЙСОВ
# ======================================================================

class CaseAdminListView(ui.View):
    def __init__(self, user_id: int, guild_id: int, guild: discord.Guild):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.guild = guild
        self.page = 0
        self.per_page = 8
        self._add_top_buttons()

    def _add_top_buttons(self):
        create_btn = ui.Button(
            style=discord.ButtonStyle.success,
            label="➕ Создать кейс",
            custom_id=f"ca_create_{self.guild_id}_{self.user_id}"
        )
        create_btn.callback = self.create_callback
        self.add_item(create_btn)

    @ui.button(label="⚡ Готовые пресеты", style=discord.ButtonStyle.primary, custom_id="ca:preset")
    async def preset_btn(self, interaction: discord.Interaction):
        """Создать готовые кейсы с редкостями и ролями + полная валидация каждого шага."""
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ У бота нет права «Управлять ролями».", ephemeral=True)
            return

        from .auto_roles import PRESET_CASES, RARITY_COLORS
        await interaction.response.defer(ephemeral=True)

        async def create_role_with_retry(guild, name, color, reason, attempts=3):
            """Создание роли с ретраем при 429 (лимит)."""
            for attempt in range(attempts):
                try:
                    return await guild.create_role(
                        name=name,
                        colour=discord.Colour(color),
                        permissions=discord.Permissions.none(),
                        hoist=False,
                        mentionable=False,
                        reason=reason,
                    )
                except discord.HTTPException as e:
                    if getattr(e, "status", None) == 429:
                        retry_after = getattr(e, "retry_after", None) or 2
                        await asyncio.sleep(float(retry_after) + 0.5)
                        continue
                    raise
            return None

        guild = interaction.guild
        report_ok, report_skip, report_err = [], [], []

        # имена уже существующих кейсов — чтобы не плодить дубли при повторном нажатии
        existing_cases = await db.get_all_cases(guild.id, active_only=False)
        existing_names = {c["name"] for c in [dict(x) for x in existing_cases]}
        existing_role_names = {r.name for r in guild.roles}

        for preset in PRESET_CASES:
            name = preset["name"]

            # 0) защита от дублей
            if name in existing_names:
                report_skip.append(f"⏭️ {name} — уже существует, пропускаю")
                continue

            # нормализация шансов до 100
            rarities = []
            for r in preset["rarities"]:
                rr = dict(r)
                rr["roles"] = list(r.get("roles", []))
                rarities.append(rr)
            total_chance = sum(int(r.get("chance", 0)) for r in rarities)
            if total_chance != 100:
                for r in rarities:
                    if r["rarity"] == "common":
                        r["chance"] = int(r.get("chance", 0)) + (100 - total_chance)
                        break

            # 1) создаём кейс и проверяем, что он реально создан
            case_id = await db.create_case_return_id(
                guild.id, name, preset["case_rarity"],
                preset["case_price"], preset["key_price"],
                is_free=1 if preset.get("free") else 0,
                active=False,
            )
            case_check = await db.get_case_details(case_id) if case_id else None
            if not case_id or not case_check:
                report_err.append(f"❌ {name}: кейс не создан в БД")
                continue

            case_failed = False
            for rarity in rarities:
                # 2) создаём редкость и проверяем
                rarity_id = await db.add_rarity_return_id(
                    case_id, rarity["rarity"], int(rarity["chance"]), int(rarity["price"])
                )
                rarity_check = await db.get_case_rarity_details(rarity_id) if rarity_id else None
                if not rarity_id or not rarity_check:
                    report_err.append(f"❌ {name}: редкость {rarity['rarity']} не создана")
                    case_failed = True
                    break

                # 3) создаём и привязываем роли
                for role_name in rarity["roles"]:
                    final_name, counter = role_name, 2
                    while final_name in existing_role_names:
                        final_name = f"{role_name} {counter}"
                        counter += 1

                    try:
                        role = await create_role_with_retry(
                            guild, final_name,
                            RARITY_COLORS.get(rarity["rarity"], 0x808080),
                            f"Пресет кейса {name}",
                        )
                    except discord.Forbidden:
                        report_err.append(f"❌ {name}: нет прав создать роль {final_name}")
                        case_failed = True
                        break
                    except discord.HTTPException as e:
                        report_err.append(f"❌ {name}: ошибка создания роли {final_name}: {e}")
                        case_failed = True
                        break

                    if role is None or not getattr(role, "id", None):
                        report_err.append(f"❌ {name}: роль {final_name} не создана (лимит/429)")
                        case_failed = True
                        break

                    existing_role_names.add(final_name)

                    # привязка роли к редкости
                    await db.add_roles_to_case_rarity(rarity_id, [role.id])

                    # 4) проверяем, что роль реально привязалась к редкости
                    rarity_after = await db.get_case_rarity_details(rarity_id)
                    if not rarity_after or role.id not in rarity_after.get("roles", []):
                        report_err.append(
                            f"❌ {name}: роль {final_name} создана, но НЕ привязалась к {rarity['rarity']}"
                        )
                        case_failed = True
                        break

                    # пауза, чтобы не упереться в лимит создания ролей
                    await asyncio.sleep(0.5)

                if case_failed:
                    break

            if case_failed:
                # битый кейс не активируем — он останется в списке «не активен»
                continue

            # 5) финальная валидация и активация
            act = await db.activate_case(case_id)
            if act["success"]:
                report_ok.append(f"✅ {name} — создан, роли привязаны, активирован")
            else:
                report_err.append(
                    f"⚠️ {name} — создан, но НЕ активирован: {'; '.join(act.get('details', []))}"
                )

        lines = []
        if report_ok:
            lines.append("**Готово:**")
            lines.extend(report_ok)
        if report_skip:
            lines.append("**Пропущено:**")
            lines.extend(report_skip)
        if report_err:
            lines.append("**Ошибки:**")
            lines.extend(report_err)
        if not lines:
            lines.append("Пресеты пусты.")

        text = "\n".join(lines)
        # разбиваем длинный отчёт на части по 1900 символов
        for i in range(0, len(text), 1900):
            await interaction.followup.send(text[i:i + 1900], ephemeral=True)

    async def refresh(self, interaction: discord.Interaction):
        cases = await self._load_cases()
        embed = self._build(cases, include_back=True)
        await deliver_message(interaction, embed=embed, view=self)

    async def refresh_message(self, message):
        if message is None:
            return

        try:
            cases = await self._load_cases()
            embed = self._build(cases, include_back=True)
            await message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass

    async def create_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        await interaction.response.send_modal(CreateCaseModal(self))

    async def refresh_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        await self.refresh(interaction)

    async def preset_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        panel_message = getattr(interaction, "message", None)
        await _install_presets_background(interaction)
        await self.refresh_message(panel_message)

    async def gen_all_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "❌ У бота нет права «Управлять ролями».",
                ephemeral=True
            )
            return

        try:
            await interaction.response.send_message(
                "⏳ Генерирую роли для всех кейсов...",
                ephemeral=True
            )
        except discord.HTTPException:
            return

        from .auto_roles import generate_roles_for_case

        cases = await db.get_all_cases(self.guild_id, active_only=False)
        total = 0
        errors = []

        for case in cases:
            try:
                created, error = await generate_roles_for_case(interaction.guild, case["id"])
                total += created
                if error:
                    errors.append(f"{case['name']}: {error}")
            except Exception as e:
                errors.append(f"{case['name']}: {e}")

            await asyncio.sleep(0.5)

        msg = f"✅ Всего создано ролей: **{total}**"
        if errors:
            msg += "\n⚠️ Ошибки:\n" + "\n".join(errors[:10])

        try:
            await interaction.edit_original_response(content=msg[:2000])
        except discord.HTTPException:
            pass

        await self.refresh_message(getattr(interaction, "message", None))

    async def delete_all_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        await interaction.response.send_modal(DeleteAllCasesModal(self))

    async def back_to_admin_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        from .admin import show_main_menu
        await show_main_menu(interaction)

    async def prev_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        self.page -= 1
        await self.refresh(interaction)

    async def next_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        self.page += 1
        await self.refresh(interaction)

    def make_case_callback(self, case_id: int):
        async def callback(interaction: discord.Interaction, *_):
            if interaction.user.id != self.user_id or not can_manage_cases(interaction):
                await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
                return

            view = CaseAdminView(self.user_id, self.guild_id, self.guild, case_id)
            await view.refresh(interaction)

        return callback


# ======================================================================
# НАСТРОЙКА ОДНОГО КЕЙСА
# ======================================================================

class CaseAdminView(ui.View):
    def __init__(self, user_id: int, guild_id: int, guild: discord.Guild, case_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.guild = guild
        self.case_id = case_id

    def _build(self, case):
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
            return embed

        case_rarity_info = get_rarity_emoji(case["case_rarity"])
        total_chance = sum(r["drop_chance"] for r in case["rarities"])
        total_roles = sum(len(r["roles"]) for r in case["rarities"])

        embed = discord.Embed(
            title=f"{case_rarity_info} Кейс: {case['name']}",
            description=(
                "Здесь можно настроить кейс:\n"
                "• цены кейса и ключа\n"
                "• редкость кейса и бесплатный доступ\n"
                "• редкости и шансы выпадения\n"
                "• рыночную цену ролей\n"
                "• роли внутри каждой редкости"
            ),
            color=0xFFD700
        )

        embed.add_field(name="ID кейса", value=str(case["id"]), inline=True)
        embed.add_field(name="Редкость кейса", value=get_rarity_name(case["case_rarity"]), inline=True)
        embed.add_field(name="Статус", value="✅ Активен" if case["is_active"] else "⏸️ Не активен", inline=True)
        embed.add_field(
            name="Цена кейса",
            value=f"{case['case_price']} 💰 / {case.get('case_crystal_price') or 0} 💎",
            inline=True
        )
        embed.add_field(
            name="Цена ключа",
            value=f"{case['key_price']} 💰 / {case.get('key_crystal_price') or 0} 💎",
            inline=True
        )
        embed.add_field(name="Бесплатный", value="✅ Да" if case.get("is_free") else "❌ Нет", inline=True)
        embed.add_field(name="Всего ролей", value=str(total_roles), inline=True)

        chance_status = "✅" if total_chance == 100 else "⚠️"
        embed.add_field(name="Сумма шансов", value=f"{chance_status} {total_chance}%", inline=True)

        settings_btn = ui.Button(style=discord.ButtonStyle.primary, label="⚙️ Настройки кейса")
        settings_btn.callback = self.settings_callback
        self.add_item(settings_btn)

        meta_btn = ui.Button(style=discord.ButtonStyle.primary, label="🎨 Редкость / бесплатный")
        meta_btn.callback = self.meta_callback
        self.add_item(meta_btn)

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

        return embed

    async def refresh(self, interaction: discord.Interaction):
        case = await db.get_case_details(self.case_id)
        embed = self._build(case)
        await deliver_message(interaction, embed=embed, view=self)

    async def refresh_message(self, message):
        if message is None:
            return
        try:
            case = await db.get_case_details(self.case_id)
            embed = self._build(case)
            await message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass

    async def settings_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        case = await db.get_case_details(self.case_id)
        if not case:
            await interaction.response.send_message("❌ Кейс не найден.", ephemeral=True)
            return

        await interaction.response.send_modal(CaseSettingsModal(self, case))

    async def meta_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        case = await db.get_case_details(self.case_id)
        if not case:
            await interaction.response.send_message("❌ Кейс не найден.", ephemeral=True)
            return

        await interaction.response.send_modal(CaseMetaModal(self, case))

    async def add_rarity_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        await interaction.response.send_modal(AddRarityModal(self))

    async def activate_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        result = await db.activate_case(self.case_id)
        if result["success"]:
            await interaction.response.send_message("✅ Кейс активирован.", ephemeral=True)
        else:
            details = "\n".join(result.get("details", []))
            await interaction.response.send_message(
                f"❌ {result['error']}\n{details}",
                ephemeral=True
            )

        await self.refresh_message(getattr(interaction, "message", None))

    async def deactivate_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        await db.deactivate_case(self.case_id)
        await interaction.response.send_message("✅ Кейс деактивирован.", ephemeral=True)
        await self.refresh_message(getattr(interaction, "message", None))

    async def delete_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        await interaction.response.send_modal(DeleteCaseModal(self))

    async def back_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        view = CaseAdminListView(self.user_id, self.guild_id, self.guild)
        await view.refresh(interaction)

    def make_rarity_callback(self, case_rarity_id: int):
        async def callback(interaction: discord.Interaction, *_):
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


# ======================================================================
# НАСТРОЙКА РЕДКОСТИ
# ======================================================================

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

    def _build(self, rarity, case):
        self.clear_items()

        rarity_emoji = get_rarity_emoji(rarity["rarity"])
        rarity_name = get_rarity_name(rarity["rarity"])

        embed = discord.Embed(
            title=f"{rarity_emoji} Редкость: {rarity_name}",
            description=(
                f"Кейс: **{case['name']}**\n"
                "Здесь можно настроить шанс выпадения, рыночную цену роли,\n"
                "а также добавлять и удалять роли."
            ),
            color=0xFFD700
        )

        embed.add_field(name="Шанс выпадения", value=f"{rarity['drop_chance']}%", inline=True)
        embed.add_field(name="Рыночная цена", value=f"{rarity['sell_price']} монет", inline=True)
        embed.add_field(name="Ролей внутри", value=str(len(rarity["roles"])), inline=True)

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

        for role_id in roles[start:end]:
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

        return embed

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

        embed = self._build(rarity, case)
        await deliver_message(interaction, embed=embed, view=self)

    async def refresh_message(self, message):
        if message is None:
            return

        rarity = await db.get_case_rarity_details(self.case_rarity_id)
        case = await db.get_case_details(self.case_id)

        if not rarity or not case:
            return

        try:
            embed = self._build(rarity, case)
            await message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass

    async def settings_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        rarity = await db.get_case_rarity_details(self.case_rarity_id)
        if not rarity:
            await interaction.response.send_message("❌ Редкость не найдена.", ephemeral=True)
            return

        await interaction.response.send_modal(RaritySettingsModal(self, rarity))

    async def add_role_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        await interaction.response.send_modal(AddRoleModal(self))

    async def prev_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return
        self.page -= 1
        await self.refresh(interaction)

    async def next_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return
        self.page += 1
        await self.refresh(interaction)

    async def delete_rarity_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        await db.remove_rarity_from_case(self.case_rarity_id)
        await interaction.response.send_message(
            "✅ Редкость удалена вместе со всеми ролями.",
            ephemeral=True
        )

        view = CaseAdminView(self.user_id, self.guild_id, self.guild, self.case_id)
        await view.refresh_message(getattr(interaction, "message", None))

    async def back_callback(self, interaction: discord.Interaction, *_):
        if interaction.user.id != self.user_id or not can_manage_cases(interaction):
            await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
            return

        view = CaseAdminView(self.user_id, self.guild_id, self.guild, self.case_id)
        await view.refresh(interaction)

    def make_remove_role_callback(self, role_id: int):
        async def callback(interaction: discord.Interaction, *_):
            if interaction.user.id != self.user_id or not can_manage_cases(interaction):
                await interaction.response.send_message("У тебя нет доступа.", ephemeral=True)
                return

            await db.remove_role_from_case_rarity(self.case_rarity_id, role_id)
            await interaction.response.send_message("✅ Роль удалена из редкости.", ephemeral=True)
            await self.refresh_message(getattr(interaction, "message", None))

        return callback


def register(bot):
    # Панели кейсов живут внутри /admin.
    # Отдельная команда /case_admin удалена.
    try:
        bot.tree.remove_command("case_admin")
    except KeyError:
        pass

    # --- Автозащита всех UI-коллбэков модуля ---
    for _cls in list(globals().values()):
        try:
            if not (isinstance(_cls, type) and (
                    issubclass(_cls, discord.ui.View) or issubclass(_cls, discord.ui.Item))):
                continue
        except TypeError:
            continue

        for _name, _attr in list(vars(_cls).items()):
            if _name == "callback" and callable(_attr) and not getattr(_attr, "_wrapped_by_guard", False):
                setattr(_cls, _name, make_resilient(_attr))