from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"1", "true", "yes", "on"}:
            return True
        if token in {"0", "false", "no", "off", ""}:
            return False
    return bool(default if value is None else value)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coerce_str(value: Any, default: str = "") -> str:
    text = str(value if value is not None else "").strip()
    if text:
        return text
    return str(default)


@dataclass(frozen=True)
class RuntimeSettings:
    debug: bool = False
    quiet: bool = False
    log_output_dir: str = "logs"
    default_language: str = "en"
    windows_single_instance: bool = True
    windows_single_instance_lock_name: str = "ow_wheelpicker_instance"
    force_fusion_style: bool = False
    disable_tooltips: bool = False


@dataclass(frozen=True)
class TraceSettings:
    flow: bool = False
    shutdown: bool = False
    focus: bool = False
    hover: bool = False
    spin_perf: bool = False
    clear_on_start: bool = False
    ocr_runtime: bool = False


@dataclass(frozen=True)
class StartupSettings:
    mode_choice_input_guard_ms: int = 220
    mode_choice_online_enabled: bool = False
    startup_finalize_delay_ms: int = 60
    startup_warmup_cooldown_ms: int = 0
    startup_input_drain_ms: int = 0
    startup_min_block_input_ms: int = 0
    startup_drop_choice_pointer_events: bool = True
    startup_clear_focus_while_blocked: bool = True
    startup_visual_finalize_deferred: bool = True
    startup_visual_finalize_delay_ms: int = 280
    startup_visual_finalize_busy_retry_ms: int = 250
    startup_wheel_cache_warmup: bool = True
    startup_ocr_preload: bool = False
    startup_ocr_preload_max_wait_ms: int = 1800
    startup_ocr_preload_running_max_wait_ms: int = 14000
    startup_map_prebuild_max_wait_ms: int = 2200
    map_prebuild_on_start: bool = True


@dataclass(frozen=True)
class ShutdownSettings:
    overlay_enabled: bool = True
    overlay_delay_ms: int = 320
    blocker_trace_interval_ms: int = 250
    ocr_async_graceful_wait_ms: int = 1200
    ocr_async_terminate_wait_ms: int = 700
    ocr_preload_graceful_wait_ms: int = 1400
    ocr_preload_terminate_wait_ms: int = 350
    ocr_preload_force_stop_on_close: bool = False
    child_thread_graceful_wait_ms: int = 350
    child_thread_terminate_wait_ms: int = 250
    thread_max_defer_ms: int = 2500
    ocr_preload_max_defer_ms: int = 1200
    ocr_async_max_defer_ms: int = 1500
    child_thread_max_defer_ms: int = 1200
    python_thread_max_defer_ms: int = 1800
    app_quit_guard_ms: int = 1500
    app_force_exit_loop_ms: int = 2400
    keep_window_visible_until_exit: bool = False
    force_exit_watchdog_enabled: bool = False
    force_exit_watchdog_ms: int = 12000
    force_exit_on_orphan_ms: int = 2200
    release_ocr_cache: bool = False


@dataclass(frozen=True)
class OcrSettings:
    engine: str = "easyocr"
    easyocr_lang: str = "en,de,ja,ch_sim,ko"
    easyocr_model_dir: str = ""
    easyocr_user_network_dir: str = ""
    easyocr_gpu: str = "auto"
    easyocr_download_enabled: bool = False
    timeout_s: float = 8.0
    timeout_s_windows: float = 6.0
    runtime_sleep_until_used: bool = True
    background_preload_enabled: bool = True
    background_preload_delay_ms: int = 2500
    background_preload_min_uptime_ms: int = 8000
    background_preload_allow_during_startup: bool = True
    background_preload_busy_retry_ms: int = 1800
    preload_subprocess_timeout_s: float = 60.0
    preload_use_subprocess_probe: bool = True
    preload_use_subprocess_probe_win_frozen: bool = False
    preload_inprocess_cache_warmup: bool = True
    preload_cancel_running_on_spin: bool = False
    idle_cache_release_ms: int = 30000
    idle_cache_release_busy_retry_ms: int = 2500
    release_cache_on_spin: bool = False
    debug_show_report: bool = False
    debug_log_to_file: bool = True


