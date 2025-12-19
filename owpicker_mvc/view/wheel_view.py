from typing import List, Optional, Union
import random, itertools, difflib
from PySide6 import QtCore, QtGui, QtWidgets
from logic.spin_engine import plan_spin
from view.wheel_widget import WheelWidget
from view.name_list import NamesList, NameRowWidget
import config
import i18n

class WheelView(QtWidgets.QWidget):
    spun = QtCore.Signal(str)
    request_spin = QtCore.Signal()
    stateChanged = QtCore.Signal()
    def __init__(self, title: str, defaults: List[str], pair_mode=False, allow_pair_toggle=False, subrole_labels: Optional[List[str]] = None, title_key: Optional[str] = None):
        super().__init__()
        self.pair_mode = pair_mode; self.allow_pair_toggle = allow_pair_toggle; self._is_spinning = False
        self.subrole_labels = subrole_labels or []
        self.use_subrole_filter = False
        self._suppress_wheel_render = False
        self._suppress_state_signal = False
        self._force_spin_enabled = False
        self._override_entries: Optional[List[dict]] = None
        self._subrole_controls_visible = True
        self._header_controls_visible = True
        self._show_names_visible = True
        self._title_key = title_key
        self._title_fallback = title
        self.view = WheelWidget(self._effective_names_from(defaults))
        self.view.segmentToggled.connect(self._on_segment_toggled)
        self.wheel = self.view.wheel
        r = self.wheel.radius
        self._disabled_indices: set[int] = set()
        self._disabled_labels: set[str] = set()
        self._last_wheel_names: List[str] = list(self.wheel.names)
        self._result_state: str = "empty"  # empty | value | too_few
        self._result_value: Optional[str] = None

        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.label = QtWidgets.QLabel()
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        # Deutlicher sichtbarer Titel über jedem Rad
        self.label.setStyleSheet(
            "font-size:18px; font-weight:800; letter-spacing:0.3px;"
        )
        self._apply_title()

        header.addStretch(1)
        header.addWidget(self.label)
        header.addStretch(1)

        self.toggle = None
        if allow_pair_toggle:
            self.toggle = QtWidgets.QCheckBox(i18n.t("wheel.pairs_toggle"))
            self.toggle.setChecked(self.pair_mode)
            self.toggle.stateChanged.connect(self._on_toggle_pair_mode)
            header.setSpacing(12)
            header.addWidget(self.toggle, 0, QtCore.Qt.AlignVCenter)
        self.chk_subroles = None
        if self.subrole_labels and allow_pair_toggle:
            self.chk_subroles = QtWidgets.QCheckBox(i18n.t("wheel.subroles_toggle"))
            self.chk_subroles.setChecked(False)
            hint = i18n.t("wheel.subroles_hint_generic")
            if len(self.subrole_labels) >= 2:
                hint = i18n.t(
                    "wheel.subroles_hint_labels",
                    a=self.subrole_labels[0],
                    b=self.subrole_labels[1],
                )
            self.chk_subroles.setToolTip(hint)
            self.chk_subroles.setEnabled(self.pair_mode)
            self.chk_subroles.stateChanged.connect(self._on_toggle_subroles)
            header.addWidget(self.chk_subroles, 0, QtCore.Qt.AlignVCenter)

        # Optional: Checkbox "Namen anzeigen" im Header
        self.chk_show_names = QtWidgets.QCheckBox(i18n.t("wheel.show_names"))
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
        self.btn_clear_result.setToolTip(i18n.t("wheel.clear_result_tooltip"))
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
        self.names_hint = QtWidgets.QLabel("")
        self.names_hint.setStyleSheet("color:#444; font-size:12px; padding:2px;")
        self.btn_sort_names = QtWidgets.QPushButton(i18n.t("wheel.sort_names"))
        self.btn_sort_names.setFixedHeight(28)
        self.btn_sort_names.setToolTip(i18n.t("wheel.sort_names_tooltip"))
        self.btn_sort_names.clicked.connect(self._on_sort_names_clicked)
        self.names = NamesList(subrole_labels=self.subrole_labels)

        # Start-Namen anlegen – neue Namen sind standardmäßig aktiv (Checked)
        for entry in self._normalize_entries(defaults):
            self.names.add_name(
                entry["name"],
                subroles=entry.get("subroles", []),
                active=entry.get("active", True),
            )
        
        # Falls gar keine Defaults/Saved Names vorhanden sind, eine leere Zeile hinzufügen
        if self.names.count() == 0:
            self.names.add_name("")

        # Änderungen an Text oder Häkchen überwachen
        self.names.itemChanged.connect(self._on_names_list_changed)
        self.names.model().rowsInserted.connect(self._on_names_list_changed)
        self.names.model().rowsRemoved.connect(self._on_names_list_changed)
        self.names.metaChanged.connect(self._on_names_list_changed)
        # Neue Zeilen sollen sofort die korrekte Sichtbarkeit der Subrollen übernehmen
        self.names.model().rowsInserted.connect(lambda *_: self._apply_subrole_visibility())
