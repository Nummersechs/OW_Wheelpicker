from __future__ import annotations

from dataclasses import dataclass


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
    timeout_s_windows: float = 8.0
    low_end_mode: str = "auto"
    low_end_cpu_count_max: int = 4
    runtime_sleep_until_used: bool = True
    background_preload_enabled: bool = True
    background_preload_low_end_enabled: bool = False
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
    debug_log_to_file: bool = False


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


@dataclass(frozen=True)
class MapSettings:
    categories: tuple[str, ...] = ()
    include_defaults: tuple[str, ...] = ()
    list_names_min_visible_rows: int = 2
    list_names_max_visible_rows: int = 6
    list_names_extra_padding_px: int = 8


__all__ = [
    "RuntimeSettings",
    "TraceSettings",
    "StartupSettings",
    "ShutdownSettings",
    "OcrSettings",
    "SpinUiSettings",
    "NetworkSettings",
    "MapSettings",
]
