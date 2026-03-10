from pathlib import Path
import os
import time
from typing import Callable

from PySide6 import QtCore, QtWidgets

import i18n
from . import (
    hover_tooltip_ops,
    result_state_ops,
    runtime_tracing,
)
from .main_window_parts.main_window_input import MainWindowInputMixin
from .main_window_parts.main_window_appearance import MainWindowAppearanceMixin
from .main_window_parts.main_window_background import MainWindowBackgroundMixin
from .main_window_parts.main_window_mode import MainWindowModeMixin
from .main_window_parts.main_window_ocr import MainWindowOCRMixin
from .main_window_parts.main_window_shutdown import MainWindowShutdownMixin
from .main_window_parts.main_window_sound import MainWindowSoundMixin
from .main_window_parts.main_window_startup import MainWindowStartupMixin
from .main_window_parts.main_window_state import MainWindowStateMixin
from .main_window_parts.main_window_spin import MainWindowSpinMixin
from .main_window_runtime_bridge import MainWindowRuntimeBridgeMixin
from .main_window_ui_builder import MainWindowUIBuilderMixin
from .ocr.ocr_role_import import PendingOCRImport
from services import state_store
from services.app_settings import AppSettings
from services import settings_provider
from model.main_window_runtime_state import ShutdownRuntimeState, StartupRuntimeState
from model.mode_keys import AppMode
from model.role_keys import role_wheels
from utils import theme as theme_util
from .state_sync import StateSyncController
from .tooltip_manager import TooltipManager
from .focus_policy import FocusPolicyManager
from .timer_registry import TimerRegistry


