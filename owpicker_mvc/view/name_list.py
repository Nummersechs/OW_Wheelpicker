from __future__ import annotations

from typing import List, Optional
from PySide6 import QtCore, QtGui, QtWidgets
import i18n
from view import style_helpers


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

    def __init__(self, parent=None, subrole_labels: Optional[List[str]] = None):
        super().__init__(parent)
        self.subrole_labels = subrole_labels or []
        self.has_subroles = bool(self.subrole_labels)
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
        return item

    def _attach_row_widget(self, item: QtWidgets.QListWidgetItem):
        widget = NameRowWidget(self, item, self.subrole_labels)
        self.setItemWidget(item, widget)

    def add_name(self, text: str = "", subroles: Optional[List[str]] = None, active: Optional[bool] = None):
        item = self._new_item(text, subroles=subroles, active=active)
        self.addItem(item)
        self._attach_row_widget(item)
        self.setCurrentItem(item)
        if not text:
            widget = self.itemWidget(item)
            if widget:
                widget.focus_name()

    def insert_name_at(self, row: int, text: str = ""):
        item = self._new_item(text)
        self.insertItem(row, item)
        self._attach_row_widget(item)
        self.setCurrentItem(item)
        widget = self.itemWidget(item)
        if widget:
            widget.focus_name()

    def delete_row(self, row: int):
        if self.count() <= 1:
            return
        if 0 <= row < self.count():
            item = self.item(row)
            if item is not None:
                widget = self.itemWidget(item)
                if widget:
                    widget.setParent(None)
            self.takeItem(row)

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
        blockers = [
            QtCore.QSignalBlocker(self),
            QtCore.QSignalBlocker(self.model()),
        ]
        try:
            while self.count():
                it = self.takeItem(0)
                widget = self.itemWidget(it)
                if widget:
                    widget.setParent(None)
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
        layout.setContentsMargins(4, 0, 4, 0)
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

        layout.addStretch(1)
        if not self.edit.text().strip():
            QtCore.QTimer.singleShot(0, self.focus_name)

    def focus_name(self):
        self.edit.setFocus()
        self.edit.deselect()
        self.edit.setCursorPosition(len(self.edit.text()))

    def selected_subroles(self) -> set[str]:
        return {cb.text() for cb in self.subrole_checks if cb.isChecked()}

    def _current_subroles(self) -> set[str]:
        data = self.item.data(self.list_widget.SUBROLE_ROLE)
        if isinstance(data, (list, set, tuple)):
            return set(data)
        return set()

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
        row = self.list_widget.row(self.item)
        self.list_widget.delete_row(row)
        prev_row = row - 1
        if 0 <= prev_row < self.list_widget.count():
            prev_item = self.list_widget.item(prev_row)
            self.list_widget.setCurrentItem(prev_item)
            widget = self.list_widget.itemWidget(prev_item)
            if isinstance(widget, NameRowWidget):
                widget.focus_name()

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
        row = self.list_widget.row(self.item)
        self.list_widget.insert_name_at(row + 1, "")

    def _on_subrole_changed(self, _checked: bool):
        self.item.setData(self.list_widget.SUBROLE_ROLE, list(self.selected_subroles()))
        self.list_widget.metaChanged.emit()


class NamesListPanel(QtWidgets.QWidget):
    """Composite widget: names list with select/deselect and sort actions."""
    def __init__(self, parent=None, subrole_labels: Optional[List[str]] = None):
        super().__init__(parent)
        self.names = NamesList(self, subrole_labels=subrole_labels)

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

        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addWidget(self.btn_toggle_all_names, 0, QtCore.Qt.AlignLeft)
        action_row.addStretch(1)
        action_row.addWidget(self.btn_sort_names, 0, QtCore.Qt.AlignRight)
        layout.addLayout(action_row)

        self.names.itemChanged.connect(self._update_toggle_all_button_label)
        self.names.model().rowsInserted.connect(self._update_toggle_all_button_label)
        self.names.model().rowsRemoved.connect(self._update_toggle_all_button_label)
        self.names.metaChanged.connect(self._update_toggle_all_button_label)
        self._update_toggle_all_button_label()
        self.apply_fixed_widths()

    def set_language(self, _lang: str):
        self.btn_sort_names.setText(i18n.t("wheel.sort_names"))
        self.btn_sort_names.setToolTip(i18n.t("wheel.sort_names_tooltip"))
        self._update_toggle_all_button_label()
        self.apply_fixed_widths()

    def apply_theme(self, theme):
        style_helpers.style_primary_button(self.btn_sort_names, theme)
        style_helpers.style_primary_button(self.btn_toggle_all_names, theme)
        style_helpers.style_names_list(self.names, theme)

    def apply_fixed_widths(self):
        def set_min(widget, keys, padding=20, prefixes=None):
            if widget is None:
                return
            prefixes_local = prefixes or [""]
            font = widget.font()
            fm = QtGui.QFontMetrics(font)
            max_w = 0
            for key in keys:
                entry = i18n.TRANSLATIONS.get(key, {})
                texts = entry.values() if isinstance(entry, dict) else [entry]
                for txt in texts:
                    if txt is None:
                        continue
                    for pre in prefixes_local:
                        max_w = max(max_w, fm.horizontalAdvance(f"{pre}{txt}"))
            width = max_w + padding
            widget.setMinimumWidth(width)
            widget.setMaximumWidth(width)

        set_min(self.btn_toggle_all_names, ["wheel.select_all", "wheel.deselect_all"], padding=44, prefixes=["☑ ", "☐ "])
        set_min(self.btn_sort_names, ["wheel.sort_names"], padding=44)

    def refresh_action_state(self):
        self._update_toggle_all_button_label()

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

    def _update_toggle_all_button_label(self):
        items = self._named_items()
        if not items:
            self.btn_toggle_all_names.setEnabled(False)
            self.btn_toggle_all_names.setText(f"☑ {i18n.t('wheel.select_all')}")
            self.btn_toggle_all_names.setToolTip(i18n.t("wheel.select_all_tooltip"))
            return
        self.btn_toggle_all_names.setEnabled(True)
        if self._all_named_items_checked():
            self.btn_toggle_all_names.setText(f"☐ {i18n.t('wheel.deselect_all')}")
            self.btn_toggle_all_names.setToolTip(i18n.t("wheel.deselect_all_tooltip"))
        else:
            self.btn_toggle_all_names.setText(f"☑ {i18n.t('wheel.select_all')}")
            self.btn_toggle_all_names.setToolTip(i18n.t("wheel.select_all_tooltip"))

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
