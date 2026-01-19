from pathlib import Path
import sys

from PySide6 import QtCore, QtGui, QtWidgets

import config
import i18n
from . import mode_manager, spin_service
from services import persistence, state_store, sync_service
from services.sound import SoundManager
from utils import flag_icons, theme as theme_util, ui_helpers
from view.overlay import ResultOverlay
from view.wheel_view import WheelView
from view.spin_mode_toggle import SpinModeToggle
from controller.map_ui import MapUI
from controller.map_mode import MapModeController
from controller.open_queue import OpenQueueController
from controller.player_list_panel import PlayerListPanelController
from controller.role_mode import RoleModeController
from view import style_helpers

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
        self.theme = saved.get("theme", "light") if isinstance(saved, dict) else "light"
        if self.theme not in theme_util.THEMES:
            self.theme = "light"

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
        self._pending_sync_payload: list[dict] | None = None

        # Timer für sanftere Sync-/Tooltip-Operationen
        self._sync_timer = QtCore.QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._flush_role_sync)
        self._tooltip_refresh_timer = QtCore.QTimer(self)
        self._tooltip_refresh_timer.setSingleShot(True)
        self._tooltip_refresh_timer.timeout.connect(self._run_tooltip_cache_refresh)
        self._tooltip_refresh_step = 80

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
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
        self.btn_language.setIconSize(QtCore.QSize(28, 20))
        self.btn_language.clicked.connect(self._toggle_language)
        self.btn_theme = QtWidgets.QToolButton()
        self.btn_theme.setAutoRaise(True)
        self.btn_theme.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_theme.setFixedSize(40, 32)
        self.btn_theme.setIconSize(QtCore.QSize(24, 24))
        self.btn_theme.clicked.connect(self._toggle_theme)
        vol_row.addWidget(self.lbl_volume_icon, 0, QtCore.Qt.AlignVCenter)
        vol_row.addWidget(self.volume_slider, 0, QtCore.Qt.AlignVCenter)
        vol_row.addSpacing(6)
        vol_row.addWidget(self.btn_language, 0, QtCore.Qt.AlignVCenter)
        vol_row.addSpacing(4)
        vol_row.addWidget(self.btn_theme, 0, QtCore.Qt.AlignVCenter)
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
        ui_helpers.set_fixed_width_from_translations(
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
        self.role_container = role_container
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
        self.role_mode = RoleModeController(self)

        grid.addWidget(self.tank, 0, 0)
        grid.addWidget(self.dps, 0, 1)
        grid.addWidget(self.support, 0, 2)
        self.btn_all_players = QtWidgets.QPushButton(i18n.t("players.list_button"))
        ui_helpers.set_fixed_width_from_translations([self.btn_all_players], ["players.list_button"], padding=40)
        self.btn_all_players.setFixedHeight(36)
        self.player_list_panel = PlayerListPanelController(self, self.btn_all_players)
        self.btn_all_players.clicked.connect(self.player_list_panel.toggle_panel)
        grid.addWidget(self.btn_all_players, 1, 0, QtCore.Qt.AlignLeft)
        # Basisbreiten nach dem ersten Layout ermitteln
        QtCore.QTimer.singleShot(0, self._capture_role_base_widths)

        # ----- Map-Mode-Container -----
        self._map_result_text = "–"
        self.map_ui = MapUI(self._state_store, self.language, self.theme, (self.tank, self.dps, self.support))
        self.map_mode = MapModeController(self)
        self.map_container = self.map_ui.container
        self.map_ui.stateChanged.connect(self._update_spin_all_enabled)
        self.map_ui.stateChanged.connect(self._save_state)
        self.map_ui.requestSpinCategory.connect(self.map_mode.spin_category)
        # Kompatibilitäts-Aliase, damit bestehende Logik funktioniert
        self.map_main = self.map_ui.map_main
        self.map_lists = self.map_ui.map_lists
        self.map_categories = self.map_ui.map_categories

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
        ui_helpers.set_fixed_width_from_translations([self.btn_spin_all], ["controls.spin_all"], padding=40)
        self.btn_spin_all.setFixedHeight(44)
        self.btn_spin_all.clicked.connect(self.spin_all)
        self.spin_mode_toggle = SpinModeToggle()
        self.spin_mode_toggle.valueChanged.connect(self._update_spin_all_enabled)
        controls.addStretch(1)
        self.lbl_anim_duration = QtWidgets.QLabel(i18n.t("controls.anim_duration"))
        controls.addWidget(self.lbl_anim_duration)
        self.duration.setFixedHeight(30)
        controls.addWidget(self.duration)
        controls.addWidget(self.spin_mode_toggle)
        controls.addWidget(self.btn_spin_all)
        self.btn_cancel_spin = QtWidgets.QPushButton(i18n.t("controls.cancel_spin"))
        ui_helpers.set_fixed_width_from_translations([self.btn_cancel_spin], ["controls.cancel_spin"], padding=40)
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
        self.open_queue = OpenQueueController(self)
        for w in (self.tank, self.dps, self.support):
            w.spun.connect(self._wheel_finished)
        if hasattr(self, "map_main"):
            self.map_main.spun.connect(self._wheel_finished)

        self.overlay = ResultOverlay(parent=central)
        self.overlay.hide()
        self.overlay.closed.connect(self._on_overlay_closed)
        self.overlay.languageToggleRequested.connect(self._toggle_language)
        self.overlay.disableResultsRequested.connect(self._on_overlay_disable_results)
        
        self.online_mode = False  # Standard
        self.overlay.modeChosen.connect(self._on_mode_chosen)
        self._pending_mode_choice: bool | None = None
        self._pending_language_toggle: str | None = None
        self._warmup_active = False
        self.installEventFilter(self)
        app = QtWidgets.QApplication.instance()
        if app:
            app.installEventFilter(self)

        # Direkt beim Start Modus wählen lassen
        self._set_controls_enabled(False)
        self.overlay.show_online_choice()
        # Buttons vorerst gesperrt lassen, erst nach Tooltip-Warmup freigeben
        QtCore.QTimer.singleShot(0, self._warmup_tooltips_initial)

        # JETZT: Save-Hooks anschließen
        for w in (self.tank, self.dps, self.support):
            w.stateChanged.connect(self._save_state)
            w.btn_include_in_all.toggled.connect(self._update_spin_all_enabled)
            w.stateChanged.connect(self._update_spin_all_enabled)
            w.stateChanged.connect(self._on_wheel_state_changed)
            w.btn_include_in_all.toggled.connect(self._on_role_include_toggled)
        if hasattr(self, "map_lists"):
            for w in self.map_lists.values():
                w.stateChanged.connect(self._save_state)
                w.btn_include_in_all.toggled.connect(self._save_state)
                w.btn_include_in_all.toggled.connect(self._update_spin_all_enabled)
                # Sicherstellen, dass Buttons aktiv bleiben (nicht wie disabled im UI aussehen)
                w.btn_local_spin.setEnabled(True)
                w.btn_include_in_all.setEnabled(True)

        # jetzt darf gespeichert werden
        self._restoring_state = False

        # Buttons initial updaten (nutzt schon include_in_all)
        self._update_spin_all_enabled()
        self._update_cancel_enabled()
        self._apply_mode_results(self._mode_key())
        self._apply_theme()
        self._apply_language()
        # Tooltips sofort erlauben (werden später noch einmal frisch berechnet)
        self._set_tooltips_ready(True)

    def _warmup_tooltips_initial(self):
        """Initial Cache/Tooltips vorbereiten und Online/Offline-Buttons freigeben."""
        # Erst alles sperren, dann die Caches zweimal aufbauen, damit das Dark-Theme-Repolish
        # erledigt ist, bevor die Buttons anklickbar werden.
        self._warmup_active = True
        self._pending_mode_choice = None
        self._pending_language_toggle = None
        self.overlay.set_choice_enabled(False)
        self.overlay.set_hover_blocked(True)
        self._set_language_buttons_enabled(False)
        # Während des Warmups keine Hover-Tooltips zulassen
        self._set_tooltips_ready(False)
        def _rebuild_tooltips():
            self._refresh_tooltip_caches()
            self._reset_hover_cache_under_cursor()
        _rebuild_tooltips()
        QtCore.QTimer.singleShot(220, _rebuild_tooltips)
        QtCore.QTimer.singleShot(620, _rebuild_tooltips)
        # Mehr Luft lassen, damit der erste Klick nicht vor dem Tooltip-Warmup passiert
        QtCore.QTimer.singleShot(2000, self._finish_warmup)

    def _finish_warmup(self):
        """Hebt den Warmup-Block auf; idempotent."""
        if not getattr(self, "_warmup_active", False):
            return
        self._warmup_active = False
        self.overlay.set_hover_blocked(False)
        self.overlay.set_choice_enabled(True)
        self._set_tooltips_ready(True)
        self._set_language_buttons_enabled(True)
        self._reset_hover_cache_under_cursor()
        if self._pending_mode_choice is not None:
            choice = self._pending_mode_choice
            self._pending_mode_choice = None
            self._apply_mode_choice(choice)
        if self._pending_language_toggle:
            lang = self._pending_language_toggle
            self._pending_language_toggle = None
            self._switch_language(lang)

    def _on_overlay_closed(self):
        self._set_controls_enabled(True)
        self.sound.stop_ding()
        if self.hero_ban_active:
            self._hero_ban_override_role = None
            self._update_hero_ban_wheel()
        # Tooltip/Truncation nach finalem Layout aktualisieren
        QtCore.QTimer.singleShot(0, self._refresh_tooltip_caches)
        QtCore.QTimer.singleShot(200, self._refresh_tooltip_caches)

    def _on_overlay_disable_results(self):
        last_view = getattr(self.overlay, "_last_view", {}) or {}
        if last_view.get("type") != "result":
            return
        data = last_view.get("data") or ()
        if len(data) != 3:
            return
        mapping = [(self.tank, data[0]), (self.dps, data[1]), (self.support, data[2])]
        names_to_remove: set[str] = set()
        for wheel, label in mapping:
            if hasattr(wheel, "result_label_names"):
                names_to_remove.update(wheel.result_label_names(label))
            elif isinstance(label, str) and label.strip():
                names_to_remove.add(label.strip())
        if not names_to_remove:
            return
        for wheel in (self.tank, self.dps, self.support):
            if hasattr(wheel, "deactivate_names"):
                wheel.deactivate_names(names_to_remove)

    def eventFilter(self, obj, event):
        # Nach längeren Pausen/Focus-Wechsel Tooltip-Caches auffrischen
        if event.type() in (
            QtCore.QEvent.FocusIn,
            QtCore.QEvent.WindowActivate,
            QtCore.QEvent.ApplicationActivate,
        ):
            self._refresh_tooltips_after_focus()
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if hasattr(self, "player_list_panel"):
                self.player_list_panel.maybe_close_on_click(obj, event)
        return super().eventFilter(obj, event)

    def _refresh_tooltips_after_focus(self):
        """Bringt Tooltip-Caches nach Fokuswechsel zurück, ohne zu blockieren."""
        self._refresh_tooltip_caches_async(delay_step_ms=50)
        QtCore.QTimer.singleShot(200, self._reset_hover_cache_under_cursor)
        if not getattr(self, "_warmup_active", False):
            self._set_tooltips_ready(True)


    def _apply_theme(self):
        """Apply the selected light/dark theme without freezing the UI."""
        theme = theme_util.get_theme(getattr(self, "theme", "light"))
        theme_util.apply_app_theme(theme)  # einmal zentral, danach in Scheiben
        tool_style = theme_util.tool_button_stylesheet(theme)

        # Schnelle/kleine Updates sofort
        if hasattr(self, "btn_language"):
            self.btn_language.setStyleSheet(tool_style)
        if hasattr(self, "btn_theme"):
            self.btn_theme.setStyleSheet(tool_style)
        self._update_theme_button_label()
        if hasattr(self, "summary"):
            self.summary.setStyleSheet(f"font-size:15px; color:{theme.muted_text}; margin:10px 0 6px 0;")
        if hasattr(self, "btn_spin_all"):
            style_helpers.style_primary_button(self.btn_spin_all, theme)
        if hasattr(self, "spin_mode_toggle"):
            self.spin_mode_toggle.apply_theme(theme)
        if hasattr(self, "btn_all_players"):
            style_helpers.style_primary_button(self.btn_all_players, theme)
        if hasattr(self, "btn_cancel_spin"):
            style_helpers.style_danger_button(self.btn_cancel_spin, theme)
        if hasattr(self, "player_list_panel"):
            self.player_list_panel.apply_theme()
        if hasattr(self, "overlay"):
            self.overlay.apply_theme(theme, tool_style)

        # Größere Widget-Mengen in kleinen Paketen aktualisieren
        targets = []
        for w in (getattr(self, "tank", None), getattr(self, "dps", None), getattr(self, "support", None)):
            if w and hasattr(w, "apply_theme"):
                targets.append(w)
        if hasattr(self, "map_ui"):
            self.map_ui.apply_theme(theme)
        # Map-spezifische Widgets IMMER stylen, damit ein späterer Moduswechsel nicht den alten Theme-Stand zeigt
        if hasattr(self, "map_main") and hasattr(self.map_main, "apply_theme"):
            targets.append(self.map_main)
        if hasattr(self, "map_lists"):
            for wheel in self.map_lists.values():
                if hasattr(wheel, "apply_theme"):
                    targets.append(wheel)

        step_ms = 15
        for idx, w in enumerate(targets):
            QtCore.QTimer.singleShot(idx * step_ms, lambda _w=w: _w.apply_theme(theme))

        total_delay = len(targets) * step_ms
        QtCore.QTimer.singleShot(total_delay, self._update_mode_button_styles)
        # Theme-Button wieder freigeben, falls er kurz deaktiviert wurde
        if hasattr(self, "btn_theme"):
            QtCore.QTimer.singleShot(total_delay + 40, lambda: self.btn_theme.setEnabled(True))

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
        if self.overlay and self.centralWidget():
            self.overlay.setGeometry(self.centralWidget().rect())
        if hasattr(self, "player_list_panel"):
            self.player_list_panel.on_resize()

    def _update_spin_all_enabled(self):
        """Aktiviere/Deaktiviere den 'Drehen'-Button je nach Auswahl."""
        open_names: list[str] | None = None
        if getattr(self, "hero_ban_active", False):
            any_selected = any(w.btn_include_in_all.isChecked() for w in (self.tank, self.dps, self.support))
            # In Hero-Ban zählen die effektiven Namen des zentralen Rads (inkl. Override).
            has_candidates = bool(self.dps.get_effective_wheel_names())
            self.btn_spin_all.setEnabled(any_selected and has_candidates and self.pending == 0)
        elif self.current_mode == "maps":
            any_selected = any(w.btn_include_in_all.isChecked() for w in getattr(self, "map_lists", {}).values())
            has_candidates = bool(self.map_ui.combined_names() if hasattr(self, "map_ui") else [])
            self.btn_spin_all.setEnabled(any_selected and has_candidates and self.pending == 0)
        elif self.open_queue.is_mode_active():
            slots = self.open_queue.slots()
            open_names = self.open_queue.names()
            has_candidates = slots > 0 and len(open_names) >= slots
            self.btn_spin_all.setEnabled(has_candidates and self.pending == 0)
        else:
            # Nur aktiv, wenn allgemein erlaubt UND mindestens ein Rad ausgewählt
            self.btn_spin_all.setEnabled(self.role_mode.can_spin_all())
        self._update_spin_mode_ui()
        if hasattr(self, "player_list_panel"):
            self.player_list_panel.update_button()
        self.open_queue.apply_preview(open_names)
        self._update_cancel_enabled()

    def _update_spin_mode_ui(self):
        if not hasattr(self, "spin_mode_toggle"):
            return
        allowed = self.open_queue.spin_mode_allowed()
        self.spin_mode_toggle.setVisible(allowed)
        if not allowed:
            self.spin_mode_toggle.setEnabled(False)
            return
        self.spin_mode_toggle.setEnabled(self.pending == 0)
        slots = self.open_queue.slots()
        self.spin_mode_toggle.set_texts(
            i18n.t("controls.spin_mode_role"),
            i18n.t("controls.spin_mode_open", count=slots),
        )

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
    def _refresh_tooltip_caches_async(self, delay_step_ms: int = 80):
        """
        Baut die Tooltip-Caches in kleinen Scheiben (per Timer) neu auf,
        damit der UI-Thread beim Online/Offline-Klick nicht blockiert.
        Mehrfachaufrufe werden kurz gesammelt, um die Render-Last zu drosseln.
        """
        step = max(0, int(delay_step_ms))
        self._tooltip_refresh_step = step
        timer = getattr(self, "_tooltip_refresh_timer", None)
        if timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._run_tooltip_cache_refresh)
            self._tooltip_refresh_timer = timer
        # Timer neu starten -> debounce
        timer.start(60)

    def _run_tooltip_cache_refresh(self):
        """Führt den eigentlichen Cache-Rebuild sequenziell aus."""
        wheels = [self.tank, self.dps, self.support]
        if getattr(self, "map_main", None):
            wheels.append(self.map_main)

        def rebuild_single(w):
            wheel = getattr(getattr(w, "view", None), "wheel", None)
            if wheel and hasattr(wheel, "_ensure_cache"):
                try:
                    wheel._cached = None
                    wheel._ensure_cache(force=True)
                except Exception:
                    pass

        step_ms = max(0, int(getattr(self, "_tooltip_refresh_step", 80)))
        for idx, w in enumerate(wheels):
            QtCore.QTimer.singleShot(idx * step_ms, lambda _w=w: rebuild_single(_w))
        # Am Ende Tooltips freigeben und Hover-Cache setzen
        total_delay = len(wheels) * step_ms + 40
        QtCore.QTimer.singleShot(total_delay, lambda: (self._set_tooltips_ready(True), self._reset_hover_cache_under_cursor()))

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
            if hasattr(self, "spin_mode_toggle"):
                self.spin_mode_toggle.setEnabled(False)
            if hasattr(self, "btn_all_players"):
                self.btn_all_players.setEnabled(False)
            if hasattr(self, "player_list_panel"):
                self.player_list_panel.hide_panel()
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
            self.map_mode.spin_all()
        elif self.open_queue.is_mode_active():
            spin_service.spin_open_queue(self)
        else:
            spin_service.spin_all(self)

    def spin_open_queue(self):
        """Zieht Spieler aus allen aktiven Listen ohne Rollenbindung."""
        if self.current_mode == "maps":
            return
        spin_service.spin_open_queue(self)
    def _spin_single(self, wheel: WheelView, mult: float = 1.0, hero_ban_override: bool = True):
        if self.current_mode == "maps":
            self.map_mode.spin_single()
        else:
            spin_service.spin_single(self, wheel, mult=mult, hero_ban_override=hero_ban_override)

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
                    self.map_mode.rebuild_wheel()
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
            if self.open_queue.spin_active():
                self.open_queue.restore_spin_overrides()
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
        if self.open_queue.spin_active():
            self.open_queue.restore_spin_overrides()
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

    def _activate_role_modes(self):
        if hasattr(self, "mode_stack"):
            self.mode_stack.setCurrentIndex(0)
        if hasattr(self, "player_list_panel"):
            self.player_list_panel.hide_panel()


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
            self.map_mode.capture_state()
            self.map_mode.activate_mode()
            return

        # wenn wir aus dem Map-Mode zurückkommen, zuerst speichern
        if self.current_mode == "maps":
            self.map_mode.capture_state()
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
        # Nach Sprachwechsel Label-Messungen aktualisieren, damit Tooltips weiter funktionieren
        self._set_tooltips_ready(False)
        self._refresh_tooltip_caches_async()
        # Wenn im Warmup die Sprache gewechselt wird, Warmup abschließen,
        # damit die Buttons nicht dauerhaft gesperrt bleiben.
        if getattr(self, "_warmup_active", False):
            self._finish_warmup()
        else:
            # Falls das Online/Offline-Overlay offen ist und Warmup schon vorbei war,
            # Aktivierung sicherstellen (Setzen der Sprache ruft show_online_choice erneut auf).
            last_view = getattr(self.overlay, "_last_view", {}) or {}
            if last_view.get("type") == "online_choice":
                self.overlay.set_choice_enabled(True)
                self.overlay.set_hover_blocked(False)
        if not getattr(self, "_restoring_state", False):
            self._save_state()

    def _toggle_language(self):
        """Toggle between German and English via the single flag button."""
        next_lang = "en" if self.language == "de" else "de"
        # Wenn Warmup läuft, den Toggle vormerken und Buttons deaktivieren
        if getattr(self, "_warmup_active", False):
            self._pending_language_toggle = next_lang
            self._set_language_buttons_enabled(False)
            return
        self._switch_language(next_lang)

    def _set_language_buttons_enabled(self, enabled: bool):
        """Aktiviert/Deaktiviert sowohl das Haupt-Sprachicon als auch das Overlay-Icon."""
        if hasattr(self, "btn_language"):
            self.btn_language.setEnabled(enabled)
        if hasattr(self, "overlay") and hasattr(self.overlay, "btn_language"):
            self.overlay.btn_language.setEnabled(enabled)

    def _toggle_theme(self):
        """Switch between light and dark mode."""
        if hasattr(self, "btn_theme"):
            self.btn_theme.setEnabled(False)
        self.theme = "dark" if getattr(self, "theme", "light") == "light" else "light"
        self._apply_theme()
        if not getattr(self, "_restoring_state", False):
            self._save_state()

    def _update_theme_button_label(self):
        """Update text/tooltip of the theme toggle."""
        if not hasattr(self, "btn_theme"):
            return
        is_dark = getattr(self, "theme", "light") == "dark"
        self.btn_theme.setText("☀️" if is_dark else "🌙")
        tooltip = i18n.t("theme.toggle.to_light") if is_dark else i18n.t("theme.toggle.to_dark")
        self.btn_theme.setToolTip(tooltip)

    def _apply_language(self):
        i18n.set_language(self.language)
        if hasattr(self, "btn_language"):
            self.btn_language.setIcon(flag_icons.icon_for_language(self.language))
            self.btn_language.setText("")  # avoid emoji fallback on Windows
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
        if hasattr(self, "btn_all_players"):
            self.btn_all_players.setText(i18n.t("players.list_button"))
            ui_helpers.set_fixed_width_from_translations([self.btn_all_players], ["players.list_button"], padding=40)
        if hasattr(self, "player_list_panel"):
            self.player_list_panel.set_language(self.language)
        self._update_title()
        for w in (self.tank, self.dps, self.support):
            w.set_language(self.language)
        if hasattr(self, "map_mode"):
            self.map_mode.retranslate_ui()
        if hasattr(self, "overlay"):
            self.overlay.set_language(self.language)
            # Flag auf dem Overlay aktualisieren
            self.overlay._apply_flag()
        self._update_theme_button_label()
        self._update_spin_mode_ui()
        self._update_summary_from_results()

    def _load_saved_state(self) -> dict:
        """
        Lädt den gespeicherten Zustand aus saved_state.json, falls vorhanden.
        Struktur:
        {
          "players": {"Tank": {...}, "Damage": {...}, "Support": {...}},
          "heroes":  {"Tank": {...}, "Damage": {...}, "Support": {...}},
          "maps": {...},
          "volume": int,
          "language": "de" | "en",   # fallback ist Englisch
          "theme": "light" | "dark"
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
            self.map_mode.capture_state()
        state = self._state_store.to_saved(self.volume_slider.value())
        state["language"] = self.language
        state["theme"] = self.theme
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
        # Wenn Warmup noch läuft, Klick merken und nach Warmup ausführen
        if getattr(self, "_warmup_active", False):
            self._pending_mode_choice = online
            self.overlay.set_choice_enabled(False)
            return
        self._apply_mode_choice(online)

    def _apply_mode_choice(self, online: bool):
        self.online_mode = online
        self._set_controls_enabled(True)
        # Tooltip-Caches ohne spürbare Blockade asynchron neu aufbauen
        self._set_tooltips_ready(False)
        self._refresh_tooltip_caches_async()
        # Nach dem Klick einen „Refokus“ durchführen, damit Hover/Tooltips sofort wieder greifen
        QtCore.QTimer.singleShot(300, self._refresh_tooltips_after_focus)

        if self.online_mode:
            config.debug_print("Online-Modus aktiv.")
        else:
            config.debug_print("Offline-Modus aktiv.")
        # Sync ggf. neu einplanen oder abbrechen
        self._sync_all_roles_to_server()
            
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
            self._pending_sync_payload = None
            if hasattr(self, "_sync_timer") and self._sync_timer.isActive():
                self._sync_timer.stop()
            return
        payload = [
            {"role": "Tank", "names": self.tank.get_current_names()},
            {"role": "Damage", "names": self.dps.get_current_names()},
            {"role": "Support", "names": self.support.get_current_names()},
        ]
        self._pending_sync_payload = payload
        if hasattr(self, "_sync_timer") and self._sync_timer is not None:
            # kurze Verzögerung, um schnelle State-Änderungen zu bündeln
            self._sync_timer.start(200)
        else:
            sync_service.sync_roles(payload)

    def _flush_role_sync(self):
        """Sendet den letzten vorbereiteten Sync-Payload (debounced)."""
        if not getattr(self, "online_mode", False):
            self._pending_sync_payload = None
            return
        payload = getattr(self, "_pending_sync_payload", None)
        self._pending_sync_payload = None
        if payload:
            sync_service.sync_roles(payload)
