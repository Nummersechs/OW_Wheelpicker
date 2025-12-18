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
        self.current_mode = "players"  # immer mit Spieler-Auswahl starten
        self.last_non_hero_mode = "players"
        self.hero_ban_active = False
        self._hero_ban_rebuild = False
        self._hero_ban_pending = False
        self._hero_ban_override_role: str | None = None
        self._mode_states = self._build_mode_states(saved)

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        self._apply_theme()
        root = QtWidgets.QVBoxLayout(central)

        self.title = QtWidgets.QLabel("")
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        self.title.setStyleSheet("font-size:22px; font-weight:700; margin:8px 0 2px 0;")

        # Lautstärke-Regler oben rechts
        vol_row = QtWidgets.QHBoxLayout()
        vol_row.setContentsMargins(4, 10, 20, 6)  # extra Right-Margin für Volume-Block
        vol_row.addStretch(1)
        spacer_for_balance = QtWidgets.QSpacerItem(160, 0, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Minimum)
        vol_row.addItem(spacer_for_balance)
        vol_row.addWidget(self.title, 0, QtCore.Qt.AlignCenter)
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

        # Modus-Schalter (Spieler / Helden)
        self.btn_mode_players = QtWidgets.QPushButton("Spieler-Auswahl")
        self.btn_mode_players.setCheckable(True)
        self.btn_mode_heroes = QtWidgets.QPushButton("Helden-Auswahl")
        self.btn_mode_heroes.setCheckable(True)
        self.btn_mode_heroban = QtWidgets.QPushButton("Hero-Ban")
        self.btn_mode_heroban.setCheckable(True)
        self.btn_mode_players.clicked.connect(lambda: self._on_mode_button_clicked("players"))
        self.btn_mode_heroes.clicked.connect(lambda: self._on_mode_button_clicked("heroes"))
        self.btn_mode_heroban.clicked.connect(lambda: self._on_mode_button_clicked("hero_ban"))
        mode_group = QtWidgets.QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self.btn_mode_players)
        mode_group.addButton(self.btn_mode_heroes)
        mode_group.addButton(self.btn_mode_heroban)
        mode_row = QtWidgets.QHBoxLayout()
        mode_row.setContentsMargins(8, 0, 8, 4)
        mode_row.addStretch(1)
        mode_row.addWidget(QtWidgets.QLabel("Modus:"))
        mode_row.addWidget(self.btn_mode_players)
        mode_row.addWidget(self.btn_mode_heroes)
        mode_row.addWidget(self.btn_mode_heroban)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        grid = QtWidgets.QGridLayout()
        root.addLayout(grid, 1)

        # Startzustand pro Rolle (Spieler-Modus)
        active_states = self._mode_states[self.current_mode]
        tank_state = active_states["Tank"]
        dps_state = active_states["Damage"]
        support_state = active_states["Support"]

        self.tank = WheelView(
            "Tank",
            tank_state.get("entries", []),
            pair_mode=tank_state.get("pair_mode", False),
            allow_pair_toggle=False,
        )
        self.dps = WheelView(
            "Damage",
            dps_state.get("entries", []),
            pair_mode=dps_state.get("pair_mode", True),
            allow_pair_toggle=True,
            subrole_labels=["HS", "FDPS"],
        )
        self.support = WheelView(
            "Support",
            support_state.get("entries", []),
            pair_mode=support_state.get("pair_mode", True),
            allow_pair_toggle=True,
            subrole_labels=["MS", "FS"],
        )

        grid.addWidget(self.tank, 0, 0)
        grid.addWidget(self.dps, 0, 1)
        grid.addWidget(self.support, 0, 2)

        # Aktiven Modus vollständig anwenden (Einträge, Toggles etc.)
        self.btn_mode_players.setChecked(self.current_mode == "players")
        self.btn_mode_heroes.setChecked(self.current_mode == "heroes")
        self.btn_mode_heroban.setChecked(False)
        self._load_mode_into_wheels(self.current_mode)

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
        self.overlay.closed.connect(self._on_overlay_closed)
        
        self.online_mode = False  # Standard
        self.overlay.modeChosen.connect(self._on_mode_chosen)

        # Direkt beim Start Modus wählen lassen
        self._set_controls_enabled(False)
        self.overlay.show_online_choice()

        # JETZT: Save-Hooks anschließen
        for w in (self.tank, self.dps, self.support):
            w.stateChanged.connect(self._save_state)
            w.btn_include_in_all.toggled.connect(self._update_spin_all_enabled)
            w.stateChanged.connect(self._on_wheel_state_changed)
            w.btn_include_in_all.toggled.connect(self._on_role_include_toggled)

        # jetzt darf gespeichert werden
        self._restoring_state = False

        # Buttons initial updaten (nutzt schon include_in_all)
        self._update_spin_all_enabled()
        self._update_cancel_enabled()

    def _on_overlay_closed(self):
        self._set_controls_enabled(True)
        self.sound.stop_ding()
        if self.hero_ban_active:
            self._hero_ban_override_role = None
            self._update_hero_ban_wheel()

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
        if getattr(self, "hero_ban_active", False):
            any_selected = any(w.btn_include_in_all.isChecked() for w in (self.tank, self.dps, self.support))
            # In Hero-Ban zählen die effektiven Namen des zentralen Rads (inkl. Override).
            has_candidates = bool(self.dps.get_effective_wheel_names())
            self.btn_spin_all.setEnabled(any_selected and has_candidates and self.pending == 0)
            self._update_cancel_enabled()
            return
        any_selected = any(
            w.is_selected_for_global_spin()
            for w in (self.tank, self.dps, self.support)
        )
        # Nur aktiv, wenn allgemein erlaubt UND mindestens ein Rad ausgewählt
        self.btn_spin_all.setEnabled(any_selected and self.pending == 0)
        self._update_cancel_enabled()

    def _set_hero_ban_visuals(self, active: bool):
        """
        Graut nur die Rad-Grafiken aus. Listen und Buttons bleiben bedienbar.
        Include-Buttons steuern, welche Rollen ins zentrale Rad einfließen.
        """
        self.hero_ban_active = active
        for wheel in (self.tank, self.dps, self.support):
            effect = QtWidgets.QGraphicsOpacityEffect(wheel.view) if active else None
            if active:
                is_center = wheel is self.dps
                op = 1.0 if is_center else 0.25
                effect.setOpacity(op)
                wheel.view.setGraphicsEffect(effect)
                wheel.view.setEnabled(is_center)
                # Nur das mittlere Rad bleibt interaktiv, äußere Rad-Grafiken aus
                if is_center:
                    wheel.set_interactive_enabled(True)
                    wheel.btn_local_spin.setEnabled(True)
                    wheel.set_force_spin_enabled(True)
                    wheel.set_spin_button_text("🔁 Diese Rolle drehen")
                    wheel.btn_include_in_all.setEnabled(True)
                    wheel.names.setEnabled(True)
                else:
                    # Rad selbst ausblenden, aber Liste/Editieren und Include-Button aktiv lassen
                    wheel.view.setEnabled(False)
                    wheel.btn_local_spin.setEnabled(True)
                    # Local spin soll auch ohne sichtbares Rad erlaubt bleiben
                    wheel.set_force_spin_enabled(True)
                    wheel.set_show_names_visible(False)
                    wheel.set_spin_button_text(None)
                    wheel.btn_include_in_all.setEnabled(True)
                    wheel.names.setEnabled(True)
                    # Paare/Subrollen aus
                    wheel.set_interactive_enabled(True)
                    if wheel.toggle:
                        wheel.toggle.setEnabled(False)
                        wheel.toggle.setChecked(False)
                    if wheel.chk_subroles:
                        wheel.chk_subroles.setEnabled(False)
                        wheel.chk_subroles.setChecked(False)
                # Im Hero-Ban immer Einzel-Helden → Paar/Subrollen aus
                if wheel.toggle:
                    wheel.toggle.setEnabled(False)
                    wheel.toggle.setChecked(False)
                if wheel.chk_subroles:
                    wheel.chk_subroles.setEnabled(False)
                    wheel.chk_subroles.setChecked(False)
                # Header-Toggles und Subrollen-Kästchen ausblenden
                wheel.set_header_controls_visible(False)
                wheel.set_subrole_controls_visible(False)
                # Seitliche Räder leer zeichnen, mittleres normal
                if wheel is not self.dps:
                    wheel.set_wheel_render_enabled(False)
                else:
                    wheel.set_wheel_render_enabled(True)
            else:
                wheel.view.setGraphicsEffect(None)
                wheel.view.setEnabled(True)
                wheel.set_interactive_enabled(True)
                if wheel.toggle:
                    wheel.toggle.setEnabled(True)
                if wheel.chk_subroles:
                    wheel.chk_subroles.setEnabled(True)
                wheel.btn_local_spin.setEnabled(True)
                wheel.set_force_spin_enabled(False)
                wheel.set_show_names_visible(True)
                wheel.set_spin_button_text(None)
                wheel.btn_include_in_all.setEnabled(True)
                wheel.names.setEnabled(True)
                wheel.set_wheel_render_enabled(True)
                wheel.set_header_controls_visible(True)
                wheel.set_subrole_controls_visible(True)
                wheel.set_override_entries(None)

    def _set_controls_enabled(self, en: bool):
        if en:
            self._update_spin_all_enabled()
        else:
            self.btn_spin_all.setEnabled(False)
        for w in (self.tank, self.dps, self.support):
            w.set_interactive_enabled(en)
        if not en:
            self._update_cancel_enabled()
        if self.hero_ban_active and en:
            self._set_hero_ban_visuals(True)
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
        if self.hero_ban_active:
            if self.pending > 0:
                return
            # Immer mit allen aktuell gewählten Rollen arbeiten, nicht mit einem alten Override.
            self._hero_ban_override_role = None
            self._update_hero_ban_wheel()
            self._spin_single(self.dps, 1.0, hero_ban_override=False)
            return
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
    def _spin_single(self, wheel: WheelView, mult: float = 1.0, hero_ban_override: bool = True):
        if self.pending > 0: return
        if self.hero_ban_active:
            role_map = {self.tank: "Tank", self.dps: "Damage", self.support: "Support"}
            self._hero_ban_override_role = role_map.get(wheel) if hero_ban_override else None
            self._update_hero_ban_wheel()
            target_wheel = self.dps
        else:
            target_wheel = wheel
        self._result_sent_this_spin = False
        self._snapshot_results()
        self.sound.stop_ding(); self._stop_all_wheels(); self._set_controls_enabled(False)
        self.summary.setText(""); self.pending = 0; self.overlay.hide()
        self.sound.play_spin()
        duration = int(self.duration.value()*mult)
        if target_wheel.spin(duration_ms=duration): self.pending = 1
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

            if self.hero_ban_active:
                d = self.dps.result.text().replace("Ergebnis: ", "")
                self.summary.setText(f"Hero-Ban: {d}")
                self.overlay.show_message("Hero-Ban", [d, "", ""])
                self._last_results_snapshot = None
                self._update_cancel_enabled()
                return
            else:
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
    def _normalize_entries_for_state(self, defaults) -> list[dict]:
        """Formatiert eine Eingabeliste in das interne Eintragsformat."""
        entries: list[dict] = []
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
                entries.append({
                    "name": name,
                    "subroles": subs_list,
                    "active": bool(item.get("active", True)),
                })
        return entries

    def _default_role_state(self, role: str, mode: str) -> dict:
        """Liefert Startwerte pro Rolle/Modus."""
        pair_defaults = {"Tank": False, "Damage": True, "Support": True}
        if mode == "heroes":
            defaults = config.DEFAULT_HEROES.get(role, [])
        else:
            defaults = config.DEFAULT_NAMES.get(role, [])
        return {
            "entries": self._normalize_entries_for_state(defaults),
            "include_in_all": True,
            "pair_mode": pair_defaults.get(role, False),
            "use_subroles": False,
        }

    def _role_state_from_saved(self, data, role: str, mode: str) -> dict:
        """Mischt gespeicherte Werte mit Defaults."""
        base = self._default_role_state(role, mode)
        if not isinstance(data, dict):
            return base
        if "entries" in data:
            base["entries"] = self._normalize_entries_for_state(data["entries"])
        elif "names" in data:
            base["entries"] = self._normalize_entries_for_state(data["names"])
        base["include_in_all"] = bool(data.get("include_in_all", base["include_in_all"]))
        base["pair_mode"] = bool(data.get("pair_mode", base["pair_mode"]))
        base["use_subroles"] = bool(data.get("use_subroles", base["use_subroles"]))
        return base

    def _build_mode_states(self, saved: dict) -> dict:
        """Baut Modus-States aus gespeicherten Daten (inkl. Legacy-Fallback)."""
        roles = ("Tank", "Damage", "Support")
        players_saved = saved.get("players") if isinstance(saved, dict) else {}
        heroes_saved = saved.get("heroes") if isinstance(saved, dict) else {}
        mode_states = {"players": {}, "heroes": {}}
        for role in roles:
            if isinstance(players_saved, dict) and role in players_saved:
                players_src = players_saved.get(role, {})
            else:
                players_src = saved.get(role, {})
            mode_states["players"][role] = self._role_state_from_saved(players_src, role, "players")

            heroes_src = heroes_saved.get(role, {}) if isinstance(heroes_saved, dict) else {}
            mode_states["heroes"][role] = self._role_state_from_saved(heroes_src, role, "heroes")
        return mode_states

    def _role_states_from_wheels(self) -> dict:
        """Aktuellen Zustand aller Räder (aktiver Modus) auslesen."""
        base_state = self._mode_states.get(self.current_mode, {}) if self.hero_ban_active else {}

        def wheel_state(w: WheelView, role: str) -> dict:
            base = base_state.get(role, {}) if isinstance(base_state, dict) else {}
            return {
                "entries": w.get_current_entries(),
                "include_in_all": w.btn_include_in_all.isChecked(),
                "pair_mode": base.get("pair_mode", getattr(w, "pair_mode", False)),
                "use_subroles": base.get("use_subroles", getattr(w, "use_subrole_filter", False)),
            }
        return {
            "Tank": wheel_state(self.tank, "Tank"),
            "Damage": wheel_state(self.dps, "Damage"),
            "Support": wheel_state(self.support, "Support"),
        }

    def _capture_current_mode_state(self):
        """Schreibt den UI-Zustand des aktiven Modus in _mode_states."""
        self._mode_states[self.current_mode] = self._role_states_from_wheels()

    def _load_mode_into_wheels(self, mode: str, hero_ban: bool = False):
        """Wendet den gespeicherten Zustand eines Modus auf die UI an."""
        if mode not in self._mode_states:
            return
        state = self._mode_states[mode]
        prev_restoring = getattr(self, "_restoring_state", False)
        self._restoring_state = True
        try:
            for role, wheel in (("Tank", self.tank), ("Damage", self.dps), ("Support", self.support)):
                role_state = state.get(role) or self._default_role_state(role, mode)
                state[role] = role_state
                wheel.load_entries(
                    role_state.get("entries", []),
                    pair_mode=False if hero_ban else role_state.get("pair_mode", False),
                    include_in_all=role_state.get("include_in_all", True),
                    use_subroles=False if hero_ban else role_state.get("use_subroles", False),
                )
        finally:
            self._restoring_state = prev_restoring
        if hero_ban:
            self._set_hero_ban_visuals(True)
            self._update_hero_ban_wheel()
        else:
            self._set_hero_ban_visuals(False)
            for w in (self.tank, self.dps, self.support):
                w.set_header_controls_visible(True)
                w.set_subrole_controls_visible(True)
                w.set_show_names_visible(True)
            # sicherstellen, dass das mittlere Rad wieder seine eigene Liste nutzt
            self.dps.set_override_entries(None)
        if hasattr(self, "btn_spin_all"):
            self._update_spin_all_enabled()
        if hasattr(self, "btn_cancel_spin"):
            self._update_cancel_enabled()
        self._update_title()

    def _on_mode_button_clicked(self, target: str):
        came_from_hero_ban = self.hero_ban_active
        if target == "hero_ban":
            if self.hero_ban_active:
                return
            self.last_non_hero_mode = self.current_mode
            self._capture_current_mode_state()
            self.current_mode = "heroes"
            self.btn_mode_players.setChecked(False)
            self.btn_mode_heroes.setChecked(False)
            self.btn_mode_heroban.setChecked(True)
            self._load_mode_into_wheels("heroes", hero_ban=True)
            return

        if target not in ("players", "heroes"):
            return
        # Beim Verlassen des Hero-Ban die Hero-Listen sichern
        if self.hero_ban_active:
            self._capture_current_mode_state()
            self.hero_ban_active = False
            # Mittleres Rad wieder normalisieren
            self.dps.set_override_entries(None)
        # Wenn wir aus dem Hero-Ban kommen, trotz identischem target neu laden
        if target == self.current_mode and not came_from_hero_ban:
            return
        self.current_mode = target
        self.last_non_hero_mode = target
        self.btn_mode_players.setChecked(target == "players")
        self.btn_mode_heroes.setChecked(target == "heroes")
        self.btn_mode_heroban.setChecked(False)
        self._load_mode_into_wheels(target, hero_ban=False)
        self._save_state()

    def _update_title(self):
        self.title.setText("Overwatch 2 – Triple Wheel Picker")
    def _load_saved_state(self) -> dict:
        """
        Lädt den gespeicherten Zustand aus saved_state.json, falls vorhanden.
        Struktur:
        {
          "players": {"Tank": {...}, "Damage": {...}, "Support": {...}},
          "heroes":  {"Tank": {...}, "Damage": {...}, "Support": {...}},
          "volume": int
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
        Liest den aktuellen Zustand beider Modi aus.
        """
        self._capture_current_mode_state()
        return {
            "players": self._mode_states.get("players", {}),
            "heroes": self._mode_states.get("heroes", {}),
            "volume": self.volume_slider.value(),
        }

    def _update_hero_ban_wheel(self):
        """Führt die aktivierten Rollen zu einem zentralen Rad zusammen (Einzel-Helden)."""
        if not self.hero_ban_active:
            return
        if self._hero_ban_rebuild:
            # Wenn wir gerade am Neuaufbau sind, das Update nach Abschluss nachholen.
            self._hero_ban_pending = True
            return
        self._hero_ban_rebuild = True
        # Wir starten jetzt einen frischen Rebuild – eventuell markiertes Pending zurücksetzen.
        self._hero_ban_pending = False
        # Im Normalfall alle per Include-Button gewählten Rollen zusammenführen.
        # Wenn ein lokaler Spin einer Rolle gestartet wurde, nur diese Rolle nutzen.
        selected_roles: list[str] = []
        if self._hero_ban_override_role:
            selected_roles.append(self._hero_ban_override_role)
        else:
            if self.tank.btn_include_in_all.isChecked():
                selected_roles.append("Tank")
            if self.dps.btn_include_in_all.isChecked():
                selected_roles.append("Damage")
            if self.support.btn_include_in_all.isChecked():
                selected_roles.append("Support")

        combined: list[dict] = []
        seen = set()
        role_to_wheel = {"Tank": self.tank, "Damage": self.dps, "Support": self.support}
        for role in selected_roles:
            wheel = role_to_wheel.get(role)
            if not wheel:
                continue
            base_entries = wheel.get_current_entries()
            for entry in base_entries:
                if not entry.get("active", True):
                    continue
                name = str(entry.get("name", "")).strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                combined.append({"name": name, "subroles": [], "active": True})

        try:
            # Nur das mittlere Rad nutzt die zusammengeführte Liste – ohne die sichtbare Liste zu überschreiben.
            self.dps.set_override_entries(combined)
        finally:
            self._hero_ban_rebuild = False
        self._set_hero_ban_visuals(True)
        # sicherstellen, dass nur das mittlere Rad spinnt
        self.tank.btn_local_spin.setEnabled(True)
        self.support.btn_local_spin.setEnabled(True)
        self.dps.btn_local_spin.setEnabled(True)
        self._update_spin_all_enabled()
        # Falls während des Aufbaus weitere Änderungen kamen, sofort nachziehen.
        if self._hero_ban_pending:
            self._hero_ban_pending = False
            QtCore.QTimer.singleShot(0, self._update_hero_ban_wheel)

    def _on_role_include_toggled(self, _checked: bool):
        if self.hero_ban_active:
            # Zurück in den normalen Zusammenführungsmodus
            self._hero_ban_override_role = None
            self._update_hero_ban_wheel()
    def _on_wheel_state_changed(self):
        """Reagiert auf Änderungen in den Rädern (z.B. Namensliste) im Hero-Ban-Modus."""
        if not self.hero_ban_active:
            return
        if self._hero_ban_rebuild:
            # Signal kam während eines Rebuilds → später nachholen
            self._hero_ban_pending = True
            return
        self._hero_ban_override_role = None
        self._update_hero_ban_wheel()

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
        if self.hero_ban_active:
            self._update_hero_ban_wheel()
    
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
