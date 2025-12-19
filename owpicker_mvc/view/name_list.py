from __future__ import annotations

from typing import List, Optional
from PySide6 import QtCore, QtGui, QtWidgets
import i18n


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
        self.chk_active.setChecked(item.checkState() == QtCore.Qt.Checked)
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
