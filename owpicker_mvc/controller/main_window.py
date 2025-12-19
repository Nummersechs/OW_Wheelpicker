from pathlib import Path
import random
import json
import os
import sys

from PySide6 import QtCore, QtGui, QtWidgets

import config
import i18n
from . import mode_manager, spin_service
from services import hero_ban_merge, persistence, spin_planner, state_store, sync_service
from services.sound import SoundManager
from view.overlay import ResultOverlay
from view.wheel_view import WheelView

# Fallback für "unbegrenzt" bei Widgetbreiten/Höhen (PySide6 exportiert QWIDGETSIZE_MAX nicht immer)
QWIDGETSIZE_MAX = getattr(QtWidgets, "QWIDGETSIZE_MAX", getattr(QtCore, "QWIDGETSIZE_MAX", 16777215))

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        # Basisverzeichnisse bestimmen (Assets vs. writable state) und gespeicherten Zustand laden
        self._asset_dir = self._asset_base_dir()
        self._state_dir = self._state_base_dir()
        self._state_file = self._get_state_file()
        saved = self._load_saved_state()
        default_lang = getattr(config, "DEFAULT_LANGUAGE", "en")
        self.language = saved.get("language", default_lang) if isinstance(saved, dict) else default_lang
        i18n.set_language(self.language)

        self.setWindowTitle(i18n.t("app.title.main"))
        self.resize(1200, 650)
        self.sound = SoundManager(base_dir=self._asset_dir)

        self._restoring_state = True   # während des Aufbaus nicht speichern
        self.current_mode = "players"  # immer mit Spieler-Auswahl starten
        self.last_non_hero_mode = "players"
        self.hero_ban_active = False
        self._hero_ban_rebuild = False
        self._hero_ban_pending = False
        self._hero_ban_override_role: str | None = None
        self._role_base_widths: dict[str, int] = {}
        self._state_store = state_store.ModeStateStore.from_saved(saved)
        self._mode_results: dict[str, dict[str, str]] = {}

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
        self.lbl_volume_icon.setToolTip(i18n.t("volume.icon_tooltip"))
        self.lbl_volume_icon.setStyleSheet("font-size:18px; padding:0 4px; background:transparent; border:none;")
        self.lbl_volume_icon.clicked.connect(self._on_volume_icon_clicked)
        self.volume_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(100)
        self.volume_slider.setFixedWidth(120)
        self.volume_slider.setFixedHeight(28)
        self.volume_slider.setToolTip(i18n.t("volume.slider_tooltip"))
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        self.volume_slider.sliderReleased.connect(self._play_volume_preview)
        self.volume_slider.sliderPressed.connect(self._play_volume_preview)
        self.btn_language = QtWidgets.QToolButton()
        self.btn_language.setAutoRaise(True)
        self.btn_language.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_language.setFixedSize(40, 32)
        self.btn_language.setStyleSheet(
            "QToolButton { font-size:18px; padding:2px; background:transparent; border:none; border-radius:6px; }"
            "QToolButton:hover { background:rgba(0,0,0,0.06); }"
            "QToolButton:pressed { background:rgba(0,0,0,0.12); }"
        )
        self.btn_language.clicked.connect(self._toggle_language)
        vol_row.addWidget(self.lbl_volume_icon, 0, QtCore.Qt.AlignVCenter)
        vol_row.addWidget(self.volume_slider, 0, QtCore.Qt.AlignVCenter)
        vol_row.addSpacing(6)
        vol_row.addWidget(self.btn_language, 0, QtCore.Qt.AlignVCenter)
        vol_row.addStretch(0)
        root.addLayout(vol_row)
        saved_volume = saved.get("volume", 100)
        try:
            self.volume_slider.setValue(int(saved_volume))
        except Exception:
            pass
        self._on_volume_changed(self.volume_slider.value())
        self._last_volume_before_mute = self.volume_slider.value()

        # Modus-Schalter (Spieler / Helden / Hero-Ban / Maps)
        self.btn_mode_players = QtWidgets.QPushButton(i18n.t("mode.players"))
        self.btn_mode_players.setCheckable(True)
        self.btn_mode_heroes = QtWidgets.QPushButton(i18n.t("mode.heroes"))
        self.btn_mode_heroes.setCheckable(True)
        self.btn_mode_heroban = QtWidgets.QPushButton(i18n.t("mode.hero_ban"))
        self.btn_mode_heroban.setCheckable(True)
        self.btn_mode_maps = QtWidgets.QPushButton(i18n.t("mode.maps"))
        self.btn_mode_maps.setCheckable(True)
        # Fixe Breiten, damit Sprache die Buttons nicht springen lässt
        self._set_fixed_width_from_translations(
            [
                self.btn_mode_players,
                self.btn_mode_heroes,
                self.btn_mode_heroban,
                self.btn_mode_maps,
            ],
            ["mode.players", "mode.heroes", "mode.hero_ban", "mode.maps"],
            padding=48,
        )
        self._mode_buttons = [
            self.btn_mode_players,
            self.btn_mode_heroes,
            self.btn_mode_heroban,
            self.btn_mode_maps,
        ]
        for btn in self._mode_buttons:
            btn.setProperty("modeButton", True)
            btn.toggled.connect(self._update_mode_button_styles)
        self.btn_mode_players.clicked.connect(lambda: self._on_mode_button_clicked("players"))
        self.btn_mode_heroes.clicked.connect(lambda: self._on_mode_button_clicked("heroes"))
        self.btn_mode_heroban.clicked.connect(lambda: self._on_mode_button_clicked("hero_ban"))
        self.btn_mode_maps.clicked.connect(lambda: self._on_mode_button_clicked("maps"))
        mode_group = QtWidgets.QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self.btn_mode_players)
        mode_group.addButton(self.btn_mode_heroes)
        mode_group.addButton(self.btn_mode_heroban)
        mode_group.addButton(self.btn_mode_maps)
        mode_row = QtWidgets.QHBoxLayout()
        mode_row.setContentsMargins(8, 0, 8, 4)
        mode_row.addStretch(1)
        self.lbl_mode = QtWidgets.QLabel(i18n.t("label.mode"))
        mode_row.addWidget(self.lbl_mode)
        mode_row.addWidget(self.btn_mode_players)
        mode_row.addWidget(self.btn_mode_heroes)
        mode_row.addWidget(self.btn_mode_heroban)
        mode_row.addWidget(self.btn_mode_maps)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

        # ----- Rolle/Grid-Container (Players/Heroes/Hero-Ban) -----
        role_container = QtWidgets.QWidget()
        grid = QtWidgets.QGridLayout(role_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(12)
        # Alle drei Spalten gleichmäßig strecken, damit die Breiten beim Moduswechsel stabil bleiben
        for col in range(3):
            grid.setColumnStretch(col, 1)

        # Startzustand pro Rolle (Spieler-Modus)
        active_states = self._state_store.get_mode_state(self.current_mode)
        tank_state = active_states["Tank"]
        dps_state = active_states["Damage"]
        support_state = active_states["Support"]

        self.tank = WheelView(
            "Tank",
            tank_state.get("entries", []),
            pair_mode=tank_state.get("pair_mode", False),
            allow_pair_toggle=True,
            subrole_labels=["MT", "OT"],
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
        # Basisbreiten nach dem ersten Layout ermitteln
        QtCore.QTimer.singleShot(0, self._capture_role_base_widths)

        # ----- Map-Mode-Container -----
        self._map_result_text = "–"
        self.map_container = self._build_map_mode_ui()

        # ----- Stacked Content -----
        self.mode_stack = QtWidgets.QStackedLayout()
        self.mode_stack.addWidget(role_container)  # index 0
        self.mode_stack.addWidget(self.map_container)  # index 1
        root.addLayout(self.mode_stack, 1)

        # Aktiven Modus vollständig anwenden (Einträge, Toggles etc.)
        self.btn_mode_players.setChecked(self.current_mode == "players")
        self.btn_mode_heroes.setChecked(self.current_mode == "heroes")
        self.btn_mode_heroban.setChecked(False)
        self._update_mode_button_styles()
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
        self.duration.setToolTip(i18n.t("controls.anim_duration_tooltip"))
        self.btn_spin_all = QtWidgets.QPushButton(i18n.t("controls.spin_all"))
        self._set_fixed_width_from_translations([self.btn_spin_all], ["controls.spin_all"], padding=40)
        self.btn_spin_all.setFixedHeight(44)
        self.btn_spin_all.clicked.connect(self.spin_all)
        controls.addStretch(1)
        self.lbl_anim_duration = QtWidgets.QLabel(i18n.t("controls.anim_duration"))
        controls.addWidget(self.lbl_anim_duration)
        self.duration.setFixedHeight(30)
        controls.addWidget(self.duration)
        controls.addWidget(self.btn_spin_all)
        self.btn_cancel_spin = QtWidgets.QPushButton(i18n.t("controls.cancel_spin"))
        self._set_fixed_width_from_translations([self.btn_cancel_spin], ["controls.cancel_spin"], padding=40)
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
        if hasattr(self, "map_main"):
            self.map_main.spun.connect(self._wheel_finished)

        self.overlay = ResultOverlay(parent=central)
        self.overlay.hide()
        self.overlay.closed.connect(self._on_overlay_closed)
        self.overlay.languageToggleRequested.connect(self._toggle_language)
        
        self.online_mode = False  # Standard
        self.overlay.modeChosen.connect(self._on_mode_chosen)
        self.installEventFilter(self)
        app = QtWidgets.QApplication.instance()
        if app:
            app.installEventFilter(self)

        # Direkt beim Start Modus wählen lassen
        self._set_controls_enabled(False)
        self.overlay.show_online_choice()
        # Buttons vorerst sperren, bis Caches einmal aufgebaut sind
        self.overlay.set_choice_enabled(False)
        QtCore.QTimer.singleShot(0, self._warmup_tooltips_initial)

        # JETZT: Save-Hooks anschließen
        for w in (self.tank, self.dps, self.support):
            w.stateChanged.connect(self._save_state)
            w.btn_include_in_all.toggled.connect(self._update_spin_all_enabled)
            w.stateChanged.connect(self._on_wheel_state_changed)
            w.btn_include_in_all.toggled.connect(self._on_role_include_toggled)
        if hasattr(self, "map_lists"):
            for w in self.map_lists.values():
                w.stateChanged.connect(self._save_state)
                w.btn_include_in_all.toggled.connect(self._save_state)
                w.btn_include_in_all.toggled.connect(self._update_spin_all_enabled)

        # jetzt darf gespeichert werden
        self._restoring_state = False

        # Buttons initial updaten (nutzt schon include_in_all)
        self._update_spin_all_enabled()
        self._update_cancel_enabled()
        self._apply_mode_results(self._mode_key())
        self._apply_language()
        # Tooltips sofort erlauben (werden später noch einmal frisch berechnet)
        self._set_tooltips_ready(True)

    def _warmup_tooltips_initial(self):
        """Initial Cache/Tooltips vorbereiten und Online/Offline-Buttons freigeben."""
        self._refresh_tooltip_caches()
        self._reset_hover_cache_under_cursor()
        QtCore.QTimer.singleShot(180, lambda: self.overlay.set_choice_enabled(True))

    def _on_overlay_closed(self):
        self._set_controls_enabled(True)
        self.sound.stop_ding()
        if self.hero_ban_active:
            self._hero_ban_override_role = None
            self._update_hero_ban_wheel()
        # Tooltip/Truncation nach finalem Layout aktualisieren
        QtCore.QTimer.singleShot(0, self._refresh_tooltip_caches)
        QtCore.QTimer.singleShot(200, self._refresh_tooltip_caches)

    def eventFilter(self, obj, event):
        # Nach längeren Pausen/Focus-Wechsel Tooltip-Caches auffrischen
        if event.type() in (
            QtCore.QEvent.FocusIn,
            QtCore.QEvent.WindowActivate,
            QtCore.QEvent.ApplicationActivate,
        ):
            QtCore.QTimer.singleShot(0, self._refresh_tooltip_caches)
            QtCore.QTimer.singleShot(150, self._refresh_tooltip_caches)
        return super().eventFilter(obj, event)

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
            QPushButton[modeButton="true"] {
                padding:6px 14px;
                font-size:13px;
                min-width:120px;
            }
            QPushButton[modeButton="true"]:checked {
                padding:10px 18px;
                font-size:14px;
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

    def _update_mode_button_styles(self, *_args):
        """
        Erzwingt ein Neupolishen der Mode-Buttons, damit die padding-Änderung
        bei checked/unchecked sofort gegriffen wird.
        """
        if not getattr(self, "_mode_buttons", None):
            return
        for btn in self._mode_buttons:
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.updateGeometry()

    def _capture_role_base_widths(self):
        """Merkt sich die aktuelle Breite jeder Rollen-Karte als Referenz."""
        widths: dict[str, int] = {}
        for name, widget in (("Tank", self.tank), ("Damage", self.dps), ("Support", self.support)):
            w = widget.width() or widget.sizeHint().width()
            widths[name] = max(1, int(w))
        self._role_base_widths = widths

    def _apply_role_width_lock(self, lock: bool):
        """
        Begrenze/entgrenze die Rollenbreiten – in Hero-Ban sperren wir auf die
        gemerkte Basisbreite, damit z.B. Tank nicht breiter wird.
        """
        if not self._role_base_widths:
            self._capture_role_base_widths()
        for name, widget in (("Tank", self.tank), ("Damage", self.dps), ("Support", self.support)):
            base = self._role_base_widths.get(name, widget.sizeHint().width() or widget.width())
            if lock:
                widget.setMaximumWidth(base)
            else:
                widget.setMaximumWidth(QWIDGETSIZE_MAX)

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
        if self.current_mode == "maps":
            any_selected = any(w.btn_include_in_all.isChecked() for w in getattr(self, "map_lists", {}).values())
            has_candidates = bool(getattr(self, "_map_combined", []))
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

    def _mode_key(self) -> str:
        return "hero_ban" if self.hero_ban_active else self.current_mode

    def _snapshot_mode_results(self):
        """Merkt Summary/Resultate für den aktuellen Modus (temp, nicht persistiert)."""
        key = self._mode_key()
        if self.current_mode == "maps":
            self._mode_results[key] = {
                "map": getattr(self, "_map_result_text", "–"),
            }
        else:
            self._mode_results[key] = {
                "wheels": {
                    "tank": self.tank.get_result_payload(),
                    "dps": self.dps.get_result_payload(),
                    "support": self.support.get_result_payload(),
                }
            }

    def _apply_mode_results(self, key: str):
        """Stellt Summary/Resultate für den gewünschten Modus wieder her."""
        if not hasattr(self, "summary"):
            return
        snap = self._mode_results.get(key)
        if not snap:
            # Reset auf neutrale Anzeige
            if self.current_mode == "maps":
                self._map_result_text = "–"
            else:
                for wheel in (self.tank, self.dps, self.support):
                    wheel.clear_result()
            self.summary.setText("")
            return
        self.summary.setText("")
        if self.current_mode == "maps":
            self._map_result_text = snap.get("map", "–")
            self._update_summary_from_results()
        else:
            mapping = [("tank", self.tank), ("dps", self.dps), ("support", self.support)]
            wheel_payloads = snap.get("wheels", {})
            for name, wheel in mapping:
                wheel.apply_result_payload(wheel_payloads.get(name))
            self._update_summary_from_results()

    def _update_summary_from_results(self):
        """Erzeugt die Summary basierend auf den aktuellen Resultaten und Modus."""
        if self.current_mode == "maps":
            choice = getattr(self, "_map_result_text", "–")
            if choice and choice != "–":
                self.summary.setText(i18n.t("map.summary.choice", choice=choice))
            else:
                self.summary.setText("")
            return
        if self.hero_ban_active:
            pick = self.dps.get_result_value()
            self.summary.setText(i18n.t("summary.hero_ban", pick=pick or "–") if pick else "")
            return
        t = self.tank.get_result_value()
        d = self.dps.get_result_value()
        s = self.support.get_result_value()
        if t or d or s:
            self.summary.setText(i18n.t("summary.team", tank=t or "–", dps=d or "–", sup=s or "–"))
        else:
            self.summary.setText("")

    def _refresh_tooltip_caches(self):
        """Baut die Label-/Tooltip-Caches nach finalem Layout neu auf und schaltet sie frei."""
        wheels = [self.tank, self.dps, self.support]
        if getattr(self, "map_main", None):
            wheels.append(self.map_main)
        for w in wheels:
            wheel = getattr(getattr(w, "view", None), "wheel", None)
            if wheel and hasattr(wheel, "_ensure_cache"):
                try:
                    wheel._cached = None
                    wheel._ensure_cache(force=True)
                except Exception:
                    pass
            if wheel and hasattr(wheel, "set_tooltips_ready"):
                try:
                    wheel.set_tooltips_ready(True)
                except Exception:
                    pass

    def _reset_hover_cache_under_cursor(self):
        """Simuliert einen Hover unter dem aktuellen Cursor, um Tooltip-Cache zu aktualisieren."""
        for w in (self.tank, self.dps, self.support, getattr(self, "map_main", None)):
            if not w:
                continue
            wheel = getattr(getattr(w, "view", None), "wheel", None)
            if wheel and hasattr(wheel, "_ensure_cache") and hasattr(wheel, "_needs_tooltip_runtime"):
                # Cache leeren und neu aufbauen
                try:
                    wheel._cached = None
                    wheel._ensure_cache(force=True)
                except Exception:
                    pass

    def _set_tooltips_ready(self, ready: bool = True):
        """Setzt das Tooltip-Ready-Flag für alle Räder."""
        wheels = [self.tank, self.dps, self.support]
        if getattr(self, "map_main", None):
            wheels.append(self.map_main)
        for w in wheels:
            wheel = getattr(getattr(w, "view", None), "wheel", None)
            if wheel and hasattr(wheel, "set_tooltips_ready"):
                try:
                    wheel.set_tooltips_ready(bool(ready))
                except Exception:
                    pass

    def _set_hero_ban_visuals(self, active: bool):
        """Delegiert an den Mode-Manager und sperrt Breiten in Hero-Ban."""
        self._apply_role_width_lock(active)
        mode_manager.set_hero_ban_visuals(self, active)
    def _set_controls_enabled(self, en: bool):
        if en:
            self._update_spin_all_enabled()
        else:
            self.btn_spin_all.setEnabled(False)
        for w in (self.tank, self.dps, self.support):
            w.set_interactive_enabled(en)
        if getattr(self, "current_mode", "") == "maps" and hasattr(self, "map_lists"):
            for w in self.map_lists.values():
                w.set_interactive_enabled(en)
            if hasattr(self, "map_main"):
                self.map_main.set_interactive_enabled(en)
        if not en:
            self._update_cancel_enabled()
        if self.hero_ban_active and en:
            self._set_hero_ban_visuals(True)
    def _stop_all_wheels(self):
        for w in (self.tank, self.dps, self.support): w.hard_stop()
    def _update_cancel_enabled(self):
        self.btn_cancel_spin.setEnabled(self.pending > 0)
    
    def spin_all(self):
        """Dreht alle selektierten Räder auf faire Weise."""
        if self.current_mode == "maps":
            self._spin_map_all()
        else:
            spin_service.spin_all(self)
    def _spin_single(self, wheel: WheelView, mult: float = 1.0, hero_ban_override: bool = True):
        if self.current_mode == "maps":
            self._spin_map_single()
        else:
            spin_service.spin_single(self, wheel, mult=mult, hero_ban_override=hero_ban_override)

    def _spin_map_all(self, subset: list[str] | None = None):
        if self.pending > 0:
            return
        # Neuer Spin → finale Anzeige wieder erlauben
        self._result_sent_this_spin = False
        candidates = list(subset) if subset is not None else list(getattr(self, "_map_combined", []))
        if not candidates:
            self.summary.setText(i18n.t("map.summary.prompt"))
            return
        self._snapshot_results()
        self.sound.stop_ding()
        self._stop_all_wheels()
        self._set_controls_enabled(False)
        self.summary.setText("")
        self.pending = 0
        self.overlay.hide()
        self.sound.play_spin()
        duration = int(self.duration.value())
        self._pending_map_choice = None
        if hasattr(self, "map_main"):
            # Wähle Zielname gezielt, falls möglich
            # Temporär override, falls subset vorgegeben
            if subset is not None:
                override_entries = [{"name": n, "subroles": [], "active": True} for n in candidates]
                self.map_main.set_override_entries(override_entries)
                self._map_temp_override = True
            else:
                self._map_temp_override = False
            candidates = self.map_main.get_effective_wheel_names(include_disabled=False)
            if candidates:
                choice = random.choice(candidates)
                self._pending_map_choice = choice
                ok = self.map_main.spin_to_name(choice, duration_ms=duration)
            else:
                ok = self.map_main.spin(duration_ms=duration)
        else:
            ok = False
        if ok:
            self.pending = 1
        else:
            self.sound.stop_spin()
            self._set_controls_enabled(True)
            self.summary.setText(i18n.t("map.summary.prompt"))
        self._update_cancel_enabled()

    def _spin_map_single(self):
        # lokaler Spin im Map-Mode entspricht globalem Spin (nur ein Rad)
        self._spin_map_all()

    def _spin_map_category(self, category: str):
        wheel = self.map_lists.get(category)
        if wheel is None:
            return
        names = [e.get("name", "").strip() for e in wheel._active_entries() if e.get("name", "").strip()]
        self._spin_map_all(subset=names)

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
                d = self.dps.get_result_value() or "–"
                self.summary.setText(i18n.t("summary.hero_ban", pick=d))
                self.overlay.show_message(i18n.t("overlay.hero_ban_title"), [d, "", ""])
                self._last_results_snapshot = None
                self._update_cancel_enabled()
                return
            if self.current_mode == "maps":
                choice = getattr(self, "_pending_map_choice", None) or getattr(self, "_map_result_text", "–")
                self._map_result_text = choice
                self._update_summary_from_results()
                self.overlay.show_message(i18n.t("overlay.map_title"), [choice, "", ""])
                self._last_results_snapshot = None
                self._snapshot_mode_results()
                if getattr(self, "_map_temp_override", False):
                    self._rebuild_map_wheel()
                    self._map_temp_override = False
                self._set_controls_enabled(True)
                self._update_cancel_enabled()
                return
            else:
                t = self.tank.get_result_value() or "–"
                d = self.dps.get_result_value() or "–"
                s = self.support.get_result_value() or "–"

                self.summary.setText(i18n.t("summary.team", tank=t, dps=d, sup=s))
                self.overlay.show_result(t, d, s)

                # Nur noch EIN Request pro abgeschlossenem Spin
                self._send_spin_result_to_server(t, d, s)
            self._last_results_snapshot = None
            # Ergebnisse für den aktuellen Modus merken
            self._snapshot_mode_results()
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
        self.overlay.show_message(
            i18n.t("overlay.spin_cancelled_title"),
            [i18n.t("overlay.spin_cancelled_line1"), i18n.t("overlay.spin_cancelled_line2"), ""],
        )
        self._set_controls_enabled(True)
        self._update_cancel_enabled()

    def _snapshot_results(self):
        """Merkt aktuelle Resultate & Summary, um sie bei Abbruch wiederherzustellen."""
        if self.current_mode == "maps":
            self._last_results_snapshot = {
                "mode": "maps",
                "map": getattr(self, "_map_result_text", "–"),
            }
        else:
            self._last_results_snapshot = {
                "mode": self._mode_key(),
                "wheels": {
                    "tank": self.tank.get_result_payload(),
                    "dps": self.dps.get_result_payload(),
                    "support": self.support.get_result_payload(),
                },
            }

    def _restore_results_snapshot(self):
        snap = getattr(self, "_last_results_snapshot", None)
        if not snap:
            return
        if snap.get("mode") == "maps":
            txt = snap.get("map", None)
            if txt is not None:
                self._map_result_text = txt
            self._update_summary_from_results()
        else:
            mapping = [("tank", self.tank), ("dps", self.dps), ("support", self.support)]
            wheel_payloads = snap.get("wheels", {})
            for key, wheel in mapping:
                wheel.apply_result_payload(wheel_payloads.get(key))
            self._update_summary_from_results()
        self._last_results_snapshot = None

    def _asset_base_dir(self) -> Path:
        """
        Liefert das Basisverzeichnis für Assets/Sounds.
        - Im Script-Run: Projektstamm (eine Ebene über controller/)
        - In der PyInstaller-onefile-EXE: entpacktes _MEIPASS (enthält add-data)
        """
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)  # type: ignore[attr-defined]
        return Path(__file__).resolve().parent.parent

    def _state_base_dir(self) -> Path:
        """
        Schreibbares Verzeichnis für saved_state.json.
        - Im Script-Run: Projektstamm (eine Ebene über controller/)
        - In der PyInstaller-onefile-EXE: neben der .exe (nicht im temporären _MEIPASS)
        """
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent.parent

    def _get_state_file(self) -> Path:
        """Gibt den Pfad zur saved_state.json zurück."""
        return persistence.state_file(self._state_dir)

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

    def _load_mode_into_wheels(self, mode: str, hero_ban: bool = False):
        """Wendet den gespeicherten Zustand eines Modus auf die UI an."""
        state = self._state_store.get_mode_state(mode)
        if not state:
            return
        prev_restoring = getattr(self, "_restoring_state", False)
        self._restoring_state = True
        try:
            for role, wheel in (("Tank", self.tank), ("Damage", self.dps), ("Support", self.support)):
                role_state = state.get(role) or self._state_store.default_role_state(role, mode)
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
        # Modusabhängige Ergebnisse laden
        self._apply_mode_results(self._mode_key())

    # ----- Map-Mode -----
    def _build_map_mode_ui(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.map_categories = list(getattr(config, "MAP_CATEGORIES", [])) or list(config.DEFAULT_MAPS.keys())
        map_state = self._state_store.get_mode_state("maps") or {}
        self.map_lists: dict[str, WheelView] = {}
        self._map_combined: list[str] = []
        self._map_result_text = "–"

        # --- Typen-Sidebar ---
        sidebar = QtWidgets.QFrame()
        sidebar.setStyleSheet("QFrame { background: rgba(245,245,245,0.9); border:1px solid #ddd; border-radius:8px; }")
        sb_layout = QtWidgets.QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(8, 8, 8, 8)
        sb_layout.setSpacing(6)
        self.lbl_map_types = QtWidgets.QLabel(i18n.t("map.types"))
        self.lbl_map_types.setStyleSheet("font-weight:600;")
        self._set_fixed_width_from_translations([self.lbl_map_types], ["map.types"], padding=30)
        sb_layout.addWidget(self.lbl_map_types)
        self.map_type_checks: dict[str, QtWidgets.QCheckBox] = {}
        self._map_type_list_layout = QtWidgets.QVBoxLayout()
        self._map_type_list_layout.setSpacing(4)
        sb_layout.addLayout(self._map_type_list_layout)
        self.btn_edit_map_types = QtWidgets.QPushButton(i18n.t("map.edit_types"))
        self._set_fixed_width_from_translations([self.btn_edit_map_types], ["map.edit_types"], padding=48)
        self.btn_edit_map_types.clicked.connect(lambda: self._show_map_type_editor(container))
        sb_layout.addWidget(self.btn_edit_map_types, 0, QtCore.Qt.AlignLeft)
        sb_layout.addStretch(1)
        self.map_sidebar = sidebar

        # --- Listen-Gitter rechts ---
        self.map_grid_container = QtWidgets.QWidget()
        self.map_grid = QtWidgets.QVBoxLayout(self.map_grid_container)
        self.map_grid.setContentsMargins(4, 4, 4, 4)
        self.map_grid.setSpacing(8)

        # Scroll um viele Listen aufzunehmen (ohne äußeren Rahmen)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.map_grid_container)
        scroll.setObjectName("mapListScroll")
        scroll.setStyleSheet(
            "#mapListScroll { border: none; background: transparent; }"
        )
        self.map_lists_frame = scroll
        scroll.installEventFilter(self)
        # Wrapper, um den rechten Bereich gezielt zu verschieben
        right_wrap = QtWidgets.QWidget()
        right_wrap_layout = QtWidgets.QVBoxLayout(right_wrap)
        right_wrap_layout.setSpacing(0)
        right_wrap_layout.addWidget(scroll)
        self.map_lists_wrapper = right_wrap

        # Listen initial erstellen
        self._build_map_lists(map_state)

        # zentrales Map-Rad zum Drehen
        self.map_main = WheelView("Map-Rad", [], pair_mode=False, allow_pair_toggle=False, title_key="map.wheel_title")
        self.map_main.set_header_controls_visible(False)
        self.map_main.set_subrole_controls_visible(False)
        self.map_main.set_show_names_visible(True)
        self.map_main.btn_include_in_all.setVisible(False)
        self.map_main.btn_local_spin.setText(i18n.t("wheel.spin_map"))
        self.map_main.request_spin.connect(self._spin_map_single)
        self.map_main.spun.connect(self._wheel_finished)
        # Nur Rad + „Namen anzeigen“ zeigen, rest ausblenden
        self.map_main.names.setVisible(False)
        self.map_main.names_hint.setVisible(False)
        if hasattr(self.map_main, "btn_sort_names"):
            self.map_main.btn_sort_names.setVisible(False)
        self.map_main.result_widget.setVisible(False)
        self.map_main.btn_local_spin.setVisible(False)
        # Rad-Größe an den Standard-Rädern ausrichten (WHEEL_RADIUS*2 + Padding)
        base_canvas = max(200, int(2 * config.WHEEL_RADIUS + 80))
        self.map_main.view.setMinimumSize(base_canvas, base_canvas)
        self.map_main.view.setMaximumSize(QtCore.QSize(16777215, 16777215))
        self.map_main.view.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        # Gesamt-Layout: Sidebar | Rad | Listen
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(sidebar, 0)
        row.addWidget(self.map_main, 0, QtCore.Qt.AlignCenter)
        row.addWidget(right_wrap, 1)
        row.setStretch(0, 0)
        row.setStretch(1, 1)
        row.setStretch(2, 1)
        layout.addLayout(row, 1)
        layout.setStretchFactor(row, 1)
        # Höhe des Map-Rads an die anderen Räder angleichen
        def _cap_heights():
            ref_h = max(
                200,
                self.tank.height() or self.tank.sizeHint().height(),
                self.dps.height() or self.dps.sizeHint().height(),
                self.support.height() or self.support.sizeHint().height(),
            )
            self.map_main.view.setMinimumHeight(ref_h)
            self.map_main.view.setMaximumHeight(ref_h)
            self.map_main.setMinimumHeight(ref_h)
            self.map_main.setMaximumHeight(ref_h)
            if hasattr(self, "map_lists_frame"):
                adj = max(100, ref_h - 20)  # 20px weniger Höhe
                self.map_lists_frame.setMinimumHeight(adj)
                self.map_lists_frame.setMaximumHeight(adj)
            if hasattr(self, "map_lists_wrapper"):
                adj = max(100, ref_h - 20)
                self.map_lists_wrapper.setMinimumHeight(adj)
                self.map_lists_wrapper.setMaximumHeight(adj)
            if hasattr(self, "map_sidebar"):
                adj = max(100, ref_h - 20)
                self.map_sidebar.setMinimumHeight(adj)
                self.map_sidebar.setMaximumHeight(adj)
        QtCore.QTimer.singleShot(0, _cap_heights)
        QtCore.QTimer.singleShot(0, self._rebuild_map_wheel)
        return container

    def _on_map_list_changed(self, *args):
        if self.current_mode != "maps":
            return
        self._rebuild_map_wheel()

    def _build_map_lists(self, map_state: dict, include_map: dict | None = None):
        self._map_rebuild_guard = True
        # bestehende Einträge bereinigen
        while self.map_grid.count():
            item = self.map_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self.map_lists.clear()
        self.map_type_checks.clear()
        # Layout für Typen-Checkboxen leeren
        while self._map_type_list_layout.count():
            item = self._map_type_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        for idx, cat in enumerate(self.map_categories):
            role_state = map_state.get(cat) or {"entries": [], "pair_mode": False, "use_subroles": False}
            include_checked = True if include_map is None else include_map.get(cat, True)
            w = WheelView(cat, role_state.get("entries", []), pair_mode=False, allow_pair_toggle=False)
            w.set_header_controls_visible(False)
            w.set_subrole_controls_visible(False)
            w.set_wheel_render_enabled(False)
            w.set_show_names_visible(False)
            w.view.setVisible(False)  # nur Liste zeigen
            w.result_widget.setVisible(False)
            w.btn_local_spin.setVisible(True)
            w.btn_local_spin.setEnabled(True)
            w.btn_local_spin.setText(i18n.t("wheel.spin_single_map"))
            w.btn_local_spin.clicked.connect(lambda _=None, c=cat: self._spin_map_category(c))
            w.btn_include_in_all.setChecked(include_checked)
            w.btn_include_in_all.toggled.connect(self._rebuild_map_wheel)
            w.stateChanged.connect(self._on_map_list_changed)
            w.set_interactive_enabled(True)
            self.map_lists[cat] = w
            self.map_grid.addWidget(w)

            cb = QtWidgets.QCheckBox(cat)
            cb.setChecked(include_checked)
            cb.toggled.connect(lambda checked, c=cat: self._on_map_type_toggled(c, checked))
            self.map_type_checks[cat] = cb
            self._map_type_list_layout.addWidget(cb)

        self._map_type_list_layout.addStretch(1)
        self._map_rebuild_guard = False
        self._rebuild_map_wheel()

    def _on_map_type_toggled(self, category: str, checked: bool):
        wheel = self.map_lists.get(category)
        if wheel:
            wheel.btn_include_in_all.setChecked(checked)
            wheel.setVisible(checked)
            wheel.set_interactive_enabled(checked)
        self._rebuild_map_wheel()

    def _show_map_type_editor(self, parent_widget: QtWidgets.QWidget):
        if not hasattr(self, "_map_type_editor"):
            self._map_type_editor = QtWidgets.QFrame(parent_widget)
            self._map_type_editor.setStyleSheet(
                "QFrame { background: white; border: 2px solid #444; border-radius: 10px; }"
            )
            self._map_type_editor.setFixedSize(360, 320)
            layout = QtWidgets.QVBoxLayout(self._map_type_editor)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(8)
            self._map_type_editor_title = QtWidgets.QLabel(i18n.t("map.editor.title"))
            self._map_type_editor_title.setStyleSheet("font-weight:700; font-size:14px;")
            self._set_fixed_width_from_translations([self._map_type_editor_title], ["map.editor.title"], padding=28)
            layout.addWidget(self._map_type_editor_title)

            self._map_type_list_widget = QtWidgets.QListWidget()
            self._map_type_list_widget.setEditTriggers(
                QtWidgets.QAbstractItemView.SelectedClicked
                | QtWidgets.QAbstractItemView.EditKeyPressed
            )
            self._map_type_list_widget.itemClicked.connect(self._start_map_type_edit)
            layout.addWidget(self._map_type_list_widget, 1)

            btn_grid = QtWidgets.QGridLayout()
            btn_grid.setContentsMargins(16, 6, 16, 6)
            btn_grid.setHorizontalSpacing(16)
            self._map_type_btn_add = QtWidgets.QPushButton(i18n.t("map.editor.add"))
            self._map_type_btn_del = QtWidgets.QPushButton(i18n.t("map.editor.delete"))
            common_btn_style = "QPushButton { padding:8px 12px; margin:2px; min-width:100px; border-radius:6px; }"
            self._map_type_btn_add.setStyleSheet(common_btn_style)
            self._map_type_btn_del.setStyleSheet(common_btn_style)
            self._map_type_btn_add.clicked.connect(self._add_map_type_row)
            self._map_type_btn_del.clicked.connect(self._del_map_type_row)
            self._set_fixed_width_from_translations(
                [self._map_type_btn_add, self._map_type_btn_del],
                ["map.editor.add", "map.editor.delete"],
                padding=40,
            )
            btn_grid.addWidget(self._map_type_btn_add, 0, 0, QtCore.Qt.AlignLeft)
            btn_grid.addWidget(self._map_type_btn_del, 0, 1, QtCore.Qt.AlignRight)
            btn_grid.setColumnStretch(0, 1)
            btn_grid.setColumnStretch(1, 1)
            layout.addLayout(btn_grid)

            confirm_row = QtWidgets.QHBoxLayout()
            confirm_row.setContentsMargins(16, 6, 16, 6)
            self._map_type_btn_ok = QtWidgets.QPushButton(i18n.t("map.editor.apply"))
            self._map_type_btn_cancel = QtWidgets.QPushButton(i18n.t("map.editor.cancel"))
            self._map_type_btn_ok.setStyleSheet("QPushButton { background:#2e7d32; color:white; padding:8px 12px; margin:2px; min-width:100px; border-radius:6px; }"
                                  "QPushButton:hover { background:#388e3c; }")
            self._map_type_btn_cancel.setStyleSheet("QPushButton { background:#c62828; color:white; padding:8px 12px; margin:2px; min-width:100px; border-radius:6px; }"
                                      "QPushButton:hover { background:#d32f2f; }")
            self._map_type_btn_ok.clicked.connect(self._confirm_map_types)
            self._map_type_btn_cancel.clicked.connect(lambda: self._map_type_editor.hide())
            self._set_fixed_width_from_translations(
                [self._map_type_btn_ok, self._map_type_btn_cancel],
                ["map.editor.apply", "map.editor.cancel"],
                padding=44,
            )
            confirm_row.addWidget(self._map_type_btn_ok, 0, QtCore.Qt.AlignLeft)
            confirm_row.addWidget(self._map_type_btn_cancel, 0, QtCore.Qt.AlignRight)
            layout.addLayout(confirm_row)

        # Inhalte aktualisieren
        self._map_type_list_widget.clear()
        for cat in self.map_categories:
            item = QtWidgets.QListWidgetItem(cat)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
            self._map_type_list_widget.addItem(item)

        # Frame mittig im Parent platzieren
        if parent_widget:
            pw = parent_widget.width()
            ph = parent_widget.height()
            w = self._map_type_editor.width()
            h = self._map_type_editor.height()
            self._map_type_editor.move(max(0, (pw - w) // 2), max(0, (ph - h) // 2))
        self._map_type_editor.show()
        self._map_type_editor.raise_()

    def _add_map_type_row(self):
        if hasattr(self, "_map_type_list_widget"):
            item = QtWidgets.QListWidgetItem(i18n.t("map.editor.new_type"))
            item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
            self._map_type_list_widget.addItem(item)
            self._map_type_list_widget.setCurrentItem(item)
            self._start_map_type_edit(item)

    def _del_map_type_row(self):
        if hasattr(self, "_map_type_list_widget"):
            row = self._map_type_list_widget.currentRow()
            if row >= 0:
                self._map_type_list_widget.takeItem(row)

    def _confirm_map_types(self):
        if not hasattr(self, "_map_type_list_widget"):
            return
        new_types = []
        for i in range(self._map_type_list_widget.count()):
            text = self._map_type_list_widget.item(i).text().strip()
            if text and text not in new_types:
                new_types.append(text)
        if not new_types:
            self._map_type_editor.hide()
            return
        QtCore.QTimer.singleShot(0, lambda: self._apply_map_types(new_types))
        self._map_type_editor.hide()
    def _start_map_type_edit(self, item: QtWidgets.QListWidgetItem):
        """Sofort in den Edit-Modus mit Cursor am Ende springen."""
        if not item:
            return
        self._map_type_list_widget.editItem(item)
        QtCore.QTimer.singleShot(0, lambda: self._focus_editor_end())

    def _focus_editor_end(self):
        # Finde den aktiven Editor (QLineEdit) und setze Cursor ans Ende ohne Auswahl
        editors = self._map_type_list_widget.findChildren(QtWidgets.QLineEdit)
        if not editors:
            return
        editor = editors[-1]
        editor.setFocus()
        editor.deselect()
        editor.setCursorPosition(len(editor.text()))

    def _apply_map_types(self, new_types: list[str]):
        # Aktuellen Zustand der Listen sichern, damit Einträge bei Umbenennung erhalten bleiben
        current_states = {}
        include_map = {}
        for cat, wheel in getattr(self, "map_lists", {}).items():
            current_states[cat] = {
                "entries": wheel.get_current_entries(),
                "pair_mode": False,
                "use_subroles": False,
            }
            include_map[cat] = wheel.btn_include_in_all.isChecked()

        # Fallback auf gespeicherten State
        saved_state = self._state_store.get_mode_state("maps") or {}

        new_state = {}
        new_include_map = {}
        old_categories = list(self.map_categories)
        for idx, cat in enumerate(new_types):
            if cat in current_states:
                new_state[cat] = current_states[cat]
                new_include_map[cat] = include_map.get(cat, True)
            elif cat in saved_state:
                new_state[cat] = saved_state[cat]
                new_include_map[cat] = True
            elif idx < len(old_categories):
                # Rename auf gleicher Position -> alten State übernehmen
                old_cat = old_categories[idx]
                st = current_states.get(old_cat) or saved_state.get(old_cat)
                if st:
                    new_state[cat] = st
                    new_include_map[cat] = include_map.get(old_cat, True)
                else:
                    new_state[cat] = {"entries": [], "pair_mode": False, "use_subroles": False}
                    new_include_map[cat] = True
            else:
                # neuer Typ -> leere Liste
                new_state[cat] = {"entries": [], "pair_mode": False, "use_subroles": False}
                new_include_map[cat] = True

        self.map_categories = list(new_types)
        self._build_map_lists(new_state, include_map=new_include_map)

    def _rebuild_map_wheel(self):
        if getattr(self, "_map_rebuild_guard", False):
            return
        if self.current_mode != "maps":
            return
        combined: list[str] = []
        for _cat, wheel in getattr(self, "map_lists", {}).items():
            if not wheel.btn_include_in_all.isChecked():
                continue
            for entry in wheel._active_entries():
                name = entry.get("name", "").strip()
                if name:
                    combined.append(name)
        self._map_combined = combined
        if hasattr(self, "map_main"):
            # Override-Einträge nutzen, damit das zentrale Rad nur die kombinierten Maps zeigt
            self.map_main.set_override_entries([{"name": n, "subroles": [], "active": True} for n in combined])
        self._update_spin_all_enabled()

    def _load_map_state(self):
        if not hasattr(self, "map_lists"):
            return
        state = self._state_store.get_mode_state("maps") or {}
        for cat, wheel in self.map_lists.items():
            role_state = state.get(cat) or self._state_store.default_role_state(cat, "maps")
            wheel.load_entries(role_state.get("entries", []))
        self._rebuild_map_wheel()

    def _capture_map_state(self):
        if not hasattr(self, "map_lists"):
            return
        self._state_store.capture_mode_from_wheels("maps", self.map_lists)

    def _activate_map_mode(self):
        if hasattr(self, "mode_stack"):
            self.mode_stack.setCurrentIndex(1)
        self.hero_ban_active = False
        self.dps.set_override_entries(None)
        self.current_mode = "maps"
        self.btn_mode_players.setChecked(False)
        self.btn_mode_heroes.setChecked(False)
        self.btn_mode_heroban.setChecked(False)
        self.btn_mode_maps.setChecked(True)
        self._load_map_state()
        self._update_title()
        self._apply_mode_results(self._mode_key())
        self._update_spin_all_enabled()

    def _activate_role_modes(self):
        if hasattr(self, "mode_stack"):
            self.mode_stack.setCurrentIndex(0)


    def _on_mode_button_clicked(self, target: str):
        # Aktuelle Ergebnisse für den Modus merken, bevor wir wechseln
        self._snapshot_mode_results()
        if target == "maps":
            # Merk dir, welcher Rollen-Modus gerade in den Wheels steckt,
            # damit Map-Mode-Saves später nicht versehentlich den falschen Modus überschreiben.
            self.last_non_hero_mode = self.current_mode
            if self.hero_ban_active:
                self.hero_ban_active = False
                self.dps.set_override_entries(None)
                self._set_hero_ban_visuals(False)
            # vorherige Zustände sichern
            self._state_store.capture_mode_from_wheels(
                self.current_mode,
                {"Tank": self.tank, "Damage": self.dps, "Support": self.support},
                hero_ban_active=self.hero_ban_active,
            )
            self._capture_map_state()
            self._activate_map_mode()
            return

        # wenn wir aus dem Map-Mode zurückkommen, zuerst speichern
        if self.current_mode == "maps":
            self._capture_map_state()
        self._activate_role_modes()
        mode_manager.on_mode_button_clicked(self, target)

    def _update_title(self):
        if self.current_mode == "maps":
            text = i18n.t("app.title.map")
        else:
            text = i18n.t("app.title.main")
        self.title.setText(text)
        self.setWindowTitle(text)

    def _switch_language(self, lang: str):
        lang = lang if lang in i18n.SUPPORTED_LANGS else "de"
        if lang == getattr(self, "language", "de"):
            return
        self.language = lang
        self._apply_language()
        if not getattr(self, "_restoring_state", False):
            self._save_state()

    def _toggle_language(self):
        """Toggle between German and English via the single flag button."""
        next_lang = "en" if self.language == "de" else "de"
        self._switch_language(next_lang)

    def _retranslate_map_ui(self):
        if hasattr(self, "lbl_map_types"):
            self.lbl_map_types.setText(i18n.t("map.types"))
        if hasattr(self, "btn_edit_map_types"):
            self.btn_edit_map_types.setText(i18n.t("map.edit_types"))
        if hasattr(self, "_map_type_editor_title"):
            self._map_type_editor_title.setText(i18n.t("map.editor.title"))
        if hasattr(self, "_map_type_btn_add"):
            self._map_type_btn_add.setText(i18n.t("map.editor.add"))
        if hasattr(self, "_map_type_btn_del"):
            self._map_type_btn_del.setText(i18n.t("map.editor.delete"))
        if hasattr(self, "_map_type_btn_ok"):
            self._map_type_btn_ok.setText(i18n.t("map.editor.apply"))
        if hasattr(self, "_map_type_btn_cancel"):
            self._map_type_btn_cancel.setText(i18n.t("map.editor.cancel"))

    def _apply_language(self):
        i18n.set_language(self.language)
        if hasattr(self, "btn_language"):
            self.btn_language.setText(i18n.flag_for_language(self.language))
            tooltip = i18n.t("language.tooltip.de") if self.language == "de" else i18n.t("language.tooltip.en")
            self.btn_language.setToolTip(tooltip)
        self.lbl_mode.setText(i18n.t("label.mode"))
        self.btn_mode_players.setText(i18n.t("mode.players"))
        self.btn_mode_heroes.setText(i18n.t("mode.heroes"))
        self.btn_mode_heroban.setText(i18n.t("mode.hero_ban"))
        self.btn_mode_maps.setText(i18n.t("mode.maps"))
        self.lbl_volume_icon.setToolTip(i18n.t("volume.icon_tooltip"))
        self.volume_slider.setToolTip(i18n.t("volume.slider_tooltip"))
        self.btn_spin_all.setText(i18n.t("controls.spin_all"))
        self.btn_cancel_spin.setText(i18n.t("controls.cancel_spin"))
        self.lbl_anim_duration.setText(i18n.t("controls.anim_duration"))
        self.duration.setToolTip(i18n.t("controls.anim_duration_tooltip"))
        self._update_title()
        for w in (self.tank, self.dps, self.support):
            w.set_language(self.language)
        if getattr(self, "map_main", None):
            self.map_main.set_language(self.language)
            self.map_main.set_spin_button_text(i18n.t("wheel.spin_map"))
        if getattr(self, "map_lists", None):
            for w in self.map_lists.values():
                w.set_language(self.language)
                w.set_spin_button_text(i18n.t("wheel.spin_single_map"))
        self._retranslate_map_ui()
        if hasattr(self, "overlay"):
            self.overlay.set_language(self.language)
            # Flag auf dem Overlay aktualisieren
            self.overlay._apply_flag()
        self._update_summary_from_results()

    def _set_fixed_width_from_translations(self, widgets, keys, padding: int = 20, prefixes: list[str] | None = None):
        """Set min/max width so labels don't jump between languages."""
        if not isinstance(widgets, (list, tuple)):
            widgets = [widgets]
        prefixes = prefixes or [""]
        # Sammle alle Texte für alle Keys über alle Sprachen
        all_texts: list[str] = []
        for key in keys:
            entry = i18n.TRANSLATIONS.get(key, {})
            if isinstance(entry, dict):
                all_texts.extend([str(v) for v in entry.values()])
            elif entry:
                all_texts.append(str(entry))
        for widget in widgets:
            font = widget.font()
            fm = QtGui.QFontMetrics(font)
            max_w = 0
            for txt in all_texts:
                for pre in prefixes:
                    max_w = max(max_w, fm.horizontalAdvance(f"{pre}{txt}"))
            width = max_w + padding
            widget.setMinimumWidth(width)
            widget.setMaximumWidth(width)
    def _load_saved_state(self) -> dict:
        """
        Lädt den gespeicherten Zustand aus saved_state.json, falls vorhanden.
        Struktur:
        {
          "players": {"Tank": {...}, "Damage": {...}, "Support": {...}},
          "heroes":  {"Tank": {...}, "Damage": {...}, "Support": {...}},
          "maps": {...},
          "volume": int,
          "language": "de" | "en"   # fallback ist Englisch
        }
        """
        data = persistence.load_state(self._state_file)
        if isinstance(data, dict):
            return data
        return {}

    def _gather_state(self) -> dict:
        """
        Liest den aktuellen Zustand beider Modi aus.
        """
        mode_to_capture = self.current_mode
        if mode_to_capture == "maps":
            mode_to_capture = getattr(self, "last_non_hero_mode", "players") or "players"
            if mode_to_capture not in ("players", "heroes"):
                mode_to_capture = "players"
        self._state_store.capture_mode_from_wheels(
            mode_to_capture,
            {"Tank": self.tank, "Damage": self.dps, "Support": self.support},
            hero_ban_active=self.hero_ban_active if mode_to_capture == "heroes" else False,
        )
        if getattr(self, "map_lists", None):
            self._capture_map_state()
        state = self._state_store.to_saved(self.volume_slider.value())
        state["language"] = self.language
        return state

    def _update_hero_ban_wheel(self):
        """Delegiert an den Mode-Manager."""
        mode_manager.update_hero_ban_wheel(self)

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
        state = self._gather_state()
        persistence.save_state(self._state_file, state)
        self._sync_all_roles_to_server()
        if self.hero_ban_active:
            self._update_hero_ban_wheel()
    
    @QtCore.Slot(bool)
    def _on_mode_chosen(self, online: bool):
        self.online_mode = online
        self._set_controls_enabled(True)
        self._refresh_tooltip_caches()
        QtCore.QTimer.singleShot(150, self._refresh_tooltip_caches)
        QtCore.QTimer.singleShot(0, self._reset_hover_cache_under_cursor)

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
        pair_modes = {
            "Tank": getattr(self.tank, "pair_mode", False),
            "Damage": getattr(self.dps, "pair_mode", False),
            "Support": getattr(self.support, "pair_mode", False),
        }
        sync_service.send_spin_result(tank, damage, support, pair_modes)
        
    def _sync_all_roles_to_server(self):
        if not getattr(self, "online_mode", False):
            config.debug_print("Sync übersprungen: Offline-Modus.")
            return
        payload = [
            {"role": "Tank", "names": self.tank.get_current_names()},
            {"role": "Damage", "names": self.dps.get_current_names()},
            {"role": "Support", "names": self.support.get_current_names()},
        ]
        sync_service.sync_roles(payload)
