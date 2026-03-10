from __future__ import annotations

import time

from PySide6 import QtCore, QtWidgets

from .focus_policy import FocusPolicyManager
from .ocr.pipeline.role_import import PendingOCRImport
from .state_sync import StateSyncController
from .timer_registry import TimerRegistry
from .tooltip_manager import TooltipManager
from model.main_window_runtime_state import ShutdownRuntimeState, StartupRuntimeState
from model.mode_keys import AppMode
from services import state_store


class MainWindowRuntimeSetupMixin:
    """Builds runtime state, timers and controllers used after bootstrapping."""

    def _init_runtime_state_and_services(self, saved: dict) -> None:
        self._init_mode_runtime_state(saved)
        self._init_startup_runtime_state()
        self._init_focus_hover_runtime_state()
        self._init_trace_runtime_state()
        self._init_runtime_managers_and_timers()
        self._init_ocr_runtime_state()

    def _init_mode_runtime_state(self, saved: dict) -> None:
        self._restoring_state = True
        self._player_profile_combo_syncing = False
        self.current_mode = AppMode.PLAYERS.value
        self.last_non_hero_mode = AppMode.PLAYERS.value
        self.hero_ban_active = False
        self._hero_ban_rebuild = False
        self._hero_ban_pending = False
        self._hero_ban_override_role: str | None = None
        self._role_base_widths: dict[str, int] = {}
        self._state_store = state_store.ModeStateStore.from_saved(saved, settings=self.settings)
        self._mode_results: dict[str, dict[str, str]] = {}
        self.state_sync = StateSyncController(self, self._state_file)
        self._mode_choice_locked = False
        self._startup_state = StartupRuntimeState()
        self._shutdown_state = ShutdownRuntimeState()
        self._sync_startup_runtime_attrs()
        self._sync_shutdown_runtime_attrs()
        self._choice_shown_at: float | None = None

    def _init_startup_runtime_state(self) -> None:
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

    def _init_focus_hover_runtime_state(self) -> None:
        self._focus_trace_enabled = self._trace_bool("focus", "TRACE_FOCUS", False)
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
        self._hover_trace_enabled = self._trace_bool("hover", "TRACE_HOVER", False)
        self._hover_trace_count = 0
        self._hover_trace_max_events = int(self._cfg("HOVER_TRACE_MAX_EVENTS", 200))
        self._hover_trace_last_t: float | None = None
        self._hover_trace_file = self._log_dir / "hover_trace.log"
        self._write_trace_run_header(self._hover_trace_enabled, self._hover_trace_file)
        self._hover_forward_last: float | None = None
        self._hover_forwarding = False
        self._hover_seen = False
        self._hover_activity_last: float | None = None
        self._hover_user_move_last: float | None = None
        self._hover_prime_pending = False
        self._hover_prime_reason: str | None = None
        self._hover_prime_deferred_count = 0
        self._hover_prime_first_reason: str | None = None
        self._hover_prime_last_reason: str | None = None
        self._hover_pump_until: float | None = None
        self._hover_pump_timer: QtCore.QTimer | None = None
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
        self._blocked_input_total = 0
        self._blocked_input_counts: dict[int, int] = {}
        self._blocked_input_first_t: float | None = None
        self._blocked_input_last_t: float | None = None
        self._startup_drain_timer: QtCore.QTimer | None = None
        self._drained_input_total = 0
        self._drained_input_counts: dict[int, int] = {}
        self._drained_input_first_t: float | None = None
        self._drained_input_last_t: float | None = None
        self._focus_trace_file = self._log_dir / "focus_trace.log"
        self._write_trace_run_header(self._focus_trace_enabled, self._focus_trace_file)

    def _init_trace_runtime_state(self) -> None:
        self._trace_enabled = bool(
            self._trace_bool("flow", "TRACE_FLOW", False)
            or self._trace_bool("shutdown", "TRACE_SHUTDOWN", False)
            or self._runtime_bool("debug", "DEBUG", False)
        )
        self._trace_last_t: float | None = None
        self._trace_file = self._log_dir / "flow_trace.log"
        self._spin_perf_enabled = self._trace_bool("spin_perf", "TRACE_SPIN_PERF", False)
        self._spin_perf_file = self._log_dir / "spin_perf.log"
        self._write_trace_run_header(self._spin_perf_enabled, self._spin_perf_file)
        if self._trace_enabled:
            self._trace_event("startup", run_id=self._run_id)
        if self._runtime_bool("disable_tooltips", "DISABLE_TOOLTIPS", False):
            try:
                QtWidgets.QToolTip.setEnabled(False)
            except (AttributeError, RuntimeError):
                pass

    def _init_runtime_managers_and_timers(self) -> None:
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
        self._tooltip_manager = TooltipManager(self)
        self._focus_policy = FocusPolicyManager(self)
        self._pending_delete_names_panel = None

    def _init_ocr_runtime_state(self) -> None:
        self._pending_ocr_import: PendingOCRImport | None = None
        self._ocr_async_job = None
        self._ocr_runtime_activated = False
        self._ocr_preload_job = None
        self._ocr_preload_done = False
        self._ocr_preload_attempted = False
        self._role_ocr_buttons: dict[str, QtWidgets.QPushButton] = {}
