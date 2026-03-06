from __future__ import annotations

from typing import Callable, List, Optional
from PySide6 import QtCore, QtGui, QtWidgets
import i18n
from view import style_helpers, ui_tokens
from utils import ui_helpers

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
_DELETE_MARKED_STYLE_CACHE: dict[str, str] = {}
_NAMES_ACTION_ROW_STYLE_CACHE: dict[str, str] = {}


def _delete_marked_button_style(theme) -> str:
    theme_key = str(getattr(theme, "key", "light"))
    cached = _DELETE_MARKED_STYLE_CACHE.get(theme_key)
    if cached is not None:
        return cached
    cached = (
        "QToolButton {"
        f" color:{theme.text}; background:{theme.base}; border:1px solid {theme.border};"
        " border-radius:8px; font-size:15px; }"
        f"QToolButton:hover {{ background:{theme.tool_hover}; }}"
        f"QToolButton:pressed {{ background:{theme.tool_pressed}; }}"
        "QToolButton[dangerActive=\"true\"] {"
        " color:white; background:#c62828; border:1px solid #8e1f1f; }"
        "QToolButton[dangerActive=\"true\"]:hover { background:#d32f2f; }"
        "QToolButton[dangerActive=\"true\"]:pressed { background:#b71c1c; }"
        f"QToolButton:disabled {{ color:{theme.disabled_text}; background:{theme.alt_base}; border:1px solid {theme.border}; }}"
    )
    _DELETE_MARKED_STYLE_CACHE[theme_key] = cached
    return cached


def _names_action_row_style(theme) -> str:
    theme_key = str(getattr(theme, "key", "light"))
    cached = _NAMES_ACTION_ROW_STYLE_CACHE.get(theme_key)
    if cached is not None:
        return cached
    cached = "QWidget#namesActionRow { background: transparent; border: none; }"
    _NAMES_ACTION_ROW_STYLE_CACHE[theme_key] = cached
    return cached


class _NoPaintDelegate(QtWidgets.QStyledItemDelegate):
    """Unterdrückt Standard-Rendering von Text/Checkboxen für Index-Widgets."""
    def paint(self, painter, option, index):
        # Nichts zeichnen – die indexWidgets übernehmen die Darstellung
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
    """Editor für einen Eintrag in der Namensliste.
    Wenn der Text leer ist und der Nutzer Backspace/Delete drückt,
    wird ein Signal zum Löschen der Zeile ausgelöst.
    Außerdem können Pfeil-oben/unten zum Zeilenwechsel genutzt werden.
    """
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


