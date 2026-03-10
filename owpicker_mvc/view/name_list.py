from __future__ import annotations

from typing import List, Optional
from PySide6 import QtCore, QtGui, QtWidgets
import i18n
from view import ui_tokens
from view.name_list_geometry import NamesListGeometryMixin
from view.name_list_support import (
    DELETE_MARK_COLUMN_WIDTH,
    DELETE_MARK_ROW_RIGHT_MARGIN,
    NAME_EDIT_HEIGHT,
    NAME_EDIT_MAX_WIDTH_WITH_SUBROLES,
    NAME_EDIT_MIN_WIDTH_WITHOUT_SUBROLES,
    NAME_EDIT_MIN_WIDTH_WITH_SUBROLES,
    NAME_LIST_ROW_HEIGHT,
    SUBROLE_CHECKBOX_HORIZONTAL_PADDING,
    SUBROLE_CHECK_SPACING,
    SUBROLE_GROUP_LEFT_MARGIN,
    SUBROLE_GROUP_RIGHT_MARGIN,
    NameLineEdit,
    NoPaintDelegate as _NoPaintDelegate,
)


class NamesList(NamesListGeometryMixin, QtWidgets.QListWidget):
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
        self._last_viewport_width = -1
        self._syncing_viewport_margin = False
        self._geometry_sync_pending = False
        self._bulk_update_depth = 0
        self._bulk_geometry_dirty = False
        self._bulk_prev_updates_enabled = True
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
        self._schedule_geometry_sync()

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
        if self._bulk_update_depth > 0:
            select_row = False
            focus_if_empty = False
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
        if self._bulk_update_depth > 0:
            self._bulk_geometry_dirty = True
        else:
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
            with self.batch_update():
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
        self._applied_edit_min_width = -1
        self._applied_edit_max_width = -1
        self.subrole_checks: list[QtWidgets.QCheckBox] = []
        self._subrole_group: QtWidgets.QWidget | None = None
        self._subrole_layout: QtWidgets.QHBoxLayout | None = None
        self._delete_cell: QtWidgets.QWidget | None = None
        self._subrole_checkbox_hpadding = 0

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
            self._relayout_subrole_group()
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
        if dynamic_min != self._applied_edit_min_width:
            self.edit.setMinimumWidth(dynamic_min)
            self._applied_edit_min_width = dynamic_min
        if dynamic_max != self._applied_edit_max_width:
            self.edit.setMaximumWidth(dynamic_max)
            self._applied_edit_max_width = dynamic_max

    def set_name_edit_width_profile(self, *, min_width: int, max_width: int | None) -> None:
        self._configured_name_min_width = max(1, int(min_width))
        self._configured_name_max_width = None if max_width is None else max(1, int(max_width))
        self._apply_name_edit_width_constraints()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_name_edit_width_constraints()

    def _relayout_subrole_group(self) -> None:
        if self._subrole_group is None:
            return
        # Re-measure after style changes so two-letter labels do not clip on Windows.
        for cb in self.subrole_checks:
            cb.ensurePolished()
            style = cb.style()
            fm = cb.fontMetrics()
            text_w = int(fm.horizontalAdvance(cb.text()))
            indicator_w = int(style.pixelMetric(QtWidgets.QStyle.PM_IndicatorWidth, None, cb))
            label_spacing = int(style.pixelMetric(QtWidgets.QStyle.PM_CheckBoxLabelSpacing, None, cb))
            if label_spacing < 0:
                label_spacing = 4
            # Safety slack avoids clipping of compact labels like MT/OT on Windows.
            content_w = (
                indicator_w
                + label_spacing
                + text_w
                + (2 * max(0, int(self._subrole_checkbox_hpadding)))
                + 8
            )
            target_w = max(
                1,
                int(cb.sizeHint().width()),
                int(cb.minimumSizeHint().width()),
                int(content_w),
            )
            cb.setFixedWidth(target_w)
        self._subrole_group.ensurePolished()
        self._subrole_group.adjustSize()
        width = max(1, int(self._subrole_group.sizeHint().width()))
        self._subrole_group.setMinimumWidth(width)
        self._subrole_group.setMaximumWidth(width)

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
        if checkbox_hpadding > 0:
            style = (
                "QCheckBox { "
                f"padding-left: {int(checkbox_hpadding)}px; "
                f"padding-right: {int(checkbox_hpadding)}px; "
                "}"
            )
        else:
            style = ""
        self._subrole_checkbox_hpadding = max(0, int(checkbox_hpadding))
        for cb in self.subrole_checks:
            cb.setStyleSheet(style)
        self._relayout_subrole_group()
        self._apply_name_edit_width_constraints()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self._subrole_group is not None:
            QtCore.QTimer.singleShot(0, self._relayout_subrole_group)

    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() in (
            QtCore.QEvent.StyleChange,
            QtCore.QEvent.FontChange,
            QtCore.QEvent.PolishRequest,
            QtCore.QEvent.ApplicationFontChange,
        ):
            if self._subrole_group is not None:
                QtCore.QTimer.singleShot(0, self._relayout_subrole_group)

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



# Re-export for compatibility with existing imports.
from view.name_list_panel import NamesListPanel

__all__ = ["NamesList", "NameRowWidget", "NamesListPanel"]
