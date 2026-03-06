from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from view.name_list import NameRowWidget


def item_text(list_widget, item: QtWidgets.QListWidgetItem) -> str:
    widget = list_widget.itemWidget(item)
    if isinstance(widget, NameRowWidget):
        return widget.edit.text().strip()
    return item.text().strip()


def item_subroles(list_widget, item: QtWidgets.QListWidgetItem) -> set[str]:
    widget = list_widget.itemWidget(item)
    if isinstance(widget, NameRowWidget):
        return widget.selected_subroles()
    data = item.data(list_widget.SUBROLE_ROLE)
    if isinstance(data, (list, set, tuple)):
        return set(data)
    return set()


def item_state(list_widget, item: QtWidgets.QListWidgetItem) -> QtCore.Qt.CheckState:
    getter = getattr(list_widget, "item_state", None)
    if callable(getter):
        try:
            return getter(item)
        except Exception:
            pass
    return item.checkState()


def rebuild_entries_cache(list_widget) -> dict[str, list]:
    entries: list[dict] = []
    active_entries: list[dict] = []
    base_names: list[str] = []
    active_names: list[str] = []
    for i in range(list_widget.count()):
        item = list_widget.item(i)
        if item is None:
            continue
        name = item_text(list_widget, item)
        if not name:
            continue
        subroles = list(item_subroles(list_widget, item))
        active = item_state(list_widget, item) == QtCore.Qt.Checked
        entries.append({"name": name, "subroles": subroles, "active": active})
        base_names.append(name)
        if active:
            active_entries.append({"name": name, "subroles": subroles})
            active_names.append(name)
    return {
        "entries": entries,
        "active_entries": active_entries,
        "base_names": base_names,
        "active_names": active_names,
    }


def apply_subrole_visibility(list_widget, visible: bool) -> None:
    target_visible = bool(visible)
    for i in range(list_widget.count()):
        widget = list_widget.itemWidget(list_widget.item(i))
        if isinstance(widget, NameRowWidget):
            group = getattr(widget, "_subrole_group", None)
            if isinstance(group, QtWidgets.QWidget):
                group.setVisible(target_visible)
            for cb in widget.subrole_checks:
                cb.setVisible(target_visible)
            delete_cb = getattr(widget, "chk_mark_for_delete", None)
            if isinstance(delete_cb, QtWidgets.QCheckBox):
                show_delete = bool(getattr(list_widget, "enable_mark_for_delete", True))
                delete_cb.setVisible(show_delete)
                delete_cell = delete_cb.parentWidget()
                if isinstance(delete_cell, QtWidgets.QWidget):
                    delete_cell.setVisible(show_delete)
            layout = widget.layout()
            if isinstance(layout, QtWidgets.QLayout):
                layout.invalidate()
            widget.updateGeometry()
    try:
        list_widget.doItemsLayout()
    except Exception:
        pass
    sync_viewport = getattr(list_widget, "_sync_viewport_right_padding", None)
    if callable(sync_viewport):
        try:
            sync_viewport()
        except Exception:
            pass
