# modules/persistent.py
# ======================================================================
# Решает warning:
#   "View interaction referencing unknown view for item <...>. Discarding"
#
# Причина: когда timeout вью истекает, discord.py выписывает её элементы
# из реестра (_ViewStore в 2.x / _view_store в форках 2.5) — и клики по
# старым сообщениям молча отбрасываются. Все интерфейсы этого бота
# перестраиваются на месте (edit_original_response), поэтому старые
# кнопки должны оставаться живыми вечно.
#
# Реализация совместима с ДВУМЯ внутренними API:
#   A) старый _view_store.remove_view(message)   (форк хостинга)
#   B) новый _ViewStore.remove_view(view)        (discord.py 2.6+/2.7)
# Определяется автоматически при install(bot).
#
# Подключение в main.py (в setup_hook, до bot.run):
#   from modules import persistent; persistent.install(bot)
# ======================================================================

import logging

log = logging.getLogger(__name__)

# Все префиксы custom_id проекта (собрано сканером AST по modules/*.py).
_PERSISTENT_PREFIXES = (
    "pw2:",       # universal make_id() prefix (shop, inventory, wheel, ...)
    "ra:",        # role_actions buttons
    "ram:",       # role_actions modals
    "adm:",       # admin panel
    "ca:",        # case_admin panels
    "auc:",       # auctions
    "bet_",       # auction bid modal inputs
    "game_",      # minigames menus
    "coin_", "dice_", "rps_", "mine_", "bj_", "pvpbj_", "roulette_",  # minigame actions
    "case_", "key_", "create_case", "delete_case", "add_role", "add_rarity",
    "remove_role", "rarity_",   # case_admin modals/buttons
    "market:",    # legacy market ids
    "shop:", "inv2:", "wheel:",  # legacy direct ids (без pw2:)
)


def _is_persistent_cid(cid) -> bool:
    return isinstance(cid, str) and cid.startswith(_PERSISTENT_PREFIXES)


def _view_is_persistent(view) -> bool:
    try:
        children = list(view.walk_children())
    except Exception:
        children = list(getattr(view, "children", []))
    return any(_is_persistent_cid(getattr(i, "custom_id", None)) for i in children)


def _get_store(client):
    """Вернуть реестр вью независимо от версии discord.py."""
    # 1) форк 2.5 (хостинг): client._view_store
    store = getattr(client, "_view_store", None)
    if store is not None and hasattr(store, "remove_view"):
        return store, "legacy"
    # 2) discord.py 2.6+/2.7: client._connection._view_store (ViewStore)
    conn = getattr(client, "_connection", None)
    for holder in (conn, client):
        if holder is None:
            continue
        cand = getattr(holder, "_view_store", None)
        if cand is not None and hasattr(cand, "remove_view") and hasattr(cand, "add_view"):
            return cand, "new"
    # 3) последний шанс — любой атрибут connection с add/remove_view
    if conn is not None:
        try:
            names = list(vars(conn))
        except TypeError:
            names = []
        for name in names:
            obj = getattr(conn, name)
            if hasattr(obj, "remove_view") and hasattr(obj, "add_view"):
                return obj, "new"
    return None, None


def install(client) -> None:
    store, kind = _get_store(client)
    if store is None:
        log.warning("persistent: реестр вью не найден — версия discord.py не поддерживается")
        return

    orig_remove = store.remove_view

    if kind == "legacy":
        # remove_view(message) — нельзя удалять persistent-вью этого сообщения
        def remove_view(message):
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

            for _, view in keepers:
                try:
                    store.add_view(view, message)
                except Exception:
                    pass
            return result
    else:
        # discord.py 2.6+/2.7: remove_view(view) — просто пропускаем удаление
        # persistent-вью целиком. Элементы остаются в dispatch-картах,
        # клики по старым сообщениям продолжают работать.
        def remove_view(view):
            if _view_is_persistent(view):
                return None
            return orig_remove(view)

    store.remove_view = remove_view
    log.info("Persistent view registry installed (%s): stable custom_id views survive timeouts", kind)