class NamesList(QtWidgets.QListWidget):
    """Liste mit Checkboxen und textfeldähnlichem Verhalten."""
    metaChanged = QtCore.Signal()
    SUBROLE_ROLE = QtCore.Qt.UserRole + 1
    MARK_FOR_DELETE_ROLE = QtCore.Qt.UserRole + 2
    ACTIVE_STATE_ROLE = QtCore.Qt.UserRole + 3

    def __init__(
        self,
        parent=None,
        subrole_labels: Optional[List[str]] = None,
        *,
        enable_mark_for_delete: bool = True,
    ):
        super().__init__(parent)
        self.subrole_labels = subrole_labels or []
        self.has_subroles = bool(self.subrole_labels)
        self.enable_mark_for_delete = bool(enable_mark_for_delete)
        self._auto_focus_enabled = True
        self._auto_focus_requires_active = False
        self._viewport_right_margin = -1
        self._syncing_viewport_margin = False
        self._row_height = NAME_LIST_ROW_HEIGHT
        self._name_edit_height = NAME_EDIT_HEIGHT
        self._name_min_width_with_subroles = NAME_EDIT_MIN_WIDTH_WITH_SUBROLES
        self._name_min_width_without_subroles = NAME_EDIT_MIN_WIDTH_WITHOUT_SUBROLES
        self._subrole_controls_layout_visible = bool(self.has_subroles)
        self._subrole_group_left_margin = SUBROLE_GROUP_LEFT_MARGIN
        self._subrole_group_right_margin = SUBROLE_GROUP_RIGHT_MARGIN
        self._subrole_check_spacing = SUBROLE_CHECK_SPACING
        self._subrole_checkbox_horizontal_padding = SUBROLE_CHECKBOX_HORIZONTAL_PADDING
        # Keep subrole rows compact and stable even after list rebuild/sort.
        self._name_max_width: int | None = (
            NAME_EDIT_MAX_WIDTH_WITH_SUBROLES if (self.has_subroles and NAME_EDIT_MAX_WIDTH_WITH_SUBROLES > 0) else None
        )
        self._name_rows_read_only = False
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setResizeMode(QtWidgets.QListView.Adjust)
        self.setViewMode(QtWidgets.QListView.ListMode)
        self.setSpacing(0)
        self.setUniformItemSizes(True)
        self.setItemDelegate(_NoPaintDelegate(self))

        self.setStyleSheet(
            "QListView::item:selected { background: transparent; color: inherit; }"
            "QListView::item:selected:active { background: transparent; color: inherit; }"
            "QListView::item:focus { outline: none; }"
            "QListView::item { margin:0px; padding:0px; border:0px; }"
        )

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        sb = self.verticalScrollBar()
        if sb is not None:
            sb.rangeChanged.connect(self._sync_viewport_right_padding)
        QtCore.QTimer.singleShot(0, self._sync_viewport_right_padding)

    def _scrollbar_extent(self, sb: QtWidgets.QScrollBar | None = None) -> int:
        scrollbar = sb if sb is not None else self.verticalScrollBar()
        if scrollbar is None:
            return 0
        extent = self.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent, None, scrollbar)
        hint = scrollbar.sizeHint().width()
        return max(0, int(extent), int(hint))

    def _sync_viewport_right_padding(self, *_args) -> None:
        if self._syncing_viewport_margin:
            return
        # Keep viewport margins at 0 so row widgets are always laid out to the
        # actually visible width and right-side controls cannot be clipped.
        margin_right = 0
        if margin_right == self._viewport_right_margin:
            self._refresh_row_widget_geometry()
            return
        self._viewport_right_margin = margin_right
        self._syncing_viewport_margin = True
        try:
            self.setViewportMargins(0, 0, margin_right, 0)
        finally:
            self._syncing_viewport_margin = False
        # Viewport margin changes can make previously laid-out row widgets too wide.
        # Re-layout immediately so right-side controls do not get clipped.
        self._refresh_row_widget_geometry()

    def _refresh_row_widget_geometry(self) -> None:
        try:
            self.doItemsLayout()
        except Exception:
            pass
        for i in range(self.count()):
            item = self.item(i)
            if item is None:
                continue
            row_widget = self.itemWidget(item)
            if isinstance(row_widget, NameRowWidget):
                row_widget._apply_name_edit_width_constraints()

    def resizeEvent(self, ev: QtGui.QResizeEvent) -> None:
        super().resizeEvent(ev)
        self._refresh_row_widget_geometry()
        QtCore.QTimer.singleShot(0, self._sync_viewport_right_padding)
        QtCore.QTimer.singleShot(0, self._refresh_row_widget_geometry)

    def showEvent(self, ev: QtGui.QShowEvent) -> None:
        super().showEvent(ev)
        try:
            self.doItemsLayout()
        except Exception:
            pass
        self._sync_viewport_right_padding()
        QtCore.QTimer.singleShot(0, self._sync_viewport_right_padding)

    def wheelEvent(self, ev: QtGui.QWheelEvent):
        """Etwas weniger sensibles Scrollen als Qt-Default."""
        sb = self.verticalScrollBar()
        if not sb:
            return super().wheelEvent(ev)
        angle = ev.angleDelta().y()
        pixel = ev.pixelDelta().y()
        factor = 0.4  # <1 -> langsamer

        if angle:
            base = (angle / 120.0) * sb.singleStep()
            step = int(base * factor)
        elif pixel:
            step = int(pixel * factor)
        else:
            return super().wheelEvent(ev)

        if step == 0:
            step = 1 if (angle or pixel) > 0 else -1

        sb.setValue(sb.value() - step)
        ev.accept()

    def _new_item(self, text: str = "", subroles: Optional[List[str]] = None, active: Optional[bool] = None) -> QtWidgets.QListWidgetItem:
        item = QtWidgets.QListWidgetItem(text)
        item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
        item.setSizeHint(QtCore.QSize(0, max(1, int(self._row_height))))
        state: QtCore.Qt.CheckState
        if active is not None:
            state = QtCore.Qt.Checked if active else QtCore.Qt.Unchecked
        elif text.strip():
            state = QtCore.Qt.Checked
        else:
            state = QtCore.Qt.Unchecked
        self.set_item_state(item, state)
        item.setData(self.SUBROLE_ROLE, list(subroles or []))
        item.setData(self.MARK_FOR_DELETE_ROLE, False)
        return item

    @staticmethod
    def _normalize_check_state(state) -> QtCore.Qt.CheckState:
        if state == QtCore.Qt.PartiallyChecked:
            return QtCore.Qt.PartiallyChecked
        if state == QtCore.Qt.Checked:
            return QtCore.Qt.Checked
        return QtCore.Qt.Unchecked

    @staticmethod
    def _state_to_int(state: QtCore.Qt.CheckState) -> int:
        normalized = NamesList._normalize_check_state(state)
        if normalized == QtCore.Qt.PartiallyChecked:
            return 1
        if normalized == QtCore.Qt.Checked:
            return 2
        return 0

    @staticmethod
    def _int_to_state(value) -> QtCore.Qt.CheckState:
        try:
            raw = int(value)
        except Exception:
            return QtCore.Qt.Unchecked
        if raw == 1:
            return QtCore.Qt.PartiallyChecked
        if raw == 2:
            return QtCore.Qt.Checked
        return QtCore.Qt.Unchecked

    def item_state(self, item: QtWidgets.QListWidgetItem) -> QtCore.Qt.CheckState:
        if item is None:
            return QtCore.Qt.Unchecked
        raw = item.data(self.ACTIVE_STATE_ROLE)
        if isinstance(raw, int):
            return self._int_to_state(raw)
        if raw in (QtCore.Qt.Unchecked, QtCore.Qt.PartiallyChecked, QtCore.Qt.Checked):
            return self._normalize_check_state(raw)
        if isinstance(raw, bool):
            return QtCore.Qt.Checked if raw else QtCore.Qt.Unchecked
        return QtCore.Qt.Unchecked

    def set_item_state(self, item: QtWidgets.QListWidgetItem, state) -> bool:
        if item is None:
            return False
        target = self._normalize_check_state(state)
        previous = self.item_state(item)
        item.setData(self.ACTIVE_STATE_ROLE, self._state_to_int(target))
        # Keep Qt's native check indicator data empty so rows do not reserve
        # an additional left indicator column.
        item.setData(QtCore.Qt.CheckStateRole, None)
        return previous != target

    def _attach_row_widget(self, item: QtWidgets.QListWidgetItem):
        widget = NameRowWidget(self, item, self.subrole_labels)
        self.setItemWidget(item, widget)
        self._apply_row_visual_profile(item, widget)

    def _apply_row_visual_profile(
        self,
        item: QtWidgets.QListWidgetItem,
        widget: QtWidgets.QWidget | None = None,
    ) -> None:
        if item is None:
            return
        item.setSizeHint(QtCore.QSize(0, max(1, int(self._row_height))))
        row_widget = widget if widget is not None else self.itemWidget(item)
        if not isinstance(row_widget, NameRowWidget):
            return
        row_widget.edit.setFixedHeight(max(1, int(self._name_edit_height)))
        use_subrole_profile = bool(self.has_subroles and self._subrole_controls_layout_visible)
        min_width = (
            int(self._name_min_width_with_subroles)
            if use_subrole_profile
            else int(self._name_min_width_without_subroles)
        )
        max_width: int | None
        if use_subrole_profile and isinstance(self._name_max_width, int) and self._name_max_width > 0:
            max_width = int(self._name_max_width)
        else:
            max_width = None
        row_widget.set_name_edit_width_profile(min_width=min_width, max_width=max_width)
        row_widget.apply_subrole_visual_profile(
            left_margin=max(0, int(self._subrole_group_left_margin)),
            right_margin=max(0, int(self._subrole_group_right_margin)),
            spacing=max(0, int(self._subrole_check_spacing)),
            checkbox_hpadding=max(0, int(self._subrole_checkbox_horizontal_padding)),
        )
        if self._name_rows_read_only:
            row_widget.edit.setReadOnly(True)
            row_widget.edit.setFocusPolicy(QtCore.Qt.NoFocus)
        else:
            row_widget.edit.setReadOnly(False)
            row_widget.edit.setFocusPolicy(QtCore.Qt.ClickFocus)

    def _apply_visual_profile_to_all_rows(self) -> None:
        for i in range(self.count()):
            item = self.item(i)
            if item is None:
                continue
            self._apply_row_visual_profile(item)

    def set_row_visual_profile(
        self,
        *,
        row_height: int | None = None,
        name_edit_height: int | None = None,
        name_min_width_with_subroles: int | None = None,
        name_min_width_without_subroles: int | None = None,
        name_max_width: int | None = None,
        subrole_group_left_margin: int | None = None,
        subrole_group_right_margin: int | None = None,
        subrole_check_spacing: int | None = None,
        subrole_checkbox_horizontal_padding: int | None = None,
        read_only: bool | None = None,
    ) -> None:
        if row_height is not None:
            self._row_height = max(1, int(row_height))
        if name_edit_height is not None:
            self._name_edit_height = max(1, int(name_edit_height))
        if name_min_width_with_subroles is not None:
            self._name_min_width_with_subroles = max(1, int(name_min_width_with_subroles))
        if name_min_width_without_subroles is not None:
            self._name_min_width_without_subroles = max(1, int(name_min_width_without_subroles))
        self._name_max_width = None if name_max_width is None else max(1, int(name_max_width))
        if subrole_group_left_margin is not None:
            self._subrole_group_left_margin = max(0, int(subrole_group_left_margin))
        if subrole_group_right_margin is not None:
            self._subrole_group_right_margin = max(0, int(subrole_group_right_margin))
        if subrole_check_spacing is not None:
            self._subrole_check_spacing = max(0, int(subrole_check_spacing))
        if subrole_checkbox_horizontal_padding is not None:
            self._subrole_checkbox_horizontal_padding = max(0, int(subrole_checkbox_horizontal_padding))
        if read_only is not None:
            self._name_rows_read_only = bool(read_only)
        self._apply_visual_profile_to_all_rows()
        self.doItemsLayout()
        QtCore.QTimer.singleShot(0, self._sync_viewport_right_padding)

    def _detach_row_widget(self, item: QtWidgets.QListWidgetItem) -> None:
        widget = self.itemWidget(item)
        if widget is None:
            return
        # Keep QListWidget/QAbstractItemView internal editor bookkeeping consistent.
        self.removeItemWidget(item)
        widget.deleteLater()

    def _create_name_row(
        self,
        text: str = "",
        *,
        subroles: Optional[List[str]] = None,
        active: Optional[bool] = None,
        marked_for_delete: bool = False,
        row: int | None = None,
        select_row: bool = True,
        focus_if_empty: bool = True,
    ) -> QtWidgets.QListWidgetItem:
        item = self._new_item(text, subroles=subroles, active=active)
        item.setData(self.MARK_FOR_DELETE_ROLE, bool(marked_for_delete))
        if row is None:
            self.addItem(item)
        else:
            safe_row = max(0, min(int(row), self.count()))
            self.insertItem(safe_row, item)
        self._attach_row_widget(item)
        if select_row:
            self.setCurrentItem(item)
        if focus_if_empty and not text:
            widget = self.itemWidget(item)
            if widget and self._allow_auto_focus():
                widget.focus_name()
        try:
            self.doItemsLayout()
        except Exception:
            pass
        self._sync_viewport_right_padding()
        return item

    def add_name(self, text: str = "", subroles: Optional[List[str]] = None, active: Optional[bool] = None):
        self._create_name_row(text, subroles=subroles, active=active)

    def insert_name_at(self, row: int, text: str = ""):
        self._create_name_row(
            text,
            row=row,
            select_row=True,
            focus_if_empty=True,
        )

    def delete_row(self, row: int):
        if self.count() <= 1:
            return
        if 0 <= row < self.count():
            item = self.item(row)
            if item is not None:
                self._detach_row_widget(item)
            removed_item = self.takeItem(row)
            if removed_item is not None:
                del removed_item

    def remove_rows(self, rows: List[int], ensure_one_empty: bool = True) -> int:
        removed = 0
        for row in sorted(set(rows), reverse=True):
            if not (0 <= row < self.count()):
                continue
            item = self.item(row)
            if item is not None:
                self._detach_row_widget(item)
            removed_item = self.takeItem(row)
            if removed_item is not None:
                del removed_item
            removed += 1
        if ensure_one_empty and self.count() == 0:
            self.add_name("")
        return removed

    def mousePressEvent(self, ev: QtGui.QMouseEvent):
        if ev.button() == QtCore.Qt.LeftButton:
            item = self.itemAt(ev.pos())
            if item is not None:
                super().mousePressEvent(ev)
                widget = self.itemWidget(item)
                if isinstance(widget, NameRowWidget):
                    QtCore.QTimer.singleShot(0, widget.focus_name)
                return
        super().mousePressEvent(ev)

    def _allow_auto_focus(self) -> bool:
        if not self._auto_focus_enabled:
            return False
        if not self._auto_focus_requires_active:
            return True
        app = QtWidgets.QApplication.instance()
        if not app:
            return False
        focus_widget = app.focusWidget()
        return focus_widget is not None and (focus_widget is self or self.isAncestorOf(focus_widget))

    def set_auto_focus_enabled(self, enabled: bool, require_active_focus: bool | None = None) -> None:
        self._auto_focus_enabled = bool(enabled)
        if require_active_focus is not None:
            self._auto_focus_requires_active = bool(require_active_focus)

    def keyPressEvent(self, ev: QtGui.QKeyEvent):
        key = ev.key()
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            row = self.currentRow()
            if row < 0:
                row = self.count() - 1
            self.insert_name_at(row + 1, "")
            return
        super().keyPressEvent(ev)

    def sort_alphabetically(self):
        """Sortiert die Liste A→Z (Case-insensitive), leere Namen ans Ende."""
        entries: list[tuple[str, bool, list[str], bool]] = []
        subrole_checks_visible: bool | None = None
        subrole_group_visible: bool | None = None
        for i in range(self.count()):
            item = self.item(i)
            if item is None:
                continue
            widget = self.itemWidget(item)
            if isinstance(widget, NameRowWidget) and widget.subrole_checks and subrole_checks_visible is None:
                subrole_checks_visible = bool(widget.subrole_checks[0].isVisible())
            if isinstance(widget, NameRowWidget) and subrole_group_visible is None:
                group = getattr(widget, "_subrole_group", None)
                if isinstance(group, QtWidgets.QWidget):
                    subrole_group_visible = bool(group.isVisible())
            text = widget.edit.text() if isinstance(widget, NameRowWidget) else item.text()
            entries.append(
                (
                    str(text),
                    self.item_state(item) == QtCore.Qt.Checked,
                    list(item.data(self.SUBROLE_ROLE) or []),
                    bool(item.data(self.MARK_FOR_DELETE_ROLE)),
                )
            )

        entries.sort(key=lambda e: (not e[0].strip(), e[0].strip().casefold()))

        prev_auto_focus_enabled = bool(self._auto_focus_enabled)
        prev_auto_focus_requires_active = bool(self._auto_focus_requires_active)
        self._auto_focus_enabled = False
        blockers = [QtCore.QSignalBlocker(self), QtCore.QSignalBlocker(self.model())]
        try:
            while self.count():
                old_item = self.item(0)
                if old_item is None:
                    break
                self._detach_row_widget(old_item)
                removed_item = self.takeItem(0)
                if removed_item is not None:
                    del removed_item
            for text, active, subroles, marked in entries:
                # Reuse the same creation path as the initial list build.
                self.add_name(text, subroles=subroles, active=active)
                item = self.item(self.count() - 1)
                if item is None:
                    continue
                item.setData(self.MARK_FOR_DELETE_ROLE, bool(marked))
                row_widget = self.itemWidget(item)
                if isinstance(row_widget, NameRowWidget):
                    if row_widget.chk_mark_for_delete is not None:
                        row_widget.chk_mark_for_delete.setChecked(bool(marked))
                        # Keep delete marker control visible after rebuild/sort.
                        row_widget.chk_mark_for_delete.setVisible(True)
                        delete_cell = row_widget.chk_mark_for_delete.parentWidget()
                        if isinstance(delete_cell, QtWidgets.QWidget):
                            delete_cell.setVisible(True)
                    if subrole_group_visible is not None:
                        group = getattr(row_widget, "_subrole_group", None)
                        if isinstance(group, QtWidgets.QWidget):
                            group.setVisible(bool(subrole_group_visible))
                    if subrole_checks_visible is not None and row_widget.subrole_checks:
                        for cb in row_widget.subrole_checks:
                            cb.setVisible(bool(subrole_checks_visible))
                    row_layout = row_widget.layout()
                    if isinstance(row_layout, QtWidgets.QLayout):
                        row_layout.invalidate()
                    row_widget.updateGeometry()
        finally:
            self._auto_focus_enabled = prev_auto_focus_enabled
            self._auto_focus_requires_active = prev_auto_focus_requires_active
            del blockers
        try:
            self.doItemsLayout()
        except Exception:
            pass
        self._sync_viewport_right_padding()
        self.metaChanged.emit()

    def _show_context_menu(self, pos: QtCore.QPoint):
        item = self.itemAt(pos)
        if item is not None and not item.isSelected():
            self.setCurrentItem(item)
            item.setSelected(True)

        menu = QtWidgets.QMenu(self)
        act_new = menu.addAction(i18n.t("names.context_new"))
        act_del = menu.addAction(i18n.t("names.context_delete"))
        if not self.selectedItems():
            act_del.setEnabled(False)
        action = menu.exec(self.mapToGlobal(pos))
        if action == act_new:
            self.add_name("")
        elif action == act_del:
            rows = sorted({self.row(i) for i in self.selectedItems()}, reverse=True)
            for r in rows:
                self.delete_row(r)


