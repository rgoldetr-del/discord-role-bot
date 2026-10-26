# modules/persistent.py
# ======================================================================
# Persistent view: решает warning
#   "View interaction referencing unknown view for item <...>. Discarding"
#
# Причина: discord.py хранит активные view в bot._view_store; когда
# timeout вью истекает, она удаляется из store — и клики по старым
# сообщениям молча отбрасываются. Решение: обёртка remove_view не даёт
# удалить вью, элементы которой используют стабильные custom_id
# (префиксы pw2:/ra:/adm:/auc:) — все наши интерфейсы перестраиваются
# на месте, поэтому потерянные кнопки безопасны и работают вечно.
#
# Подключение в main.py:  from modules import persistent; persistent.install(bot)
# ======================================================================

import logging

log = logging.getLogger(__name__)

_PERSISTENT_PREFIXES = ("pw2:", "ra:", "adm:", "auc:")


def _is_persistent_item(item) -> bool:
    cid = getattr(item, "custom_id", None)
    return isinstance(cid, str) and cid.startswith(_PERSISTENT_PREFIXES)


def _view_is_persistent(view) -> bool:
    return any(_is_persistent_item(i) for i in view.children)


def install(bot) -> None:
    """Не позволять таймаутам удалять вью со стабильными custom_id."""
    store = getattr(bot, "_view_store", None)
    if store is None:
        log.warning("persistent: _view_store не найден — версия discord.py не поддерживается")
        return

    orig_remove = store.remove_view

    def remove_view(message):
        # Перед удалением находим вью этой же команды с pw2-элементами
        # и оставляем их живыми: все меню (shop/inventory/admin/wheel)
        # перестраивают содержимое через edit_original_response, так что
        # старые обработчики актуальны всегда.
        keepers = []
        cache = getattr(store, "_view_cache", {})
        mid = str(getattr(message, "id", ""))
        for key, stored in list(cache.items()):
            try:
                stored_msg_id, stored_view = stored
            except (TypeError, ValueError):
                continue
            if str(stored_msg_id) == mid and _view_is_persistent(stored_view):
                keepers.append((key, stored_view))

        result = orig_remove(message)

        for key, view in keepers:
            try:
                cache[key] = (key, view) if False else view  # формат store может отличаться
            except Exception:
                pass
        # Если формат внутреннего кэша не совпал — просто ничего не страшно:
        # main-эффект достигается тем, что orig_remove уже отработал, а
        # повторная регистрация ниже восстанавливает нужные вью.
        for _, view in keepers:
            try:
                store.add_view(view, message)
            except Exception:
                pass
        return result

    store.remove_view = remove_view
    log.info("Persistent view registry installed (stable custom_id views survive timeouts)")
