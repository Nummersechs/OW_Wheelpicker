from pathlib import Path
import os
import sys
import time
from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets

import config
import i18n
from . import (
    hover_tooltip_ops,
    mode_manager,
    result_state_ops,
    runtime_tracing,
    shutdown_manager,
)
from .main_window_input import MainWindowInputMixin
from .main_window_background import MainWindowBackgroundMixin
from .main_window_ocr import MainWindowOCRMixin
from .main_window_sound import MainWindowSoundMixin
from .main_window_spin import MainWindowSpinMixin
from .ocr_role_import import PendingOCRImport
from services import state_store
from services.app_settings import AppSettings
from model.role_keys import role_wheel_map, role_wheels
from utils import flag_icons, theme as theme_util, ui_helpers
from view.overlay import ResultOverlay
from view.wheel_view import WheelView
from view.spin_mode_toggle import SpinModeToggle
from view.profile_dropdown import PlayerProfileDropdown
from controller.map_mode import MapModeController
from controller.open_queue import OpenQueueController
from controller.player_list_panel import PlayerListPanelController
from controller.role_mode import RoleModeController
from controller.state_sync import StateSyncController
from controller.tooltip_manager import TooltipManager
from controller.focus_policy import FocusPolicyManager
from controller.timer_registry import TimerRegistry
from view import style_helpers

# Fallback für "unbegrenzt" bei Widgetbreiten/Höhen (PySide6 exportiert QWIDGETSIZE_MAX nicht immer)
QWIDGETSIZE_MAX = getattr(QtWidgets, "QWIDGETSIZE_MAX", getattr(QtCore, "QWIDGETSIZE_MAX", 16777215))