class NameRowWidget(QtWidgets.QWidget):
    """Zeilen-Widget mit Aktiv-Checkbox, Namensfeld und optionalen Subrollen."""
    def __init__(self, list_widget: NamesList, item: QtWidgets.QListWidgetItem, subrole_labels: List[str]):
        super().__init__(list_widget)
        self.list_widget = list_widget
        self.item = item
        layout = QtWidgets.QHBoxLayout(self)
        right_margin = DELETE_MARK_ROW_RIGHT_MARGIN if subrole_labels else 4
        # Keep the active checkbox visually clear from the name edit field.
        layout.setContentsMargins(0, 0, right_margin, 0)
        layout.setSpacing(ui_tokens.NAME_ROW_HORIZONTAL_SPACING)
        self._configured_name_min_width = 1
        self._configured_name_max_width: int | None = None
        self.subrole_checks: list[QtWidgets.QCheckBox] = []
        self._subrole_group: QtWidgets.QWidget | None = None
        self._subrole_layout: QtWidgets.QHBoxLayout | None = None
        self._delete_cell: QtWidgets.QWidget | None = None

        self.chk_active = QtWidgets.QCheckBox()
        self.chk_active.setFixedWidth(18)
        self.chk_active.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        state = self.list_widget.item_state(item)
        if state == QtCore.Qt.PartiallyChecked:
            self.chk_active.setTristate(True)
            self.chk_active.setCheckState(state)
        else:
            self.chk_active.setChecked(state == QtCore.Qt.Checked)
        self.chk_active.toggled.connect(self._on_active_toggled)
        self.chk_active.setToolTip(i18n.t("names.active_tooltip"))
        layout.addWidget(self.chk_active, 0, QtCore.Qt.AlignVCenter)

        self.edit = NameLineEdit()
        self.edit.setText(item.text())
        self.edit.setToolTip(str(item.text() or ""))
        # Keep field flexible, but avoid forcing row overflow with subrole checkboxes.
        if subrole_labels:
            min_name_width = int(
                getattr(
                    list_widget,
                    "_name_min_width_with_subroles",
                    NAME_EDIT_MIN_WIDTH_WITH_SUBROLES,
                )
            )
        else:
            min_name_width = int(
                getattr(
                    list_widget,
                    "_name_min_width_without_subroles",
                    NAME_EDIT_MIN_WIDTH_WITHOUT_SUBROLES,
                )
            )
        self.edit.setMinimumWidth(min_name_width)
        max_name_width = getattr(list_widget, "_name_max_width", None)
        configured_max_width: int | None = None
        if isinstance(max_name_width, int) and max_name_width > 0:
            configured_max_width = int(max_name_width)
        self.edit.setFixedHeight(max(1, int(getattr(list_widget, "_name_edit_height", NAME_EDIT_HEIGHT))))
        # Let the name field absorb most width changes, keep role/delete controls fixed.
        self.edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.edit.textChanged.connect(self._on_text_changed)
        self.edit.deleteEmptyRequested.connect(self._delete_self_if_empty)
        self.edit.moveUpRequested.connect(self._focus_prev)
        self.edit.moveDownRequested.connect(self._focus_next)
        self.edit.newRowRequested.connect(self._insert_new_row)
        layout.addWidget(self.edit, 1, QtCore.Qt.AlignVCenter)
        self.set_name_edit_width_profile(min_width=min_name_width, max_width=configured_max_width)

        if subrole_labels:
            self._subrole_group = QtWidgets.QWidget(self)
            group_policy = self._subrole_group.sizePolicy()
            group_policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Fixed)
            group_policy.setVerticalPolicy(QtWidgets.QSizePolicy.Fixed)
            group_policy.setRetainSizeWhenHidden(True)
            self._subrole_group.setSizePolicy(group_policy)
            subrole_layout = QtWidgets.QHBoxLayout(self._subrole_group)
            self._subrole_layout = subrole_layout
            subrole_layout.setContentsMargins(
                SUBROLE_GROUP_LEFT_MARGIN,
                0,
                SUBROLE_GROUP_RIGHT_MARGIN,
                0,
            )
            subrole_layout.setSpacing(SUBROLE_CHECK_SPACING)
            for lbl in subrole_labels:
                cb = QtWidgets.QCheckBox(lbl)
                cb.setChecked(lbl in self._current_subroles())
                cb.toggled.connect(self._on_subrole_changed)
                cb.setToolTip(i18n.t("names.subrole_tooltip", label=lbl))
                cb.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
                cb.setMinimumWidth(cb.sizeHint().width())
                self.subrole_checks.append(cb)
                subrole_layout.addWidget(cb, 0, QtCore.Qt.AlignVCenter)
            # Keep subrole block content-tight so it does not eat horizontal slack.
            subrole_width = max(1, int(self._subrole_group.sizeHint().width()))
            self._subrole_group.setMinimumWidth(subrole_width)
            self._subrole_group.setMaximumWidth(subrole_width)
            layout.addWidget(self._subrole_group, 0, QtCore.Qt.AlignVCenter)

        self.chk_mark_for_delete: QtWidgets.QCheckBox | None = None
        if subrole_labels and self.list_widget.enable_mark_for_delete:
            self.chk_mark_for_delete = QtWidgets.QCheckBox()
            self.chk_mark_for_delete.setChecked(self._is_marked_for_delete())
            self.chk_mark_for_delete.setToolTip(i18n.t("names.mark_for_delete_tooltip"))
            self.chk_mark_for_delete.toggled.connect(self._on_mark_for_delete_toggled)
            delete_cell = QtWidgets.QWidget(self)
            self._delete_cell = delete_cell
            delete_cell_width = max(
                int(DELETE_MARK_COLUMN_WIDTH),
                int(self.chk_mark_for_delete.sizeHint().width()),
            )
            delete_cell.setFixedWidth(delete_cell_width)
            delete_cell_layout = QtWidgets.QHBoxLayout(delete_cell)
            delete_cell_layout.setContentsMargins(0, 0, 0, 0)
            delete_cell_layout.setSpacing(0)
            delete_cell_layout.addWidget(
                self.chk_mark_for_delete,
                0,
                QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
            )
            layout.addWidget(delete_cell, 0, QtCore.Qt.AlignVCenter)
        # Kein automatischer Fokus auf neue/leer Zeilen

    def _fixed_non_edit_width(self) -> int:
        fixed = 0
        widgets: list[QtWidgets.QWidget] = [self.chk_active]
        if self._subrole_group is not None and self._subrole_group.isVisible():
            widgets.append(self._subrole_group)
        if self._delete_cell is not None and self._delete_cell.isVisible():
            widgets.append(self._delete_cell)
        for widget in widgets:
            fixed += max(
                int(widget.width()),
                int(widget.minimumSizeHint().width()),
                int(widget.sizeHint().width()),
            )
        return fixed

    def _available_name_edit_width(self) -> int:
        row_width = max(1, int(self.width()))
        layout = self.layout()
        margins_left = margins_right = spacing = 0
        if isinstance(layout, QtWidgets.QHBoxLayout):
            margins = layout.contentsMargins()
            margins_left = int(margins.left())
            margins_right = int(margins.right())
            spacing = max(0, int(layout.spacing()))
        fixed = self._fixed_non_edit_width()
        # Visible sequence includes the edit itself, so gaps = non-edit widgets count.
        non_edit_count = 1
        if self._subrole_group is not None and self._subrole_group.isVisible():
            non_edit_count += 1
        if self._delete_cell is not None and self._delete_cell.isVisible():
            non_edit_count += 1
        gaps = non_edit_count
        usable = row_width - margins_left - margins_right - fixed - (spacing * gaps)
        return max(1, int(usable))

    def minimum_safe_width_hint(self) -> int:
        layout = self.layout()
        margins_left = margins_right = spacing = 0
        if isinstance(layout, QtWidgets.QHBoxLayout):
            margins = layout.contentsMargins()
            margins_left = int(margins.left())
            margins_right = int(margins.right())
            spacing = max(0, int(layout.spacing()))
        non_edit_count = 1
        if self._subrole_group is not None and self._subrole_group.isVisible():
            non_edit_count += 1
        if self._delete_cell is not None and self._delete_cell.isVisible():
            non_edit_count += 1
        gaps = non_edit_count
        # Keep at least 1 px for the edit so all checkboxes stay visible.
        return max(1, margins_left + margins_right + self._fixed_non_edit_width() + (spacing * gaps) + 1)

    def _apply_name_edit_width_constraints(self) -> None:
        available = self._available_name_edit_width()
        configured_min = max(1, int(self._configured_name_min_width))
        configured_max = self._configured_name_max_width
        dynamic_max = available
        if isinstance(configured_max, int) and configured_max > 0:
            dynamic_max = min(dynamic_max, int(configured_max))
        dynamic_max = max(1, int(dynamic_max))
        dynamic_min = max(1, min(configured_min, dynamic_max))
        self.edit.setMinimumWidth(dynamic_min)
        self.edit.setMaximumWidth(dynamic_max)

    def set_name_edit_width_profile(self, *, min_width: int, max_width: int | None) -> None:
        self._configured_name_min_width = max(1, int(min_width))
        self._configured_name_max_width = None if max_width is None else max(1, int(max_width))
        self._apply_name_edit_width_constraints()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_name_edit_width_constraints()

    def apply_subrole_visual_profile(
        self,
        *,
        left_margin: int,
        right_margin: int,
        spacing: int,
        checkbox_hpadding: int,
    ) -> None:
        if self._subrole_layout is not None:
            self._subrole_layout.setContentsMargins(
                max(0, int(left_margin)),
                0,
                max(0, int(right_margin)),
                0,
            )
            self._subrole_layout.setSpacing(max(0, int(spacing)))
        if self._subrole_group is not None:
            # Re-lock width after spacing/margins changed.
            self._subrole_group.adjustSize()
            width = max(1, int(self._subrole_group.sizeHint().width()))
            self._subrole_group.setMinimumWidth(width)
            self._subrole_group.setMaximumWidth(width)
        if checkbox_hpadding > 0:
            style = (
                "QCheckBox { "
                f"padding-left: {int(checkbox_hpadding)}px; "
                f"padding-right: {int(checkbox_hpadding)}px; "
                "}"
            )
        else:
            style = ""
        for cb in self.subrole_checks:
            cb.setStyleSheet(style)
        self._apply_name_edit_width_constraints()

    def focus_name(self, force: bool = False):
        if force:
            self.edit.setFocus(QtCore.Qt.OtherFocusReason)
        self.edit.deselect()
        self.edit.setCursorPosition(len(self.edit.text()))

    def refresh_texts(self):
        self.chk_active.setToolTip(i18n.t("names.active_tooltip"))
        for cb in self.subrole_checks:
            cb.setToolTip(i18n.t("names.subrole_tooltip", label=cb.text()))
        if self.chk_mark_for_delete is not None:
            self.chk_mark_for_delete.setToolTip(i18n.t("names.mark_for_delete_tooltip"))

    def selected_subroles(self) -> set[str]:
        return {cb.text() for cb in self.subrole_checks if cb.isChecked()}

    def _current_subroles(self) -> set[str]:
        data = self.item.data(self.list_widget.SUBROLE_ROLE)
        if isinstance(data, (list, set, tuple)):
            return set(data)
        return set()

    def _is_marked_for_delete(self) -> bool:
        return bool(self.item.data(self.list_widget.MARK_FOR_DELETE_ROLE))

    def _on_active_toggled(self, checked: bool):
        self.list_widget.set_item_state(
            self.item,
            QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked,
        )
        self.list_widget.metaChanged.emit()

    def _on_text_changed(self, text: str):
        old_text = self.item.text().strip()
        new_text = text.strip()
        self.edit.setToolTip(new_text)
        if not old_text and new_text:
            self.list_widget.set_item_state(self.item, QtCore.Qt.Checked)
            self.chk_active.setChecked(True)
        elif old_text and not new_text:
            self.list_widget.set_item_state(self.item, QtCore.Qt.Unchecked)
            self.chk_active.setChecked(False)
        self.item.setText(text)

    def _delete_self_if_empty(self):
        list_widget = self.list_widget

        def _apply_delete():
            if list_widget is None:
                return
            current_row = list_widget.row(self.item)
            if current_row < 0:
                return
            list_widget.delete_row(current_row)
            prev_row = current_row - 1
            if 0 <= prev_row < list_widget.count():
                prev_item = list_widget.item(prev_row)
                list_widget.setCurrentItem(prev_item)
                widget = list_widget.itemWidget(prev_item)
                if isinstance(widget, NameRowWidget):
                    widget.focus_name()

        # Avoid mutating QListWidget while Qt is still processing key events.
        QtCore.QTimer.singleShot(0, _apply_delete)

    def _focus_prev(self):
        row = self.list_widget.row(self.item)
        target = row - 1
        if 0 <= target < self.list_widget.count():
            item = self.list_widget.item(target)
            self.list_widget.setCurrentItem(item)
            widget = self.list_widget.itemWidget(item)
            if isinstance(widget, NameRowWidget):
                widget.focus_name()

    def _focus_next(self):
        row = self.list_widget.row(self.item)
        target = row + 1
        if 0 <= target < self.list_widget.count():
            item = self.list_widget.item(target)
            self.list_widget.setCurrentItem(item)
            widget = self.list_widget.itemWidget(item)
            if isinstance(widget, NameRowWidget):
                widget.focus_name()

    def _insert_new_row(self):
        list_widget = self.list_widget

        def _apply_insert():
            if list_widget is None:
                return
            current_row = list_widget.row(self.item)
            if current_row < 0:
                current_row = list_widget.count() - 1
            insert_row = max(0, min(current_row + 1, list_widget.count()))
            list_widget.insert_name_at(insert_row, "")
            inserted_item = list_widget.item(insert_row)
            if inserted_item is None:
                return
            inserted_widget = list_widget.itemWidget(inserted_item)
            if isinstance(inserted_widget, NameRowWidget):
                inserted_widget.focus_name(force=True)

        # Defer model mutation to the next event-loop tick to prevent
        # re-entrant geometry/editor updates inside keyPressEvent.
        QtCore.QTimer.singleShot(0, _apply_insert)

    def _on_subrole_changed(self, _checked: bool):
        self.item.setData(self.list_widget.SUBROLE_ROLE, list(self.selected_subroles()))
        self.list_widget.metaChanged.emit()

    def _on_mark_for_delete_toggled(self, checked: bool):
        self.item.setData(self.list_widget.MARK_FOR_DELETE_ROLE, bool(checked))
        self.list_widget.metaChanged.emit()