# ---------- Buttons unter dem Rad ----------
        self._default_spin_label = i18n.t("wheel.spin_role")
        self.btn_local_spin = QtWidgets.QPushButton(self._default_spin_label)
        self.btn_local_spin.setFixedHeight(36)
        self.btn_local_spin.clicked.connect(self.request_spin.emit)
        self._custom_spin_label: Optional[str] = None

        # Toggle-Button statt Checkbox, optisch wie ein weiterer Button
        self.btn_include_in_all = QtWidgets.QPushButton()
        self.btn_include_in_all.setCheckable(True)
        self.btn_include_in_all.setChecked(True)
        self.btn_include_in_all.setFixedHeight(36)
        self.btn_include_in_all.setToolTip(i18n.t("wheel.include_tooltip"))

        # Initialen Text mit Symbol setzen
        self._on_include_in_all_toggled(self.btn_include_in_all.isChecked())
        # Bei jedem Umschalten Text aktualisieren
        self.btn_include_in_all.toggled.connect(self._on_include_in_all_toggled)
        # Fixe Breite, damit Sprache das Layout nicht verschiebt
        self._apply_fixed_min_widths()


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
        inner.addWidget(self.btn_sort_names, 0, QtCore.Qt.AlignRight)
        
        # Checkbox-Styling konsistent halten
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

        # Startwert für Namensanzahl merken und UI initial justieren
        self._last_name_count = len(self._base_names())
        self._update_name_dependent_ui()
        self._apply_placeholder()
        self._apply_result_state()

        outer = QtWidgets.QVBoxLayout(self)
        outer.addWidget(card)
        QtCore.QTimer.singleShot(0, self._refit_view)
    def _apply_title(self):
        text = self._title_fallback
        if self._title_key:
            text = i18n.t(self._title_key)
        self.label.setText(text)

    def set_language(self, lang: str):
        """Reapply translated labels for the current wheel."""
        i18n.set_language(lang)
        self._default_spin_label = i18n.t("wheel.spin_role")
        self._apply_title()
        if self.toggle:
            self.toggle.setText(i18n.t("wheel.pairs_toggle"))
        if self.chk_subroles:
            self.chk_subroles.setText(i18n.t("wheel.subroles_toggle"))
            hint = i18n.t("wheel.subroles_hint_generic")
            if len(self.subrole_labels) >= 2:
                hint = i18n.t(
                    "wheel.subroles_hint_labels",
                    a=self.subrole_labels[0],
                    b=self.subrole_labels[1],
                )
            self.chk_subroles.setToolTip(hint)
        if self.chk_show_names:
            self.chk_show_names.setText(i18n.t("wheel.show_names"))
        self.btn_clear_result.setToolTip(i18n.t("wheel.clear_result_tooltip"))
        self.btn_sort_names.setText(i18n.t("wheel.sort_names"))
        self.btn_sort_names.setToolTip(i18n.t("wheel.sort_names_tooltip"))
        self.btn_include_in_all.setToolTip(i18n.t("wheel.include_tooltip"))
        self._on_include_in_all_toggled(self.btn_include_in_all.isChecked())
        if self._custom_spin_label is None:
            self.set_spin_button_text(None)
        self._apply_placeholder()
        self._apply_result_state()
        self._apply_fixed_min_widths()

    def _refit_view(self):
        """Reicht Größenanpassung an das WheelWidget weiter."""
        if hasattr(self, "view") and hasattr(self.view, "_refit_view"):
            self.view._refit_view()

    def _apply_result_state(self):
        """Render the current result state with translated labels."""
        if self._result_state == "value" and self._result_value is not None:
            self.result.setText(i18n.t("wheel.result_prefix", result=self._result_value))
        elif self._result_state == "too_few":
            self.result.setText(i18n.t("wheel.result_too_few"))
        else:
            self.result.setText("–")
        self._update_clear_button_enabled()

    def _apply_fixed_min_widths(self):
        """Set fixed widths based on max translation to avoid layout jumps."""
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

        set_min(self.btn_local_spin, ["wheel.spin_role", "wheel.spin_map", "wheel.spin_single_map"], padding=44)
        set_min(self.btn_include_in_all, ["wheel.include_prefix"], padding=42, prefixes=["☑ ", "☐ "])
        set_min(self.btn_sort_names, ["wheel.sort_names"], padding=44)
        if self.toggle:
            set_min(self.toggle, ["wheel.pairs_toggle"], padding=30)
        if self.chk_subroles:
            set_min(self.chk_subroles, ["wheel.subroles_toggle"], padding=30)
        if self.chk_show_names:
            set_min(self.chk_show_names, ["wheel.show_names"], padding=30)

    def set_result_value(self, value: str):
        self._result_state = "value"
        self._result_value = value
        self._apply_result_state()

    def set_result_too_few(self):
        self._result_state = "too_few"
        self._result_value = None
        self._apply_result_state()

    def clear_result(self):
        self._result_state = "empty"
        self._result_value = None
        self._apply_result_state()

    def get_result_value(self) -> Optional[str]:
        return self._result_value if self._result_state == "value" else None

    def get_result_payload(self) -> dict:
        return {"state": self._result_state, "value": self._result_value}

    def apply_result_payload(self, payload: Optional[dict]):
        if not payload:
            self.clear_result()
            return
        state = payload.get("state")
        value = payload.get("value")
        if state == "value" and isinstance(value, str):
            self.set_result_value(value)
        elif state == "too_few":
            self.set_result_too_few()
        else:
            self.clear_result()
        
    def _on_sort_names_clicked(self):
        """Sortiert die Namensliste alphabetisch und aktualisiert das Rad."""
        self.names.sort_alphabetically()
        self._on_names_list_changed()

    def _apply_placeholder(self):
        tooltip_key = "wheel.tooltip_pairs" if self.pair_mode else "wheel.tooltip_single"
        self.result.setToolTip(i18n.t(tooltip_key))

        if self.pair_mode:
            if self.use_subrole_filter and len(self.subrole_labels) >= 2:
                self.names_hint.setText(
                    i18n.t(
                        "wheel.names_hint_pairs_subroles",
                        a=self.subrole_labels[0],
                        b=self.subrole_labels[1],
                    )
                )
            else:
                self.names_hint.setText(i18n.t("wheel.names_hint_pairs"))
        else:
            self.names_hint.setText(i18n.t("wheel.names_hint_single"))

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
    def set_override_entries(self, entries: Optional[List[dict]]):
        """
        Externe Einträge für das Rad setzen (z.B. im Hero-Ban).
        Die sichtbare Namensliste bleibt unverändert.
        """
        self._override_entries = list(entries) if entries is not None else None
        self._apply_override()
    def get_effective_wheel_names(self, include_disabled: bool = True) -> List[str]:
        """
        Liefert die aktuell vom Rad genutzten Namen (Override falls gesetzt).
        """
        base_entries = self._override_entries if self._override_entries is not None else self._active_entries()
        names = self._effective_names_from(base_entries, include_disabled=True)
        if not include_disabled and getattr(self, "_disabled_indices", None):
            names = [n for i, n in enumerate(names) if i not in self._disabled_indices]
        return names
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

    def _entries_for_spin(self) -> List[dict]:
        """Nutzt Override-Einträge, falls gesetzt, sonst die aktiven Einträge."""
        if self._override_entries is not None:
            return list(self._override_entries)
        return self._active_entries()

    def _active_names(self) -> List[str]:
        return [entry["name"] for entry in self._active_entries()]

    def _on_names_list_changed(self, *args):
        """Wenn Namen geändert, hinzugefügt oder entfernt werden."""
        if self._override_entries is not None:
            # Override bestimmt das Rad – sichtbare Liste nur Anzeige
            self._apply_override()
            if not self._suppress_state_signal:
                self.stateChanged.emit()
            return
        old_names = list(getattr(self, "_last_wheel_names", []))
        new_names = self._effective_names_from(self._active_entries(), include_disabled=True)
        # Rad mit aktiven Namen aktualisieren
        if getattr(self, "_suppress_wheel_render", False):
            self.wheel.set_names([])
            self._rebuild_disabled_indices([], [])
        else:
            self.wheel.set_names(new_names)
            self._rebuild_disabled_indices(old_names, new_names)
        self._refresh_disabled_indices()
        self._update_name_dependent_ui()
        self._last_wheel_names = list(new_names)
        self._apply_subrole_visibility()
        if not self._suppress_state_signal:
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
    def _apply_subrole_visibility(self):
        """Blendet Subrollen-Checkboxen in den Zeilen ein/aus."""
        for i in range(self.names.count()):
            widget = self.names.itemWidget(self.names.item(i))
            if isinstance(widget, NameRowWidget):
                for cb in widget.subrole_checks:
                    cb.setVisible(self._subrole_controls_visible)
    def _apply_override(self):
        """Wendet die Override-Liste auf das Rad an, ohne die sichtbare Liste zu ändern."""
        if self._override_entries is None:
            # Zurück zum normalen Rendering basierend auf der Liste
            self._on_names_list_changed()
            return
        names = self._effective_names_from(self._override_entries, include_disabled=True)
        # Bei neuem Override: deaktivierte Segmente zurücksetzen, damit Indizes passen
        self._disabled_indices.clear()
        self._disabled_labels.clear()
        self.wheel.set_names(names)
        self._refresh_disabled_indices()
        self._last_wheel_names = list(names)

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

    def _rebuild_disabled_indices(self, old_names: List[str], new_names: List[str]):
        """
        Überträgt deaktivierte Segmente auf die neue Namensliste, wenn Einträge
        entfernt oder hinzugefügt wurden. Deaktivierte Einträge, die nicht mehr
        existieren, fallen dabei weg.
        """
        if not getattr(self, "_disabled_indices", None):
            self._disabled_indices = set()
            self._disabled_labels = set()
            return

        sm = difflib.SequenceMatcher(a=old_names, b=new_names)
        mapped: set[int] = set()
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for offset in range(i2 - i1):
                    if (i1 + offset) in self._disabled_indices:
                        mapped.add(j1 + offset)
        self._disabled_indices = mapped
        self._disabled_labels = {new_names[i] for i in self._disabled_indices}

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
        self.btn_include_in_all.setText(f"{prefix} {i18n.t('wheel.include_prefix')}")
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
        self.clear_result()

        base_entries = self._entries_for_spin()
        names = self._effective_names_from(base_entries, include_disabled=True)
        enabled_indices = [i for i in range(len(names)) if i not in self._disabled_indices]
        if (self.pair_mode and len(base_entries) < 2) or not enabled_indices:
            self.set_result_too_few()
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
        self.clear_result()

        base_entries = self._entries_for_spin()
        names = self._effective_names_from(base_entries, include_disabled=True)
        enabled_indices = [i for i in range(len(names)) if i not in self._disabled_indices]
        if (self.pair_mode and len(base_entries) < 2) or not enabled_indices:
            self.set_result_too_few()
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
            self.set_result_value(str(self._pending_result))
            self.spun.emit(self._pending_result)
            delattr(self, "_pending_result")

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
        if not self._force_spin_enabled:
            self.btn_local_spin.setEnabled(count > 0)
        else:
            self.btn_local_spin.setEnabled(True)

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
        self.btn_clear_result.setVisible(self._result_state == "value")
    def _clear_result(self):
        self.clear_result()
    def set_spin_button_text(self, text: Optional[str]):
        """Setzt den Text des lokalen Spin-Buttons (None → Default)."""
        if text:
            self._custom_spin_label = text
            self.btn_local_spin.setText(text)
        else:
            self._custom_spin_label = None
            self.btn_local_spin.setText(self._default_spin_label)
    def set_force_spin_enabled(self, enabled: bool):
        """Erzwingt, dass der lokale Spin-Button aktiv bleibt (Hero-Ban)."""
        self._force_spin_enabled = bool(enabled)
        self._update_name_dependent_ui()
    def set_show_names_visible(self, visible: bool):
        """Blendet die Checkbox 'Namen anzeigen' ein/aus."""
        self._show_names_visible = bool(visible)
        if self.chk_show_names:
            self.chk_show_names.setVisible(visible)
    def set_header_controls_visible(self, visible: bool):
        """Blendet Pair-/Subrollen-Toggles im Header ein/aus."""
        self._header_controls_visible = bool(visible)
        if self.toggle:
            self.toggle.setVisible(visible)
        if self.chk_subroles:
            self.chk_subroles.setVisible(visible)
    def set_subrole_controls_visible(self, visible: bool):
        """Blendet Subrollen-Kästchen in den Zeilen ein/aus."""
        self._subrole_controls_visible = bool(visible)
        self._apply_subrole_visibility()
    def set_wheel_render_enabled(self, enabled: bool):
        """
        Schaltet das Zeichnen des Rads an/aus (z.B. im Hero-Ban für äußere Räder).
        Listen/Buttons bleiben davon unberührt.
        """
        self._suppress_wheel_render = not enabled
        prev = self._suppress_state_signal
        self._suppress_state_signal = True
        try:
            self._on_names_list_changed()
        finally:
            self._suppress_state_signal = prev
    def _normalize_entries(self, defaults: Union[List[str], List[dict]]) -> List[dict]:
        """
        Macht aus verschiedenen Input-Formaten eine einheitliche Liste von
        {"name": str, "subroles": [str], "active": bool}.
        """
        entries: List[dict] = []
        for item in defaults or []:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    entries.append({"name": name, "subroles": [], "active": True})
            elif isinstance(item, dict) and "name" in item:
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                subs = item.get("subroles", [])
                if isinstance(subs, (list, set, tuple)):
                    subs_list = [str(s) for s in subs if str(s).strip()]
                else:
                    subs_list = []
                active = bool(item.get("active", True))
                entries.append({"name": name, "subroles": subs_list, "active": active})
        return entries
    def load_entries(self, entries: Union[List[str], List[dict]],
                     pair_mode: Optional[bool] = None,
                     include_in_all: Optional[bool] = None,
                     use_subroles: Optional[bool] = None):
        """
        Ersetzt die gesamte Namensliste durch neue Einträge (z.B. beim Moduswechsel).
        Optionale Flags setzen Pair-/Subrollen- und Include-Status mit.
        """
        normalized = self._normalize_entries(entries)
        # Liste ohne Signale neu aufbauen
        blockers = [
            QtCore.QSignalBlocker(self.names),
            QtCore.QSignalBlocker(self.names.model()),
        ]
        try:
            self.names.clear()
            for entry in normalized:
                self.names.add_name(
                    entry.get("name", ""),
                    subroles=entry.get("subroles", []),
                    active=entry.get("active", True),
                )
            if not normalized:
                self.names.add_name("")
        finally:
            del blockers

        # Disabled-Segmente und Hilfswerte zurücksetzen
        self._disabled_indices.clear()
        self._disabled_labels.clear()
        self._last_wheel_names = []

        # Pair-/Subrollen-Status setzen (Signale blocken, UI updaten)
        if pair_mode is not None and not getattr(self, "allow_pair_toggle", False):
            pair_mode = False
        if pair_mode is not None:
            self.pair_mode = bool(pair_mode)
            if getattr(self, "toggle", None):
                blocker = QtCore.QSignalBlocker(self.toggle)
                self.toggle.setChecked(self.pair_mode)
                del blocker
            if not self.pair_mode and getattr(self, "chk_subroles", None):
                blocker = QtCore.QSignalBlocker(self.chk_subroles)
                self.chk_subroles.setChecked(False)
                del blocker
        if use_subroles is not None and getattr(self, "chk_subroles", None):
            blocker = QtCore.QSignalBlocker(self.chk_subroles)
            self.chk_subroles.setChecked(bool(use_subroles))
            del blocker
            self.use_subrole_filter = bool(self.chk_subroles.isChecked())
        self._update_subrole_toggle_state()

        if include_in_all is not None and hasattr(self, "btn_include_in_all"):
            blocker = QtCore.QSignalBlocker(self.btn_include_in_all)
            self.btn_include_in_all.setChecked(bool(include_in_all))
            del blocker
            self._on_include_in_all_toggled(self.btn_include_in_all.isChecked())

        self._apply_placeholder()
        self._on_names_list_changed()
        # Sichtbarkeit der Subrollen-Kästchen nach einem vollständigen Neuaufbau anwenden
        self._apply_subrole_visibility()

    # --- Added resize behaviour ---

    # wheel resizing handled by WheelWidget
