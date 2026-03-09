from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class StartupRuntimeState:
    finalize_done: bool = False
    finalize_scheduled: bool = False
    visual_finalize_pending: bool = False
    block_input: bool = False
    block_input_until: float | None = None
    warmup_running: bool = False
    warmup_done: bool = False
    warmup_finalize_scheduled: bool = False
    task_queue: list[tuple[str, Callable[[], None]]] = field(default_factory=list)
    current_task: str | None = None
    waiting_for_map: bool = False
    map_prebuild_deadline: float | None = None
    waiting_for_ocr_preload: bool = False
    ocr_preload_deadline: float | None = None
    ocr_preload_started_at: float | None = None
    ocr_preload_running_wait_logged: bool = False
    drain_active: bool = False


@dataclass
class ShutdownRuntimeState:
    closing: bool = False
    close_overlay_active: bool = False
    close_overlay_done: bool = False
    close_overlay_timer: object | None = None
    close_retry_timer: object | None = None
    close_thread_wait_started_at: float | None = None
    shutdown_force_exit_deadline: float | None = None
    shutdown_force_exit_watchdog_token: object | None = None
    shutdown_blocker_trace_last_at: float | None = None
