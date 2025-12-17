from typing import List, Optional, Union
import random, itertools
from PySide6 import QtCore, QtGui, QtWidgets
from view.wheel_disc import WheelDisc
from logic.spin_engine import plan_spin
import config

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
            # Leere Zeile + Löschen → Zeile entfernen
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
        # Einzel-Auswahl
        self.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        # Eigene Widgets pro Zeile – Standard-Editing aus
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setItemDelegate(_NoPaintDelegate(self))

        # Auswahl-Markierung optisch unsichtbar machen
        self.setStyleSheet(
            "QListView::item:selected { background: transparent; color: inherit; }"
            "QListView::item:selected:active { background: transparent; color: inherit; }"
            "QListView::item:focus { outline: none; }"
        )

        # Kontextmenü aktivieren
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)


    def _new_item(self, text: str = "", subroles: Optional[List[str]] = None) -> QtWidgets.QListWidgetItem:
        item = QtWidgets.QListWidgetItem(text)
        item.setFlags(
            item.flags()
            | QtCore.Qt.ItemIsUserCheckable
            | QtCore.Qt.ItemIsEditable
        )
        # Neue Zeile: Checkbox abhängig vom Inhalt setzen
        # - leerer Text  → unchecked
        # - nicht leerer Text → checked
        if text.strip():
            item.setCheckState(QtCore.Qt.Checked)
        else:
            item.setCheckState(QtCore.Qt.Unchecked)
        item.setData(self.SUBROLE_ROLE, list(subroles or []))
        return item

    def _attach_row_widget(self, item: QtWidgets.QListWidgetItem):
        widget = NameRowWidget(self, item, self.subrole_labels)
        self.setItemWidget(item, widget)

    def add_name(self, text: str = "", subroles: Optional[List[str]] = None):
        item = self._new_item(text, subroles=subroles)
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
        # Letzte vorhandene Zeile nie löschen – es soll immer mindestens eine geben
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
        # Linksklick auf einen Eintrag: Fokus in die Zeile setzen
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
        # ENTER: neue Zeile unter der aktuellen
        if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            row = self.currentRow()
            if row < 0:
                row = self.count() - 1

            self.insert_name_at(row + 1, "")
            return

        # Andere Tasten normal behandeln
        super().keyPressEvent(ev)

    def _show_context_menu(self, pos: QtCore.QPoint):
        # Bei Rechtsklick die Zeile unter dem Mauszeiger zur aktuellen machen
        item = self.itemAt(pos)
        if item is not None and not item.isSelected():
            self.setCurrentItem(item)
            item.setSelected(True)

        menu = QtWidgets.QMenu(self)
        act_new = menu.addAction("Neuer Name")
        act_del = menu.addAction("Ausgewählte löschen")
        if not self.selectedItems():
            act_del.setEnabled(False)
        action = menu.exec_(self.mapToGlobal(pos))
        if action == act_new:
            self.add_name("")
        elif action == act_del:
            # Alle selektierten Zeilen löschen
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
        self.edit.textChanged.connect(self._on_text_changed)
        self.edit.deleteEmptyRequested.connect(self._delete_self_if_empty)
        self.edit.moveUpRequested.connect(self._focus_prev)
        self.edit.moveDownRequested.connect(self._focus_next)
        self.edit.newRowRequested.connect(self._insert_new_row)
        layout.addWidget(self.edit, 1)

        self.subrole_checks: list[QtWidgets.QCheckBox] = []
        for lbl in subrole_labels:
            cb = QtWidgets.QCheckBox(lbl)
            cb.setChecked(lbl in self._current_subroles())
            cb.toggled.connect(self._on_subrole_changed)
            cb.setToolTip(f"Subrolle {lbl}")
            self.subrole_checks.append(cb)
            layout.addWidget(cb, 0, QtCore.Qt.AlignVCenter)

        layout.addStretch(1)
        if not self.edit.text().strip():
            QtCore.QTimer.singleShot(0, self.focus_name)

    # ---- helpers ----
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

    # ---- signal handlers ----
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

