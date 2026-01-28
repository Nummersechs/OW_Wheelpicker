from pathlib import Path
import sys
import time

from PySide6 import QtCore, QtGui, QtWidgets

import config
import i18n
from . import mode_manager, spin_service
from services import persistence, state_store
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
from controller.state_sync import StateSyncController
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
        saved = StateSyncController.load_saved_state(self._state_file)
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
        self.state_sync = StateSyncController(self, self._state_file)
        self._mode_choice_locked = False
        self._closing = False
        self._choice_shown_at: float | None = None
        self._post_choice_delay_ms = 350
        self._post_choice_step_ms = 90
        self._post_choice_warmup_step_ms = 40
        self._post_choice_timer = QtCore.QTimer(self)
        self._post_choice_timer.setSingleShot(True)
        self._post_choice_timer.timeout.connect(self._run_post_choice_init)
        self._theme_heavy_pending = False
        self._language_heavy_pending = False
        self._post_choice_init_done = False
        self._stack_switching = False
        self._stack_switch_timer = QtCore.QTimer(self)
        self._stack_switch_timer.setSingleShot(True)
        self._stack_switch_timer.timeout.connect(self._clear_stack_switching)
        self._map_init_in_progress = False
        self._map_lists_ready = False
        self._map_prebuild_in_progress = False
        self._focus_trace_enabled = bool(getattr(config, "TRACE_FOCUS", False))
        self._focus_trace_count = 0
        self._focus_trace_max_events = int(getattr(config, "FOCUS_TRACE_MAX_EVENTS", 120))
        self._focus_trace_until = time.monotonic() + float(getattr(config, "FOCUS_TRACE_DURATION_S", 3.0))
        self._focus_trace_window_events = bool(getattr(config, "FOCUS_TRACE_WINDOW_EVENTS", True))
        self._focus_trace_windows_only = bool(getattr(config, "FOCUS_TRACE_WINDOWS_ONLY", False))
        self._focus_trace_snapshot_interval_ms = int(getattr(config, "FOCUS_TRACE_SNAPSHOT_INTERVAL_MS", 0))
        self._focus_trace_snapshot_remaining = int(getattr(config, "FOCUS_TRACE_SNAPSHOT_COUNT", 0))
        self._focus_trace_snapshot_timer: QtCore.QTimer | None = None
        self._focus_trace_window_handle_installed = False
        self._focus_trace_file = self._state_dir / "focus_trace.log"
        if self._focus_trace_enabled:
            try:
                self._focus_trace_file.write_text("", encoding="utf-8")
            except Exception:
                pass
        self._trace_enabled = bool(getattr(config, "TRACE_FLOW", False) or getattr(config, "DEBUG", False))
        self._trace_file = self._state_dir / "flow_trace.log"
        if self._trace_enabled:
            self._trace_event("startup")
        if getattr(config, "DISABLE_TOOLTIPS", False):
            try:
                QtWidgets.QToolTip.setEnabled(False)
            except Exception:
                pass

        # Timer für sanftere Sync-/Tooltip-Operationen
        self._tooltip_refresh_timer = QtCore.QTimer(self)
        self._tooltip_refresh_timer.setSingleShot(True)
        self._tooltip_refresh_timer.timeout.connect(self._run_tooltip_cache_refresh)
        self._tooltip_refresh_step = 80
        central, root = self._build_root()
        self._build_header(root, saved)
        self._build_mode_switcher(root)
        role_container = self._build_role_container()
        self._build_map_container()
        self._build_mode_stack(root, role_container)
        self._apply_initial_mode_state()
        self._wire_spin_signals()
        self._build_controls(root)
        self._build_summary(root)
        self._init_spin_state()
        self._build_overlay(central)
        self._install_event_filters()
        self._show_mode_choice()
        self._connect_state_signals()
        self._finalize_startup()
        self._apply_focus_policy_defaults()
        self._schedule_clear_focus()

    def _build_root(self) -> tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        return central, root

    def _build_header(self, root: QtWidgets.QVBoxLayout, saved: dict) -> None:
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

    def _build_mode_switcher(self, root: QtWidgets.QVBoxLayout) -> None:
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

    def _build_role_container(self) -> QtWidgets.QWidget:
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
        return role_container

    def _build_map_container(self) -> None:
        # ----- Map-Mode-Container -----
        self._map_result_text = "–"
        self._map_initialized = False
        self.map_mode = MapModeController(self)
        self.map_container = QtWidgets.QWidget()
        self.map_container.setFocusPolicy(QtCore.Qt.NoFocus)
        self._map_container_layout = QtWidgets.QVBoxLayout(self.map_container)
        self._map_container_layout.setContentsMargins(0, 0, 0, 0)
        self._map_container_layout.setSpacing(0)

    def _ensure_map_ui(self) -> None:
        """Build map UI lazily to keep startup fast."""
        self._trace_event("ensure_map_ui:start", map_initialized=getattr(self, "_map_initialized", False))
        if getattr(self, "_map_initialized", False):
            return
        self._map_init_in_progress = True
        try:
            self._map_lists_ready = False
            self.map_ui = MapUI(
                self._state_store,
                self.language,
                self.theme,
                (self.tank, self.dps, self.support),
                defer_lists=True,
            )
            self.map_ui.listsBuilt.connect(self._on_map_lists_ready)
            self._map_container_layout.addWidget(self.map_ui.container)
            self.map_ui.stateChanged.connect(self._update_spin_all_enabled)
            self.map_ui.stateChanged.connect(self.state_sync.save_state)
            self.map_ui.requestSpinCategory.connect(self.map_mode.spin_category)
            # Kompatibilitäts-Aliase, damit bestehende Logik funktioniert
            self.map_main = self.map_ui.map_main
            self.map_lists = self.map_ui.map_lists
            self.map_ui.set_language(self.language)
            self.map_ui.apply_theme(theme_util.get_theme(self.theme))
            # Map-Mode soll keinen Fokus ziehen
            try:
                self.map_ui.container.setFocusPolicy(QtCore.Qt.NoFocus)
            except Exception:
                pass
            for w in (self.map_ui.map_main, *self.map_ui.map_lists.values()):
                try:
                    w.setFocusPolicy(QtCore.Qt.NoFocus)
                except Exception:
                    pass
                view = getattr(w, "view", None)
                if view:
                    try:
                        view.setFocusPolicy(QtCore.Qt.NoFocus)
                    except Exception:
                        pass
            self._map_initialized = True
            self._trace_event("ensure_map_ui:done")
            self._apply_focus_policy_defaults()
        finally:
            self._map_init_in_progress = False

    def _build_mode_stack(self, root: QtWidgets.QVBoxLayout, role_container: QtWidgets.QWidget) -> None:
        # ----- Stacked Content -----
        self.mode_stack = QtWidgets.QStackedLayout()
        self.mode_stack.addWidget(role_container)  # index 0
        self.mode_stack.addWidget(self.map_container)  # index 1
        root.addLayout(self.mode_stack, 1)

    def _apply_initial_mode_state(self) -> None:
        # Aktiven Modus vollständig anwenden (Einträge, Toggles etc.)
        self.btn_mode_players.setChecked(self.current_mode == "players")
        self.btn_mode_heroes.setChecked(self.current_mode == "heroes")
        self.btn_mode_heroban.setChecked(False)
        self._update_mode_button_styles()
        self._load_mode_into_wheels(self.current_mode)

    def _wire_spin_signals(self) -> None:
        # Spin-Signale
        self.tank.request_spin.connect(lambda: self._spin_single(self.tank, 1.00))
        self.dps.request_spin.connect(lambda: self._spin_single(self.dps, 1.10))
        self.support.request_spin.connect(lambda: self._spin_single(self.support, 1.20))

    def _build_controls(self, root: QtWidgets.QVBoxLayout) -> None:
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

    def _build_summary(self, root: QtWidgets.QVBoxLayout) -> None:
        self.summary = QtWidgets.QLabel("")
        self.summary.setAlignment(QtCore.Qt.AlignCenter)
        self.summary.setStyleSheet("font-size:15px; color:#333; margin:10px 0 6px 0;")
        root.addWidget(self.summary)

    def _init_spin_state(self) -> None:
        self.pending = 0
        self._result_sent_this_spin = False
        self._last_results_snapshot: dict | None = None
        self.open_queue = OpenQueueController(self)
        for w in (self.tank, self.dps, self.support):
            w.spun.connect(self._wheel_finished)
        if hasattr(self, "map_main"):
            self.map_main.spun.connect(self._wheel_finished)

    def _build_overlay(self, central: QtWidgets.QWidget) -> None:
        self.overlay = ResultOverlay(parent=central)
        self.overlay.hide()
        self.overlay.closed.connect(self._on_overlay_closed)
        self.overlay.languageToggleRequested.connect(self._toggle_language)
        self.overlay.disableResultsRequested.connect(self._on_overlay_disable_results)

        self.online_mode = False  # Standard
        self.overlay.modeChosen.connect(self._on_mode_chosen)

    def _install_event_filters(self) -> None:
        self.installEventFilter(self)
        app = QtWidgets.QApplication.instance()
        if app:
            app.installEventFilter(self)
            if getattr(self, "_focus_trace_enabled", False):
                try:
                    app.focusChanged.connect(self._trace_focus_signal)
                except Exception:
                    pass
                try:
                    QtGui.QGuiApplication.applicationStateChanged.connect(self._trace_app_state)
                except Exception:
                    pass
                try:
                    QtGui.QGuiApplication.focusWindowChanged.connect(self._trace_focus_window_signal)
                except Exception:
                    pass
                if self._focus_trace_snapshot_interval_ms > 0 and self._focus_trace_snapshot_remaining > 0:
                    QtCore.QTimer.singleShot(0, self._start_focus_snapshots)

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if not getattr(self, "_focus_trace_enabled", False):
            return
        self._install_window_handle_filter()

    def _install_window_handle_filter(self) -> None:
        if self._focus_trace_window_handle_installed:
            return
        try:
            handle = self.windowHandle()
        except Exception:
            handle = None
        if handle is None:
            return
        try:
            handle.installEventFilter(self)
            self._focus_trace_window_handle_installed = True
        except Exception:
            pass

    def _start_focus_snapshots(self) -> None:
        if not getattr(self, "_focus_trace_enabled", False):
            return
        if self._focus_trace_snapshot_remaining <= 0:
            return
        if self._focus_trace_snapshot_timer is None:
            self._focus_trace_snapshot_timer = QtCore.QTimer(self)
            self._focus_trace_snapshot_timer.timeout.connect(self._trace_window_snapshot)
        self._focus_trace_snapshot_timer.start(max(40, self._focus_trace_snapshot_interval_ms))

    def _show_mode_choice(self) -> None:
        """Direkt beim Start Modus wählen lassen."""
        self._set_controls_enabled(False)
        self._set_heavy_ui_updates_enabled(False)
        self.overlay.show_online_choice()
        self._choice_shown_at = time.monotonic()
        self._trace_event("show_mode_choice")

    def _connect_state_signals(self) -> None:
        # JETZT: Save-Hooks anschließen
        for w in (self.tank, self.dps, self.support):
            w.stateChanged.connect(self.state_sync.save_state)
            w.btn_include_in_all.toggled.connect(self._update_spin_all_enabled)
            w.stateChanged.connect(self._update_spin_all_enabled)
            w.stateChanged.connect(self._on_wheel_state_changed)
            w.btn_include_in_all.toggled.connect(self._on_role_include_toggled)
        if hasattr(self, "map_lists"):
            for w in self.map_lists.values():
                w.stateChanged.connect(self.state_sync.save_state)
                w.btn_include_in_all.toggled.connect(self.state_sync.save_state)
                w.btn_include_in_all.toggled.connect(self._update_spin_all_enabled)
                # Sicherstellen, dass Buttons aktiv bleiben (nicht wie disabled im UI aussehen)
                w.btn_local_spin.setEnabled(True)
                w.btn_include_in_all.setEnabled(True)

    def _finalize_startup(self) -> None:
        # jetzt darf gespeichert werden
        self._restoring_state = False

        # Buttons initial updaten (nutzt schon include_in_all)
        self._update_spin_all_enabled()
        self._update_cancel_enabled()
        self._apply_mode_results(self._mode_key())
        # Heavy parts (wheel styling, full wheel retranslate) erst nach Mode-Choice
        self._apply_theme(defer_heavy=True)
        self._apply_language(defer_heavy=True)
        # Tooltips sofort erlauben (werden später noch einmal frisch berechnet)
        self._set_tooltips_ready(True)

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
        if getattr(self, "_focus_trace_enabled", False):
            self._trace_focus_event(obj, event)
        if getattr(self, "_closing", False):
            return super().eventFilter(obj, event)
        if self._overlay_choice_active():
            return super().eventFilter(obj, event)
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if hasattr(self, "player_list_panel"):
                self.player_list_panel.maybe_close_on_click(obj, event)
        return super().eventFilter(obj, event)

    def _event_type_name(self, etype: int) -> str:
        try:
            return QtCore.QEvent.Type(etype).name  # type: ignore[attr-defined]
        except Exception:
            return str(etype)

    def _trace_focus_signal(self, old, new) -> None:
        if not getattr(self, "_focus_trace_enabled", False):
            return
        try:
            now = time.monotonic()
            if now > getattr(self, "_focus_trace_until", 0):
                self._focus_trace_enabled = False
                return
            if self._focus_trace_count >= getattr(self, "_focus_trace_max_events", 0):
                self._focus_trace_enabled = False
                return
            old_name = type(old).__name__ if old is not None else None
            new_name = type(new).__name__ if new is not None else None
            old_obj = old.objectName() if old is not None else None
            new_obj = new.objectName() if new is not None else None
            line = (
                f"t={round(now, 3)} | signal=focusChanged | old={old_name} | old_name={old_obj} | "
                f"new={new_name} | new_name={new_obj}"
            )
            with self._focus_trace_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._focus_trace_count += 1
        except Exception:
            pass

    def _trace_focus_window_signal(self, win) -> None:
        if not getattr(self, "_focus_trace_enabled", False):
            return
        try:
            now = time.monotonic()
            if now > getattr(self, "_focus_trace_until", 0):
                self._focus_trace_enabled = False
                return
            if self._focus_trace_count >= getattr(self, "_focus_trace_max_events", 0):
                self._focus_trace_enabled = False
                return
            win_name = type(win).__name__ if win is not None else None
            win_obj = win.objectName() if win is not None else None
            try:
                win_title = win.title() if win is not None else None
            except Exception:
                win_title = None
            is_active = None
            is_visible = None
            window_state = None
            flags = None
            if isinstance(win, QtGui.QWindow):
                try:
                    is_active = win.isActive()
                    is_visible = win.isVisible()
                    window_state = int(win.windowState())
                    flags = int(win.flags())
                except Exception:
                    pass
            line = (
                f"t={round(now, 3)} | signal=focusWindowChanged | win={win_name} | win_name={win_obj} | "
                f"title={win_title} | active={is_active} | visible={is_visible} | "
                f"window_state={window_state} | flags={flags}"
            )
            with self._focus_trace_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._focus_trace_count += 1
        except Exception:
            pass

    def _trace_app_state(self, state) -> None:
        if not getattr(self, "_focus_trace_enabled", False):
            return
        try:
            now = time.monotonic()
            if now > getattr(self, "_focus_trace_until", 0):
                self._focus_trace_enabled = False
                return
            if self._focus_trace_count >= getattr(self, "_focus_trace_max_events", 0):
                self._focus_trace_enabled = False
                return
            line = f"t={round(now, 3)} | signal=appState | state={state}"
            with self._focus_trace_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._focus_trace_count += 1
        except Exception:
            pass

    def _trace_window_snapshot(self) -> None:
        if not getattr(self, "_focus_trace_enabled", False):
            return
        try:
            now = time.monotonic()
            if now > getattr(self, "_focus_trace_until", 0):
                self._focus_trace_enabled = False
                return
            if self._focus_trace_count >= getattr(self, "_focus_trace_max_events", 0):
                self._focus_trace_enabled = False
                return
            app = QtGui.QGuiApplication.instance()
            windows = []
            if app:
                for win in app.allWindows():
                    try:
                        info = {
                            "type": type(win).__name__,
                            "title": win.title(),
                            "name": win.objectName(),
                            "visible": win.isVisible(),
                            "active": win.isActive(),
                            "state": int(win.windowState()),
                            "flags": int(win.flags()),
                        }
                    except Exception:
                        continue
                    windows.append(info)
            line = f"t={round(now, 3)} | snapshot=windows | data={windows}"
            with self._focus_trace_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._focus_trace_count += 1
            self._focus_trace_snapshot_remaining -= 1
            if self._focus_trace_snapshot_remaining <= 0 and self._focus_trace_snapshot_timer:
                self._focus_trace_snapshot_timer.stop()
        except Exception:
            pass

    def _trace_focus_event(self, obj, event) -> None:
        if not getattr(self, "_focus_trace_enabled", False):
            return
        try:
            now = time.monotonic()
            if now > getattr(self, "_focus_trace_until", 0):
                self._focus_trace_enabled = False
                return
            if self._focus_trace_count >= getattr(self, "_focus_trace_max_events", 0):
                self._focus_trace_enabled = False
                return
            etype = int(event.type())
            focus_events = (
                QtCore.QEvent.FocusIn,
                QtCore.QEvent.FocusOut,
                QtCore.QEvent.WindowActivate,
                QtCore.QEvent.WindowDeactivate,
                QtCore.QEvent.ApplicationActivate,
                QtCore.QEvent.ApplicationDeactivate,
            )
            window_events = (
                QtCore.QEvent.Show,
                QtCore.QEvent.Hide,
                QtCore.QEvent.ShowToParent,
                QtCore.QEvent.HideToParent,
                QtCore.QEvent.WindowStateChange,
                QtCore.QEvent.ActivationChange,
                QtCore.QEvent.Move,
                QtCore.QEvent.Resize,
            )
            if etype not in focus_events:
                if not self._focus_trace_window_events or etype not in window_events:
                    return
            app = QtWidgets.QApplication.instance()
            focus_widget = app.focusWidget() if app else None
            focus_name = type(focus_widget).__name__ if focus_widget is not None else None
            focus_obj = focus_widget.objectName() if focus_widget is not None else None
            obj_name = obj.objectName() if hasattr(obj, "objectName") else None
            obj_type = type(obj).__name__ if obj is not None else None
            is_window = False
            is_visible = None
            is_active = None
            window_state = None
            if isinstance(obj, QtWidgets.QWidget):
                try:
                    is_window = obj.isWindow()
                    is_visible = obj.isVisible()
                    is_active = obj.isActiveWindow()
                    window_state = int(obj.windowState())
                except Exception:
                    pass
            elif isinstance(obj, QtGui.QWindow):
                try:
                    is_window = True
                    is_visible = obj.isVisible()
                    is_active = obj.isActive()
                    window_state = int(obj.windowState())
                except Exception:
                    pass
            if getattr(self, "_focus_trace_windows_only", False) and not is_window:
                return
            text = None
            if hasattr(obj, "text"):
                try:
                    text = obj.text()
                except Exception:
                    text = None
            line = (
                f"t={round(now, 3)} | etype={etype} | etype_name={self._event_type_name(etype)} | "
                f"obj={obj_type} | obj_name={obj_name} | obj_text={text} | "
                f"is_window={is_window} | is_visible={is_visible} | is_active={is_active} | "
                f"window_state={window_state} | focus={focus_name} | focus_name={focus_obj}"
            )
            with self._focus_trace_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            self._focus_trace_count += 1
        except Exception:
            pass

    def _apply_focus_policy_defaults(self) -> None:
        """Avoid automatic focus on startup by forcing ClickFocus for focusable widgets."""
        for w in self.findChildren(QtWidgets.QWidget):
            try:
                policy = w.focusPolicy()
            except Exception:
                continue
            # Don't allow buttons to grab focus on activation (prevents startup refocus flash).
            if isinstance(w, QtWidgets.QAbstractButton):
                try:
                    w.setFocusPolicy(QtCore.Qt.NoFocus)
                except Exception:
                    pass
                continue
            if policy == QtCore.Qt.NoFocus:
                continue
            if policy in (QtCore.Qt.TabFocus, QtCore.Qt.StrongFocus):
                try:
                    w.setFocusPolicy(QtCore.Qt.ClickFocus)
                except Exception:
                    pass

    def _schedule_clear_focus(self) -> None:
        """Clear any automatic focus after startup to avoid refocus flicker."""
        QtCore.QTimer.singleShot(0, self._clear_focus_now)
        QtCore.QTimer.singleShot(150, self._clear_focus_now)
        QtCore.QTimer.singleShot(400, self._clear_focus_now)

    def _clear_focus_now(self) -> None:
        try:
            app = QtWidgets.QApplication.instance()
            if app:
                fw = app.focusWidget()
                if fw:
                    fw.clearFocus()
        except Exception:
            pass
        try:
            self.clearFocus()
        except Exception:
            pass

    def _refresh_hover_under_cursor(self):
        """Trigger a hover refresh for widgets that just became enabled."""
        if getattr(self, "_closing", False):
            return
        if self._overlay_choice_active():
            return
        # Hover-Refocus deaktiviert
        return

    def _refresh_hover_state(self):
        """Normalize hover/tooltips after enable/disable transitions."""
        return

    def _ensure_hover_cache(self, ready: bool | None = None, refresh_hover: bool = False) -> None:
        """Ensure hover caches exist and optionally refresh hover or ready state."""
        if ready is not None:
            self._set_tooltips_ready(ready)
        self._reset_hover_cache_under_cursor()
        if refresh_hover:
            QtCore.QTimer.singleShot(0, self._refresh_hover_under_cursor)

    def _apply_theme(self, defer_heavy: bool = False):
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

        self._theme_heavy_pending = bool(defer_heavy)
        if defer_heavy:
            return
        self._apply_theme_heavy(theme, step_ms=15)

    def _apply_theme_heavy(self, theme: theme_util.Theme, step_ms: int = 15):
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

        step_ms = max(0, int(step_ms))
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
        if getattr(self, "_closing", False):
            return
        if self._overlay_choice_active():
            return
        self._trace_event("refresh_tooltip_caches:sync")
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
        if getattr(self, "_closing", False):
            return
        if self._overlay_choice_active():
            return
        self._trace_event("refresh_tooltip_caches:async", step_ms=delay_step_ms)
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
        if getattr(self, "_closing", False):
            return
        if self._overlay_choice_active():
            return
        if getattr(self, "_stack_switching", False):
            self._trace_event("run_tooltip_cache_refresh:defer", reason="stack_switching")
            timer = getattr(self, "_tooltip_refresh_timer", None)
            if timer is not None:
                timer.start(80)
            return
        self._trace_event("run_tooltip_cache_refresh")
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
        QtCore.QTimer.singleShot(total_delay, lambda: self._ensure_hover_cache(ready=True))

    def _reset_hover_cache_under_cursor(self):
        """Stellt sicher, dass Tooltip-Caches vorhanden sind, ohne Voll-Rebuild zu erzwingen."""
        for w in (self.tank, self.dps, self.support, getattr(self, "map_main", None)):
            if not w:
                continue
            wheel = getattr(getattr(w, "view", None), "wheel", None)
            if wheel and hasattr(wheel, "_ensure_cache") and hasattr(wheel, "_needs_tooltip_runtime"):
                try:
                    wheel._ensure_cache(force=False)
                except Exception:
                    pass

    def _set_tooltips_ready(self, ready: bool = True):
        """Setzt das Tooltip-Ready-Flag für alle Räder."""
        if getattr(self, "_closing", False):
            return
        if self._overlay_choice_active():
            return
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
        # Kein automatischer Hover-Refresh beim Aktivieren
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
            if self.map_mode.handle_spin_finished():
                return
            else:
                t = self.tank.get_result_value() or "–"
                d = self.dps.get_result_value() or "–"
                s = self.support.get_result_value() or "–"

                self.summary.setText(i18n.t("summary.team", tank=t, dps=d, sup=s))
                self.overlay.show_result(t, d, s)

                # Nur noch EIN Request pro abgeschlossenem Spin
                self.state_sync.send_spin_result(t, d, s)
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
            self.state_sync.save_state()
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
        self._trace_event("mode_button_clicked", target=target)
        if not self._post_choice_init_done and not self._overlay_choice_active():
            self._ensure_post_choice_ready()
        if target == "maps" and not getattr(self, "_map_lists_ready", False):
            self._trace_event("mode_switch_deferred", target=target)
            self._set_map_button_enabled(False)
            return
        # Aktuelle Ergebnisse für den Modus merken, bevor wir wechseln
        self._snapshot_mode_results()
        if target == "maps":
            self._ensure_map_ui()
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
            self._sync_mode_stack()
            self._trace_event("mode_switch:maps_done")
            return

        # wenn wir aus dem Map-Mode zurückkommen, zuerst speichern
        if self.current_mode == "maps":
            self.map_mode.capture_state()
            if hasattr(self, "map_ui"):
                self.map_ui.set_active(False)
        self._activate_role_modes()
        mode_manager.on_mode_button_clicked(self, target)
        self._sync_mode_stack()
        self._trace_event("mode_switch:roles_done", target=target)

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
        self._trace_event("switch_language", lang=lang)
        self.language = lang
        self._apply_language()
        # Nach Sprachwechsel Label-Messungen aktualisieren, damit Tooltips weiter funktionieren
        self._set_tooltips_ready(False)
        self._refresh_tooltip_caches_async()
        # Falls das Online/Offline-Overlay offen ist, Aktivierung sicherstellen
        last_view = getattr(self.overlay, "_last_view", {}) or {}
        if last_view.get("type") == "online_choice":
            self.overlay.set_choice_enabled(True)
        if not getattr(self, "_restoring_state", False):
            self.state_sync.save_state()

    def _toggle_language(self):
        """Toggle between German and English via the single flag button."""
        next_lang = "en" if self.language == "de" else "de"
        self._switch_language(next_lang)

    def _toggle_theme(self):
        """Switch between light and dark mode."""
        if hasattr(self, "btn_theme"):
            self.btn_theme.setEnabled(False)
        self.theme = "dark" if getattr(self, "theme", "light") == "light" else "light"
        self._apply_theme()
        if not getattr(self, "_restoring_state", False):
            self.state_sync.save_state()

    def _update_theme_button_label(self):
        """Update text/tooltip of the theme toggle."""
        if not hasattr(self, "btn_theme"):
            return
        is_dark = getattr(self, "theme", "light") == "dark"
        self.btn_theme.setText("☀️" if is_dark else "🌙")
        tooltip = i18n.t("theme.toggle.to_light") if is_dark else i18n.t("theme.toggle.to_dark")
        self.btn_theme.setToolTip(tooltip)

    def _apply_language(self, defer_heavy: bool = False):
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
        if hasattr(self, "overlay"):
            self.overlay.set_language(self.language)
            # Flag auf dem Overlay aktualisieren
            self.overlay._apply_flag()
        self._update_theme_button_label()
        self._update_spin_mode_ui()
        self._update_summary_from_results()

        self._language_heavy_pending = bool(defer_heavy)
        if defer_heavy:
            return
        self._apply_language_heavy()

    def _apply_language_heavy(self):
        for w in (self.tank, self.dps, self.support):
            w.set_language(self.language)
        if hasattr(self, "map_mode"):
            self.map_mode.retranslate_ui()

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
    
    @QtCore.Slot(bool)
    def _on_mode_chosen(self, online: bool):
        if getattr(self, "_mode_choice_locked", False):
            return
        self._mode_choice_locked = True
        self._apply_mode_choice(online)

    def _apply_mode_choice(self, online: bool):
        if getattr(self, "_closing", False):
            return
        self.online_mode = online
        self._set_controls_enabled(True)
        self._set_heavy_ui_updates_enabled(True)
        self._post_choice_init_done = False
        # Schwere Arbeiten nach der Auswahl leicht verzögern, um "Early Click"-Lags zu vermeiden.
        delay_ms = self._post_choice_delay_ms
        if self._choice_shown_at is not None:
            elapsed = time.monotonic() - self._choice_shown_at
            if elapsed < 0.8:
                delay_ms = max(delay_ms, 900)
                self._post_choice_step_ms = 140
                self._post_choice_warmup_step_ms = 55
            else:
                self._post_choice_step_ms = 90
                self._post_choice_warmup_step_ms = 40
            self._trace_event(
                "apply_mode_choice",
                online=online,
                elapsed=round(elapsed, 3),
                delay_ms=delay_ms,
            )
        self._schedule_post_choice_init(delay_ms)

        if self.online_mode:
            config.debug_print("Online-Modus aktiv.")
        else:
            config.debug_print("Offline-Modus aktiv.")
        # Sync ggf. neu einplanen oder abbrechen
        self.state_sync.sync_all_roles()

    def _set_heavy_ui_updates_enabled(self, enabled: bool) -> None:
        """Defer expensive wheel painting while the mode-choice overlay is visible."""
        self._trace_event("set_heavy_ui_updates", enabled=enabled)
        for w in (self.tank, self.dps, self.support, getattr(self, "map_main", None)):
            if not w:
                continue
            try:
                w.setUpdatesEnabled(enabled)
            except Exception:
                pass
            view = getattr(w, "view", None)
            if view:
                try:
                    view.setUpdatesEnabled(enabled)
                except Exception:
                    pass

    def _overlay_choice_active(self) -> bool:
        overlay = getattr(self, "overlay", None)
        if not overlay or not overlay.isVisible():
            return False
        view = getattr(overlay, "_last_view", {}) or {}
        return view.get("type") == "online_choice"

    def _schedule_post_choice_init(self, delay_ms: int) -> None:
        if getattr(self, "_closing", False):
            return
        if not hasattr(self, "_post_choice_timer"):
            return
        self._trace_event("schedule_post_choice_init", delay_ms=delay_ms)
        self._post_choice_timer.start(max(0, int(delay_ms)))

    def _ensure_post_choice_ready(self) -> None:
        """Run deferred init immediately after the mode choice if the user interacts fast."""
        self._trace_event("ensure_post_choice_ready")
        if self._post_choice_init_done:
            return
        if hasattr(self, "_post_choice_timer") and self._post_choice_timer.isActive():
            self._post_choice_timer.stop()
        self._run_post_choice_init()

    def _run_post_choice_init(self) -> None:
        if getattr(self, "_closing", False):
            return
        if getattr(self, "_post_choice_init_done", False):
            return
        if self._overlay_choice_active():
            return
        self._trace_event("run_post_choice_init:start")
        self._set_tooltips_ready(True)
        self._set_heavy_ui_updates_enabled(True)
        if self._language_heavy_pending:
            self._apply_language_heavy()
            self._language_heavy_pending = False
        if self._theme_heavy_pending:
            theme = theme_util.get_theme(getattr(self, "theme", "light"))
            self._apply_theme_heavy(theme, step_ms=int(self._post_choice_step_ms))
            self._theme_heavy_pending = False
        self.sound.warmup_async(self, step_ms=int(self._post_choice_warmup_step_ms))
        self._refresh_tooltip_caches_async(delay_step_ms=int(self._post_choice_step_ms))
        self._schedule_map_prebuild()
        self._post_choice_init_done = True
        self._sync_mode_stack()
        self._trace_event("run_post_choice_init:done")

    def _schedule_map_prebuild(self) -> None:
        if getattr(self, "_closing", False):
            return
        if getattr(self, "_map_initialized", False) or getattr(self, "_map_prebuild_in_progress", False):
            return
        self._set_map_button_enabled(False)
        self._map_prebuild_in_progress = True
        QtCore.QTimer.singleShot(0, self._run_map_prebuild)

    def _run_map_prebuild(self) -> None:
        if getattr(self, "_closing", False):
            return
        if getattr(self, "_map_initialized", False):
            self._set_map_button_enabled(True)
            self._map_prebuild_in_progress = False
            return
        self._trace_event("map_prebuild:start")
        self._ensure_map_ui()
        # map_lists_ready will flip once listsBuilt fires

    def _on_map_lists_ready(self) -> None:
        self._map_lists_ready = True
        self._map_prebuild_in_progress = False
        self._set_map_button_enabled(True)
        self._trace_event("map_prebuild:done")
        self._apply_focus_policy_defaults()

    def _set_map_button_enabled(self, enabled: bool) -> None:
        if hasattr(self, "btn_mode_maps"):
            try:
                self.btn_mode_maps.setEnabled(bool(enabled))
            except Exception:
                pass

    def _mark_stack_switching(self, delay_ms: int = 140) -> None:
        if getattr(self, "_closing", False):
            return
        self._stack_switching = True
        timer = getattr(self, "_stack_switch_timer", None)
        if timer is not None:
            timer.start(max(0, int(delay_ms)))
        self._trace_event("stack_switching", active=True, delay_ms=delay_ms)

    def _clear_stack_switching(self) -> None:
        if not getattr(self, "_stack_switching", False):
            return
        self._stack_switching = False
        self._trace_event("stack_switching", active=False)

    def _sync_mode_stack(self) -> None:
        if not hasattr(self, "mode_stack"):
            return
        self._mark_stack_switching()
        self._trace_event("sync_mode_stack:before")
        if self.current_mode == "maps":
            self.mode_stack.setCurrentIndex(1)
            if hasattr(self, "map_ui"):
                self.map_ui.set_active(True)
        else:
            self.mode_stack.setCurrentIndex(0)
            if hasattr(self, "map_ui"):
                self.map_ui.set_active(False)
        self._update_title()
        self._update_spin_all_enabled()
        if getattr(self, "role_container", None):
            self.role_container.update()
        if getattr(self, "map_container", None):
            self.map_container.update()
        self._trace_event("sync_mode_stack:after", force_vis=True)
        self._trace_event("sync_mode_stack:after")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._closing = True
        self._trace_event("close_event")
        try:
            self._stop_all_wheels()
            if getattr(self, "map_main", None):
                self.map_main.hard_stop()
        except Exception:
            pass
        try:
            if hasattr(self, "map_ui"):
                self.map_ui.shutdown()
        except Exception:
            pass
        try:
            if hasattr(self, "player_list_panel"):
                self.player_list_panel.shutdown()
        except Exception:
            pass
        try:
            if hasattr(self, "_tooltip_refresh_timer") and self._tooltip_refresh_timer.isActive():
                self._tooltip_refresh_timer.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "_post_choice_timer") and self._post_choice_timer.isActive():
                self._post_choice_timer.stop()
        except Exception:
            pass
        try:
            if hasattr(self, "_stack_switch_timer") and self._stack_switch_timer.isActive():
                self._stack_switch_timer.stop()
        except Exception:
            pass
        try:
            self.state_sync.save_state(sync=False)
            self.state_sync.shutdown()
        except Exception:
            pass
        try:
            self.sound.shutdown()
        except Exception:
            pass
        app = QtWidgets.QApplication.instance()
        if app:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass
        super().closeEvent(event)

    def _trace_event(self, name: str, **extra) -> None:
        if not getattr(self, "_trace_enabled", False):
            return
        try:
            stack_idx = self.mode_stack.currentIndex() if hasattr(self, "mode_stack") else None
            stack_widget = None
            if hasattr(self, "mode_stack"):
                try:
                    stack_widget = self.mode_stack.currentWidget()
                except Exception:
                    stack_widget = None
            stack_widget_name = type(stack_widget).__name__ if stack_widget is not None else None
            overlay = getattr(self, "overlay", None)
            overlay_visible = overlay.isVisible() if overlay else False
            overlay_type = getattr(overlay, "_last_view", {}) or {}
            overlay_type = overlay_type.get("type") if isinstance(overlay_type, dict) else None
            tank_updates = self.tank.updatesEnabled() if hasattr(self, "tank") else None
            map_updates = getattr(self, "map_main", None)
            map_updates = map_updates.updatesEnabled() if map_updates else None
            role_vis = None
            map_vis = None
            if getattr(self, "role_container", None):
                role_vis = self.role_container.isVisible()
            if getattr(self, "map_container", None):
                map_vis = self.map_container.isVisible()
            if extra.pop("force_vis", False):
                # no-op, but keeps the visibility fields in the trace for sync events
                pass
            base = {
                "t": round(time.monotonic(), 3),
                "event": name,
                "mode": getattr(self, "current_mode", None),
                "stack": stack_idx,
                "stack_widget": stack_widget_name,
                "overlay": overlay_type,
                "overlay_visible": overlay_visible,
                "post_init": getattr(self, "_post_choice_init_done", None),
                "map_init": getattr(self, "_map_initialized", None),
                "stack_switching": getattr(self, "_stack_switching", None),
                "tank_updates": tank_updates,
                "map_updates": map_updates,
                "role_vis": role_vis,
                "map_vis": map_vis,
            }
            base.update(extra)
            line = " | ".join(f"{k}={v}" for k, v in base.items())
            try:
                with self._trace_file.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass
            if getattr(config, "DEBUG", False):
                config.debug_print(line)
        except Exception:
            pass