class MainWindow(
    MainWindowOCRMixin,
    MainWindowSoundMixin,
    MainWindowBackgroundMixin,
    MainWindowSpinMixin,
    MainWindowInputMixin,
    QtWidgets.QMainWindow,
):
    def __init__(self):
        super().__init__()
        # Basisverzeichnisse bestimmen (Assets vs. writable state) und gespeicherten Zustand laden
        self._asset_dir = self._asset_base_dir()
        self._state_dir = self._state_base_dir()
        self._state_file = self._get_state_file()
        self.settings = AppSettings.from_module(config)
        self._run_id = f"{int(time.time() * 1000)}_{os.getpid()}"
        saved = StateSyncController.load_saved_state(self._state_file)
        default_lang = self._cfg("DEFAULT_LANGUAGE", "en")
        self.language = saved.get("language", default_lang) if isinstance(saved, dict) else default_lang
        i18n.set_language(self.language)
        self.theme = saved.get("theme", "light") if isinstance(saved, dict) else "light"
        if self.theme not in theme_util.THEMES:
            self.theme = "light"
        # Apply palette/global stylesheet baseline early so startup overlays/widgets
        # pick the persisted theme immediately.
        try:
            theme_util.apply_app_theme(theme_util.get_theme(self.theme))
        except Exception:
            pass

        self.setWindowTitle(i18n.t("app.title.main"))
        self.resize(1200, 650)
        self._init_sound_manager()

        self._restoring_state = True   # während des Aufbaus nicht speichern
        self._player_profile_combo_syncing = False
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
        self._close_overlay_active = False
        self._close_overlay_done = False
        self._close_overlay_timer: QtCore.QTimer | None = None
        self._startup_finalize_done = False
        self._startup_finalize_scheduled = False
        self._startup_visual_finalize_pending = False
        self._choice_shown_at: float | None = None
        self._post_choice_delay_ms = 350
        self._post_choice_step_ms = 90
        self._post_choice_warmup_step_ms = 40
        self._post_choice_timer = QtCore.QTimer(self)
        self._post_choice_timer.setSingleShot(True)
        self._post_choice_timer.timeout.connect(self._run_post_choice_init)
        self._startup_visual_finalize_timer = QtCore.QTimer(self)
        self._startup_visual_finalize_timer.setSingleShot(True)
        self._startup_visual_finalize_timer.timeout.connect(self._run_startup_visual_finalize)
        self._theme_heavy_pending = False
        self._language_heavy_pending = False
        self._post_choice_init_done = False
        self._post_choice_input_guard_until: float | None = None
        self._stack_switching = False
        self._stack_switch_timer = QtCore.QTimer(self)
        self._stack_switch_timer.setSingleShot(True)
        self._stack_switch_timer.timeout.connect(self._clear_stack_switching)
        self._map_init_in_progress = False
        self._map_lists_ready = False
        self._map_prebuild_in_progress = False
        self._map_spin_connected = False
        self._focus_trace_enabled = bool(self._cfg("TRACE_FOCUS", False))
        self._focus_trace_count = 0
        self._focus_trace_max_events = int(self._cfg("FOCUS_TRACE_MAX_EVENTS", 120))
        self._focus_trace_until = time.monotonic() + float(self._cfg("FOCUS_TRACE_DURATION_S", 3.0))
        self._focus_trace_window_events = bool(self._cfg("FOCUS_TRACE_WINDOW_EVENTS", True))
        self._focus_trace_windows_only = bool(self._cfg("FOCUS_TRACE_WINDOWS_ONLY", False))
        self._focus_trace_snapshot_interval_ms = int(self._cfg("FOCUS_TRACE_SNAPSHOT_INTERVAL_MS", 0))
        self._focus_trace_snapshot_remaining = int(self._cfg("FOCUS_TRACE_SNAPSHOT_COUNT", 0))
        self._focus_trace_snapshot_timer: QtCore.QTimer | None = None
        self._focus_trace_window_handle_installed = False
        self._focus_trace_last_t: float | None = None
        self._hover_rearm_last: float | None = None
        self._hover_trace_enabled = bool(self._cfg("TRACE_HOVER", False))
        self._hover_trace_count = 0
        self._hover_trace_max_events = int(self._cfg("HOVER_TRACE_MAX_EVENTS", 200))
        self._hover_trace_last_t: float | None = None
        self._hover_trace_file = self._state_dir / "hover_trace.log"
        self._write_trace_run_header(self._hover_trace_enabled, self._hover_trace_file)
        self._hover_forward_last: float | None = None
        self._hover_forwarding = False
        self._hover_seen = False
        self._hover_activity_last: float | None = None
        self._hover_user_move_last: float | None = None
        self._hover_watchdog_last: float | None = None
        self._hover_watchdog_started = False
        self._hover_prime_pending = False
        self._hover_prime_reason: str | None = None
        self._hover_prime_deferred_count = 0
        self._hover_prime_first_reason: str | None = None
        self._hover_prime_last_reason: str | None = None
        self._hover_pump_until: float | None = None
        self._hover_pump_timer: QtCore.QTimer | None = None
        self._hover_watchdog_timer: QtCore.QTimer | None = None
        self._deferred_hover_rearm_reason: str | None = None
        self._deferred_hover_rearm_force = False
        self._deferred_hover_rearm_timer: QtCore.QTimer | None = None
        self._deferred_tooltip_refresh_reason: str | None = None
        self._deferred_tooltip_refresh_timer: QtCore.QTimer | None = None
        self._background_services_paused = False
        self._paused_background_timers: list[tuple[object, int, bool]] = []
        self._wheel_cache_warmup_timer: QtCore.QTimer | None = None
        self._wheel_cache_warmup_queue: list[object] = []
        self._app_event_filter_installed = False
        self._applied_theme_key: str | None = None
        self._mode_button_checked_cache: dict[int, bool] = {}
        self._startup_block_input = False
        self._startup_block_input_until: float | None = None
        self._startup_warmup_running = False
        self._startup_warmup_done = False
        self._startup_warmup_finalize_scheduled = False
        self._startup_task_queue: list[tuple[str, Callable[[], None]]] = []
        self._startup_current_task: str | None = None
        self._startup_waiting_for_map = False
        self._blocked_input_total = 0
        self._blocked_input_counts: dict[int, int] = {}
        self._blocked_input_first_t: float | None = None
        self._blocked_input_last_t: float | None = None
        self._startup_drain_active = False
        self._startup_drain_timer: QtCore.QTimer | None = None
        self._drained_input_total = 0
        self._drained_input_counts: dict[int, int] = {}
        self._drained_input_first_t: float | None = None
        self._drained_input_last_t: float | None = None
        self._focus_trace_file = self._state_dir / "focus_trace.log"
        self._write_trace_run_header(self._focus_trace_enabled, self._focus_trace_file)
        self._trace_enabled = bool(
            self._cfg("TRACE_FLOW", False)
            or self._cfg("TRACE_SHUTDOWN", False)
            or self._cfg("DEBUG", False)
        )
        self._trace_last_t: float | None = None
        self._trace_file = self._state_dir / "flow_trace.log"
        if self._trace_enabled:
            self._trace_event("startup", run_id=self._run_id)
        if self._cfg("DISABLE_TOOLTIPS", False):
            try:
                QtWidgets.QToolTip.setEnabled(False)
            except Exception:
                pass
        self._timers = TimerRegistry()
        self._post_choice_timer = self._timers.register(self._post_choice_timer) or self._post_choice_timer
        self._startup_visual_finalize_timer = (
            self._timers.register(self._startup_visual_finalize_timer) or self._startup_visual_finalize_timer
        )
        self._stack_switch_timer = self._timers.register(self._stack_switch_timer) or self._stack_switch_timer
        self._hover_pump_timer = QtCore.QTimer(self)
        self._hover_pump_timer.setInterval(max(20, int(self._cfg("HOVER_PUMP_INTERVAL_MS", 40))))
        self._hover_pump_timer.timeout.connect(self._hover_pump_tick)
        self._hover_pump_timer = self._timers.register(self._hover_pump_timer) or self._hover_pump_timer
        self._map_button_loading = False
        self._pending_map_mode_switch = False
        self._hover_watchdog_timer = QtCore.QTimer(self)
        self._hover_watchdog_timer.setInterval(max(100, int(self._cfg("HOVER_WATCHDOG_INTERVAL_MS", 250))))
        self._hover_watchdog_timer.timeout.connect(self._hover_watchdog_tick)
        self._hover_watchdog_timer = self._timers.register(self._hover_watchdog_timer) or self._hover_watchdog_timer
        self._tooltip_manager = TooltipManager(self)
        self._focus_policy = FocusPolicyManager(self)
        self._pending_delete_names_panel = None
        self._pending_ocr_import: PendingOCRImport | None = None
        self._ocr_async_job = None
        self._ocr_runtime_activated = False
        self._role_ocr_buttons: dict[str, QtWidgets.QPushButton] = {}
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
        self._schedule_finalize_startup()
        self._apply_focus_policy_defaults()
        self._schedule_clear_focus()
        try:
            self.setMouseTracking(True)
            central.setMouseTracking(True)
        except Exception:
            pass

    def _cfg(self, key: str, default=None):
        settings = getattr(self, "settings", None)
        if settings is not None and hasattr(settings, "get"):
            try:
                return settings.get(key, default)
            except Exception:
                pass
        return getattr(config, key, default)

    def _write_trace_run_header(self, enabled: bool, trace_file: Path) -> None:
        if not enabled:
            return
        try:
            if bool(self._cfg("TRACE_CLEAR_ON_START", False)):
                trace_file.write_text("", encoding="utf-8")
            with trace_file.open("a", encoding="utf-8") as handle:
                handle.write(f"=== run {self._run_id} ===\n")
        except Exception:
            pass

    def _role_wheels(self) -> list[tuple[str, object]]:
        return role_wheels(self)

    @staticmethod
    def _role_state_key(role: str) -> str:
        return {
            "Tank": "tank",
            "Damage": "dps",
            "Support": "support",
        }.get(role, role.strip().lower())

    def _build_root(self) -> tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        return central, root

    def _build_header(self, root: QtWidgets.QVBoxLayout, saved: dict) -> None:
        current_theme = theme_util.get_theme(getattr(self, "theme", "light"))
        self.title = QtWidgets.QLabel("")
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        style_helpers.apply_theme_roles(current_theme, ((self.title, "label.window_title"),))

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
        self.btn_language.setIconSize(QtCore.QSize(28, 20))
        self.btn_language.clicked.connect(self._toggle_language)
        self.btn_theme = QtWidgets.QToolButton()
        self.btn_theme.setAutoRaise(True)
        self.btn_theme.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_theme.setFixedSize(40, 32)
        self.btn_theme.setIconSize(QtCore.QSize(24, 24))
        self.btn_theme.clicked.connect(self._toggle_theme)
        style_helpers.apply_theme_roles(
            current_theme,
            (
                (self.btn_language, "tool.button"),
                (self.btn_theme, "tool.button"),
            ),
        )
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
        self.btn_mode_players.setToolTip(i18n.t("mode.players_tooltip"))
        self.btn_mode_heroes = QtWidgets.QPushButton(i18n.t("mode.heroes"))
        self.btn_mode_heroes.setCheckable(True)
        self.btn_mode_heroes.setToolTip(i18n.t("mode.heroes_tooltip"))
        self.btn_mode_heroban = QtWidgets.QPushButton(i18n.t("mode.hero_ban"))
        self.btn_mode_heroban.setCheckable(True)
        self.btn_mode_heroban.setToolTip(i18n.t("mode.hero_ban_tooltip"))
        self.btn_mode_maps = QtWidgets.QPushButton(i18n.t("mode.maps"))
        self.btn_mode_maps.setCheckable(True)
        self.btn_mode_maps.setToolTip(i18n.t("mode.maps_tooltip"))
        # Fixe Breiten, damit Sprache die Buttons nicht springen lässt
        ui_helpers.set_fixed_width_from_translations(
            [
                self.btn_mode_players,
                self.btn_mode_heroes,
                self.btn_mode_heroban,
                self.btn_mode_maps,
            ],
            ["mode.players", "mode.heroes", "mode.hero_ban", "mode.maps", "mode.maps_loading"],
            padding=56,
        )
        self._mode_buttons = [
            self.btn_mode_players,
            self.btn_mode_heroes,
            self.btn_mode_heroban,
            self.btn_mode_maps,
        ]
        for btn in self._mode_buttons:
            btn.setProperty("modeButton", True)
            btn.setFixedHeight(38)
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
        self.lbl_player_profile = QtWidgets.QLabel(i18n.t("players.profile_label"))
        self.player_profile_dropdown = PlayerProfileDropdown()
        self.player_profile_dropdown.setMinimumWidth(220)
        self.player_profile_dropdown.setFixedHeight(34)
        self.player_profile_dropdown.profileActivated.connect(self._on_player_profile_changed)
        self.player_profile_dropdown.profileRenamed.connect(self._on_player_profile_name_edited)
        self.player_profile_dropdown.orderChanged.connect(self._on_player_profile_reordered)
        self._refresh_player_profile_combo()
        mode_row.addWidget(self.lbl_player_profile)
        mode_row.addWidget(self.player_profile_dropdown)
        mode_row.addSpacing(10)
        mode_row.addStretch(1)
        self.lbl_mode = QtWidgets.QLabel(i18n.t("label.mode"))
        self.lbl_mode.setToolTip(i18n.t("label.mode_tooltip"))
        mode_row.addWidget(self.lbl_mode)
        mode_row.addWidget(self.btn_mode_players)
        mode_row.addWidget(self.btn_mode_heroes)
        mode_row.addWidget(self.btn_mode_heroban)
        mode_row.addWidget(self.btn_mode_maps)
        mode_row.addStretch(1)
        root.addLayout(mode_row)

    def _capture_players_state_for_profiles(self) -> None:
        if getattr(self, "current_mode", "") != "players":
            return
        if getattr(self, "hero_ban_active", False):
            return
        self._state_store.capture_mode_from_wheels(
            "players",
            role_wheel_map(self),
            hero_ban_active=False,
        )

    def _refresh_player_profile_combo(self) -> None:
        if not hasattr(self, "player_profile_dropdown"):
            return
        names = self._state_store.get_player_profile_names()
        idx = self._state_store.get_active_player_profile_index()
        self._player_profile_combo_syncing = True
        try:
            self.player_profile_dropdown.set_profiles(names, idx)
            self.player_profile_dropdown.set_dropdown_tooltip(i18n.t("players.profile_tooltip"))
        finally:
            self._player_profile_combo_syncing = False

    def _on_player_profile_changed(self, index: int) -> None:
        if self._player_profile_combo_syncing:
            return
        if index < 0:
            return
        self._capture_players_state_for_profiles()
        changed = self._state_store.set_active_player_profile(index)
        if not changed:
            return
        if getattr(self, "current_mode", "") == "players" and not getattr(self, "hero_ban_active", False):
            self._load_mode_into_wheels("players", hero_ban=False)
        self._refresh_player_profile_combo()
        if not getattr(self, "_restoring_state", False):
            self.state_sync.save_state(sync=False)

    def _on_player_profile_name_edited(self, index: int | None = None, name: str | None = None) -> None:
        if self._player_profile_combo_syncing:
            return
        if not hasattr(self, "player_profile_dropdown"):
            return
        idx = int(index) if isinstance(index, int) else self.player_profile_dropdown.current_profile_index()
        if idx < 0:
            return
        label = name if isinstance(name, str) else self.player_profile_dropdown.current_profile_name()
        changed = self._state_store.rename_player_profile(idx, label)
        self._refresh_player_profile_combo()
        if changed and not getattr(self, "_restoring_state", False):
            self.state_sync.save_state(sync=False)

    def _on_player_profile_reordered(self, order: list[int] | None = None) -> None:
        if self._player_profile_combo_syncing:
            return
        if not hasattr(self, "player_profile_dropdown"):
            return
        resolved = list(order) if isinstance(order, list) else self.player_profile_dropdown.current_order()
        if not resolved:
            return
        changed = self._state_store.reorder_player_profiles(resolved)
        if not changed:
            return
        self._refresh_player_profile_combo()
        if not getattr(self, "_restoring_state", False):
            self.state_sync.save_state(sync=False, immediate=True)

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
        self.btn_tank_ocr_import = QtWidgets.QPushButton(i18n.t("ocr.tank_button"))
        self.btn_tank_ocr_import.setFixedHeight(36)
        self.btn_tank_ocr_import.clicked.connect(
            lambda _checked=False: self._on_role_ocr_import_clicked("tank")
        )
        self.tank.set_wheel_overlay_widget(
            self.btn_tank_ocr_import,
            margin_top=8,
            margin_right=8,
        )
        self._register_role_ocr_button("tank", self.btn_tank_ocr_import)
        self.dps = WheelView(
            "Damage",
            dps_state.get("entries", []),
            pair_mode=dps_state.get("pair_mode", True),
            allow_pair_toggle=True,
            subrole_labels=["HS", "FDPS"],
        )
        self.btn_dps_ocr_import = QtWidgets.QPushButton(i18n.t("ocr.dps_button"))
        self.btn_dps_ocr_import.setFixedHeight(36)
        self.btn_dps_ocr_import.clicked.connect(
            lambda _checked=False: self._on_role_ocr_import_clicked("dps")
        )
        self.dps.set_wheel_overlay_widget(
            self.btn_dps_ocr_import,
            margin_top=8,
            margin_right=8,
        )
        self._register_role_ocr_button("dps", self.btn_dps_ocr_import)
        self.support = WheelView(
            "Support",
            support_state.get("entries", []),
            pair_mode=support_state.get("pair_mode", True),
            allow_pair_toggle=True,
            subrole_labels=["MS", "FS"],
        )
        self.btn_support_ocr_import = QtWidgets.QPushButton(i18n.t("ocr.support_button"))
        self.btn_support_ocr_import.setFixedHeight(36)
        self.btn_support_ocr_import.clicked.connect(
            lambda _checked=False: self._on_role_ocr_import_clicked("support")
        )
        self.support.set_wheel_overlay_widget(
            self.btn_support_ocr_import,
            margin_top=8,
            margin_right=8,
        )
        self._register_role_ocr_button("support", self.btn_support_ocr_import)
        for panel in (self.tank.names_panel, self.dps.names_panel, self.support.names_panel):
            panel.set_delete_confirm_handler(
                lambda count, _panel=panel: self._request_delete_names_confirm(_panel, count)
            )
        self.role_mode = RoleModeController(self)

        grid.addWidget(self.tank, 0, 0)
        grid.addWidget(self.dps, 0, 1)
        grid.addWidget(self.support, 0, 2)
        self.btn_all_players = QtWidgets.QPushButton(i18n.t("players.list_button"))
        ui_helpers.set_fixed_width_from_translations([self.btn_all_players], ["players.list_button"], padding=40)
        self.btn_all_players.setFixedHeight(36)
        self.btn_all_players.setToolTip(i18n.t("players.list_button_tooltip"))
        self.player_list_panel = PlayerListPanelController(self, self.btn_all_players)
        self.btn_all_players.clicked.connect(self.player_list_panel.toggle_panel)
        self.btn_open_q_ocr = QtWidgets.QPushButton(i18n.t("ocr.open_q_button"))
        ui_helpers.set_fixed_width_from_translations([self.btn_open_q_ocr], ["ocr.open_q_button"], padding=40)
        self.btn_open_q_ocr.setFixedHeight(36)
        self.btn_open_q_ocr.setToolTip(i18n.t("ocr.open_q_button_tooltip"))
        self.btn_open_q_ocr.clicked.connect(self._on_open_q_ocr_clicked)
        self._role_left_controls = QtWidgets.QWidget()
        role_left_controls_layout = QtWidgets.QHBoxLayout(self._role_left_controls)
        role_left_controls_layout.setContentsMargins(0, 0, 0, 0)
        role_left_controls_layout.setSpacing(8)
        role_left_controls_layout.addWidget(self.btn_all_players)
        role_left_controls_layout.addWidget(self.btn_open_q_ocr)
        role_left_controls_layout.addStretch(1)
        grid.addWidget(self._role_left_controls, 1, 0)
        self._update_role_ocr_buttons_enabled()
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
        from controller.map_ui import MapUI

        self._map_init_in_progress = True
        try:
            self._map_lists_ready = False
            self.map_ui = MapUI(
                self._state_store,
                self.language,
                self.theme,
                tuple(wheel for _role, wheel in self._role_wheels()),
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
            if not getattr(self, "_map_spin_connected", False):
                try:
                    self.map_main.spun.connect(self._wheel_finished)
                    self._map_spin_connected = True
                except Exception:
                    pass
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
        self.btn_spin_all.setObjectName("btn_spin_all")
        ui_helpers.set_fixed_width_from_translations([self.btn_spin_all], ["controls.spin_all"], padding=40)
        self.btn_spin_all.setFixedHeight(44)
        self.btn_spin_all.setToolTip(i18n.t("controls.spin_all_tooltip"))
        self.btn_spin_all.clicked.connect(self.spin_all)
        self.spin_mode_toggle = SpinModeToggle()
        self.spin_mode_toggle.setToolTip(i18n.t("controls.spin_mode_tooltip"))
        self.spin_mode_toggle.valueChanged.connect(self._update_spin_all_enabled)
        self.lbl_open_count = QtWidgets.QLabel(i18n.t("controls.open_count_label"))
        self.lbl_open_count.setToolTip(i18n.t("controls.open_count_tooltip"))
        self.open_count_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.open_count_slider.setRange(1, 6)
        self.open_count_slider.setValue(3)
        self.open_count_slider.setFixedWidth(96)
        self.open_count_slider.setToolTip(i18n.t("controls.open_count_tooltip"))
        self.open_count_slider.valueChanged.connect(self._on_open_count_changed)
        self.lbl_open_count_value = QtWidgets.QLabel("3")
        self.lbl_open_count_value.setMinimumWidth(18)
        self.lbl_open_count_value.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.lbl_open_count_value.setToolTip(i18n.t("controls.open_count_tooltip"))
        controls.addStretch(1)
        self.lbl_anim_duration = QtWidgets.QLabel(i18n.t("controls.anim_duration"))
        controls.addWidget(self.lbl_anim_duration)
        self.duration.setFixedHeight(30)
        controls.addWidget(self.duration)
        controls.addWidget(self.spin_mode_toggle)
        controls.addWidget(self.lbl_open_count)
        controls.addWidget(self.open_count_slider)
        controls.addWidget(self.lbl_open_count_value)
        controls.addWidget(self.btn_spin_all)
        self.btn_cancel_spin = QtWidgets.QPushButton(i18n.t("controls.cancel_spin"))
        self.btn_cancel_spin.setObjectName("btn_cancel_spin")
        ui_helpers.set_fixed_width_from_translations([self.btn_cancel_spin], ["controls.cancel_spin"], padding=40)
        self.btn_cancel_spin.setFixedHeight(44)
        self.btn_cancel_spin.setEnabled(False)
        self.btn_cancel_spin.setToolTip(i18n.t("controls.cancel_spin_tooltip"))
        style_helpers.style_danger_button(self.btn_cancel_spin, theme_util.get_theme(getattr(self, "theme", "light")))
        self.btn_cancel_spin.clicked.connect(self._cancel_spin)
        controls.addWidget(self.btn_cancel_spin)
        controls.addStretch(1)
        self.lbl_open_count.setVisible(False)
        self.open_count_slider.setVisible(False)
        self.lbl_open_count_value.setVisible(False)

    def _build_summary(self, root: QtWidgets.QVBoxLayout) -> None:
        current_theme = theme_util.get_theme(getattr(self, "theme", "light"))
        self.summary = QtWidgets.QLabel("")
        self.summary.setAlignment(QtCore.Qt.AlignCenter)
        style_helpers.apply_theme_roles(current_theme, ((self.summary, "label.summary"),))
        root.addWidget(self.summary)

    def _init_spin_state(self) -> None:
        self.pending = 0
        self._result_sent_this_spin = False
        self._last_results_snapshot: dict | None = None
        self._spin_started_at_monotonic: float | None = None
        self._spin_watchdog_timer: QtCore.QTimer | None = None
        if bool(self._cfg("SPIN_WATCHDOG_ENABLED", False)):
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._on_spin_watchdog_timeout)
            self._spin_watchdog_timer = timer
        self.open_queue = OpenQueueController(self)
        if hasattr(self, "open_count_slider"):
            self.open_queue.set_player_count(int(self.open_count_slider.value()))
        for _role, w in self._role_wheels():
            w.spun.connect(self._wheel_finished)
        if hasattr(self, "map_main"):
            self.map_main.spun.connect(self._wheel_finished)

    def _build_overlay(self, central: QtWidgets.QWidget) -> None:
        self.overlay = ResultOverlay(parent=central)
        # ResultOverlay defaults to light internally; enforce persisted app theme.
        theme = theme_util.get_theme(getattr(self, "theme", "light"))
        self.overlay.apply_theme(theme, theme_util.tool_button_stylesheet(theme))
        self.overlay.hide()
        self.overlay.closed.connect(self._on_overlay_closed)
        self.overlay.languageToggleRequested.connect(self._toggle_language)
        self.overlay.disableResultsRequested.connect(self._on_overlay_disable_results)
        self.overlay.deleteNamesConfirmed.connect(self._on_overlay_delete_names_confirmed)
        self.overlay.deleteNamesCancelled.connect(self._on_overlay_delete_names_cancelled)
        self.overlay.ocrImportConfirmed.connect(self._on_overlay_ocr_import_confirmed)
        self.overlay.ocrImportReplaceRequested.connect(self._on_overlay_ocr_import_replace_requested)
        self.overlay.ocrImportCancelled.connect(self._on_overlay_ocr_import_cancelled)

        self.online_mode = False  # Standard
        self.overlay.modeChosen.connect(self._on_mode_chosen)

    def _request_delete_names_confirm(self, panel, count: int) -> bool:
        overlay = getattr(self, "overlay", None)
        if overlay is None:
            return False
        self._pending_delete_names_panel = panel
        try:
            overlay.show_delete_names_confirm(int(count))
        except Exception:
            self._pending_delete_names_panel = None
            return False
        return True

    def _install_event_filters(self) -> None:
        self.installEventFilter(self)
        app = QtWidgets.QApplication.instance()
        if app:
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
        self._refresh_app_event_filter_state()

    def _set_app_event_filter_enabled(self, enabled: bool) -> None:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        target = bool(enabled)
        current = bool(getattr(self, "_app_event_filter_installed", False))
        if target == current:
            return
        if target:
            app.installEventFilter(self)
            self._app_event_filter_installed = True
            return
        try:
            app.removeEventFilter(self)
        except Exception:
            pass
        self._app_event_filter_installed = False

    def _needs_app_event_filter(self) -> bool:
        if getattr(self, "_focus_trace_enabled", False):
            return True
        if bool(self._cfg("HOVER_FORWARD_MOUSEMOVE", False)):
            return True
        if getattr(self, "_startup_block_input", False) or getattr(self, "_startup_drain_active", False):
            return True
        if self._overlay_choice_active():
            return True
        if self._post_choice_input_guard_active():
            return True
        panel = getattr(self, "player_list_panel", None)
        if panel is not None and hasattr(panel, "is_visible"):
            try:
                if panel.is_visible():
                    return True
            except Exception:
                pass
        return False

    def _refresh_app_event_filter_state(self) -> None:
        if getattr(self, "_closing", False):
            self._set_app_event_filter_enabled(False)
            return
        self._set_app_event_filter_enabled(self._needs_app_event_filter())

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        # Ensure heavy startup finalize runs only after the first paint request.
        self._schedule_finalize_startup()
        if not getattr(self, "_focus_trace_enabled", False):
            return
        self._install_window_handle_filter()

    def _schedule_finalize_startup(self, delay_ms: int | None = None) -> None:
        if getattr(self, "_startup_finalize_done", False):
            return
        if getattr(self, "_startup_finalize_scheduled", False):
            return
        self._startup_finalize_scheduled = True
        if delay_ms is None:
            delay_ms = int(self._cfg("STARTUP_FINALIZE_DELAY_MS", 60))
        QtCore.QTimer.singleShot(max(0, int(delay_ms)), self._run_finalize_startup)

    def _run_finalize_startup(self) -> None:
        self._startup_finalize_scheduled = False
        if getattr(self, "_startup_finalize_done", False):
            return
        self._finalize_startup()

    def _schedule_startup_visual_finalize(self, delay_ms: int | None = None) -> None:
        if getattr(self, "_closing", False):
            return
        if not bool(getattr(self, "_startup_visual_finalize_pending", False)):
            return
        timer = getattr(self, "_startup_visual_finalize_timer", None)
        if timer is None:
            return
        if delay_ms is None:
            delay_ms = int(self._cfg("STARTUP_VISUAL_FINALIZE_DELAY_MS", 280))
        timer.start(max(0, int(delay_ms)))

    def _startup_visual_finalize_block_reason(self) -> str | None:
        if getattr(self, "_closing", False):
            return "closing"
        if self._overlay_choice_active():
            return "overlay_choice"
        try:
            if int(getattr(self, "pending", 0) or 0) > 0:
                return "spin_pending"
        except Exception:
            pass
        if bool(getattr(self, "_background_services_paused", False)):
            return "background_services_paused"
        if bool(getattr(self, "_stack_switching", False)):
            return "stack_switching"
        return None

    def _run_startup_visual_finalize(self) -> None:
        if getattr(self, "_closing", False):
            return
        if not bool(getattr(self, "_startup_visual_finalize_pending", False)):
            return
        block_reason = self._startup_visual_finalize_block_reason()
        if block_reason:
            retry_ms = max(120, int(self._cfg("STARTUP_VISUAL_FINALIZE_BUSY_RETRY_MS", 250)))
            self._trace_event(
                "startup_visual_finalize:defer",
                reason=block_reason,
                retry_ms=retry_ms,
            )
            self._schedule_startup_visual_finalize(delay_ms=retry_ms)
            return
        self._startup_visual_finalize_pending = False
        self._trace_event("startup_visual_finalize:start")
        self._apply_theme(defer_heavy=True)
        self._apply_language(defer_heavy=True)
        self._flush_startup_visual_finalize_pending_heavy()
        self._trace_event("startup_visual_finalize:done")

    def _flush_startup_visual_finalize_pending_heavy(self) -> None:
        """
        Apply deferred heavy theme/language updates immediately when startup warmup
        is already done. Without this, dark-mode wheel styling can stay stale until
        a later explicit theme toggle.
        """
        warmup_done = bool(getattr(self, "_startup_warmup_done", False))
        post_choice_done = bool(getattr(self, "_post_choice_init_done", False))
        if not (warmup_done or post_choice_done):
            return
        if self._overlay_choice_active():
            return
        did_work = self._flush_pending_heavy_ui_updates(step_ms=int(getattr(self, "_post_choice_step_ms", 15)))
        if did_work:
            self._trace_event("startup_visual_finalize:flushed_heavy")

    def _flush_pending_heavy_ui_updates(self, step_ms: int | None = None) -> bool:
        if step_ms is None:
            step_ms = int(getattr(self, "_post_choice_step_ms", 15))
        did_work = False
        self._set_heavy_ui_updates_enabled(True)
        if bool(getattr(self, "_language_heavy_pending", False)):
            self._apply_language_heavy()
            self._language_heavy_pending = False
            did_work = True
        if bool(getattr(self, "_theme_heavy_pending", False)):
            theme = theme_util.get_theme(getattr(self, "theme", "light"))
            self._apply_theme_heavy(theme, step_ms=int(step_ms))
            self._theme_heavy_pending = False
            did_work = True
        return did_work

    def _ensure_deferred_hover_rearm_timer(self) -> QtCore.QTimer:
        timer = getattr(self, "_deferred_hover_rearm_timer", None)
        if timer is not None:
            return timer
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._run_deferred_hover_rearm)
        if hasattr(self, "_timers"):
            self._timers.register(timer)
        self._deferred_hover_rearm_timer = timer
        return timer

    def _run_deferred_hover_rearm(self) -> None:
        reason = self._deferred_hover_rearm_reason or "deferred_hover_rearm"
        force = bool(self._deferred_hover_rearm_force)
        self._deferred_hover_rearm_reason = None
        self._deferred_hover_rearm_force = False
        if getattr(self, "_background_services_paused", False):
            self._deferred_hover_rearm_reason = reason
            self._deferred_hover_rearm_force = bool(force)
            return
        self._rearm_hover_tracking(reason=reason, force=force)

    def _schedule_hover_rearm(self, reason: str, delay_ms: int = 0, *, force: bool = False) -> None:
        if getattr(self, "_background_services_paused", False):
            self._deferred_hover_rearm_reason = str(reason or "deferred_hover_rearm")
            self._deferred_hover_rearm_force = bool(force) or bool(self._deferred_hover_rearm_force)
            return
        if max(0, int(delay_ms)) <= 0:
            self._rearm_hover_tracking(reason=reason, force=force)
            return
        timer = self._ensure_deferred_hover_rearm_timer()
        self._deferred_hover_rearm_reason = str(reason or "deferred_hover_rearm")
        self._deferred_hover_rearm_force = bool(force) or bool(self._deferred_hover_rearm_force)
        timer.start(max(0, int(delay_ms)))

    def _ensure_deferred_tooltip_refresh_timer(self) -> QtCore.QTimer:
        timer = getattr(self, "_deferred_tooltip_refresh_timer", None)
        if timer is not None:
            return timer
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._run_deferred_tooltip_refresh)
        if hasattr(self, "_timers"):
            self._timers.register(timer)
        self._deferred_tooltip_refresh_timer = timer
        return timer

    def _run_deferred_tooltip_refresh(self) -> None:
        reason = self._deferred_tooltip_refresh_reason or "deferred_refresh"
        self._deferred_tooltip_refresh_reason = None
        if getattr(self, "_background_services_paused", False):
            self._deferred_tooltip_refresh_reason = str(reason or "deferred_refresh")
            return
        if self._cfg("DISABLE_TOOLTIPS", False):
            return
        self._refresh_tooltip_caches_async(reason=reason)

    def _schedule_tooltip_refresh(self, reason: str, delay_ms: int = 0) -> None:
        if self._cfg("DISABLE_TOOLTIPS", False):
            return
        if getattr(self, "_background_services_paused", False):
            self._deferred_tooltip_refresh_reason = str(reason or "deferred_refresh")
            return
        if max(0, int(delay_ms)) <= 0:
            self._refresh_tooltip_caches_async(reason=reason)
            return
        timer = self._ensure_deferred_tooltip_refresh_timer()
        self._deferred_tooltip_refresh_reason = str(reason or "deferred_refresh")
        timer.start(max(0, int(delay_ms)))

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
            if hasattr(self, "_timers"):
                self._timers.register(self._focus_trace_snapshot_timer)
        self._focus_trace_snapshot_timer.start(max(40, self._focus_trace_snapshot_interval_ms))

    def _show_mode_choice(self) -> None:
        """Direkt beim Start Modus wählen lassen."""
        self._set_controls_enabled(False)
        self._set_heavy_ui_updates_enabled(False)
        self.overlay.show_online_choice()
        self.overlay.set_choice_enabled(False)
        self._choice_shown_at = time.monotonic()
        self._trace_event("show_mode_choice")
        self._start_startup_warmup()
        self._refresh_app_event_filter_state()

    def _start_startup_warmup(self) -> None:
        if getattr(self, "_startup_warmup_done", False) or getattr(self, "_startup_warmup_running", False):
            try:
                if hasattr(self, "overlay"):
                    self.overlay.set_choice_enabled(True)
            except Exception:
                pass
            return
        tasks: list[tuple[str, callable]] = []
        if self._cfg("SOUND_WARMUP_ON_START", False):
            tasks.append(("sound_warmup", self._startup_task_sound))
        if self._cfg("TOOLTIP_CACHE_ON_START", False) and not self._cfg("DISABLE_TOOLTIPS", False):
            tasks.append(("tooltip_cache", self._startup_task_tooltips))
        if self._cfg("MAP_PREBUILD_ON_START", False):
            tasks.append(("map_prebuild", self._startup_task_map_prebuild))
        min_block_ms = max(0, int(self._cfg("STARTUP_MIN_BLOCK_INPUT_MS", 0)))
        # Fast-path for normal startup: no warmup tasks and no explicit lock.
        if not tasks and min_block_ms <= 0:
            self._startup_task_queue = []
            self._startup_warmup_running = False
            self._startup_warmup_done = True
            self._startup_block_input = False
            self._startup_block_input_until = None
            self._startup_drain_active = False
            self._trace_event("startup_warmup:skipped")
            self._refresh_app_event_filter_state()
            try:
                if hasattr(self, "overlay"):
                    self.overlay.set_choice_enabled(True)
            except Exception:
                pass
            return
        self._startup_task_queue = tasks
        self._startup_warmup_running = True
        self._startup_block_input = True
        if min_block_ms > 0:
            self._startup_block_input_until = time.monotonic() + (min_block_ms / 1000.0)
        else:
            self._startup_block_input_until = None
        self._refresh_app_event_filter_state()
        self._trace_event("startup_warmup:start", tasks=[name for name, _ in tasks], min_block_ms=min_block_ms)
        if not tasks:
            self._finish_startup_warmup()
            return
        self._run_next_startup_task()

    def _run_next_startup_task(self) -> None:
        if not self._startup_task_queue:
            self._finish_startup_warmup()
            return
        name, fn = self._startup_task_queue.pop(0)
        self._startup_current_task = name
        self._trace_event("startup_warmup:task_start", task=name)
        QtCore.QTimer.singleShot(0, fn)

    def _startup_task_done(self, name: str | None = None) -> None:
        task = name or getattr(self, "_startup_current_task", None)
        if task:
            self._trace_event("startup_warmup:task_done", task=task)
        self._startup_current_task = None
        QtCore.QTimer.singleShot(0, self._run_next_startup_task)

    def _finish_startup_warmup(self) -> None:
        if getattr(self, "_startup_warmup_done", False):
            return
        if getattr(self, "_startup_warmup_finalize_scheduled", False):
            return
        self._startup_warmup_finalize_scheduled = True
        extra_ms = max(0, int(self._cfg("STARTUP_WARMUP_COOLDOWN_MS", 500)))
        remaining_lock_ms = 0
        block_until = getattr(self, "_startup_block_input_until", None)
        if block_until is not None:
            remaining_lock_ms = max(0, int((float(block_until) - time.monotonic()) * 1000.0))
            extra_ms = max(extra_ms, remaining_lock_ms)
        self._trace_event("startup_warmup:cooldown", delay_ms=extra_ms, remaining_lock_ms=remaining_lock_ms)
        QtCore.QTimer.singleShot(extra_ms, self._finalize_startup_warmup)

    def _finalize_startup_warmup(self) -> None:
        if getattr(self, "_startup_warmup_done", False):
            return
        self._startup_warmup_running = False
        self._startup_warmup_done = True
        self._flush_posted_events("startup_warmup_done")
        self._startup_block_input = False
        self._startup_block_input_until = None
        self._startup_drain_active = True
        self._refresh_app_event_filter_state()
        self._restart_startup_drain_timer()
        self._startup_task_queue = []
        self._startup_current_task = None
        self._startup_waiting_for_map = False
        # Heavy UI updates were deferred; apply once warmup is done.
        self._flush_pending_heavy_ui_updates(step_ms=int(self._post_choice_step_ms))
        self._sync_mode_stack()
        self._trace_event("startup_warmup:done")
        self._rearm_hover_tracking(reason="startup_warmup:done")
        if not self._cfg("DISABLE_TOOLTIPS", False) and not self._cfg("TOOLTIP_CACHE_ON_START", False):
            self._refresh_tooltip_caches_async(reason="startup_warmup_done")

    def _record_blocked_input_event(self, etype: int) -> None:
        now = time.monotonic()
        if self._blocked_input_first_t is None:
            self._blocked_input_first_t = now
        self._blocked_input_last_t = now
        self._blocked_input_total += 1
        self._blocked_input_counts[etype] = self._blocked_input_counts.get(etype, 0) + 1

    def _flush_blocked_input_stats(self, reason: str) -> None:
        total = self._blocked_input_total
        if total <= 0:
            return
        first = self._blocked_input_first_t
        last = self._blocked_input_last_t
        duration_ms = None
        if first is not None and last is not None:
            duration_ms = int((last - first) * 1000)
        items = sorted(self._blocked_input_counts.items(), key=lambda kv: kv[1], reverse=True)
        top = []
        for etype, count in items[:6]:
            top.append(f"{self._event_type_name(int(etype))}={count}")
        self._trace_event(
            "startup_input_blocked",
            reason=reason,
            total=total,
            duration_ms=duration_ms,
            top=",".join(top),
        )
        self._blocked_input_total = 0
        self._blocked_input_counts = {}
        self._blocked_input_first_t = None
        self._blocked_input_last_t = None

    def _record_drained_input_event(self, etype: int) -> None:
        now = time.monotonic()
        if self._drained_input_first_t is None:
            self._drained_input_first_t = now
        self._drained_input_last_t = now
        self._drained_input_total += 1
        self._drained_input_counts[etype] = self._drained_input_counts.get(etype, 0) + 1

    def _flush_drained_input_stats(self, reason: str) -> None:
        total = self._drained_input_total
        if total <= 0:
            return
        first = self._drained_input_first_t
        last = self._drained_input_last_t
        duration_ms = None
        if first is not None and last is not None:
            duration_ms = int((last - first) * 1000)
        items = sorted(self._drained_input_counts.items(), key=lambda kv: kv[1], reverse=True)
        top = []
        for etype, count in items[:6]:
            top.append(f"{self._event_type_name(int(etype))}={count}")
        self._trace_event(
            "startup_input_drained",
            reason=reason,
            total=total,
            duration_ms=duration_ms,
            top=",".join(top),
        )
        self._drained_input_total = 0
        self._drained_input_counts = {}
        self._drained_input_first_t = None
        self._drained_input_last_t = None

    def _end_startup_input_drain(self) -> None:
        self._startup_drain_active = False
        self._refresh_app_event_filter_state()
        self._flush_posted_events("startup_drain_done")
        self._flush_drained_input_stats("startup_drain_done")
        self._trace_event("startup_input_drain:done")
        try:
            if hasattr(self, "overlay"):
                self.overlay.set_choice_enabled(True)
        except Exception:
            pass
        self._rearm_hover_tracking(reason="startup_drain:done")
        if getattr(self, "_hover_prime_pending", False) and not self._overlay_choice_active():
            self._hover_prime_pending = False
            reason = self._hover_prime_reason or "startup_drain:prime"
            self._hover_prime_reason = None
            self._flush_hover_prime_deferred_trace()
            self._hover_seen = False
            self._hover_forward_last = None
            self._trace_hover_event("hover_prime_after_drain", reason=reason)
            self._hover_poke_under_cursor(reason=reason)
            self._start_hover_pump(reason=reason, duration_ms=1200, force=True)

    def _restart_startup_drain_timer(self) -> None:
        drain_ms = max(0, int(self._cfg("STARTUP_INPUT_DRAIN_MS", 180)))
        if self._startup_drain_timer is None:
            self._startup_drain_timer = QtCore.QTimer(self)
            self._startup_drain_timer.setSingleShot(True)
            self._startup_drain_timer.timeout.connect(self._end_startup_input_drain)
        already_active = self._startup_drain_timer.isActive()
        self._startup_drain_timer.start(drain_ms)
        if not already_active:
            self._trace_event("startup_input_drain:start", delay_ms=drain_ms)

    def _flush_posted_events(self, reason: str) -> None:
        try:
            app = QtCore.QCoreApplication.instance()
        except Exception:
            app = None
        if app is None:
            return
        if int(getattr(self, "pending", 0) or 0) > 0 or self._has_active_spin_animations(
            include_internal_flags=True
        ):
            self._trace_event("posted_events_flush_skipped", reason=reason, scope="spin_active")
            return
        targets = [self, getattr(self, "overlay", None)]
        count = 0
        for target in targets:
            if target is None:
                continue
            try:
                QtCore.QCoreApplication.removePostedEvents(target)
                count += 1
            except Exception:
                pass
        self._trace_event("posted_events_flushed", reason=reason, scope="targets", targets=count)

    def _has_active_spin_animations(self, *, include_internal_flags: bool = False) -> bool:
        role_wheels_fn = getattr(self, "_role_wheels", None)
        if callable(role_wheels_fn):
            try:
                for _role, wheel in role_wheels_fn():
                    try:
                        if hasattr(wheel, "is_anim_running") and bool(wheel.is_anim_running()):
                            return True
                        if include_internal_flags and bool(getattr(wheel, "_is_spinning", False)):
                            return True
                    except Exception:
                        continue
            except Exception:
                pass
        map_main = getattr(self, "map_main", None)
        if map_main is None:
            return False
        try:
            if hasattr(map_main, "is_anim_running") and bool(map_main.is_anim_running()):
                return True
            if include_internal_flags and bool(getattr(map_main, "_is_spinning", False)):
                return True
        except Exception:
            return False
        return False

    def _startup_task_tooltips(self) -> None:
        if self._cfg("DISABLE_TOOLTIPS", False):
            self._startup_task_done("tooltip_cache")
            return
        if not self._cfg("TOOLTIP_CACHE_ON_START", False):
            self._startup_task_done("tooltip_cache")
            return
        self._refresh_tooltip_caches_async(
            delay_step_ms=int(self._post_choice_step_ms),
            on_done=lambda: self._startup_task_done("tooltip_cache"),
        )

    def _startup_task_map_prebuild(self) -> None:
        if not self._cfg("MAP_PREBUILD_ON_START", False):
            self._startup_task_done("map_prebuild")
            return
        if getattr(self, "_map_initialized", False) and getattr(self, "_map_lists_ready", False):
            self._startup_task_done("map_prebuild")
            return
        self._startup_waiting_for_map = True
        self._schedule_map_prebuild()

    def _connect_state_signals(self) -> None:
        # JETZT: Save-Hooks anschließen
        for _role, w in self._role_wheels():
            w.stateChanged.connect(self.state_sync.save_state)
            w.btn_include_in_all.toggled.connect(self._update_spin_all_enabled)
            w.stateChanged.connect(self._update_spin_all_enabled)
            w.stateChanged.connect(self._on_wheel_state_changed)
            w.btn_include_in_all.toggled.connect(self._on_role_include_toggled)
            if getattr(w, "toggle", None) is not None:
                w.toggle.stateChanged.connect(self._update_spin_all_enabled)
        if hasattr(self, "map_lists"):
            for w in self.map_lists.values():
                w.stateChanged.connect(self.state_sync.save_state)
                w.btn_include_in_all.toggled.connect(self.state_sync.save_state)
                w.btn_include_in_all.toggled.connect(self._update_spin_all_enabled)
                # Sicherstellen, dass Buttons aktiv bleiben (nicht wie disabled im UI aussehen)
                w.btn_local_spin.setEnabled(True)
                w.btn_include_in_all.setEnabled(True)

    def _finalize_startup(self) -> None:
        if getattr(self, "_startup_finalize_done", False):
            return
        # jetzt darf gespeichert werden
        self._restoring_state = False

        # Buttons initial updaten (nutzt schon include_in_all)
        self._update_spin_all_enabled()
        self._update_cancel_enabled()
        self._apply_mode_results(self._mode_key())
        if bool(self._cfg("STARTUP_VISUAL_FINALIZE_DEFERRED", True)):
            # Keep first paint/input responsive; visual finalize runs once the
            # overlay is gone and the UI is idle.
            self._startup_visual_finalize_pending = True
            # Apply lightweight theme/language updates immediately so widgets
            # don't temporarily render with stale startup colors.
            self._apply_theme(defer_heavy=True)
            self._apply_language(defer_heavy=True)
            self._schedule_startup_visual_finalize()
        else:
            self._apply_theme(defer_heavy=True)
            self._apply_language(defer_heavy=True)
        # Tooltips sofort erlauben (werden später noch einmal frisch berechnet)
        self._set_tooltips_ready(True)
        self._startup_finalize_done = True

    def _on_overlay_closed(self):
        if self.pending <= 0:
            self._set_controls_enabled(True)
        else:
            self._trace_event("overlay_closed_ignored", reason="spin_active", pending=self.pending)
            self._update_cancel_enabled()
        self.sound.stop_ding()
        if self.hero_ban_active:
            self._hero_ban_override_role = None
            self._update_hero_ban_wheel()
        # Ensure hover tracking re-arms after the choice overlay disappears.
        self._schedule_hover_rearm("overlay_closed", force=True)
        self._schedule_hover_rearm("overlay_closed:late", delay_ms=200)
        # Tooltip/Truncation nach finalem Layout aktualisieren
        if not self._cfg("DISABLE_TOOLTIPS", False):
            self._set_tooltips_ready(False)
            self._schedule_tooltip_refresh("overlay_closed", delay_ms=120)
        self._refresh_app_event_filter_state()

    def _on_overlay_disable_results(self):
        last_view = getattr(self.overlay, "_last_view", {}) or {}
        if last_view.get("type") != "result":
            return
        data = last_view.get("data") or ()
        role_wheels_list = self._role_wheels()
        if len(data) != len(role_wheels_list):
            return
        mapping = [(wheel, data[idx]) for idx, (_role, wheel) in enumerate(role_wheels_list)]
        names_to_remove: set[str] = set()
        for wheel, label in mapping:
            if hasattr(wheel, "result_label_names"):
                names_to_remove.update(wheel.result_label_names(label))
            elif isinstance(label, str) and label.strip():
                names_to_remove.add(label.strip())
        if not names_to_remove:
            return
        for _role, wheel in role_wheels_list:
            if hasattr(wheel, "deactivate_names"):
                wheel.deactivate_names(names_to_remove)

    def _on_overlay_delete_names_confirmed(self):
        panel = getattr(self, "_pending_delete_names_panel", None)
        self._pending_delete_names_panel = None
        if panel is None:
            return
        try:
            panel.confirm_delete_marked()
        except Exception:
            return

    def _on_overlay_delete_names_cancelled(self):
        self._pending_delete_names_panel = None

    def _apply_theme(self, defer_heavy: bool = False):
        """Apply the selected light/dark theme without freezing the UI."""
        theme = theme_util.get_theme(getattr(self, "theme", "light"))
        if self._applied_theme_key == theme.key:
            self._theme_heavy_pending = bool(defer_heavy)
            if not defer_heavy and hasattr(self, "btn_theme"):
                self.btn_theme.setEnabled(True)
            return
        theme_util.apply_app_theme(theme)  # einmal zentral, danach in Scheiben

        # Schnelle/kleine Updates sofort
        style_helpers.apply_theme_roles(
            theme,
            (
                (getattr(self, "btn_language", None), "tool.button"),
                (getattr(self, "btn_theme", None), "tool.button"),
                (getattr(self, "title", None), "label.window_title"),
                (getattr(self, "lbl_player_profile", None), "label.section_muted"),
                (getattr(self, "lbl_mode", None), "label.section"),
                (getattr(self, "lbl_anim_duration", None), "label.section"),
                (getattr(self, "lbl_open_count", None), "label.section"),
                (getattr(self, "lbl_open_count_value", None), "label.section"),
                (getattr(self, "summary", None), "label.summary"),
            ),
        )
        self._update_theme_button_label()
        if hasattr(self, "player_profile_dropdown"):
            self.player_profile_dropdown.apply_theme(theme)
        if hasattr(self, "map_ui"):
            # Map UI should switch immediately as well; relying only on the
            # deferred heavy pass can leave stale colors in map mode.
            self.map_ui.apply_theme(theme)
        if getattr(self, "_mode_buttons", None):
            for btn in self._mode_buttons:
                style_helpers.apply_theme_role(btn, theme, "button.mode")
            # Ensure initial checked mode button gets the correct visual state
            # immediately, even before deferred heavy-theme updates run.
            self._update_mode_button_styles(force=True)
        style_helpers.apply_theme_roles(
            theme,
            (
                (getattr(self, "volume_slider", None), "slider.horizontal"),
                (getattr(self, "duration", None), "slider.horizontal"),
                (getattr(self, "open_count_slider", None), "slider.horizontal"),
                (getattr(self, "btn_spin_all", None), "button.primary"),
                (getattr(self, "btn_all_players", None), "button.primary"),
                (getattr(self, "btn_open_q_ocr", None), "button.primary"),
                (getattr(self, "btn_cancel_spin", None), "button.danger"),
            ),
        )
        if hasattr(self, "spin_mode_toggle"):
            self.spin_mode_toggle.apply_theme(theme)
        for btn in self._role_ocr_buttons.values():
            style_helpers.apply_theme_role(btn, theme, "button.primary")
        if hasattr(self, "player_list_panel"):
            self.player_list_panel.apply_theme()
        if hasattr(self, "overlay"):
            tool_style = theme_util.tool_button_stylesheet(theme)
            self.overlay.apply_theme(theme, tool_style)

        self._theme_heavy_pending = bool(defer_heavy)
        self._applied_theme_key = theme.key
        if defer_heavy:
            return
        self._apply_theme_heavy(theme, step_ms=15)

    def _apply_theme_heavy(self, theme: theme_util.Theme, step_ms: int = 15):
        # Größere Widget-Mengen in einem Block aktualisieren, um Timer-Overhead zu sparen.
        del step_ms  # kept in signature for compatibility with existing callers

        targets = []
        for _role, wheel in self._role_wheels():
            if wheel and hasattr(wheel, "apply_theme"):
                targets.append(wheel)

        freeze_targets: list[QtWidgets.QWidget] = []
        for candidate in (
            self.centralWidget(),
            getattr(self, "role_container", None),
            getattr(self, "map_container", None),
        ):
            if isinstance(candidate, QtWidgets.QWidget):
                freeze_targets.append(candidate)
        dedup: list[QtWidgets.QWidget] = []
        seen_ids: set[int] = set()
        for widget in freeze_targets:
            wid = id(widget)
            if wid in seen_ids:
                continue
            seen_ids.add(wid)
            dedup.append(widget)

        for widget in dedup:
            widget.setUpdatesEnabled(False)
        try:
            for wheel in targets:
                wheel.apply_theme(theme)
            if hasattr(self, "map_ui"):
                self.map_ui.apply_theme(theme)
            self._update_mode_button_styles(force=True)
        finally:
            for widget in dedup:
                widget.setUpdatesEnabled(True)
                widget.update()

        # Theme-Button wieder freigeben, falls er kurz deaktiviert wurde.
        if hasattr(self, "btn_theme"):
            self.btn_theme.setEnabled(True)

    def _update_mode_button_styles(self, *_args, force: bool = False):
        """
        Polisht nur Buttons, deren checked-Zustand sich geändert hat, um
        unnötige Reflows bei Theme-/UI-Updates zu vermeiden.
        """
        if not getattr(self, "_mode_buttons", None):
            return
        checked_cache = getattr(self, "_mode_button_checked_cache", {})
        for btn in self._mode_buttons:
            checked = bool(btn.isChecked())
            cache_key = id(btn)
            if not force and checked_cache.get(cache_key) == checked:
                continue
            style = btn.style()
            if style is not None:
                style.unpolish(btn)
                style.polish(btn)
            btn.updateGeometry()
            checked_cache[cache_key] = checked
        self._mode_button_checked_cache = checked_cache

    def _capture_role_base_widths(self):
        """Merkt sich die aktuelle Breite jeder Rollen-Karte als Referenz."""
        widths: dict[str, int] = {}
        for name, widget in self._role_wheels():
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
        for name, widget in self._role_wheels():
            base = self._role_base_widths.get(name, widget.sizeHint().width() or widget.width())
            if lock:
                fixed = max(1, int(base))
                widget.setMinimumWidth(fixed)
                widget.setMaximumWidth(fixed)
            else:
                widget.setMinimumWidth(0)
                widget.setMaximumWidth(QWIDGETSIZE_MAX)

    def resizeEvent(self, e: QtGui.QResizeEvent):
        super().resizeEvent(e); 
        if self.overlay and self.centralWidget():
            self.overlay.setGeometry(self.centralWidget().rect())
        if hasattr(self, "player_list_panel"):
            self.player_list_panel.on_resize()

    def _mode_key(self) -> str:
        return result_state_ops.mode_key(self)

    def _snapshot_mode_results(self):
        result_state_ops.snapshot_mode_results(self)

    def _apply_mode_results(self, key: str):
        result_state_ops.apply_mode_results(self, key)

    def _update_summary_from_results(self):
        result_state_ops.update_summary_from_results(self)

    def _refresh_tooltip_caches_async(
        self,
        delay_step_ms: int = 80,
        on_done: Callable[[], None] | None = None,
        reason: str | None = None,
        force: bool = False,
    ):
        hover_tooltip_ops.refresh_tooltip_caches_async(
            self,
            delay_step_ms=delay_step_ms,
            on_done=on_done,
            reason=reason,
            force=force,
        )

    def _reset_hover_cache_under_cursor(self):
        hover_tooltip_ops.reset_hover_cache_under_cursor(self)

    def _set_tooltips_ready(self, ready: bool = True):
        hover_tooltip_ops.set_tooltips_ready(self, ready=ready)

    def _set_hero_ban_visuals(self, active: bool):
        """Delegiert an den Mode-Manager und sperrt Breiten in Hero-Ban."""
        self._apply_role_width_lock(active)
        mode_manager.set_hero_ban_visuals(self, active)

    def _on_role_ocr_import_clicked(self, role_key: str) -> None:
        from . import ocr_capture_ops

        ocr_capture_ops.on_role_ocr_import_clicked(self, role_key)

    def _on_open_q_ocr_clicked(self) -> None:
        if not self._role_ocr_import_available("all"):
            return
        if hasattr(self, "btn_open_q_ocr"):
            self.btn_open_q_ocr.setEnabled(False)
        self._on_role_ocr_import_clicked("all")
        self._update_role_ocr_buttons_enabled()

    def _snapshot_results(self):
        result_state_ops.snapshot_results(self)

    def _restore_results_snapshot(self):
        result_state_ops.restore_results_snapshot(self)

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
        return StateSyncController.state_file(self._state_dir)

    def _load_mode_into_wheels(self, mode: str, hero_ban: bool = False):
        """Wendet den gespeicherten Zustand eines Modus auf die UI an."""
        state = self._state_store.get_mode_state(mode)
        if not state:
            return
        prev_restoring = getattr(self, "_restoring_state", False)
        self._restoring_state = True
        try:
            for role, wheel in self._role_wheels():
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
            for _role, w in self._role_wheels():
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
        if self._post_choice_input_guard_active():
            self._trace_event("mode_switch_ignored", target=target, reason="mode_choice_input_guard")
            return
        if not self._post_choice_init_done and not self._overlay_choice_active():
            self._ensure_post_choice_ready()
        if target != "maps" and getattr(self, "_pending_map_mode_switch", False):
            self._pending_map_mode_switch = False
            self._trace_event("mode_switch_cancelled", target=target)
        if target == "maps" and not getattr(self, "_map_lists_ready", False):
            self._trace_event("mode_switch_deferred", target=target)
            self._pending_map_mode_switch = True
            self._schedule_map_prebuild(force=True)
            self._set_map_button_loading(True, reason="mode_switch_deferred")
            self._set_map_button_enabled(False)
            return
        if target == "maps":
            self._pending_map_mode_switch = False
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
                role_wheel_map(self),
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
        if not self._cfg("DISABLE_TOOLTIPS", False) and not self._cfg("TOOLTIP_CACHE_ON_START", False):
            self._refresh_tooltip_caches_async()

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
        if hasattr(self, "lbl_player_profile"):
            self.lbl_player_profile.setText(i18n.t("players.profile_label"))
        if hasattr(self, "player_profile_dropdown"):
            self._refresh_player_profile_combo()
        self.lbl_mode.setText(i18n.t("label.mode"))
        self.lbl_mode.setToolTip(i18n.t("label.mode_tooltip"))
        self.btn_mode_players.setText(i18n.t("mode.players"))
        self.btn_mode_players.setToolTip(i18n.t("mode.players_tooltip"))
        self.btn_mode_heroes.setText(i18n.t("mode.heroes"))
        self.btn_mode_heroes.setToolTip(i18n.t("mode.heroes_tooltip"))
        self.btn_mode_heroban.setText(i18n.t("mode.hero_ban"))
        self.btn_mode_heroban.setToolTip(i18n.t("mode.hero_ban_tooltip"))
        if getattr(self, "_map_button_loading", False):
            self.btn_mode_maps.setText(i18n.t("mode.maps_loading"))
        else:
            self.btn_mode_maps.setText(i18n.t("mode.maps"))
        self.btn_mode_maps.setToolTip(i18n.t("mode.maps_tooltip"))
        self.lbl_volume_icon.setToolTip(i18n.t("volume.icon_tooltip"))
        self.volume_slider.setToolTip(i18n.t("volume.slider_tooltip"))
        self.btn_spin_all.setText(i18n.t("controls.spin_all"))
        self.btn_spin_all.setToolTip(i18n.t("controls.spin_all_tooltip"))
        if hasattr(self, "spin_mode_toggle"):
            self.spin_mode_toggle.setToolTip(i18n.t("controls.spin_mode_tooltip"))
        self.btn_cancel_spin.setText(i18n.t("controls.cancel_spin"))
        self.btn_cancel_spin.setToolTip(i18n.t("controls.cancel_spin_tooltip"))
        self.lbl_anim_duration.setText(i18n.t("controls.anim_duration"))
        self.duration.setToolTip(i18n.t("controls.anim_duration_tooltip"))
        if hasattr(self, "lbl_open_count"):
            self.lbl_open_count.setText(i18n.t("controls.open_count_label"))
            self.lbl_open_count.setToolTip(i18n.t("controls.open_count_tooltip"))
        if hasattr(self, "open_count_slider"):
            self.open_count_slider.setToolTip(i18n.t("controls.open_count_tooltip"))
        if hasattr(self, "lbl_open_count_value"):
            self.lbl_open_count_value.setToolTip(i18n.t("controls.open_count_tooltip"))
        if hasattr(self, "btn_all_players"):
            self.btn_all_players.setText(i18n.t("players.list_button"))
            self.btn_all_players.setToolTip(i18n.t("players.list_button_tooltip"))
            ui_helpers.set_fixed_width_from_translations([self.btn_all_players], ["players.list_button"], padding=40)
        if hasattr(self, "btn_open_q_ocr"):
            self.btn_open_q_ocr.setText(i18n.t("ocr.open_q_button"))
            self.btn_open_q_ocr.setToolTip(i18n.t("ocr.open_q_button_tooltip"))
            ui_helpers.set_fixed_width_from_translations([self.btn_open_q_ocr], ["ocr.open_q_button"], padding=40)
        self._refresh_all_role_ocr_button_texts()
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
        for _role, w in self._role_wheels():
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
        self._flush_blocked_input_stats("mode_choice")
        self._flush_hover_prime_deferred_trace()
        self._arm_post_choice_input_guard(reason="mode_choice")
        self._refresh_app_event_filter_state()
        self._hover_prime_pending = False
        self._hover_prime_reason = None
        self.online_mode = online
        self._set_controls_enabled(True)
        self._set_heavy_ui_updates_enabled(True)
        warmup_done = bool(getattr(self, "_startup_warmup_done", False))
        self._post_choice_init_done = warmup_done
        if warmup_done:
            elapsed = None
            if self._choice_shown_at is not None:
                elapsed = round(time.monotonic() - self._choice_shown_at, 3)
            self._trace_event(
                "apply_mode_choice",
                online=online,
                elapsed=elapsed,
                delay_ms=0,
                warmup_done=True,
            )
        else:
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
        # Ensure hover tracking is active right after mode choice (no focus changes).
        self._schedule_hover_rearm("mode_choice")
        self._schedule_hover_rearm("mode_choice:late", delay_ms=250)
        self._hover_seen = False
        # Force a short hover pump so hover becomes responsive even if the cursor didn't move.
        self._start_hover_pump(reason="mode_choice", duration_ms=2000, force=True)

        if self.online_mode:
            config.debug_print("Online-Modus aktiv.")
        else:
            config.debug_print("Offline-Modus aktiv.")
        # Sync ggf. neu einplanen oder abbrechen
        self.state_sync.sync_all_roles()
        if bool(getattr(self, "_startup_visual_finalize_pending", False)):
            self._schedule_startup_visual_finalize(
                delay_ms=int(self._cfg("STARTUP_VISUAL_FINALIZE_DELAY_MS", 280))
            )
        self._schedule_wheel_cache_warmup(delay_ms=120)
        self._refresh_app_event_filter_state()

    def _set_heavy_ui_updates_enabled(self, enabled: bool) -> None:
        """Defer expensive wheel painting while the mode-choice overlay is visible."""
        self._trace_event("set_heavy_ui_updates", enabled=enabled)
        wheels_to_update = [wheel for _role, wheel in self._role_wheels()]
        wheels_to_update.append(getattr(self, "map_main", None))
        for w in wheels_to_update:
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
        if (
            int(getattr(self, "pending", 0) or 0) > 0
            or bool(getattr(self, "_background_services_paused", False))
            or self._has_active_spin_animations(include_internal_flags=True)
        ):
            retry_ms = max(20, int(self._cfg("POST_CHOICE_INIT_BUSY_RETRY_MS", 220)))
            self._trace_event(
                "run_post_choice_init:defer_busy",
                pending=int(getattr(self, "pending", 0) or 0),
                retry_ms=retry_ms,
            )
            self._schedule_post_choice_init(retry_ms)
            return
        self._trace_event("run_post_choice_init:start")
        self._set_tooltips_ready(True)
        self._flush_pending_heavy_ui_updates(step_ms=int(self._post_choice_step_ms))
        self._warmup_sound_async_if_enabled(step_ms=int(self._post_choice_warmup_step_ms))
        if self._cfg("TOOLTIP_CACHE_ON_START", False) and not self._cfg("DISABLE_TOOLTIPS", False):
            self._refresh_tooltip_caches_async(delay_step_ms=int(self._post_choice_step_ms))
        self._schedule_map_prebuild()
        self._post_choice_init_done = True
        self._schedule_wheel_cache_warmup(delay_ms=0)
        self._sync_mode_stack()
        self._trace_event("run_post_choice_init:done")
        self._refresh_app_event_filter_state()

    def _schedule_map_prebuild(self, force: bool = False) -> None:
        if getattr(self, "_closing", False):
            return
        if not self._cfg("MAP_PREBUILD_ON_START", False) and not force:
            return
        if getattr(self, "_map_initialized", False) or getattr(self, "_map_prebuild_in_progress", False):
            return
        self._set_map_button_enabled(False)
        self._set_map_button_loading(True, reason="prebuild_start")
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
        self._set_map_button_loading(False, reason="lists_ready")
        self._set_map_button_enabled(True)
        self._trace_event("map_prebuild:done")
        self._apply_focus_policy_defaults()
        self._rearm_hover_tracking(reason="map_prebuild:done")
        if getattr(self, "_pending_map_mode_switch", False):
            self._pending_map_mode_switch = False
            QtCore.QTimer.singleShot(0, lambda: self._on_mode_button_clicked("maps"))
        if getattr(self, "_startup_waiting_for_map", False):
            self._startup_waiting_for_map = False
            self._startup_task_done("map_prebuild")

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
        # Stack-Wechsel kann Hover-Eingaenge verlieren -> Pump nach dem Wechsel neu starten.
        self._hover_seen = False
        self._hover_forward_last = None
        self._rearm_hover_tracking(reason="stack_switching:done")
        self._schedule_hover_rearm("stack_switching:late", delay_ms=250)

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

    def _merge_shutdown_snapshot(self, prefix: str, payload: dict | None, target: dict) -> None:
        shutdown_manager.merge_shutdown_snapshot(prefix, payload, target)

    def _shutdown_resource_snapshot(self) -> dict:
        return shutdown_manager.shutdown_resource_snapshot(self)

    def _run_shutdown_step(self, step: str, callback: Callable[[], None]) -> None:
        shutdown_manager.run_shutdown_step(self, step, callback)

    def _ensure_close_overlay_timer(self) -> QtCore.QTimer:
        timer = getattr(self, "_close_overlay_timer", None)
        if timer is not None:
            return timer
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._continue_close_after_overlay)
        if hasattr(self, "_timers"):
            self._timers.register(timer)
        self._close_overlay_timer = timer
        return timer

    def _continue_close_after_overlay(self) -> None:
        if not bool(getattr(self, "_close_overlay_active", False)):
            return
        self._close_overlay_active = False
        self._close_overlay_done = True
        overlay = getattr(self, "overlay", None)
        if overlay is not None:
            try:
                overlay.setEnabled(True)
                overlay.hide()
            except Exception:
                pass
        self.close()

    def _show_close_overlay(self) -> bool:
        if not bool(self._cfg("SHUTDOWN_OVERLAY_ENABLED", True)):
            return False
        delay_ms = max(0, int(self._cfg("SHUTDOWN_OVERLAY_DELAY_MS", 320)))
        if delay_ms <= 0:
            return False
        overlay = getattr(self, "overlay", None)
        if overlay is None:
            return False
        try:
            overlay.show_status_message(
                i18n.t("overlay.shutdown_title"),
                [i18n.t("overlay.shutdown_line1"), i18n.t("overlay.shutdown_line2"), ""],
            )
            overlay.setEnabled(False)
        except Exception:
            return False
        self._close_overlay_active = True
        self._close_overlay_done = False
        timer = self._ensure_close_overlay_timer()
        timer.start(delay_ms)
        return True

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if not getattr(self, "_closing", False):
            if bool(getattr(self, "_close_overlay_active", False)):
                event.ignore()
                return
            if not bool(getattr(self, "_close_overlay_done", False)):
                if self._show_close_overlay():
                    event.ignore()
                    return

        timer = getattr(self, "_close_overlay_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
        overlay = getattr(self, "overlay", None)
        if overlay is not None:
            try:
                overlay.setEnabled(True)
                overlay.hide()
            except Exception:
                pass

        job = getattr(self, "_ocr_async_job", None)
        if isinstance(job, dict):
            for path in list(job.get("paths") or []):
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass
            thread = job.get("thread")
            try:
                if thread is not None and thread.isRunning():
                    thread.quit()
                    thread.wait(300)
            except Exception:
                pass
            self._ocr_async_job = None
        if hasattr(self, "_cancel_ocr_runtime_cache_release"):
            try:
                self._cancel_ocr_runtime_cache_release()
            except Exception:
                pass
        if hasattr(self, "_release_ocr_runtime_cache"):
            try:
                self._release_ocr_runtime_cache()
            except Exception:
                pass
        self._set_app_event_filter_enabled(False)
        shutdown_manager.handle_close_event(self, event)

    def _trace_event(self, name: str, **extra) -> None:
        runtime_tracing.trace_event(self, name, **extra)
