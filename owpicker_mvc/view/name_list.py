from __future__ import annotations

from typing import Callable, List, Optional
from PySide6 import QtCore, QtGui, QtWidgets
import i18n
from view import style_helpers
from utils import ui_helpers

DELETE_MARK_COLUMN_WIDTH = 20
DELETE_MARK_BUTTON_WIDTH = 28
DELETE_MARK_ROW_RIGHT_MARGIN = 0
_DELETE_MARKED_STYLE_CACHE: dict[str, str] = {}


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


class _NoPaintDelegate(QtWidgets.QStyledItemDelegate):
    """Unterdrückt Standard-Rendering von Text/Checkboxen für Index-Widgets."""
    def paint(self, painter, option, index):
        # Nichts zeichnen – die indexWidgets übernehmen die Darstellung
        return

    def sizeHint(self, option, index):
        return super().sizeHint(option, index)


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
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setItemDelegate(_NoPaintDelegate(self))

        self.setStyleSheet(
            "QListView::item:selected { background: transparent; color: inherit; }"
            "QListView::item:selected:active { background: transparent; color: inherit; }"
            "QListView::item:focus { outline: none; }"
        )

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        sb = self.verticalScrollBar()
        if sb is not None:
            sb.rangeChanged.connect(self._sync_viewport_right_padding)
            sb.installEventFilter(self)
        QtCore.QTimer.singleShot(0, self._sync_viewport_right_padding)

    def _scrollbar_extent(self, sb: QtWidgets.QScrollBar | None = None) -> int:
        scrollbar = sb if sb is not None else self.verticalScrollBar()
        if scrollbar is None:
            return 0
        extent = self.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent, None, scrollbar)
        hint = scrollbar.sizeHint().width()
        return max(0, int(extent), int(hint))

    def _sync_viewport_right_padding(self, *_args) -> None:
        sb = self.verticalScrollBar()
        if sb is None:
            margin_right = 0
        else:
            # Reserve the scrollbar width while hidden so right-aligned controls
            # (delete checkbox column) stay visually stable when it appears.
            extent = self._scrollbar_extent(sb)
            has_vertical_scroll = sb.isVisible() and sb.maximum() > sb.minimum()
            margin_right = 0 if has_vertical_scroll else extent
        if margin_right == self._viewport_right_margin:
            return
        self.setViewportMargins(0, 0, margin_right, 0)
        self._viewport_right_margin = margin_right

    def eventFilter(self, obj: QtCore.QObject, ev: QtCore.QEvent) -> bool:
        sb = self.verticalScrollBar()
        if obj is sb and ev.type() in (
            QtCore.QEvent.Show,
            QtCore.QEvent.Hide,
            QtCore.QEvent.Resize,
            QtCore.QEvent.StyleChange,
        ):
            QtCore.QTimer.singleShot(0, self._sync_viewport_right_padding)
        return super().eventFilter(obj, ev)

    def resizeEvent(self, ev: QtGui.QResizeEvent) -> None:
        super().resizeEvent(ev)
        self._sync_viewport_right_padding()

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
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEditable)
        if active is not None:
            item.setCheckState(QtCore.Qt.Checked if active else QtCore.Qt.Unchecked)
        elif text.strip():
            item.setCheckState(QtCore.Qt.Checked)
        else:
            item.setCheckState(QtCore.Qt.Unchecked)
        item.setData(self.SUBROLE_ROLE, list(subroles or []))
        item.setData(self.MARK_FOR_DELETE_ROLE, False)
        return item

    def _attach_row_widget(self, item: QtWidgets.QListWidgetItem):
        widget = NameRowWidget(self, item, self.subrole_labels)
        self.setItemWidget(item, widget)

    def _detach_row_widget(self, item: QtWidgets.QListWidgetItem) -> None:
        widget = self.itemWidget(item)
        if widget is None:
            return
        # Keep QListWidget/QAbstractItemView internal editor bookkeeping consistent.
        self.removeItemWidget(item)
        widget.deleteLater()

    def add_name(self, text: str = "", subroles: Optional[List[str]] = None, active: Optional[bool] = None):
        item = self._new_item(text, subroles=subroles, active=active)
        self.addItem(item)
        self._attach_row_widget(item)
        self.setCurrentItem(item)
        if not text:
            widget = self.itemWidget(item)
            if widget and self._allow_auto_focus():
                widget.focus_name()

    def insert_name_at(self, row: int, text: str = ""):
        item = self._new_item(text)
        self.insertItem(row, item)
        self._attach_row_widget(item)
        self.setCurrentItem(item)
        widget = self.itemWidget(item)
        if widget and self._allow_auto_focus():
            widget.focus_name()

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
        entries = []
        for i in range(self.count()):
            item = self.item(i)
            entries.append(
                (
                    item.text(),
                    item.checkState() == QtCore.Qt.Checked,
                    item.data(self.SUBROLE_ROLE) or [],
                )
            )

        # Leere nach unten, ansonsten case-insensitive sortieren
        entries.sort(key=lambda e: (not e[0].strip(), e[0].lower()))

        # Bestehende Widgets sauber lösen, dann neu aufbauen
        blockers = [QtCore.QSignalBlocker(self)]
        try:
            while self.count():
                old_item = self.item(0)
                if old_item is None:
                    break
                self._detach_row_widget(old_item)
                removed_item = self.takeItem(0)
                if removed_item is not None:
                    del removed_item
            for name, active, subroles in entries:
                self.add_name(name, subroles=subroles, active=active)
        finally:
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
        action = menu.exec_(self.mapToGlobal(pos))
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
        layout.setContentsMargins(4, 0, right_margin, 0)
        layout.setSpacing(6)

        self.chk_active = QtWidgets.QCheckBox()
        state = item.checkState()
        if state == QtCore.Qt.PartiallyChecked:
            self.chk_active.setTristate(True)
            self.chk_active.setCheckState(state)
        else:
            self.chk_active.setChecked(state == QtCore.Qt.Checked)
        self.chk_active.toggled.connect(self._on_active_toggled)
        layout.addWidget(self.chk_active, 0, QtCore.Qt.AlignVCenter)

        self.edit = NameLineEdit()
        self.edit.setText(item.text())
        self.edit.setMinimumWidth(220)
        self.edit.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.edit.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.edit.textChanged.connect(self._on_text_changed)
        self.edit.deleteEmptyRequested.connect(self._delete_self_if_empty)
        self.edit.moveUpRequested.connect(self._focus_prev)
        self.edit.moveDownRequested.connect(self._focus_next)
        self.edit.newRowRequested.connect(self._insert_new_row)
        layout.addWidget(self.edit, 2)
        # Platz schaffen, damit Subrollen nach rechts rücken
        layout.addStretch(1)

        self.subrole_checks: list[QtWidgets.QCheckBox] = []
        for lbl in subrole_labels:
            cb = QtWidgets.QCheckBox(lbl)
            cb.setChecked(lbl in self._current_subroles())
            cb.toggled.connect(self._on_subrole_changed)
            cb.setToolTip(i18n.t("names.subrole_tooltip", label=lbl))
            self.subrole_checks.append(cb)
            layout.addWidget(cb, 0, QtCore.Qt.AlignVCenter)

        self.chk_mark_for_delete: QtWidgets.QCheckBox | None = None
        if subrole_labels and self.list_widget.enable_mark_for_delete:
            self.chk_mark_for_delete = QtWidgets.QCheckBox()
            self.chk_mark_for_delete.setChecked(self._is_marked_for_delete())
            self.chk_mark_for_delete.setToolTip(i18n.t("names.mark_for_delete_tooltip"))
            self.chk_mark_for_delete.toggled.connect(self._on_mark_for_delete_toggled)
            delete_cell = QtWidgets.QWidget(self)
            delete_cell.setFixedWidth(DELETE_MARK_COLUMN_WIDTH)
            delete_cell_layout = QtWidgets.QHBoxLayout(delete_cell)
            delete_cell_layout.setContentsMargins(0, 0, 0, 0)
            delete_cell_layout.setSpacing(0)
            delete_cell_layout.addWidget(
                self.chk_mark_for_delete,
                0,
                QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
            )
            layout.addStretch(1)
            layout.addWidget(delete_cell, 0, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        else:
            layout.addStretch(1)
        # Kein automatischer Fokus auf neue/leer Zeilen

    def focus_name(self, force: bool = False):
        if force:
            self.edit.setFocus(QtCore.Qt.OtherFocusReason)
        self.edit.deselect()
        self.edit.setCursorPosition(len(self.edit.text()))

    def refresh_texts(self):
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
        self.item.setCheckState(QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)

    def _on_text_changed(self, text: str):
        old_text = self.item.text().strip()
        new_text = text.strip()
        if not old_text and new_text:
            self.item.setCheckState(QtCore.Qt.Checked)
            self.chk_active.setChecked(True)
        elif old_text and not new_text:
            self.item.setCheckState(QtCore.Qt.Unchecked)
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
        self._enable_mark_for_delete = bool(enable_mark_for_delete)
        self._interaction_enabled = True
        self._delete_confirm_handler: Callable[[int], bool] | None = None
        self._applied_theme_key: str | None = None

        self.btn_delete_marked = QtWidgets.QToolButton()
        self.btn_delete_marked.setText("🗑")
        self.btn_delete_marked.setFixedSize(DELETE_MARK_BUTTON_WIDTH, 28)
        self.btn_delete_marked.setToolTip(i18n.t("names.delete_marked_tooltip"))
        self.btn_delete_marked.clicked.connect(self._on_delete_marked_clicked)
        self.btn_delete_marked.setVisible(self.names.has_subroles and self._enable_mark_for_delete)
        self.btn_delete_marked.setProperty("dangerActive", False)

        self.btn_toggle_all_names = QtWidgets.QPushButton()
        self.btn_toggle_all_names.setFixedHeight(28)
        self.btn_toggle_all_names.clicked.connect(self._on_toggle_all_names_clicked)

        self.btn_sort_names = QtWidgets.QPushButton(i18n.t("wheel.sort_names"))
        self.btn_sort_names.setFixedHeight(28)
        self.btn_sort_names.setToolTip(i18n.t("wheel.sort_names_tooltip"))
        self.btn_sort_names.clicked.connect(self._on_sort_names_clicked)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(self.names)

        self._action_row_widget = QtWidgets.QWidget(self)
        action_row = QtWidgets.QHBoxLayout(self._action_row_widget)
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        action_row.addWidget(self.btn_toggle_all_names, 0, QtCore.Qt.AlignLeft)
        action_row.addStretch(1)
        action_row.addWidget(self.btn_sort_names, 0, QtCore.Qt.AlignRight)
        action_row.addWidget(self.btn_delete_marked, 0, QtCore.Qt.AlignRight)
        layout.addWidget(self._action_row_widget)

        self.names.itemChanged.connect(self._update_toggle_all_button_label)
        self.names.model().rowsInserted.connect(self._update_toggle_all_button_label)
        self.names.model().rowsRemoved.connect(self._update_toggle_all_button_label)
        self.names.metaChanged.connect(self._update_toggle_all_button_label)
        self.names.itemChanged.connect(self._update_delete_marked_button_state)
        self.names.model().rowsInserted.connect(self._update_delete_marked_button_state)
        self.names.model().rowsRemoved.connect(self._update_delete_marked_button_state)
        self.names.metaChanged.connect(self._update_delete_marked_button_state)
        self._update_toggle_all_button_label()
        self._update_delete_marked_button_state()
        self.apply_fixed_widths()

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

    def apply_theme(self, theme):
        theme_key = str(getattr(theme, "key", "light"))
        if self._applied_theme_key == theme_key:
            return
        style_helpers.style_primary_button(self.btn_sort_names, theme)
        style_helpers.style_primary_button(self.btn_toggle_all_names, theme)
        self.btn_delete_marked.setStyleSheet(_delete_marked_button_style(theme))
        style_helpers.style_names_list(self.names, theme)
        self._applied_theme_key = theme_key

    def apply_fixed_widths(self):
        ui_helpers.set_fixed_width_from_translations(
            self.btn_toggle_all_names,
            ["wheel.select_all", "wheel.deselect_all"],
            padding=44,
            prefixes=["☑ ", "☐ "],
        )
        ui_helpers.set_fixed_width_from_translations(
            self.btn_sort_names,
            ["wheel.sort_names"],
            padding=44,
        )

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
        return all(item.checkState() == QtCore.Qt.Checked for item in items)

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
                    item.setCheckState(QtCore.Qt.Checked if target_checked else QtCore.Qt.Unchecked)
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
