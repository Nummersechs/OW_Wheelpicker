# (full, commented version was generated above — see next cell content if needed)
from pathlib import Path
import random
import json
import os
import sys
from PySide6 import QtCore, QtGui, QtWidgets
from view.wheel_view import WheelView
from view.overlay import ResultOverlay
from services.sound import SoundManager
import config
import requests

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Overwatch 2 – Triple Wheel Picker")
        self.resize(1200, 650)
        self.sound = SoundManager(base_dir=Path(__file__).resolve().parent)

        # NEU: State-Datei & geladenen Zustand vorbereiten
        self._state_file = self._get_state_file()
        saved = self._load_saved_state()
        self._restoring_state = True   # während des Aufbaus nicht speichern

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        self._apply_theme()
        root = QtWidgets.QVBoxLayout(central)

        title = QtWidgets.QLabel("Overwatch 2 – Spieler-Auswahl")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font-size:22px; font-weight:700; margin:8px 0 2px 0;")

        # Lautstärke-Regler oben rechts
        vol_row = QtWidgets.QHBoxLayout()
        vol_row.setContentsMargins(4, 10, 20, 6)  # extra Right-Margin für Volume-Block
        vol_row.addStretch(1)
        spacer_for_balance = QtWidgets.QSpacerItem(160, 0, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)
        vol_row.addItem(spacer_for_balance)
        vol_row.addWidget(title, 0, QtCore.Qt.AlignCenter)
        vol_row.addStretch(1)
        self.lbl_volume_icon = QtWidgets.QToolButton()
        self.lbl_volume_icon.setText("🔊")
        self.lbl_volume_icon.setCursor(QtCore.Qt.PointingHandCursor)
        self.lbl_volume_icon.setToolTip("Lautstärke für Soundeffekte")
        self.lbl_volume_icon.setStyleSheet("font-size:18px; padding:0 4px; background:transparent; border:none;")
        self.lbl_volume_icon.clicked.connect(self._on_volume_icon_clicked)
        self.volume_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.setToolTip("Soundeffekte-Lautstärke")
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.sliderReleased.connect(self._play_volume_preview)
        self.volume_slider.sliderPressed.connect(self._play_volume_preview)
        vol_row.addWidget(self.lbl_volume_icon, 0, QtCore.Qt.AlignVCenter)
        vol_row.addWidget(self.volume_slider, 0, QtCore.Qt.AlignVCenter)
        vol_row.addStretch(0)
        root.addLayout(vol_row)
        saved_volume = saved.get("volume", 100)
        try:
            self.volume_slider.setValue(int(saved_volume))
        except Exception:
            pass
        self._on_volume_changed(self.volume_slider.value())
        self._last_volume_before_mute = self.volume_slider.value()

        grid = QtWidgets.QGridLayout()
        root.addLayout(grid, 1)

        # gespeicherte Daten pro Rolle (falls vorhanden)
        tank_state = saved.get("Tank", {})
        dps_state = saved.get("Damage", {})
        support_state = saved.get("Support", {})

        def defaults_for(state_key: dict, role_name: str):
            # Bevorzugt die neue Struktur mit Einträgen und Subrollen.
            if "entries" in state_key:
                return state_key["entries"]
            return state_key.get("names", config.DEFAULT_NAMES[role_name])

        self.tank = WheelView(
            "Tank",
            defaults_for(tank_state, "Tank"),
            pair_mode=tank_state.get("pair_mode", False),
            allow_pair_toggle=False,
        )
        self.dps = WheelView(
            "Damage",
            defaults_for(dps_state, "Damage"),
            pair_mode=dps_state.get("pair_mode", True),
            allow_pair_toggle=True,
            subrole_labels=["HS", "FDPS"],
        )
        self.support = WheelView(
            "Support",
            defaults_for(support_state, "Support"),
            pair_mode=support_state.get("pair_mode", True),
            allow_pair_toggle=True,
            subrole_labels=["MS", "FS"],
        )

        grid.addWidget(self.tank, 0, 0)
        grid.addWidget(self.dps, 0, 1)
        grid.addWidget(self.support, 0, 2)

        # Include-in-all Flags anwenden, bevor wir Save-Hooks anschließen
        if "include_in_all" in tank_state:
            self.tank.btn_include_in_all.setChecked(tank_state["include_in_all"])
        if "include_in_all" in dps_state:
            self.dps.btn_include_in_all.setChecked(dps_state["include_in_all"])
        if "include_in_all" in support_state:
            self.support.btn_include_in_all.setChecked(support_state["include_in_all"])
        if "use_subroles" in dps_state and getattr(self.dps, "chk_subroles", None):
            self.dps.chk_subroles.setChecked(bool(dps_state["use_subroles"]))
        if "use_subroles" in support_state and getattr(self.support, "chk_subroles", None):
            self.support.chk_subroles.setChecked(bool(support_state["use_subroles"]))

        # Spin-Signale
        self.tank.request_spin.connect(lambda: self._spin_single(self.tank, 1.00))
        self.dps.request_spin.connect(lambda: self._spin_single(self.dps, 1.10))
        self.support.request_spin.connect(lambda: self._spin_single(self.support, 1.20))

        # --- Controls unten wie gehabt ---
        controls = QtWidgets.QHBoxLayout()
        root.addLayout(controls)
        self.duration = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.duration.setRange(config.MIN_DURATION_MS, config.MAX_DURATION_MS)
        self.duration.setValue(config.DEFAULT_DURATION_MS)
        self.duration.setToolTip("Dauer der Animation (ms)")
        self.btn_spin_all = QtWidgets.QPushButton("🎰 Drehen")
        self.btn_spin_all.setFixedHeight(44)
        self.btn_spin_all.clicked.connect(self.spin_all)
        controls.addStretch(1)
        controls.addWidget(QtWidgets.QLabel("Animationsdauer:"))
        controls.addWidget(self.duration)
        controls.addWidget(self.btn_spin_all)
        self.btn_cancel_spin = QtWidgets.QPushButton("✖ Abbrechen")
        self.btn_cancel_spin.setFixedHeight(44)
        self.btn_cancel_spin.setEnabled(False)
        self.btn_cancel_spin.setStyleSheet("QPushButton { background:#c62828; color:white; } QPushButton:disabled { background:#c7c7c7; color:#777; }")
        self.btn_cancel_spin.clicked.connect(self._cancel_spin)
        controls.addWidget(self.btn_cancel_spin)
        controls.addStretch(1)

        self.summary = QtWidgets.QLabel("")
        self.summary.setAlignment(QtCore.Qt.AlignCenter)
        self.summary.setStyleSheet("font-size:15px; color:#333; margin:10px 0 6px 0;")
        root.addWidget(self.summary)

        self.pending = 0
        self._result_sent_this_spin = False
        self._last_results_snapshot: dict | None = None
        for w in (self.tank, self.dps, self.support):
            w.spun.connect(self._wheel_finished)

        self.overlay = ResultOverlay(parent=central)
        self.overlay.hide()
        self.overlay.closed.connect(lambda: (self._set_controls_enabled(True), self.sound.stop_ding()))
        
        self.online_mode = False  # Standard
        self.overlay.modeChosen.connect(self._on_mode_chosen)

        # Direkt beim Start Modus wählen lassen
        self._set_controls_enabled(False)
        self.overlay.show_online_choice()

        # JETZT: Save-Hooks anschließen
        for w in (self.tank, self.dps, self.support):
            w.stateChanged.connect(self._save_state)
            w.btn_include_in_all.toggled.connect(self._update_spin_all_enabled)

        # jetzt darf gespeichert werden
        self._restoring_state = False

        # Buttons initial updaten (nutzt schon include_in_all)
        self._update_spin_all_enabled()
        self._update_cancel_enabled()

    def _apply_theme(self):
        """
        Helles, gut lesbares Theme erzwingen – unabhängig vom System-Darkmode.
        """
        from PySide6 import QtWidgets, QtGui

        QtWidgets.QApplication.setStyle("Fusion")

        pal = QtGui.QPalette()

        # Hintergründe
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(245, 246, 248))   # App-Hintergrund
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor(255, 255, 255))     # Eingabefelder
        pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(240, 240, 240))
        pal.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(255, 255, 255))
        pal.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(32, 33, 36))

        # Texte (dunkel auf hell)
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor(32, 33, 36))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(32, 33, 36))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(32, 33, 36))

        # Buttons/Highlights
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor(255, 255, 255))
        pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(0, 120, 215))
        pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(255, 255, 255))

        QtWidgets.QApplication.setPalette(pal)

        # Einheitliche, gut lesbare Typo & Kontraste
        self.setStyleSheet("""
            QLabel { color:#202124; }
            QPlainTextEdit {
                background:#ffffff; color:#202124;
                border:1px solid #e6e6e6; border-radius:10px; padding:6px;
                font-size:13px;
            }
            QSlider::groove:horizontal {
                height:6px; background:#e0e0e0; border-radius:3px;
            }
            QSlider::handle:horizontal {
                width:14px; background:#0078d4; border-radius:7px; margin:-5px 0;
            }
            QGraphicsView {
                background:transparent;
            }
            QPushButton {
                color:#ffffff;
                background:#0b57d0;
                border-radius:12px;
                font-weight:600;
                padding:8px 18px;
            }
            QPushButton:hover { background:#0a4fc0; }
            QPushButton:pressed { background:#0946ab; }

            /* CHECKED: für deinen Bei-Alle-drehen-Button */
            QPushButton:checked {
                background:#188038;
                border:2px solid #0f5f26;
            }
            QPushButton:checked:hover {
                background:#176b34;
            }
            QPushButton:checked:pressed {
                background:#14592b;
            }

            /* DISABLED: sichtbar ausgegrauter Zustand (z.B. Alle 3 drehen) */
            QPushButton:disabled {
                background:#c7c7c7;
                color:#777777;
                border-radius:12px;
                border:1px solid #b0b0b0;
            }

            QCheckBox {
                color:#202124;
                font-size:13px;
            }

            QCheckBox::indicator {
                width: 8px;
                height: 8px;
                border: 2px solid black;      /* dicker schwarzer Rand */
                border-radius: 3px;           /* optional */
                background: white;            /* Hintergrund */
            }

            QCheckBox::indicator:checked {
                background: black;            /* Hakenfarbe */
            }
        """)

    def resizeEvent(self, e: QtGui.QResizeEvent):
        super().resizeEvent(e); 
        if self.overlay and self.centralWidget(): self.overlay.setGeometry(self.centralWidget().rect())
        
    def _update_spin_all_enabled(self):
        """Aktiviere/Deaktiviere den 'Drehen'-Button je nach Auswahl."""
        any_selected = any(
            w.is_selected_for_global_spin()
            for w in (self.tank, self.dps, self.support)
        )
        # Nur aktiv, wenn allgemein erlaubt UND mindestens ein Rad ausgewählt
        self.btn_spin_all.setEnabled(any_selected and self.pending == 0)
        self._update_cancel_enabled()

    def _set_controls_enabled(self, en: bool):
        if en:
            self._update_spin_all_enabled()
        else:
            self.btn_spin_all.setEnabled(False)
        for w in (self.tank, self.dps, self.support):
            w.set_interactive_enabled(en)
        if not en:
            self._update_cancel_enabled()

    def _stop_all_wheels(self):
        for w in (self.tank, self.dps, self.support): w.hard_stop()
    def _update_cancel_enabled(self):
        self.btn_cancel_spin.setEnabled(self.pending > 0)
    
    def spin_all(self):
        """Dreht alle selektierten Räder auf faire Weise.

        Ein „Kandidat“ kann ein einzelner Spielername sein (normaler Modus)
        oder ein Paar wie „Alice + Bob“ (Paare bilden).

        Regel: Kein Spieler darf in mehr als einem gewählten Kandidaten
        (also auch nicht in mehreren Paaren) vorkommen.
        """
        if self.pending > 0:
            return
        self._result_sent_this_spin = False

        # Aktive Rollen mit ihren Rädern einsammeln
        role_wheels = [
            ("Tank", self.tank),
            ("Damage", self.dps),
            ("Support", self.support),
        ]
        active = [
            (role, wheel)
            for role, wheel in role_wheels
            if wheel.is_selected_for_global_spin()
        ]
        if not active:
            return

        # Alte Ergebnisse aller aktiven Räder zurücksetzen,
        # damit nichts Altes „hängen bleibt“ und doppelt aussieht.
        self._snapshot_results()
        for _role, wheel in active:
            wheel.result.setText("–")
            if hasattr(wheel, "_update_clear_button_enabled"):
                wheel._update_clear_button_enabled()

        # --- Kandidaten pro Rolle bestimmen ---
        # Kandidat = (label_string, [spieler1, spieler2, ...])
        all_candidates_per_role = []
        for role, wheel in active:
            base_entries = wheel._active_entries()
            labels = wheel._effective_names_from(base_entries, include_disabled=False)
            labels = [lbl.strip() for lbl in labels if lbl and lbl.strip()]

            role_candidates = []
            for lbl in labels:
                # "Alice + Bob" -> ["Alice", "Bob"]
                parts = [p.strip() for p in lbl.split("+")]
                parts = [p for p in parts if p]  # leere raus
                if not parts:
                    continue
                role_candidates.append((lbl, parts))

            all_candidates_per_role.append(role_candidates)

        # Wenn überall gar keine Kandidaten existieren:
        if all(not cands for cands in all_candidates_per_role):
            self.summary.setText("Bitte Namen für die Rollen eintragen.")
            return

        # --- Vollständige, konfliktfreie Zuordnung per Backtracking suchen ---

        num_roles = len(active)
        role_indices = list(range(num_roles))
        random.shuffle(role_indices)

        assigned_for_role = [None] * num_roles  # speichert das Label pro Rolle

        def backtrack(pos: int, used_players: set) -> bool:
            if pos == num_roles:
                return True  # alle Rollen erfolgreich belegt

            idx = role_indices[pos]
            candidates = list(all_candidates_per_role[idx])
            random.shuffle(candidates)

            for label, players in candidates:
                # Kandidat nur verwenden, wenn keiner der Spieler schon benutzt wurde
                if any(p in used_players for p in players):
                    continue
                assigned_for_role[idx] = label
                new_used = set(used_players)
                new_used.update(players)
                if backtrack(pos + 1, new_used):
                    return True
                # Rückgängig machen
                assigned_for_role[idx] = None

            return False

        if not backtrack(0, set()):
            # Es existiert keine vollständige, konfliktfreie Belegung aller ausgewählten Rollen
            self.sound.stop_spin()
            self.sound.stop_ding()
            self._set_controls_enabled(True)
            self.pending = 0

            self.summary.setText("Team kann nicht gebildet werden.")
            # Kurz gehaltener Hinweis im Overlay
            self.overlay.show_message(
                "Team kann nicht gebildet werden",
                [
                    "Mindestens eine Rolle kann nicht konfliktfrei besetzt werden.",
                    "Bitte mehr unterschiedliche Namen eintragen oder Rollen deaktivieren.",
                    "",
                ],
            )
            return

        # --- Animationen starten (jetzt garantiert mit vollständiger Belegung) ---

        self.sound.stop_ding()
        self._stop_all_wheels()
        self.summary.setText("")
        self.pending = 0
        self._set_controls_enabled(False)
        self.overlay.hide()
        self.sound.play_spin()

        duration = self.duration.value()
        multipliers = [0.85, 1.00, 1.35]
        random.shuffle(multipliers)

        for (idx, (role, wheel)), mult in zip(enumerate(active), multipliers):
            target_label = assigned_for_role[idx]
            # Sollte durch Backtracking nie None sein:
            if target_label is None:
                continue

            # Wenn verfügbar, gezielt auf den Namen drehen
            if hasattr(wheel, "spin_to_name"):
                if wheel.spin_to_name(target_label, duration_ms=int(duration * mult)):
                    self.pending += 1
            else:
                # Fallback: normales Spin
                if wheel.spin(duration_ms=int(duration * mult)):
                    self.pending += 1

        if self.pending == 0:
            self.sound.stop_spin()
            self._set_controls_enabled(True)
            self.summary.setText("Bitte Namen für die Rollen eintragen.")
        self._update_cancel_enabled()
    def _spin_single(self, wheel: WheelView, mult: float = 1.0):
        if self.pending > 0: return
        self._result_sent_this_spin = False
        self._snapshot_results()
        self.sound.stop_ding(); self._stop_all_wheels(); self._set_controls_enabled(False)
        self.summary.setText(""); self.pending = 0; self.overlay.hide()
        self.sound.play_spin()
        duration = int(self.duration.value()*mult)
        if wheel.spin(duration_ms=duration): self.pending = 1
        else:
            self.sound.stop_spin(); self._set_controls_enabled(True)
            self.summary.setText("Bitte Namen für dieses Rad eintragen.")
        self._update_cancel_enabled()

    def _wheel_finished(self, _name: str):
        # Wenn laut State gar kein Spin aktiv ist, ignorieren wir alte/späte Signale,
        # z.B. von hard_stop() oder abgebrochenen Animationen.
        if self.pending <= 0:
            return

        self.pending -= 1

        # Nur wenn wir von >0 genau auf 0 fallen, ist "dieser" Spin abgeschlossen
        if self.pending == 0:
            if self._result_sent_this_spin:
                return
            self._result_sent_this_spin = True
            self.sound.stop_spin()
            self.sound.stop_ding()
            self.sound.play_ding()

            t = self.tank.result.text().replace("Ergebnis: ", "")
            d = self.dps.result.text().replace("Ergebnis: ", "")
            s = self.support.result.text().replace("Ergebnis: ", "")

            self.summary.setText(f"Auswahl → Tank: {t} | Damage: {d} | Support: {s}")
            self.overlay.show_result(t, d, s)

            # Nur noch EIN Request pro abgeschlossenem Spin
            self._send_spin_result_to_server(t, d, s)
            self._last_results_snapshot = None
        self._update_cancel_enabled()

    def _cancel_spin(self):
        if self.pending <= 0:
            return
        self._result_sent_this_spin = True  # unterdrückt finale Anzeige
        self.pending = 0
        self.sound.stop_spin()
        self.sound.stop_ding()
        self._stop_all_wheels()
        # Ergebnisse wiederherstellen, falls Snapshot vorhanden
        self._restore_results_snapshot()
        # Hinweis anzeigen, Ergebnisse/Summary beibehalten
        self.overlay.show_message("Spin abgebrochen", ["Aktueller Spin wurde gestoppt.", "Letzte Ergebnisse bleiben erhalten.", ""])
        self._set_controls_enabled(True)
        self._update_cancel_enabled()

    def _snapshot_results(self):
        """Merkt aktuelle Resultate & Summary, um sie bei Abbruch wiederherzustellen."""
        self._last_results_snapshot = {
            "summary": self.summary.text(),
            "tank": self.tank.result.text(),
            "dps": self.dps.result.text(),
            "support": self.support.result.text(),
        }

    def _restore_results_snapshot(self):
        snap = getattr(self, "_last_results_snapshot", None)
        if not snap:
            return
        self.summary.setText(snap.get("summary", ""))
        mapping = [("tank", self.tank), ("dps", self.dps), ("support", self.support)]
        for key, wheel in mapping:
            txt = snap.get(key, None)
            if txt is not None:
                wheel.result.setText(txt)
                if hasattr(wheel, "_update_clear_button_enabled"):
                    wheel._update_clear_button_enabled()
        self._last_results_snapshot = None

    def _get_state_file(self) -> Path:
        """
        Gibt den Pfad zur saved_state.json zurück.
        - Im normalen Python-Run: neben controller.py
        - In der PyInstaller-onefile-EXE: neben der .exe
        """
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            # PyInstaller-EXE: sys.executable ist die .exe
            base_dir = Path(sys.executable).resolve().parent
        else:
            # Normaler Script-Run
            base_dir = Path(__file__).resolve().parent

        return base_dir / "saved_state.json"
    def _on_volume_changed(self, value: int):
        factor = max(0.0, min(1.0, value / 100.0))
        self.sound.set_master_volume(factor)
        self._update_volume_icon(value)
        # Wenn per Slider verändert, aktuell nicht mehr stumm gespeichert
        self._last_volume_before_mute = value if value > 0 else self._last_volume_before_mute
        if not getattr(self, "_restoring_state", False):
            self._save_state()
    def _update_volume_icon(self, value: int):
        if value <= 0:
            icon = "🔇"
        elif value <= 30:
            icon = "🔈"
        elif value <= 70:
            icon = "🔉"
        else:
            icon = "🔊"
        self.lbl_volume_icon.setText(icon)
    def _play_volume_preview(self):
        if self.volume_slider.value() > 0:
            self.sound.play_preview()
    def _on_volume_icon_clicked(self):
        current = self.volume_slider.value()
        if current > 0:
            # mute und Wert merken
            self._last_volume_before_mute = current
            self.volume_slider.blockSignals(True)
            self.volume_slider.setValue(0)
            self.volume_slider.blockSignals(False)
            self._on_volume_changed(0)
        else:
            # unmute auf letzten Wert oder Default 100
            new_val = self._last_volume_before_mute if self._last_volume_before_mute > 0 else 100
            self.volume_slider.blockSignals(True)
            self.volume_slider.setValue(new_val)
            self.volume_slider.blockSignals(False)
            self._on_volume_changed(new_val)
    def _load_saved_state(self) -> dict:
        """
        Lädt den gespeicherten Zustand aus saved_state.json, falls vorhanden.
        Struktur:
        {
          "Tank":    {"names": [...], "include_in_all": bool, "pair_mode": bool},
          "Damage":  {...},
          "Support": {...}
        }
        """
        try:
            if self._state_file.exists():
                with self._state_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            config.debug_print("Konnte saved_state.json nicht laden:", e)
        return {}

    def _gather_state(self) -> dict:
        """
        Liest den aktuellen Zustand aller drei Wheels aus.
        """
        def wheel_state(w: WheelView) -> dict:
            return {
                "names": w.get_current_names(),
                "entries": w.get_current_entries(),
                "include_in_all": w.btn_include_in_all.isChecked(),
                "pair_mode": getattr(w, "pair_mode", False),
                "use_subroles": getattr(w, "use_subrole_filter", False),
            }

        return {
            "Tank": wheel_state(self.tank),
            "Damage": wheel_state(self.dps),
            "Support": wheel_state(self.support),
            "volume": self.volume_slider.value(),
        }

    def _save_state(self):
        """
        Speichert den aktuellen Zustand in saved_state.json neben dem Script/der EXE.
        """
        if getattr(self, "_restoring_state", False):
            return
        try:
            state = self._gather_state()
            with self._state_file.open("w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            config.debug_print("Konnte saved_state.json nicht speichern:", e)
        self._sync_all_roles_to_server()
    
    @QtCore.Slot(bool)
    def _on_mode_chosen(self, online: bool):
        self.online_mode = online
        self._set_controls_enabled(True)

        if self.online_mode:
            config.debug_print("Online-Modus aktiv.")
            self._sync_all_roles_to_server()
        else:
            config.debug_print("Offline-Modus aktiv.")
            
    def _send_spin_result_to_server(self, tank: str, damage: str, support: str):
        # Offline? → gar nicht erst versuchen zu senden
        if not getattr(self, "online_mode", False):
            config.debug_print("Spin-Result: Offline-Modus – kein Senden.")
            return
        
        import threading
        import requests

        # Kleine Hilfsfunktion: Label + pair_mode -> (name1, name2)
        def split_pair(label: str, is_pair_mode: bool):
            label = (label or "").strip()
            if not label:
                return "", ""

            if not is_pair_mode:
                # Kein Paarmodus → alles in *_1, *_2 bleibt leer
                return label, ""

            # Paarmodus: nach "+" aufsplitten
            parts = [p.strip() for p in label.split("+") if p.strip()]
            if not parts:
                return "", ""
            if len(parts) == 1:
                return parts[0], ""
            # Falls mehr als 2 drinstehen sollten, nehmen wir den ersten als *_1
            # und den Rest zusammen als *_2
            return parts[0], " + ".join(parts[1:])

        def _worker():
            try:
                tank1, tank2 = split_pair(tank,    getattr(self.tank,    "pair_mode", False))
                dps1, dps2   = split_pair(damage,  getattr(self.dps,     "pair_mode", False))
                sup1, sup2   = split_pair(support, getattr(self.support, "pair_mode", False))

                payload = {
                    "tank1": tank1,
                    "tank2": tank2,
                    "dps1": dps1,
                    "dps2": dps2,
                    "support1": sup1,
                    "support2": sup2,
                }

                base = config.API_BASE_URL
                url = base.rstrip("/") + "/spin-result"

                config.debug_print("Sende Payload:", payload)  # zum Debuggen

                resp = requests.post(url, json=payload, timeout=3)
                resp.raise_for_status()
                config.debug_print("Spin-Ergebnis erfolgreich an Server gesendet:", resp.json())
            except Exception as e:
                config.debug_print("Fehler beim Senden des Spin-Ergebnisses:", e)

        threading.Thread(target=_worker, daemon=True).start()
        
    def _sync_all_roles_to_server(self):
        if not getattr(self, "online_mode", False):
            config.debug_print("Sync übersprungen: Offline-Modus.")
            return
        """
        Schickt alle Rollenlisten in ihrer aktuellen Reihenfolge an den Server.
        """
        import threading
        import requests

        def _worker():
            try:
                payload = {
                    "roles": [
                        {
                            "role": "Tank",
                            "names": self.tank.get_current_names(),
                        },
                        {
                            "role": "Damage",
                            "names": self.dps.get_current_names(),
                        },
                        {
                            "role": "Support",
                            "names": self.support.get_current_names(),
                        },
                    ]
                }

                base = config.API_BASE_URL
                url = base.rstrip("/") + "/roles-sync"

                config.debug_print("SYNC →", payload)
                resp = requests.post(url, json=payload, timeout=3)
                resp.raise_for_status()
                config.debug_print("SYNC OK:", resp.json())

            except Exception as e:
                config.debug_print("Fehler beim Rollen-Sync:", e)

        threading.Thread(target=_worker, daemon=True).start()
