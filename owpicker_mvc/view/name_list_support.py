from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

DELETE_MARK_COLUMN_WIDTH = 18
DELETE_MARK_BUTTON_WIDTH = 28
DELETE_MARK_ROW_RIGHT_MARGIN = 0
NAME_LIST_ROW_HEIGHT = 20
NAME_EDIT_HEIGHT = 18
NAME_EDIT_MIN_WIDTH_WITH_SUBROLES = 72
NAME_EDIT_MIN_WIDTH_WITHOUT_SUBROLES = 96
SUBROLE_CHECK_SPACING = 16
SUBROLE_GROUP_LEFT_MARGIN = 2
SUBROLE_GROUP_RIGHT_MARGIN = 4
SUBROLE_CHECKBOX_HORIZONTAL_PADDING = 0
NAME_EDIT_MAX_WIDTH_WITH_SUBROLES = 0
NAMES_PANEL_MAX_WIDTH_WITH_SUBROLES = 420
NAMES_PANEL_MAX_WIDTH_DEFAULT = 560
NAMES_PANEL_MIN_WIDTH_BASE = 260

_DELETE_MARKED_STYLE_CACHE: dict[tuple[str, bool], str] = {}
_NAMES_ACTION_ROW_STYLE_CACHE: dict[str, str] = {}


def delete_marked_button_style(theme, *, danger_active: bool = False) -> str:
    theme_key = str(getattr(theme, "key", "light"))
    cache_key = (theme_key, bool(danger_active))
    cached = _DELETE_MARKED_STYLE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if danger_active:
        main_bg = "#c62828"
        main_border = "#8e1f1f"
        main_hover = "#d32f2f"
        main_pressed = "#b71c1c"
        main_text = "white"
    else:
        main_bg = str(theme.base)
        main_border = str(theme.border)
        main_hover = str(theme.tool_hover)
        main_pressed = str(theme.tool_pressed)
        main_text = str(theme.text)
    cached = (
        "QToolButton {"
        f" color:{main_text}; background:{main_bg}; border:1px solid {main_border};"
        " border-radius:8px; font-size:15px; }"
        f"QToolButton:hover {{ background:{main_hover}; }}"
        f"QToolButton:pressed {{ background:{main_pressed}; }}"
        f"QToolButton:disabled {{ color:{theme.disabled_text}; background:{theme.alt_base}; border:1px solid {theme.border}; }}"
    )
    _DELETE_MARKED_STYLE_CACHE[cache_key] = cached
    return cached


def names_action_row_style(theme) -> str:
    theme_key = str(getattr(theme, "key", "light"))
    cached = _NAMES_ACTION_ROW_STYLE_CACHE.get(theme_key)
    if cached is not None:
        return cached
    cached = "QWidget#namesActionRow { background: transparent; border: none; }"
    _NAMES_ACTION_ROW_STYLE_CACHE[theme_key] = cached
    return cached


class NoPaintDelegate(QtWidgets.QStyledItemDelegate):
    """Suppress default index painting; row widgets render content."""

    def paint(self, painter, option, index):
        del painter, option, index
        return

    def sizeHint(self, option, index):
        del index
        height = NAME_LIST_ROW_HEIGHT
        owner = self.parent()
        if owner is not None:
            try:
                height = max(1, int(getattr(owner, "_row_height", NAME_LIST_ROW_HEIGHT)))
            except Exception:
                height = NAME_LIST_ROW_HEIGHT
        return QtCore.QSize(max(1, int(option.rect.width())), height)


class NameLineEdit(QtWidgets.QLineEdit):
    deleteEmptyRequested = QtCore.Signal()
    moveUpRequested = QtCore.Signal()
    moveDownRequested = QtCore.Signal()
    newRowRequested = QtCore.Signal()

    def keyPressEvent(self, ev: QtGui.QKeyEvent) -> None:
        key = ev.key()
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.newRowRequested.emit()
            return
        if key in (QtCore.Qt.Key_Backspace, QtCore.Qt.Key_Delete) and not self.text():
            self.deleteEmptyRequested.emit()
            return
        if key == QtCore.Qt.Key_Up:
            self.moveUpRequested.emit()
            return
        if key == QtCore.Qt.Key_Down:
            self.moveDownRequested.emit()
            return
        super().keyPressEvent(ev)