class MainWindow(
    MainWindowRuntimeBridgeMixin,
    MainWindowUIBuilderMixin,
    MainWindowStateMixin,
    MainWindowShutdownMixin,
    MainWindowAppearanceMixin,
    MainWindowModeMixin,
    MainWindowOCRMixin,
    MainWindowSoundMixin,
    MainWindowStartupMixin,
    MainWindowBackgroundMixin,
    MainWindowSpinMixin,
    MainWindowInputMixin,
    QtWidgets.QMainWindow,
):
    def __init__(self, settings: AppSettings | None = None):
        super().__init__()
        # Basisverzeichnisse bestimmen (Assets vs. writable state) und gespeicherten Zustand laden
        self._asset_dir = self._asset_base_dir()
        self._state_dir = self._state_base_dir()
        self._state_file = self._get_state_file()
        resolved_settings = settings if isinstance(settings, AppSettings) else settings_provider.get_settings()
        if not isinstance(resolved_settings, AppSettings):
            resolved_settings = AppSettings(values={})
        # Backward-compatible fallback for environments that still instantiate
        # MainWindow without bootstrapping the shared settings provider.
        if not resolved_settings.values:
            try:
                import config as app_config
            except ImportError:
                pass
            else:
                resolved_settings = AppSettings.from_module(app_config)
                settings_provider.set_settings(resolved_settings)
        self.settings = resolved_settings
        self._quiet_mode = self._runtime_bool("quiet", "QUIET", False)
        configured_log_dir = self._runtime_str("log_output_dir", "LOG_OUTPUT_DIR", "logs").strip()
        log_root = Path(configured_log_dir) if configured_log_dir else Path()
        if not configured_log_dir:
            log_root = self._state_dir
        elif not log_root.is_absolute():
            log_root = self._state_dir / log_root
        self._log_dir = log_root
        if not self._quiet_mode:
            try:
                self._log_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                self._log_dir = self._state_dir
        self._run_id = f"{int(time.time() * 1000)}_{os.getpid()}"
        saved = StateSyncController.load_saved_state(self._state_file)
        default_lang = self._runtime_str("default_language", "DEFAULT_LANGUAGE", "en")
        self.language = saved.get("language", default_lang) if isinstance(saved, dict) else default_lang
        i18n.set_language(self.language)
        self.theme = saved.get("theme", "light") if isinstance(saved, dict) else "light"
        if self.theme not in theme_util.THEMES:
            self.theme = "light"
        # Apply palette/global stylesheet baseline early so startup overlays/widgets
        # pick the persisted theme immediately.
        try:
            theme_util.apply_app_theme(
                theme_util.get_theme(self.theme),
                force_fusion_style=bool(self._cfg("FORCE_FUSION_STYLE", False)),
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass

        self.setWindowTitle(i18n.t("app.title.main"))
        self.resize(1200, 650)
        self._init_sound_manager()

        self._restoring_state = True   # während des Aufbaus nicht speichern
        self._player_profile_combo_syncing = False
        self.current_mode = AppMode.PLAYERS.value  # immer mit Spieler-Auswahl starten
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
        self._pending_ocr_import: PendingOCRImport | None = None
        self._ocr_async_job = None
        self._ocr_runtime_activated = False
        self._ocr_preload_job = None
        self._ocr_preload_done = False
        self._ocr_preload_attempted = False
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
        except (AttributeError, RuntimeError):
            pass

    def _cfg(self, key: str, default=None):
        settings = getattr(self, "settings", None)
        if settings is not None and hasattr(settings, "resolve"):
            try:
                return settings.resolve(key, default)
            except (AttributeError, TypeError, ValueError):
                pass
        if settings is not None and hasattr(settings, "get"):
            try:
                return settings.get(key, default)
            except (AttributeError, TypeError):
                pass
        try:
            import config as app_config
        except ImportError:
            return default
        return getattr(app_config, key, default)

    def _runtime_settings(self):
        settings = getattr(self, "settings", None)
        return getattr(settings, "runtime", None)

    def _trace_settings(self):
        settings = getattr(self, "settings", None)
        return getattr(settings, "trace", None)

    def _spin_ui_settings(self):
        settings = getattr(self, "settings", None)
        return getattr(settings, "spin_ui", None)

    def _runtime_bool(self, attr: str, key: str, default: bool) -> bool:
        section = self._runtime_settings()
        if section is not None and hasattr(section, attr):
            try:
                return bool(getattr(section, attr))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg(key, default))

    def _runtime_str(self, attr: str, key: str, default: str) -> str:
        section = self._runtime_settings()
        if section is not None and hasattr(section, attr):
            value = str(getattr(section, attr, default) or "").strip()
            return value or str(default)
        value = str(self._cfg(key, default) or "").strip()
        return value or str(default)

    def _trace_bool(self, attr: str, key: str, default: bool) -> bool:
        section = self._trace_settings()
        if section is not None and hasattr(section, attr):
            try:
                return bool(getattr(section, attr))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg(key, default))

    def _spin_ui_bool(self, attr: str, key: str, default: bool) -> bool:
        section = self._spin_ui_settings()
        if section is not None and hasattr(section, attr):
            try:
                return bool(getattr(section, attr))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg(key, default))

    def _debug_print(self, *args, **kwargs) -> None:
        if not self._runtime_bool("debug", "DEBUG", False):
            return
        if self._runtime_bool("quiet", "QUIET", False):
            return
        try:
            print(*args, **kwargs)
        except OSError:
            pass

    def _write_trace_run_header(self, enabled: bool, trace_file: Path) -> None:
        if not enabled:
            return
        try:
            trace_file.parent.mkdir(parents=True, exist_ok=True)
            if self._trace_bool("clear_on_start", "TRACE_CLEAR_ON_START", False):
                trace_file.write_text("", encoding="utf-8")
            with trace_file.open("a", encoding="utf-8") as handle:
                handle.write(f"=== run {self._run_id} ===\n")
        except OSError:
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
        if not self._runtime_bool("disable_tooltips", "DISABLE_TOOLTIPS", False):
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
        except (AttributeError, RuntimeError):
            return

    def _on_overlay_delete_names_cancelled(self):
        self._pending_delete_names_panel = None

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

    def _set_tooltips_ready(self, ready: bool = True):
        hover_tooltip_ops.set_tooltips_ready(self, ready=ready)

    def _on_role_ocr_import_clicked(self, role_key: str) -> None:
        from .ocr import ocr_capture_ops

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

    def _trace_event(self, name: str, **extra) -> None:
        runtime_tracing.trace_event(self, name, **extra)