@dataclass(frozen=True)
class SpinUiSettings:
    min_duration_ms: int = 0
    max_duration_ms: int = 10000
    default_duration_ms: int = 3000
    spin_watchdog_enabled: bool = False
    spin_lightweight_ui_lock: bool = True


@dataclass(frozen=True)
class NetworkSettings:
    state_save_debounce_ms: int = 220
    network_sync_debounce_ms: int = 220
    network_sync_workers: int = 2
    api_base_url: str = "http://localhost:5326"


@dataclass
class AppSettings:
    values: dict[str, Any]
    runtime: RuntimeSettings = field(init=False)
    trace: TraceSettings = field(init=False)
    startup: StartupSettings = field(init=False)
    shutdown: ShutdownSettings = field(init=False)
    ocr: OcrSettings = field(init=False)
    spin_ui: SpinUiSettings = field(init=False)
    network: NetworkSettings = field(init=False)
    _typed_index: dict[str, Any] = field(init=False, repr=False, default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.values, dict):
            self.values = {}
        self._rebuild_sections()

    @classmethod
    def from_module(cls, module: Any) -> "AppSettings":
        if module is None:
            return cls(values={})
        try:
            source = vars(module)
        except TypeError:
            source = {}
        data = {
            key: value
            for key, value in source.items()
            if isinstance(key, str) and key.isupper()
        }
        return cls(values=dict(data))

    def _rebuild_sections(self) -> None:
        values = self.values
        self.runtime = RuntimeSettings(
            debug=_coerce_bool(values.get("DEBUG", False)),
            quiet=_coerce_bool(values.get("QUIET", False)),
            log_output_dir=_coerce_str(values.get("LOG_OUTPUT_DIR", "logs"), "logs"),
            default_language=_coerce_str(values.get("DEFAULT_LANGUAGE", "en"), "en").lower(),
            windows_single_instance=_coerce_bool(values.get("WINDOWS_SINGLE_INSTANCE", True)),
            windows_single_instance_lock_name=_coerce_str(
                values.get("WINDOWS_SINGLE_INSTANCE_LOCK_NAME", "ow_wheelpicker_instance"),
                "ow_wheelpicker_instance",
            ),
            force_fusion_style=_coerce_bool(values.get("FORCE_FUSION_STYLE", False)),
            disable_tooltips=_coerce_bool(values.get("DISABLE_TOOLTIPS", False)),
        )
        self.trace = TraceSettings(
            flow=_coerce_bool(values.get("TRACE_FLOW", False)),
            shutdown=_coerce_bool(values.get("TRACE_SHUTDOWN", False)),
            focus=_coerce_bool(values.get("TRACE_FOCUS", False)),
            hover=_coerce_bool(values.get("TRACE_HOVER", False)),
            spin_perf=_coerce_bool(values.get("TRACE_SPIN_PERF", False)),
            clear_on_start=_coerce_bool(values.get("TRACE_CLEAR_ON_START", False)),
            ocr_runtime=_coerce_bool(values.get("TRACE_OCR_RUNTIME", False)),
        )
        self.startup = StartupSettings(
            mode_choice_input_guard_ms=max(0, _coerce_int(values.get("MODE_CHOICE_INPUT_GUARD_MS", 220), 220)),
            mode_choice_online_enabled=_coerce_bool(values.get("MODE_CHOICE_ONLINE_ENABLED", False)),
            startup_finalize_delay_ms=max(0, _coerce_int(values.get("STARTUP_FINALIZE_DELAY_MS", 60), 60)),
            startup_warmup_cooldown_ms=max(0, _coerce_int(values.get("STARTUP_WARMUP_COOLDOWN_MS", 0), 0)),
            startup_input_drain_ms=max(0, _coerce_int(values.get("STARTUP_INPUT_DRAIN_MS", 0), 0)),
            startup_min_block_input_ms=max(0, _coerce_int(values.get("STARTUP_MIN_BLOCK_INPUT_MS", 0), 0)),
            startup_drop_choice_pointer_events=_coerce_bool(values.get("STARTUP_DROP_CHOICE_POINTER_EVENTS", True)),
            startup_clear_focus_while_blocked=_coerce_bool(values.get("STARTUP_CLEAR_FOCUS_WHILE_BLOCKED", True)),
            startup_visual_finalize_deferred=_coerce_bool(values.get("STARTUP_VISUAL_FINALIZE_DEFERRED", True)),
            startup_visual_finalize_delay_ms=max(
                0,
                _coerce_int(values.get("STARTUP_VISUAL_FINALIZE_DELAY_MS", 280), 280),
            ),
            startup_visual_finalize_busy_retry_ms=max(
                0,
                _coerce_int(values.get("STARTUP_VISUAL_FINALIZE_BUSY_RETRY_MS", 250), 250),
            ),
            startup_wheel_cache_warmup=_coerce_bool(values.get("STARTUP_WHEEL_CACHE_WARMUP", True)),
            startup_ocr_preload=_coerce_bool(values.get("STARTUP_OCR_PRELOAD", False)),
            startup_ocr_preload_max_wait_ms=max(
                0,
                _coerce_int(values.get("STARTUP_OCR_PRELOAD_MAX_WAIT_MS", 1800), 1800),
            ),
            startup_ocr_preload_running_max_wait_ms=max(
                0,
                _coerce_int(values.get("STARTUP_OCR_PRELOAD_RUNNING_MAX_WAIT_MS", 14000), 14000),
            ),
            startup_map_prebuild_max_wait_ms=max(
                0,
                _coerce_int(values.get("STARTUP_MAP_PREBUILD_MAX_WAIT_MS", 2200), 2200),
            ),
            map_prebuild_on_start=_coerce_bool(values.get("MAP_PREBUILD_ON_START", True)),
        )
        self.shutdown = ShutdownSettings(
            overlay_enabled=_coerce_bool(values.get("SHUTDOWN_OVERLAY_ENABLED", True)),
            overlay_delay_ms=max(0, _coerce_int(values.get("SHUTDOWN_OVERLAY_DELAY_MS", 320), 320)),
            blocker_trace_interval_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_BLOCKER_TRACE_INTERVAL_MS", 250), 250),
            ),
            ocr_async_graceful_wait_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_OCR_ASYNC_GRACEFUL_WAIT_MS", 1200), 1200),
            ),
            ocr_async_terminate_wait_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_OCR_ASYNC_TERMINATE_WAIT_MS", 700), 700),
            ),
            ocr_preload_graceful_wait_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_OCR_PRELOAD_GRACEFUL_WAIT_MS", 1400), 1400),
            ),
            ocr_preload_terminate_wait_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_OCR_PRELOAD_TERMINATE_WAIT_MS", 350), 350),
            ),
            ocr_preload_force_stop_on_close=_coerce_bool(
                values.get("SHUTDOWN_OCR_PRELOAD_FORCE_STOP_ON_CLOSE", False)
            ),
            child_thread_graceful_wait_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_CHILD_THREAD_GRACEFUL_WAIT_MS", 350), 350),
            ),
            child_thread_terminate_wait_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_CHILD_THREAD_TERMINATE_WAIT_MS", 250), 250),
            ),
            thread_max_defer_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_THREAD_MAX_DEFER_MS", 2500), 2500),
            ),
            ocr_preload_max_defer_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_OCR_PRELOAD_MAX_DEFER_MS", 1200), 1200),
            ),
            ocr_async_max_defer_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_OCR_ASYNC_MAX_DEFER_MS", 1500), 1500),
            ),
            child_thread_max_defer_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_CHILD_THREAD_MAX_DEFER_MS", 1200), 1200),
            ),
            python_thread_max_defer_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_PYTHON_THREAD_MAX_DEFER_MS", 1800), 1800),
            ),
            app_quit_guard_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_APP_QUIT_GUARD_MS", 1500), 1500),
            ),
            app_force_exit_loop_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_APP_FORCE_EXIT_LOOP_MS", 2400), 2400),
            ),
            keep_window_visible_until_exit=_coerce_bool(
                values.get("SHUTDOWN_KEEP_WINDOW_VISIBLE_UNTIL_EXIT", False)
            ),
            force_exit_watchdog_enabled=_coerce_bool(
                values.get("SHUTDOWN_FORCE_EXIT_WATCHDOG_ENABLED", False)
            ),
            force_exit_watchdog_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_FORCE_EXIT_WATCHDOG_MS", 12000), 12000),
            ),
            force_exit_on_orphan_ms=max(
                0,
                _coerce_int(values.get("SHUTDOWN_FORCE_EXIT_ON_ORPHAN_MS", 2200), 2200),
            ),
            release_ocr_cache=_coerce_bool(values.get("SHUTDOWN_RELEASE_OCR_CACHE", False)),
        )
        self.ocr = OcrSettings(
            engine=_coerce_str(values.get("OCR_ENGINE", "easyocr"), "easyocr"),
            easyocr_lang=_coerce_str(
                values.get("OCR_EASYOCR_LANG", "en,de,ja,ch_sim,ko"),
                "en,de,ja,ch_sim,ko",
            ),
            easyocr_model_dir=_coerce_str(values.get("OCR_EASYOCR_MODEL_DIR", ""), ""),
            easyocr_user_network_dir=_coerce_str(values.get("OCR_EASYOCR_USER_NETWORK_DIR", ""), ""),
            easyocr_gpu=_coerce_str(values.get("OCR_EASYOCR_GPU", "auto"), "auto"),
            easyocr_download_enabled=_coerce_bool(values.get("OCR_EASYOCR_DOWNLOAD_ENABLED", False)),
            timeout_s=max(0.5, _coerce_float(values.get("OCR_TIMEOUT_S", 8.0), 8.0)),
            timeout_s_windows=max(0.5, _coerce_float(values.get("OCR_TIMEOUT_S_WINDOWS", 6.0), 6.0)),
            runtime_sleep_until_used=_coerce_bool(values.get("OCR_RUNTIME_SLEEP_UNTIL_USED", True)),
            background_preload_enabled=_coerce_bool(values.get("OCR_BACKGROUND_PRELOAD_ENABLED", True)),
            background_preload_delay_ms=max(
                0,
                _coerce_int(values.get("OCR_BACKGROUND_PRELOAD_DELAY_MS", 2500), 2500),
            ),
            background_preload_min_uptime_ms=max(
                0,
                _coerce_int(values.get("OCR_BACKGROUND_PRELOAD_MIN_UPTIME_MS", 8000), 8000),
            ),
            background_preload_allow_during_startup=_coerce_bool(
                values.get("OCR_BACKGROUND_PRELOAD_ALLOW_DURING_STARTUP", True)
            ),
            background_preload_busy_retry_ms=max(
                0,
                _coerce_int(values.get("OCR_BACKGROUND_PRELOAD_BUSY_RETRY_MS", 1800), 1800),
            ),
            preload_subprocess_timeout_s=max(
                1.0,
                _coerce_float(values.get("OCR_PRELOAD_SUBPROCESS_TIMEOUT_S", 60.0), 60.0),
            ),
            preload_use_subprocess_probe=_coerce_bool(
                values.get("OCR_PRELOAD_USE_SUBPROCESS_PROBE", True)
            ),
            preload_use_subprocess_probe_win_frozen=_coerce_bool(
                values.get("OCR_PRELOAD_USE_SUBPROCESS_PROBE_WIN_FROZEN", False)
            ),
            preload_inprocess_cache_warmup=_coerce_bool(
                values.get("OCR_PRELOAD_INPROCESS_CACHE_WARMUP", True)
            ),
            preload_cancel_running_on_spin=_coerce_bool(
                values.get("OCR_PRELOAD_CANCEL_RUNNING_ON_SPIN", False)
            ),
            idle_cache_release_ms=max(
                0,
                _coerce_int(values.get("OCR_IDLE_CACHE_RELEASE_MS", 30000), 30000),
            ),
            idle_cache_release_busy_retry_ms=max(
                0,
                _coerce_int(values.get("OCR_IDLE_CACHE_RELEASE_BUSY_RETRY_MS", 2500), 2500),
            ),
            release_cache_on_spin=_coerce_bool(values.get("OCR_RELEASE_CACHE_ON_SPIN", False)),
            debug_show_report=_coerce_bool(values.get("OCR_DEBUG_SHOW_REPORT", False)),
            debug_log_to_file=_coerce_bool(values.get("OCR_DEBUG_LOG_TO_FILE", True)),
        )
        min_dur = max(0, _coerce_int(values.get("MIN_DURATION_MS", 0), 0))
        max_dur = max(min_dur, _coerce_int(values.get("MAX_DURATION_MS", 10000), 10000))
        self.spin_ui = SpinUiSettings(
            min_duration_ms=min_dur,
            max_duration_ms=max_dur,
            default_duration_ms=max(min_dur, min(max_dur, _coerce_int(values.get("DEFAULT_DURATION_MS", 3000), 3000))),
            spin_watchdog_enabled=_coerce_bool(values.get("SPIN_WATCHDOG_ENABLED", False)),
            spin_lightweight_ui_lock=_coerce_bool(values.get("SPIN_LIGHTWEIGHT_UI_LOCK", True)),
        )
        self.network = NetworkSettings(
            state_save_debounce_ms=max(0, _coerce_int(values.get("STATE_SAVE_DEBOUNCE_MS", 220), 220)),
            network_sync_debounce_ms=max(0, _coerce_int(values.get("NETWORK_SYNC_DEBOUNCE_MS", 220), 220)),
            network_sync_workers=max(1, _coerce_int(values.get("NETWORK_SYNC_WORKERS", 2), 2)),
            api_base_url=_coerce_str(values.get("API_BASE_URL", "http://localhost:5326"), "http://localhost:5326"),
        )

        self._typed_index = {
            "DEBUG": self.runtime.debug,
            "QUIET": self.runtime.quiet,
            "LOG_OUTPUT_DIR": self.runtime.log_output_dir,
            "DEFAULT_LANGUAGE": self.runtime.default_language,
            "WINDOWS_SINGLE_INSTANCE": self.runtime.windows_single_instance,
            "WINDOWS_SINGLE_INSTANCE_LOCK_NAME": self.runtime.windows_single_instance_lock_name,
            "FORCE_FUSION_STYLE": self.runtime.force_fusion_style,
            "DISABLE_TOOLTIPS": self.runtime.disable_tooltips,
            "TRACE_FLOW": self.trace.flow,
            "TRACE_SHUTDOWN": self.trace.shutdown,
            "TRACE_FOCUS": self.trace.focus,
            "TRACE_HOVER": self.trace.hover,
            "TRACE_SPIN_PERF": self.trace.spin_perf,
            "TRACE_CLEAR_ON_START": self.trace.clear_on_start,
            "TRACE_OCR_RUNTIME": self.trace.ocr_runtime,
            "MODE_CHOICE_INPUT_GUARD_MS": self.startup.mode_choice_input_guard_ms,
            "MODE_CHOICE_ONLINE_ENABLED": self.startup.mode_choice_online_enabled,
            "STARTUP_FINALIZE_DELAY_MS": self.startup.startup_finalize_delay_ms,
            "STARTUP_WARMUP_COOLDOWN_MS": self.startup.startup_warmup_cooldown_ms,
            "STARTUP_INPUT_DRAIN_MS": self.startup.startup_input_drain_ms,
            "STARTUP_MIN_BLOCK_INPUT_MS": self.startup.startup_min_block_input_ms,
            "STARTUP_DROP_CHOICE_POINTER_EVENTS": self.startup.startup_drop_choice_pointer_events,
            "STARTUP_CLEAR_FOCUS_WHILE_BLOCKED": self.startup.startup_clear_focus_while_blocked,
            "STARTUP_VISUAL_FINALIZE_DEFERRED": self.startup.startup_visual_finalize_deferred,
            "STARTUP_VISUAL_FINALIZE_DELAY_MS": self.startup.startup_visual_finalize_delay_ms,
            "STARTUP_VISUAL_FINALIZE_BUSY_RETRY_MS": self.startup.startup_visual_finalize_busy_retry_ms,
            "STARTUP_WHEEL_CACHE_WARMUP": self.startup.startup_wheel_cache_warmup,
            "STARTUP_OCR_PRELOAD": self.startup.startup_ocr_preload,
            "STARTUP_OCR_PRELOAD_MAX_WAIT_MS": self.startup.startup_ocr_preload_max_wait_ms,
            "STARTUP_OCR_PRELOAD_RUNNING_MAX_WAIT_MS": self.startup.startup_ocr_preload_running_max_wait_ms,
            "STARTUP_MAP_PREBUILD_MAX_WAIT_MS": self.startup.startup_map_prebuild_max_wait_ms,
            "MAP_PREBUILD_ON_START": self.startup.map_prebuild_on_start,
            "SHUTDOWN_OVERLAY_ENABLED": self.shutdown.overlay_enabled,
            "SHUTDOWN_OVERLAY_DELAY_MS": self.shutdown.overlay_delay_ms,
            "SHUTDOWN_BLOCKER_TRACE_INTERVAL_MS": self.shutdown.blocker_trace_interval_ms,
            "SHUTDOWN_OCR_ASYNC_GRACEFUL_WAIT_MS": self.shutdown.ocr_async_graceful_wait_ms,
            "SHUTDOWN_OCR_ASYNC_TERMINATE_WAIT_MS": self.shutdown.ocr_async_terminate_wait_ms,
            "SHUTDOWN_OCR_PRELOAD_GRACEFUL_WAIT_MS": self.shutdown.ocr_preload_graceful_wait_ms,
            "SHUTDOWN_OCR_PRELOAD_TERMINATE_WAIT_MS": self.shutdown.ocr_preload_terminate_wait_ms,
            "SHUTDOWN_OCR_PRELOAD_FORCE_STOP_ON_CLOSE": self.shutdown.ocr_preload_force_stop_on_close,
            "SHUTDOWN_CHILD_THREAD_GRACEFUL_WAIT_MS": self.shutdown.child_thread_graceful_wait_ms,
            "SHUTDOWN_CHILD_THREAD_TERMINATE_WAIT_MS": self.shutdown.child_thread_terminate_wait_ms,
            "SHUTDOWN_THREAD_MAX_DEFER_MS": self.shutdown.thread_max_defer_ms,
            "SHUTDOWN_OCR_PRELOAD_MAX_DEFER_MS": self.shutdown.ocr_preload_max_defer_ms,
            "SHUTDOWN_OCR_ASYNC_MAX_DEFER_MS": self.shutdown.ocr_async_max_defer_ms,
            "SHUTDOWN_CHILD_THREAD_MAX_DEFER_MS": self.shutdown.child_thread_max_defer_ms,
            "SHUTDOWN_PYTHON_THREAD_MAX_DEFER_MS": self.shutdown.python_thread_max_defer_ms,
            "SHUTDOWN_APP_QUIT_GUARD_MS": self.shutdown.app_quit_guard_ms,
            "SHUTDOWN_APP_FORCE_EXIT_LOOP_MS": self.shutdown.app_force_exit_loop_ms,
            "SHUTDOWN_KEEP_WINDOW_VISIBLE_UNTIL_EXIT": self.shutdown.keep_window_visible_until_exit,
            "SHUTDOWN_FORCE_EXIT_WATCHDOG_ENABLED": self.shutdown.force_exit_watchdog_enabled,
            "SHUTDOWN_FORCE_EXIT_WATCHDOG_MS": self.shutdown.force_exit_watchdog_ms,
            "SHUTDOWN_FORCE_EXIT_ON_ORPHAN_MS": self.shutdown.force_exit_on_orphan_ms,
            "SHUTDOWN_RELEASE_OCR_CACHE": self.shutdown.release_ocr_cache,
            "OCR_ENGINE": self.ocr.engine,
            "OCR_EASYOCR_LANG": self.ocr.easyocr_lang,
            "OCR_EASYOCR_MODEL_DIR": self.ocr.easyocr_model_dir,
            "OCR_EASYOCR_USER_NETWORK_DIR": self.ocr.easyocr_user_network_dir,
            "OCR_EASYOCR_GPU": self.ocr.easyocr_gpu,
            "OCR_EASYOCR_DOWNLOAD_ENABLED": self.ocr.easyocr_download_enabled,
            "OCR_TIMEOUT_S": self.ocr.timeout_s,
            "OCR_TIMEOUT_S_WINDOWS": self.ocr.timeout_s_windows,
            "OCR_RUNTIME_SLEEP_UNTIL_USED": self.ocr.runtime_sleep_until_used,
            "OCR_BACKGROUND_PRELOAD_ENABLED": self.ocr.background_preload_enabled,
            "OCR_BACKGROUND_PRELOAD_DELAY_MS": self.ocr.background_preload_delay_ms,
            "OCR_BACKGROUND_PRELOAD_MIN_UPTIME_MS": self.ocr.background_preload_min_uptime_ms,
            "OCR_BACKGROUND_PRELOAD_ALLOW_DURING_STARTUP": self.ocr.background_preload_allow_during_startup,
            "OCR_BACKGROUND_PRELOAD_BUSY_RETRY_MS": self.ocr.background_preload_busy_retry_ms,
            "OCR_PRELOAD_SUBPROCESS_TIMEOUT_S": self.ocr.preload_subprocess_timeout_s,
            "OCR_PRELOAD_USE_SUBPROCESS_PROBE": self.ocr.preload_use_subprocess_probe,
            "OCR_PRELOAD_USE_SUBPROCESS_PROBE_WIN_FROZEN": self.ocr.preload_use_subprocess_probe_win_frozen,
            "OCR_PRELOAD_INPROCESS_CACHE_WARMUP": self.ocr.preload_inprocess_cache_warmup,
            "OCR_PRELOAD_CANCEL_RUNNING_ON_SPIN": self.ocr.preload_cancel_running_on_spin,
            "OCR_IDLE_CACHE_RELEASE_MS": self.ocr.idle_cache_release_ms,
            "OCR_IDLE_CACHE_RELEASE_BUSY_RETRY_MS": self.ocr.idle_cache_release_busy_retry_ms,
            "OCR_RELEASE_CACHE_ON_SPIN": self.ocr.release_cache_on_spin,
            "OCR_DEBUG_SHOW_REPORT": self.ocr.debug_show_report,
            "OCR_DEBUG_LOG_TO_FILE": self.ocr.debug_log_to_file,
            "MIN_DURATION_MS": self.spin_ui.min_duration_ms,
            "MAX_DURATION_MS": self.spin_ui.max_duration_ms,
            "DEFAULT_DURATION_MS": self.spin_ui.default_duration_ms,
            "SPIN_WATCHDOG_ENABLED": self.spin_ui.spin_watchdog_enabled,
            "SPIN_LIGHTWEIGHT_UI_LOCK": self.spin_ui.spin_lightweight_ui_lock,
            "STATE_SAVE_DEBOUNCE_MS": self.network.state_save_debounce_ms,
            "NETWORK_SYNC_DEBOUNCE_MS": self.network.network_sync_debounce_ms,
            "NETWORK_SYNC_WORKERS": self.network.network_sync_workers,
            "API_BASE_URL": self.network.api_base_url,
        }

    def resolve(self, key: str, default: Any = None) -> Any:
        key_norm = str(key or "").strip().upper()
        if not key_norm:
            return default
        if key_norm in self._typed_index:
            return self._typed_index[key_norm]
        if key_norm in self.values:
            return self.values[key_norm]
        return default

    def update(self, mapping: dict[str, Any] | None = None, **kwargs: Any) -> None:
        updates: dict[str, Any] = {}
        if isinstance(mapping, dict):
            updates.update(mapping)
        if kwargs:
            updates.update(kwargs)
        if not updates:
            return
        for key, value in updates.items():
            if not isinstance(key, str):
                continue
            key_norm = key.strip()
            if not key_norm:
                continue
            self.values[key_norm] = value
        self._rebuild_sections()

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def bool(self, key: str, default: bool = False) -> bool:
        return _coerce_bool(self.values.get(key, default), default)

    def int(self, key: str, default: int = 0) -> int:
        return _coerce_int(self.values.get(key, default), default)

    def float(self, key: str, default: float = 0.0) -> float:
        return _coerce_float(self.values.get(key, default), default)