class WheelView(QtWidgets.QWidget):
    spun = QtCore.Signal(str)
    request_spin = QtCore.Signal()
    stateChanged = QtCore.Signal()
    def __init__(self, title: str, defaults: List[str], pair_mode=False, allow_pair_toggle=False, subrole_labels: Optional[List[str]] = None):
        super().__init__()
        self.pair_mode = pair_mode; self.allow_pair_toggle = allow_pair_toggle; self._is_spinning = False
        self.subrole_labels = subrole_labels or []
        self.use_subrole_filter = False
        self.view = QtWidgets.QGraphicsView()
        self.view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setStyleSheet("QGraphicsView { background: transparent; border: none; }")
        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scene = QtWidgets.QGraphicsScene(); self.view.setScene(self.scene)
        self.wheel = WheelDisc(self._effective_names_from(defaults), radius=config.WHEEL_RADIUS); self.scene.addItem(self.wheel); self.wheel.setPos(0,0)
        self.wheel.segmentToggled.connect(self._on_segment_toggled)
        r = self.wheel.radius
        self._disabled_indices: set[int] = set()
        self._disabled_labels: set[str] = set()

        # Szene mit etwas Rand oben (für den Pfeil) und wenig Rand unten
        self.scene.setSceneRect(-r - 80, -r - 100, 2 * r + 160, 2 * r + 160)

        self.pointer = self._make_pointer()
        self.scene.addItem(self.pointer)

        # Canvas/View: Höhe fest begrenzen, Breite darf wachsen
        size = int(2 * r + 80)          # rund um das Rad, wenig Extra-Rand
        self.view.setMinimumSize(size, size)
        # View darf in beide Richtungen mitwachsen, Rad wird via fitInView skaliert
        self.view.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        self.view.setAlignment(QtCore.Qt.AlignCenter)
        QtCore.QTimer.singleShot(0, self._refit_view)
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.label = QtWidgets.QLabel(title)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet(
            "font-size:16px; font-weight:600;"
        )

        header.addStretch(1)
        header.addWidget(self.label)
        header.addStretch(1)

        self.toggle = None
        if allow_pair_toggle:
            self.toggle = QtWidgets.QCheckBox("Paare bilden")
            self.toggle.setChecked(self.pair_mode)
            self.toggle.stateChanged.connect(self._on_toggle_pair_mode)
            header.setSpacing(12)
            header.addWidget(self.toggle, 0, QtCore.Qt.AlignVCenter)
        self.chk_subroles = None
        if self.subrole_labels and allow_pair_toggle:
            self.chk_subroles = QtWidgets.QCheckBox("Subrollen")
            self.chk_subroles.setChecked(False)
            hint = "Paare nur mit klaren Subrollen bilden"
            if len(self.subrole_labels) >= 2:
                hint = f"Paare nur {self.subrole_labels[0]} + {self.subrole_labels[1]} zulassen"
            self.chk_subroles.setToolTip(hint)
            self.chk_subroles.setEnabled(self.pair_mode)
            self.chk_subroles.stateChanged.connect(self._on_toggle_subroles)
            header.addWidget(self.chk_subroles, 0, QtCore.Qt.AlignVCenter)

        # Optional: Checkbox "Namen anzeigen" im Header
        self.chk_show_names = QtWidgets.QCheckBox("Namen anzeigen")
        self.chk_show_names.setChecked(True)
        self.chk_show_names.stateChanged.connect(self._on_toggle_show_names)
        header.addWidget(self.chk_show_names, 0, QtCore.Qt.AlignVCenter)

        # ---------- Ergebnis-Widget: Label + Löschen-Icon ----------
        self.result = QtWidgets.QLabel("–")
        # Text links, vertikal mittig
        self.result.setAlignment(QtCore.Qt.AlignCenter)
        self.result.setStyleSheet(
            "font-size:14px; color:#666; margin-top:6px;"
        )

        self.btn_clear_result = QtWidgets.QToolButton()
        self.btn_clear_result.setText("✖")
        self.btn_clear_result.setToolTip("Ergebnis löschen")
        self.btn_clear_result.setAutoRaise(True)  # kein blauer Button, nur Icon
        self.btn_clear_result.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_clear_result.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                color: #b00020;
                font-size: 14px;
            }
            QToolButton:hover {
                color: #ff1744;
            }
        """)
        self.btn_clear_result.clicked.connect(self._clear_result)
        self.btn_clear_result.setVisible(False)  # nur zeigen, wenn Ergebnis da ist

        # Container-Widget für Ergebnis + Icon
        self.result_widget = QtWidgets.QWidget()
        result_layout = QtWidgets.QHBoxLayout(self.result_widget)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(4)

        # [ Stretch | Ergebnis | X | Stretch ]
        result_layout.addStretch(1)
        result_layout.addWidget(self.result, 0, QtCore.Qt.AlignVCenter)
        result_layout.addSpacing(4)
        result_layout.addWidget(self.btn_clear_result, 0, QtCore.Qt.AlignVCenter)
        result_layout.addStretch(1)

        # ---------- Namensliste mit integrierten Checkboxen ----------
        # Eine Liste, in der jede Zeile ein Name mit Häkchen ist.
                # Hinweislabel für die Checkboxen
        self.names_hint = QtWidgets.QLabel(
            "Aktivierte Namen werden berücksichtigt.\n"
            "Segmente anklicken, um sie vom Spin auszuschließen.\n"
            "Gleiche Namen werden pro Spin nur einmal vergeben."
        )
        self.names_hint.setStyleSheet("color:#444; font-size:12px; padding:2px;")
        self.names = NamesList(subrole_labels=self.subrole_labels)

        # Start-Namen anlegen – neue Namen sind standardmäßig aktiv (Checked)
        for entry in self._normalize_entries(defaults):
            self.names.add_name(entry["name"], subroles=entry.get("subroles", []))
        
        # Falls gar keine Defaults/Saved Names vorhanden sind, eine leere Zeile hinzufügen
        if self.names.count() == 0:
            self.names.add_name("")

        # Änderungen an Text oder Häkchen überwachen
        self.names.itemChanged.connect(self._on_names_list_changed)
        self.names.model().rowsInserted.connect(self._on_names_list_changed)
        self.names.model().rowsRemoved.connect(self._on_names_list_changed)
        self.names.metaChanged.connect(self._on_names_list_changed)
# ---------- Buttons unter dem Rad ----------
        self.btn_local_spin = QtWidgets.QPushButton("🔁 Dieses Rad drehen")
        self.btn_local_spin.setFixedHeight(36)
        self.btn_local_spin.clicked.connect(self.request_spin.emit)

        # Toggle-Button statt Checkbox, optisch wie ein weiterer Button
        self.btn_include_in_all = QtWidgets.QPushButton()
        self.btn_include_in_all.setCheckable(True)
        self.btn_include_in_all.setChecked(True)
        self.btn_include_in_all.setFixedHeight(36)
        self.btn_include_in_all.setToolTip(
            "Wenn aktiv, wird dieses Rad beim Button »Drehen« mitgedreht."
        )

        # Initialen Text mit Symbol setzen
        self._on_include_in_all_toggled(self.btn_include_in_all.isChecked())
        # Bei jedem Umschalten Text aktualisieren
        self.btn_include_in_all.toggled.connect(self._on_include_in_all_toggled)


        # Buttonzeile: Spin + "Bei Drehen" nebeneinander
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self.btn_local_spin, 1)
        btn_row.addWidget(self.btn_include_in_all, 0)

        # ---------- Karte / Card-Layout ----------
        card = QtWidgets.QFrame()
        card.setObjectName("card")
        card.setStyleSheet(
            "#card { "
            "background: rgba(255,255,255,0.75); "
            "border:1px solid #e6e6e6; border-radius:16px; }"
        )

        inner = QtWidgets.QVBoxLayout(card)
        inner.setContentsMargins(16, 12, 16, 12)
        inner.addLayout(header)
        inner.addWidget(self.view, 1)
        inner.addWidget(self.result_widget)
        inner.addLayout(btn_row)
        inner.addWidget(self.names_hint)
        inner.addWidget(self.names)
        
        # NEU: Checkbox-Styling
        self.setStyleSheet("""
            QCheckBox::indicator,
            QListView::indicator {
                width: 6px;
                height: 6px;
                border: 2px solid black;
                border-radius: 3px;
                background: white;
            }

            QCheckBox::indicator:checked,
            QListView::indicator:checked {
                background: black;
            }
        """)

        # NEU: Startwert für Namensanzahl merken und UI initial justieren
        self._last_name_count = len(self._base_names())
        self._update_name_dependent_ui()

        outer = QtWidgets.QVBoxLayout(self)
        outer.addWidget(card)
        QtCore.QTimer.singleShot(0, self._refit_view)
        
    def _make_pointer(self) -> QtWidgets.QGraphicsItem:
        r = self.wheel.radius
        path = QtGui.QPainterPath()
        # Einfacher Dreiecks-Pfeil über dem Rad
        tri = QtGui.QPolygonF([
            QtCore.QPointF(-20, -r - 60),
            QtCore.QPointF(20, -r - 60),
            QtCore.QPointF(0, -r - 10),
        ])
        path.addPolygon(tri)
        item = QtWidgets.QGraphicsPathItem(path)
        item.setBrush(QtGui.QBrush(QtGui.QColor(220, 50, 40)))
        item.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        return item

    def _apply_placeholder(self):
        self.result.setToolTip(
            f"Aktuell: {'Paare' if self.pair_mode else 'Einzelnamen'}"
        )

        if self.pair_mode:
            if self.use_subrole_filter and len(self.subrole_labels) >= 2:
                self.names_hint.setText(f"Paare: {self.subrole_labels[0]} + {self.subrole_labels[1]}")
            else:
                self.names_hint.setText(
                    "Paare werden automatisch gebildet.\n"
                    "Segmente anklicken, um sie vom Spin auszuschließen.\n"
                    "Gleiche Namen werden pro Spin nur einmal vergeben."
                )
        else:
            self.names_hint.setText(
                "Aktivierte Namen werden berücksichtigt.\n"
                "Segmente anklicken, um sie vom Spin auszuschließen.\n"
                "Gleiche Namen werden pro Spin nur einmal vergeben."
            )

    def get_current_names(self) -> list[str]:
        """Liefert alle aktuell eingetragenen Namen (ohne Leerzeilen)."""
        return self._base_names()
    def get_current_entries(self) -> list[dict]:
        """
        Liefert alle Einträge (auch inaktive) mit Subrollen.
        Struktur: {"name": str, "subroles": [str], "active": bool}
        """
        entries: list[dict] = []
        for i in range(self.names.count()):
            item = self.names.item(i)
            name = self._item_text(item)
            if not name:
                continue
            subroles = list(self._item_subroles(item))
            active = item.checkState() == QtCore.Qt.Checked
            entries.append({"name": name, "subroles": subroles, "active": active})
        return entries
    def _item_text(self, item: QtWidgets.QListWidgetItem) -> str:
        widget = self.names.itemWidget(item)
        if isinstance(widget, NameRowWidget):
            return widget.edit.text().strip()
        return item.text().strip()
    def _item_subroles(self, item: QtWidgets.QListWidgetItem) -> set[str]:
        widget = self.names.itemWidget(item)
        if isinstance(widget, NameRowWidget):
            return widget.selected_subroles()
        data = item.data(self.names.SUBROLE_ROLE)
        if isinstance(data, (list, set, tuple)):
            return set(data)
        return set()
    def _base_names(self) -> List[str]:
        """Alle Namen aus der Liste (ohne Leerzeilen, Häkchen egal)."""
        names: list[str] = []
        for i in range(self.names.count()):
            text = self._item_text(self.names.item(i))
            if text:
                names.append(text)
        return names

    def _active_entries(self) -> List[dict]:
        """
        Nur die aktivierten Namen inklusive Subrollen-Auswahl.
        Rückgabe-Element: {"name": str, "subroles": set[str]}
        """
        entries: list[dict] = []
        for i in range(self.names.count()):
            item = self.names.item(i)
            text = self._item_text(item)
            if not text or item.checkState() != QtCore.Qt.Checked:
                continue
            subroles = self._item_subroles(item)
            entries.append({"name": text, "subroles": subroles})
        return entries

    def _active_names(self) -> List[str]:
        return [entry["name"] for entry in self._active_entries()]

    def _on_names_list_changed(self, *args):
        """Wenn Namen geändert, hinzugefügt oder entfernt werden."""
        # Rad mit aktiven Namen aktualisieren
        self.wheel.set_names(self._effective_names_from(self._active_entries(), include_disabled=True))
        self._refresh_disabled_indices()
        self._update_name_dependent_ui()
        self.stateChanged.emit()

    def _effective_names_from(self, base: Union[List[dict], List[str]], include_disabled: bool = True) -> List[str]:
        """
        Liefert die Labels, die tatsächlich auf dem Rad landen.
        Nutzt Subrollen-Filter, falls aktiviert.
        """
        if not base:
            return []

        # Für Abwärtskompatibilität auch reine Namenslisten akzeptieren
        if base and isinstance(base[0], str):
            entries = [{"name": n, "subroles": set()} for n in base if n]
        else:
            entries = base  # type: ignore

        base_names = [e["name"] for e in entries]
        if not self.pair_mode:
            names = base_names
        else:
            # Subrollen-Filter: nur Paare aus zwei unterschiedlichen Subrollen
            if self.use_subrole_filter and len(self.subrole_labels) >= 2:
                role_a, role_b = self.subrole_labels[:2]
                pairs: list[str] = []
                for a, b in itertools.combinations(entries, 2):
                    roles_a = set(a.get("subroles", set()) or set())
                    roles_b = set(b.get("subroles", set()) or set())
                    if not roles_a or not roles_b:
                        continue
                    cond1 = role_a in roles_a and role_b in roles_b
                    cond2 = role_b in roles_a and role_a in roles_b
                    if cond1 or cond2:
                        pairs.append(f"{a['name']} + {b['name']}")
                names = pairs
            else:
                names = [f"{a['name']} + {b['name']}" for a,b in itertools.combinations(entries,2)]

        # Segmente, die deaktiviert wurden, ausfiltern
        if not include_disabled and getattr(self, "_disabled_indices", None):
            names = [n for i, n in enumerate(names) if i not in self._disabled_indices]
        return names

    def _on_segment_toggled(self, idx: int, disabled: bool, label: str):
        if disabled:
            self._disabled_indices.add(idx)
        else:
            self._disabled_indices.discard(idx)
        self._refresh_disabled_indices()
        self.stateChanged.emit()

    def _enabled_labels(self) -> set[str]:
        if not getattr(self, "_disabled_indices", None):
            return set(self.wheel.names if hasattr(self.wheel, "names") else [])
        return {n for i, n in enumerate(getattr(self.wheel, "names", [])) if i not in self._disabled_indices}

    def _refresh_disabled_indices(self):
        names = list(getattr(self.wheel, "names", []))
        if not names:
            self._disabled_indices = set()
            self._disabled_labels = set()
            return
        # Nur valide Indizes behalten
        self._disabled_indices = {i for i in self._disabled_indices if 0 <= i < len(names)}
        self._disabled_labels = {names[i] for i in self._disabled_indices}
        self.wheel.set_disabled_indices(self._disabled_indices)

    def _on_names_changed(self):
        # Kompatibilitäts-Methode, falls sie anderswo noch aufgerufen wird
        self._on_names_list_changed()

    def _on_toggle_pair_mode(self, _state: int):
        self.pair_mode = bool(self.toggle.isChecked())
        if not self.pair_mode and self.chk_subroles:
            self.chk_subroles.setChecked(False)
        # Wechsel des Modus → Disabled-Segmente zurücksetzen
        self._disabled_indices.clear()
        self._disabled_labels.clear()
        self._update_subrole_toggle_state()
        self._apply_placeholder()
        self._on_names_changed()
        self.stateChanged.emit()
    def _on_toggle_show_names(self, _state: int):
        show = bool(self.chk_show_names.isChecked())
        self.wheel.set_show_labels(show)
        self.stateChanged.emit()
    def _on_toggle_subroles(self, _state: int):
        self.use_subrole_filter = bool(self.pair_mode and self.chk_subroles and self.chk_subroles.isChecked())
        # Subrollenwechsel → Disabled-Segmente zurücksetzen
        self._disabled_indices.clear()
        self._disabled_labels.clear()
        self._apply_placeholder()
        self._on_names_changed()
        self.stateChanged.emit()
    def set_interactive_enabled(self, en: bool):
        # Statt self.edit:
        self.names.setEnabled(en)
        # Optional, wenn du während des globalen Spins auch das Rad selbst sperren willst:
        # self.view.setEnabled(en)

        if en:
            # Wenn allgemein aktiv → Feinsteuerung über _update_name_dependent_ui
            self._update_name_dependent_ui()
        else:
            # Alles aus, wenn global deaktiviert
            self.btn_local_spin.setEnabled(False)
            if self.toggle:
                self.toggle.setEnabled(False)
            if hasattr(self, "btn_include_in_all"):
                self.btn_include_in_all.setEnabled(False)
    def _on_include_in_all_toggled(self, checked: bool):
        prefix = "☑" if checked else "☐"
        self.btn_include_in_all.setText(f"{prefix} Bei »Drehen«")
        self.stateChanged.emit()

    def is_selected_for_global_spin(self) -> bool:
        """Ob dieses Rad beim globalen Spin ('Drehen') mitgedreht werden soll."""
        return getattr(self, "btn_include_in_all", None) is None or self.btn_include_in_all.isChecked()
    def is_anim_running(self) -> bool:
        return hasattr(self, "anim") and self.anim.state() == QtCore.QAbstractAnimation.Running
    def hard_stop(self):
        if hasattr(self, "anim"):
            try:
                if self.is_anim_running(): self.anim.stop()
            finally:
                self.anim.deleteLater(); delattr(self, "anim")
        self._is_spinning = False
    def spin(self, duration_ms: int = 2500):
        if self._is_spinning and self.is_anim_running():
            return None
        
        # Sobald ein neues Spin startet, alte Auswahl löschen
        self.result.setText("–")
        self._update_clear_button_enabled()

        base_entries = self._active_entries()
        names = self._effective_names_from(base_entries, include_disabled=True)
        enabled_indices = [i for i in range(len(names)) if i not in self._disabled_indices]
        if (self.pair_mode and len(base_entries) < 2) or not enabled_indices:
            self.result.setText("(zu wenige Namen)")
            return None
        duration_ms = max(1, int(duration_ms))

        # Index wählen (kannst du auch vorgeben/seeded machen)
        idx = random.choice(enabled_indices)
        target_name = names[idx]

        # Mitte des Zielsegments in Grad (0° = rechts, mathematischer Winkel)
        step = 360.0 / len(names)
        slice_center = (idx + 0.5) * step

        # Sauber neu starten
        self.hard_stop()
        current = float(self.wheel.rotation()) % 360.0
        self.wheel.setRotation(current)

        # → Korrigierter Plan: Rot_end ≡ slice_center - 90°
        plan = plan_spin(current_deg=current,
                         slice_center_deg=slice_center,
                         duration_ms=duration_ms)

        # Animation mit starker Ease-Out (schneller Start, langsames Ausrollen)
        self.anim = QtCore.QPropertyAnimation(self.wheel, b"rotation", self)
        self.anim.setDuration(plan.duration_ms)
        self.anim.setStartValue(plan.start_deg)
        self.anim.setEndValue(plan.end_deg)
        self.anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)

        self._pending_result = target_name
        self._is_spinning = True
        self.anim.finished.connect(self._emit_result)
        self.anim.start()
        return target_name
    def spin_to_name(self, target_name: str, duration_ms: int = 2500):
        """Spinnt das Rad gezielt auf einen bestimmten Namen.

        Falls der Name im aktuellen Rad nicht vorkommt, fällt die Methode auf
        das normale Zufalls-Spin zurück.
        """
        if self._is_spinning and self.is_anim_running():
            return None

        # Sobald ein neues Spin startet, alte Auswahl löschen
        self.result.setText("–")
        self._update_clear_button_enabled()

        base_entries = self._active_entries()
        names = self._effective_names_from(base_entries, include_disabled=True)
        enabled_indices = [i for i in range(len(names)) if i not in self._disabled_indices]
        if (self.pair_mode and len(base_entries) < 2) or not enabled_indices:
            self.result.setText("(zu wenige Namen)")
            return None
        duration_ms = max(1, int(duration_ms))

        try:
            idx = names.index(target_name)
            if idx not in enabled_indices:
                raise ValueError("disabled target")
        except ValueError:
            # Zielname existiert nicht auf diesem Rad → normales Zufalls-Spin
            return self.spin(duration_ms=duration_ms)

        # Mitte des Zielsegments in Grad (0° = rechts, mathematischer Winkel)
        step = 360.0 / len(names)
        slice_center = (idx + 0.5) * step

        # Sauber neu starten
        self.hard_stop()
        current = float(self.wheel.rotation()) % 360.0
        self.wheel.setRotation(current)

        plan = plan_spin(
            current_deg=current,
            slice_center_deg=slice_center,
            duration_ms=duration_ms,
        )

        # Animation mit starker Ease-Out (schneller Start, langsames Ausrollen)
        self.anim = QtCore.QPropertyAnimation(self.wheel, b"rotation", self)
        self.anim.setDuration(plan.duration_ms)
        self.anim.setStartValue(plan.start_deg)
        self.anim.setEndValue(plan.end_deg)
        self.anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)

        self._pending_result = target_name
        self._is_spinning = True
        self.anim.finished.connect(self._emit_result)
        self.anim.start()
        return target_name


    def _emit_result(self):
        if hasattr(self, "_pending_result"):
            self.result.setText(f"Ergebnis: {self._pending_result}")
            self.spun.emit(self._pending_result)
            delattr(self, "_pending_result")

        self._update_clear_button_enabled()

        if hasattr(self, "anim"):
            self.anim.deleteLater()
            delattr(self, "anim")
        self._is_spinning = False
        
    
    def _update_name_dependent_ui(self):
        """
        Passt UI-Elemente je nach Anzahl der Basenamen an:
        - 0 Namen  → Spin-Button aus, Include-in-all aus, Pair-Toggle aus
        - 1 Name   → Spin-Button an, Pair-Toggle aus, ggf. Include-in-all an (von 0 kommend)
        - >= 2     → Spin-Button an, Pair-Toggle an
        """
        base = self._base_names()
        count = len(base)
        prev = getattr(self, "_last_name_count", count)
        self._last_name_count = count

        # --- Single-Rad drehen ---
        # Wenn kein Name da ist, deaktivieren
        self.btn_local_spin.setEnabled(count > 0)

        # --- Paare-Toggle ---
        if getattr(self, "allow_pair_toggle", False) and getattr(self, "toggle", None) is not None:
            if count < 2:
                # Wenn nur noch ein Name steht und Paare aktiviert ist, deaktiviere dann.
                if self.toggle.isChecked():
                    self.toggle.setChecked(False)
                self.toggle.setEnabled(False)
                self.pair_mode = False
                self._apply_placeholder()
            else:
                # Ab 2 Namen wieder aktivierbar
                self.toggle.setEnabled(True)

        # --- "Bei Drehen"-Toggle ---
        if hasattr(self, "btn_include_in_all"):
            if count == 0:
                # Wenn kein Name da ist, dann deaktiviere den Toggle.
                self.btn_include_in_all.setEnabled(False)
                # Leeres Rad soll bei "Drehen" NICHT teilnehmen
                if self.btn_include_in_all.isChecked():
                    self.btn_include_in_all.setChecked(False)
            else:
                # Mindestens ein Name → Toggle aktivierbar
                self.btn_include_in_all.setEnabled(True)
                # Wenn nachdem kein Name da war, jetzt ein Name ist,
                # dann aktiviere den Toggle für "Drehen" wieder.
                if prev == 0 and not self.btn_include_in_all.isChecked():
                    self.btn_include_in_all.setChecked(True)
        # --- Subrollen-Toggle ---
        self._update_subrole_toggle_state()

    def _update_subrole_toggle_state(self):
        if not getattr(self, "chk_subroles", None):
            return
        can_use = self.pair_mode and len(self._base_names()) >= 2
        self.chk_subroles.setEnabled(can_use)
        if not can_use and self.chk_subroles.isChecked():
            # deaktivieren, wenn Paare-Modus aus ist oder zu wenige Namen vorhanden sind
            self.chk_subroles.setChecked(False)
        self.use_subrole_filter = bool(can_use and self.chk_subroles.isChecked())
        self._apply_placeholder()
    def _update_clear_button_enabled(self):
        """
        Blendet das Löschen-Symbol nur ein, wenn ein echtes Ergebnis da ist.
        """
        txt = self.result.text().strip()
        has_result = bool(txt) and txt != "–" and not txt.startswith("(zu wenige Namen)")
        self.btn_clear_result.setVisible(has_result)
    def _clear_result(self):
        self.result.setText("–")
        self._update_clear_button_enabled()
    def _normalize_entries(self, defaults: Union[List[str], List[dict]]) -> List[dict]:
        """
        Macht aus verschiedenen Input-Formaten eine einheitliche Liste von
        {"name": str, "subroles": [str]}.
        """
        entries: List[dict] = []
        for item in defaults or []:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    entries.append({"name": name, "subroles": []})
            elif isinstance(item, dict) and "name" in item:
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                subs = item.get("subroles", [])
                if isinstance(subs, (list, set, tuple)):
                    subs_list = [str(s) for s in subs if str(s).strip()]
                else:
                    subs_list = []
                entries.append({"name": name, "subroles": subs_list})
        return entries

    # --- Added resize behaviour ---

    def _update_wheel_radius(self):
        """Berechnet einen sinnvollen Radius basierend auf der View-Größe
        und rendert das Rad in dieser Auflösung neu (inkl. Pfeil)."""
        if not hasattr(self, "wheel") or not hasattr(self, "scene"):
            return
        vp = self.view.viewport().size()
        vw, vh = vp.width(), vp.height()
        if vw <= 0 or vh <= 0:
            return
        # Wir wollen, dass Rad + Pfeil vollständig in die View passen:
        # Gesamt-Höhe ≈ 2*r + 80 (Rad + Pfeil + etwas Rand)
        pad = 20
        extra = 80
        avail = max(0, min(vw, vh) - pad)
        if avail <= extra:
            return
        new_r = max(40, int((avail - extra) / 2))
        if new_r <= 0:
            return
        if new_r != self.wheel.radius:
            self.wheel.set_radius(new_r)
            r = self.wheel.radius
            # Szene-Rechteck so wählen, dass der Mittelpunkt bei (0,0) liegt
            # und oben der Pfeil (r+60) noch drin ist.
            self.scene.setSceneRect(-r - 40, -r - 60, 2 * r + 80, 2 * r + 80)
            # Pfeil neu erzeugen, damit er immer korrekt relativ zum Radius sitzt
            if hasattr(self, "pointer") and self.pointer is not None:
                self.scene.removeItem(self.pointer)
            self.pointer = self._make_pointer()
            self.scene.addItem(self.pointer)

    def _refit_view(self):
        self._update_wheel_radius()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refit_view()