class NamesListPanel(QtWidgets.QWidget):
    """Composite widget: names list with select/deselect and sort actions."""
    def __init__(
        self,
        parent=None,
        subrole_labels: Optional[List[str]] = None,
        *,
        enable_mark_for_delete: bool = True,
    ):
        super().__init__(parent)
        self.names = NamesList(
            self,
            subrole_labels=subrole_labels,
            enable_mark_for_delete=enable_mark_for_delete,
        )
        self._fixed_visible_rows: int | None = None
        self._enable_mark_for_delete = bool(enable_mark_for_delete)
        self._interaction_enabled = True
        self._delete_confirm_handler: Callable[[int], bool] | None = None
        self._applied_theme_key: str | None = None
        self._panel_width_update_pending = False
        self._applied_panel_min_width = -1
        self._applied_panel_max_width = -1
        self._parent_filter_installed = False
        self._window_filter_installed = False
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        self.btn_delete_marked = QtWidgets.QToolButton()
        self.btn_delete_marked.setText("🗑")
        self.btn_delete_marked.setFixedSize(DELETE_MARK_BUTTON_WIDTH, ui_tokens.BUTTON_HEIGHT_SM)
        self.btn_delete_marked.setToolTip(i18n.t("names.delete_marked_tooltip"))
        self.btn_delete_marked.clicked.connect(self._on_delete_marked_clicked)
        self.btn_delete_marked.setVisible(self.names.has_subroles and self._enable_mark_for_delete)
        self.btn_delete_marked.setProperty("dangerActive", False)

        self.btn_toggle_all_names = QtWidgets.QPushButton()
        self.btn_toggle_all_names.setFixedHeight(ui_tokens.BUTTON_HEIGHT_SM)
        self.btn_toggle_all_names.clicked.connect(self._on_toggle_all_names_clicked)

        self.btn_sort_names = QtWidgets.QPushButton(i18n.t("wheel.sort_names"))
        self.btn_sort_names.setFixedHeight(ui_tokens.BUTTON_HEIGHT_SM)
        self.btn_sort_names.setToolTip(i18n.t("wheel.sort_names_tooltip"))
        self.btn_sort_names.clicked.connect(self._on_sort_names_clicked)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(ui_tokens.NAMES_PANEL_LAYOUT_SPACING)

        layout.addWidget(self.names)

        self._action_row_widget = QtWidgets.QWidget(self)
        self._action_row_widget.setObjectName("namesActionRow")
        action_row = QtWidgets.QHBoxLayout(self._action_row_widget)
        action_row.setContentsMargins(0, ui_tokens.NAMES_PANEL_ACTION_TOP_MARGIN, 0, 0)
        action_row.setSpacing(ui_tokens.SECTION_SPACING)
        action_row.addWidget(self.btn_toggle_all_names, 0, QtCore.Qt.AlignLeft)
        action_row.addStretch(1)
        action_row.addWidget(self.btn_sort_names, 0, QtCore.Qt.AlignRight)
        action_row.addWidget(self.btn_delete_marked, 0, QtCore.Qt.AlignRight)
        self._action_row_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        layout.addWidget(self._action_row_widget)

        self.names.itemChanged.connect(self._update_toggle_all_button_label)
        self.names.model().rowsInserted.connect(self._update_toggle_all_button_label)
        self.names.model().rowsRemoved.connect(self._update_toggle_all_button_label)
        self.names.metaChanged.connect(self._update_toggle_all_button_label)
        self.names.itemChanged.connect(self._update_delete_marked_button_state)
        self.names.model().rowsInserted.connect(self._update_delete_marked_button_state)
        self.names.model().rowsRemoved.connect(self._update_delete_marked_button_state)
        self.names.metaChanged.connect(self._update_delete_marked_button_state)
        self.names.itemChanged.connect(self._schedule_panel_width_update)
        self.names.model().rowsInserted.connect(self._schedule_panel_width_update)
        self.names.model().rowsRemoved.connect(self._schedule_panel_width_update)
        self.names.metaChanged.connect(self._schedule_panel_width_update)
        self._update_toggle_all_button_label()
        self._update_delete_marked_button_state()
        self.apply_fixed_widths()
        self._apply_panel_width_constraints()
        self._ensure_parent_event_filter()

    def _schedule_panel_width_update(self, *_args) -> None:
        if self._panel_width_update_pending:
            return
        self._panel_width_update_pending = True
        QtCore.QTimer.singleShot(0, self._apply_panel_width_constraints)

    def _ensure_parent_event_filter(self) -> None:
        if self._parent_filter_installed:
            return
        parent = self.parentWidget()
        if parent is None:
            return
        try:
            parent.installEventFilter(self)
            self._parent_filter_installed = True
        except Exception:
            self._parent_filter_installed = False

    def _ensure_window_event_filter(self) -> None:
        if self._window_filter_installed:
            return
        win = self.window()
        if win is None:
            return
        try:
            win.installEventFilter(self)
            self._window_filter_installed = True
        except Exception:
            self._window_filter_installed = False

    def _available_parent_width(self) -> int | None:
        parent = self.parentWidget()
        if parent is None:
            return None
        try:
            width = int(parent.contentsRect().width())
        except Exception:
            width = int(parent.width())
        if width <= 0:
            return None
        # Leave a tiny safety gap so centered layouts do not push to edge.
        return max(0, width - 2)

    def _list_row_content_width_hint(self) -> int:
        width = 0
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            row_widget = self.names.itemWidget(item)
            if row_widget is not None:
                try:
                    width = max(width, int(row_widget.sizeHint().width()))
                    continue
                except Exception:
                    pass
            try:
                width = max(width, int(self.names.visualItemRect(item).width()))
            except Exception:
                continue
        if width <= 0:
            try:
                width = int(self.names.minimumSizeHint().width())
            except Exception:
                width = int(NAMES_PANEL_MIN_WIDTH_BASE)
        frame = max(0, int(self.names.frameWidth())) * 2
        viewport_margin = max(0, int(getattr(self.names, "_viewport_right_margin", 0)))
        return max(0, width + frame + viewport_margin + 8)

    def _minimum_row_safe_width_hint(self) -> int:
        width = 0
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            row_widget = self.names.itemWidget(item)
            if isinstance(row_widget, NameRowWidget):
                try:
                    width = max(width, int(row_widget.minimum_safe_width_hint()))
                except Exception:
                    continue
        if width <= 0:
            width = 120
        frame = max(0, int(self.names.frameWidth())) * 2
        viewport_margin = max(0, int(getattr(self.names, "_viewport_right_margin", 0)))
        return max(1, width + frame + viewport_margin + 6)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        parent = self.parentWidget()
        win = self.window()
        if obj in (parent, win) and event.type() in (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
            QtCore.QEvent.LayoutRequest,
        ):
            self._schedule_panel_width_update()
        return super().eventFilter(obj, event)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._ensure_parent_event_filter()
        self._ensure_window_event_filter()
        self._schedule_panel_width_update()

    def _row_height_hint(self) -> int:
        row_h = -1
        try:
            row_h = int(self.names.sizeHintForRow(0))
        except Exception:
            row_h = -1
        if row_h <= 0:
            try:
                row_h = int(getattr(self.names, "_row_height", NAME_LIST_ROW_HEIGHT))
            except Exception:
                row_h = NAME_LIST_ROW_HEIGHT
        return max(1, int(row_h))

    def _apply_fixed_visible_rows_height(self) -> None:
        rows = self._fixed_visible_rows
        if rows is None or int(rows) <= 0:
            self.names.setMinimumHeight(0)
            self.names.setMaximumHeight(16777215)
            return
        frame = max(0, int(self.names.frameWidth())) * 2
        target_h = frame + self._row_height_hint() * int(rows)
        self.names.setMinimumHeight(target_h)
        self.names.setMaximumHeight(target_h)

    def set_fixed_visible_rows(self, rows: int | None) -> None:
        if rows is None:
            self._fixed_visible_rows = None
        else:
            self._fixed_visible_rows = max(1, int(rows))
        self._apply_fixed_visible_rows_height()
        self.updateGeometry()

    def set_compact_vertical(self, compact: bool = True) -> None:
        compact_mode = bool(compact)
        if compact_mode:
            self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
            self.names.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            self._action_row_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        else:
            self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
            self.names.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            self._action_row_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        self.updateGeometry()

    def set_language(self, _lang: str):
        self.btn_sort_names.setText(i18n.t("wheel.sort_names"))
        self.btn_sort_names.setToolTip(i18n.t("wheel.sort_names_tooltip"))
        self.btn_delete_marked.setToolTip(i18n.t("names.delete_marked_tooltip"))
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            widget = self.names.itemWidget(item)
            if isinstance(widget, NameRowWidget):
                widget.refresh_texts()
        self._update_toggle_all_button_label()
        self._update_delete_marked_button_state()
        self.apply_fixed_widths()
        self._apply_panel_width_constraints()
        self._apply_fixed_visible_rows_height()

    def apply_theme(self, theme):
        theme_key = str(getattr(theme, "key", "light"))
        if self._applied_theme_key == theme_key:
            return
        style_helpers.style_primary_button(self.btn_sort_names, theme)
        style_helpers.style_primary_button(self.btn_toggle_all_names, theme)
        self.btn_delete_marked.setStyleSheet(_delete_marked_button_style(theme))
        style_helpers.style_names_list(self.names, theme)
        style_helpers.set_stylesheet_if_needed(
            self._action_row_widget,
            f"names_action_row:{theme_key}",
            _names_action_row_style(theme),
        )
        self._applied_theme_key = theme_key

    def apply_fixed_widths(self):
        ui_helpers.set_fixed_width_from_translations(
            self.btn_toggle_all_names,
            ["wheel.select_all", "wheel.deselect_all"],
            padding=26,
            prefixes=["☑ ", "☐ "],
        )
        ui_helpers.set_fixed_width_from_translations(
            self.btn_sort_names,
            ["wheel.sort_names"],
            padding=24,
        )
        self._apply_panel_width_constraints()
        self._apply_fixed_visible_rows_height()

    def _apply_panel_width_constraints(self) -> None:
        self._panel_width_update_pending = False
        panel_pref_max = (
            int(NAMES_PANEL_MAX_WIDTH_WITH_SUBROLES)
            if self.names.has_subroles
            else int(NAMES_PANEL_MAX_WIDTH_DEFAULT)
        )
        panel_hard_max = panel_pref_max + (220 if self.names.has_subroles else 260)
        spacing = max(0, int(ui_tokens.SECTION_SPACING))
        actions_width = (
            int(self.btn_toggle_all_names.minimumSizeHint().width())
            + int(self.btn_sort_names.minimumSizeHint().width())
            + spacing
            + 20
        )
        if self.btn_delete_marked.isVisible():
            actions_width += int(self.btn_delete_marked.minimumSizeHint().width()) + spacing
        content_target = max(self._list_row_content_width_hint(), actions_width)
        row_safe_floor = max(1, int(self._minimum_row_safe_width_hint()))
        parent_available = self._available_parent_width()
        panel_floor = max(80, min(panel_hard_max, row_safe_floor))
        if parent_available is not None:
            parent_width = max(1, int(parent_available))
            panel_cap = max(1, min(panel_hard_max, parent_width))
            panel_floor = min(panel_floor, panel_cap)
            width_from_parent = min(panel_cap, max(1, int(round(parent_width * 0.90))))
            content_cap = min(panel_cap, max(1, int(content_target)))
            panel_target = max(panel_floor, width_from_parent, content_cap)
        else:
            panel_target = max(panel_floor, min(panel_hard_max, int(content_target)))
        panel_min = max(80, min(panel_floor, panel_target))
        panel_max = max(panel_min, panel_target)
        if panel_min != self._applied_panel_min_width:
            self._applied_panel_min_width = panel_min
            self.setMinimumWidth(panel_min)
        if panel_max != self._applied_panel_max_width:
            self._applied_panel_max_width = panel_max
            self.setMaximumWidth(panel_max)
        self.updateGeometry()

    def set_auto_focus_enabled(self, enabled: bool, require_active_focus: bool | None = None) -> None:
        if hasattr(self, "names"):
            self.names.set_auto_focus_enabled(enabled, require_active_focus=require_active_focus)

    def set_delete_confirm_handler(self, handler: Callable[[int], bool] | None) -> None:
        self._delete_confirm_handler = handler

    def refresh_action_state(self):
        self._update_toggle_all_button_label()
        self._update_delete_marked_button_state()

    def set_interactive_enabled(self, enabled: bool) -> None:
        self._interaction_enabled = bool(enabled)
        self.btn_sort_names.setEnabled(bool(enabled))
        self._update_toggle_all_button_label()
        self._update_delete_marked_button_state()

    def set_aux_controls_visible(self, visible: bool) -> None:
        show = bool(visible)
        if hasattr(self, "_action_row_widget"):
            self._action_row_widget.setVisible(show)

    def _item_text(self, item: QtWidgets.QListWidgetItem) -> str:
        widget = self.names.itemWidget(item)
        if isinstance(widget, NameRowWidget):
            return widget.edit.text().strip()
        return item.text().strip()

    def _named_items(self) -> list[QtWidgets.QListWidgetItem]:
        items: list[QtWidgets.QListWidgetItem] = []
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            if self._item_text(item):
                items.append(item)
        return items

    def _all_named_items_checked(self) -> bool:
        items = self._named_items()
        if not items:
            return False
        return all(self.names.item_state(item) == QtCore.Qt.Checked for item in items)

    def _marked_named_rows(self) -> list[int]:
        rows: list[int] = []
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            if not self._item_text(item):
                continue
            if bool(item.data(self.names.MARK_FOR_DELETE_ROLE)):
                rows.append(i)
        return rows

    def _update_toggle_all_button_label(self):
        items = self._named_items()
        if not items:
            self.btn_toggle_all_names.setEnabled(False)
            self.btn_toggle_all_names.setText(f"☑ {i18n.t('wheel.select_all')}")
            self.btn_toggle_all_names.setToolTip(i18n.t("wheel.select_all_tooltip"))
            return
        self.btn_toggle_all_names.setEnabled(bool(self._interaction_enabled))
        if self._all_named_items_checked():
            self.btn_toggle_all_names.setText(f"☐ {i18n.t('wheel.deselect_all')}")
            self.btn_toggle_all_names.setToolTip(i18n.t("wheel.deselect_all_tooltip"))
        else:
            self.btn_toggle_all_names.setText(f"☑ {i18n.t('wheel.select_all')}")
            self.btn_toggle_all_names.setToolTip(i18n.t("wheel.select_all_tooltip"))

    def _update_delete_marked_button_state(self):
        if not self.names.has_subroles or not self._enable_mark_for_delete:
            self.btn_delete_marked.setEnabled(False)
            self._set_delete_button_danger_state(False)
            return
        marked_count = len(self._marked_named_rows())
        enabled = bool(self._interaction_enabled) and marked_count > 0
        self.btn_delete_marked.setEnabled(enabled)
        self._set_delete_button_danger_state(enabled)
        if marked_count > 0:
            self.btn_delete_marked.setToolTip(i18n.t("names.delete_marked_tooltip_active", count=marked_count))
        else:
            self.btn_delete_marked.setToolTip(i18n.t("names.delete_marked_tooltip"))

    def _set_delete_button_danger_state(self, active: bool) -> None:
        self.btn_delete_marked.setProperty("dangerActive", bool(active))
        style = self.btn_delete_marked.style()
        if style is not None:
            style.unpolish(self.btn_delete_marked)
            style.polish(self.btn_delete_marked)
        self.btn_delete_marked.update()

    def _on_toggle_all_names_clicked(self):
        items = self._named_items()
        if not items:
            return
        target_checked = not self._all_named_items_checked()
        blockers = [
            QtCore.QSignalBlocker(self.names),
            QtCore.QSignalBlocker(self.names.model()),
        ]
        try:
            for item in items:
                widget = self.names.itemWidget(item)
                if isinstance(widget, NameRowWidget):
                    widget.chk_active.setChecked(target_checked)
                else:
                    self.names.set_item_state(
                        item,
                        QtCore.Qt.Checked if target_checked else QtCore.Qt.Unchecked,
                    )
        finally:
            del blockers
        self.names.metaChanged.emit()
        self._update_toggle_all_button_label()

    def _on_sort_names_clicked(self):
        self.names.sort_alphabetically()

    def _on_delete_marked_clicked(self):
        rows = self._marked_named_rows()
        if not rows:
            return
        handler = self._delete_confirm_handler
        if handler is not None:
            try:
                if bool(handler(len(rows))):
                    return
            except Exception:
                pass
        self._confirm_delete_marked()

    def confirm_delete_marked(self):
        self._confirm_delete_marked()

    def _confirm_delete_marked(self):
        rows = self._marked_named_rows()
        if not rows:
            self._update_delete_marked_button_state()
            return
        self.names.remove_rows(rows, ensure_one_empty=True)
        self.names.metaChanged.emit()
        self._update_toggle_all_button_label()
        self._update_delete_marked_button_state()
