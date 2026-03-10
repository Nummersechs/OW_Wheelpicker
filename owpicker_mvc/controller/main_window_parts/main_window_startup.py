from __future__ import annotations

import time

from PySide6 import QtCore

from model.main_window_runtime_state import OCRPreloadPhase, StartupPhase
from utils import theme as theme_util


class MainWindowStartupMixin:
    def _schedule_finalize_startup(self, delay_ms: int | None = None) -> None:
        if getattr(self, "_startup_finalize_done", False):
            return
        if getattr(self, "_startup_finalize_scheduled", False):
            return
        self._set_startup_runtime_state(finalize_scheduled=True)
        if delay_ms is None:
            delay_ms = int(self._cfg("STARTUP_FINALIZE_DELAY_MS", 60))
        QtCore.QTimer.singleShot(max(0, int(delay_ms)), self._run_finalize_startup)

    def _run_finalize_startup(self) -> None:
        self._set_startup_runtime_state(finalize_scheduled=False)
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
        self._set_startup_runtime_state(visual_finalize_pending=False)
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

    def _show_mode_choice(self) -> None:
        """Direkt beim Start Modus wählen lassen."""
        self._set_controls_enabled(False)
        self._set_heavy_ui_updates_enabled(False)
        self.overlay.show_online_choice()
        if hasattr(self.overlay, "set_online_choice_available"):
            self.overlay.set_online_choice_available(self._cfg("MODE_CHOICE_ONLINE_ENABLED", False))
        self.overlay.set_choice_enabled(False)
        self._set_startup_runtime_state(startup_phase=StartupPhase.SHOWING_MODE_CHOICE.value)
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
        if self._cfg("STARTUP_WHEEL_CACHE_WARMUP", True):
            tasks.append(("wheel_cache", self._startup_task_wheel_cache))
        if self._cfg("SOUND_WARMUP_ON_START", False):
            tasks.append(("sound_warmup", self._startup_task_sound))
        # Tooltip cache refresh is intentionally not part of startup warmup.
        # It is handled asynchronously after mode choice/post-init so warmup
        # remains focused on expensive, user-visible startup costs.
        if self._cfg("MAP_PREBUILD_ON_START", False):
            tasks.append(("map_prebuild", self._startup_task_map_prebuild))
        if self._cfg("STARTUP_OCR_PRELOAD", True):
            tasks.append(("ocr_preload", self._startup_task_ocr_preload))
        min_block_ms = max(0, int(self._cfg("STARTUP_MIN_BLOCK_INPUT_MS", 0)))
        # Fast-path for normal startup: no warmup tasks and no explicit lock.
        if not tasks and min_block_ms <= 0:
            self._set_startup_runtime_state(
                startup_phase=StartupPhase.WARMUP_DONE.value,
                task_queue=[],
                warmup_running=False,
                warmup_done=True,
                block_input=False,
                block_input_until=None,
                drain_active=False,
            )
            self._trace_event("startup_warmup:skipped")
            self._refresh_app_event_filter_state()
            try:
                if hasattr(self, "overlay"):
                    self.overlay.set_choice_enabled(True)
            except Exception:
                pass
            return
        self._set_startup_runtime_state(
            startup_phase=StartupPhase.WARMUP_RUNNING.value,
            task_queue=tasks,
            warmup_running=True,
            block_input=True,
        )
        if min_block_ms > 0:
            self._set_startup_runtime_state(block_input_until=time.monotonic() + (min_block_ms / 1000.0))
        else:
            self._set_startup_runtime_state(block_input_until=None)
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
        self._set_startup_runtime_state(current_task=name)
        self._trace_event("startup_warmup:task_start", task=name)
        QtCore.QTimer.singleShot(0, fn)

    def _startup_task_done(self, name: str | None = None) -> None:
        task = name or getattr(self, "_startup_current_task", None)
        if task:
            self._trace_event("startup_warmup:task_done", task=task)
        self._set_startup_runtime_state(current_task=None)
        QtCore.QTimer.singleShot(0, self._run_next_startup_task)

    def _finish_startup_warmup(self) -> None:
        if getattr(self, "_startup_warmup_done", False):
            return
        if getattr(self, "_startup_warmup_finalize_scheduled", False):
            return
        self._set_startup_runtime_state(
            startup_phase=StartupPhase.WARMUP_COOLDOWN.value,
            warmup_finalize_scheduled=True,
        )
        extra_ms = max(0, int(self._cfg("STARTUP_WARMUP_COOLDOWN_MS", 0)))
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
        self._set_startup_runtime_state(
            startup_phase=StartupPhase.WARMUP_DONE.value,
            warmup_running=False,
            warmup_done=True,
            block_input=False,
            block_input_until=None,
            drain_active=True,
            task_queue=[],
            current_task=None,
            waiting_for_map=False,
            map_prebuild_deadline=None,
            waiting_for_ocr_preload=False,
            ocr_preload_deadline=None,
            ocr_preload_started_at=None,
            ocr_preload_running_wait_logged=False,
            ocr_preload_phase=OCRPreloadPhase.IDLE.value,
            ocr_preload_phase_reason=None,
        )
        self._flush_posted_events("startup_warmup_done")
        self._refresh_app_event_filter_state()
        self._restart_startup_drain_timer()
        # Heavy UI updates were deferred; apply once warmup is done.
        self._flush_pending_heavy_ui_updates(step_ms=int(self._post_choice_step_ms))
        self._sync_mode_stack()
        self._trace_event("startup_warmup:done")
        self._rearm_hover_tracking(reason="startup_warmup:done")
        if not self._cfg("DISABLE_TOOLTIPS", False) and not self._cfg("TOOLTIP_CACHE_ON_START", False):
            self._refresh_tooltip_caches_async(reason="startup_warmup_done")

    def _startup_task_wheel_cache(self) -> None:
        if not self._cfg("STARTUP_WHEEL_CACHE_WARMUP", True):
            self._startup_task_done("wheel_cache")
            return
        queue: list[object] = []
        seen: set[int] = set()
        for _role, wheel in self._role_wheels():
            if not wheel:
                continue
            wid = id(wheel)
            if wid in seen:
                continue
            seen.add(wid)
            queue.append(wheel)
        map_main = getattr(self, "map_main", None)
        if map_main is not None:
            wid = id(map_main)
            if wid not in seen:
                queue.append(map_main)

        warmed = 0
        for wheel_view in queue:
            wheel_disc = getattr(wheel_view, "wheel", None)
            if wheel_disc is None or not hasattr(wheel_disc, "_ensure_cache"):
                continue
            try:
                wheel_disc._ensure_cache(force=False)
                warmed += 1
            except Exception:
                pass
        self._trace_event("startup_warmup:wheel_cache", warmed=warmed, total=len(queue))
        self._startup_task_done("wheel_cache")

    def _startup_task_ocr_preload(self) -> None:
        if not self._cfg("STARTUP_OCR_PRELOAD", True):
            self._startup_task_done("ocr_preload")
            return
        if not bool(self._cfg("OCR_BACKGROUND_PRELOAD_ENABLED", True)):
            self._startup_task_done("ocr_preload")
            return
        if bool(getattr(self, "_ocr_runtime_activated", False)) or bool(
            getattr(self, "_ocr_preload_done", False)
        ):
            self._set_startup_runtime_state(
                ocr_preload_phase=OCRPreloadPhase.DONE.value,
                ocr_preload_phase_reason="already_ready",
            )
            self._startup_task_done("ocr_preload")
            return
        run_preload = getattr(self, "_run_ocr_background_preload", None)
        if not callable(run_preload):
            self._set_startup_runtime_state(
                ocr_preload_phase=OCRPreloadPhase.FAILED.value,
                ocr_preload_phase_reason="no_runner",
            )
            self._startup_task_done("ocr_preload")
            return
        self._set_startup_runtime_state(
            waiting_for_ocr_preload=True,
            ocr_preload_running_wait_logged=False,
            ocr_preload_started_at=None,
            ocr_preload_phase=OCRPreloadPhase.RUNNING.value,
            ocr_preload_phase_reason="startup_task",
        )
        max_wait_ms = max(250, int(self._cfg("STARTUP_OCR_PRELOAD_MAX_WAIT_MS", 1800)))
        self._set_startup_runtime_state(ocr_preload_deadline=time.monotonic() + (max_wait_ms / 1000.0))
        try:
            run_preload()
        except Exception:
            self._set_startup_runtime_state(
                waiting_for_ocr_preload=False,
                ocr_preload_deadline=None,
                ocr_preload_started_at=None,
                ocr_preload_phase=OCRPreloadPhase.FAILED.value,
                ocr_preload_phase_reason="runner_error",
            )
            self._startup_task_done("ocr_preload")
            return
        if self._startup_ocr_preload_thread_running():
            self._set_startup_runtime_state(ocr_preload_started_at=time.monotonic())
        self._poll_startup_ocr_preload()

    def _startup_ocr_preload_thread_running(self) -> bool:
        preload_job = getattr(self, "_ocr_preload_job", None)
        if not isinstance(preload_job, dict):
            return False
        preload_thread = preload_job.get("thread")
        if preload_thread is None:
            return False
        try:
            return bool(preload_thread.isRunning())
        except Exception:
            return False

    def _poll_startup_ocr_preload(self) -> None:
        if not bool(getattr(self, "_startup_waiting_for_ocr_preload", False)):
            return
        if bool(getattr(self, "_ocr_preload_done", False)) or bool(getattr(self, "_ocr_preload_attempted", False)):
            self._set_startup_runtime_state(
                waiting_for_ocr_preload=False,
                ocr_preload_deadline=None,
                ocr_preload_started_at=None,
            )
            if bool(getattr(self, "_ocr_preload_done", False)):
                self._set_startup_runtime_state(
                    ocr_preload_phase=OCRPreloadPhase.DONE.value,
                    ocr_preload_phase_reason="startup_poll",
                )
            self._startup_task_done("ocr_preload")
            return
        wait_ms = max(40, int(self._cfg("POST_CHOICE_INIT_BUSY_RETRY_MS", 220)))
        deadline = getattr(self, "_startup_ocr_preload_deadline", None)
        if deadline is not None and time.monotonic() >= float(deadline):
            now = time.monotonic()
            if self._startup_ocr_preload_thread_running():
                started_at = getattr(self, "_startup_ocr_preload_started_at", None)
                if started_at is None:
                    started_at = now
                    self._set_startup_runtime_state(ocr_preload_started_at=started_at)
                running_max_wait_ms = max(
                    int(self._cfg("STARTUP_OCR_PRELOAD_MAX_WAIT_MS", 1800)),
                    int(self._cfg("STARTUP_OCR_PRELOAD_RUNNING_MAX_WAIT_MS", 14000)),
                )
                running_elapsed_ms = max(0, int((now - float(started_at)) * 1000.0))
                running_remaining_ms = max(0, int(running_max_wait_ms - running_elapsed_ms))
                if running_remaining_ms > 0:
                    wait_running_ms = max(40, min(wait_ms, running_remaining_ms))
                    self._set_startup_runtime_state(ocr_preload_deadline=now + (wait_running_ms / 1000.0))
                    if not bool(getattr(self, "_startup_ocr_preload_running_wait_logged", False)):
                        self._set_startup_runtime_state(ocr_preload_running_wait_logged=True)
                        self._trace_event(
                            "startup_warmup:ocr_preload_wait_running",
                            elapsed_ms=running_elapsed_ms,
                            max_wait_ms=running_max_wait_ms,
                        )
                    QtCore.QTimer.singleShot(wait_running_ms, self._poll_startup_ocr_preload)
                    return
            self._set_startup_runtime_state(
                waiting_for_ocr_preload=False,
                ocr_preload_deadline=None,
                ocr_preload_started_at=None,
                ocr_preload_phase=OCRPreloadPhase.FAILED.value,
                ocr_preload_phase_reason="startup_timeout",
            )
            self._trace_event("startup_warmup:ocr_preload_timeout")
            self._startup_task_done("ocr_preload")
            return
        preload_job = getattr(self, "_ocr_preload_job", None)
        preload_timer = getattr(self, "_ocr_preload_timer", None)
        timer_active = False
        if preload_timer is not None:
            try:
                timer_active = bool(preload_timer.isActive())
            except Exception:
                timer_active = False
        if not preload_job and not timer_active:
            run_preload = getattr(self, "_run_ocr_background_preload", None)
            if callable(run_preload):
                try:
                    run_preload()
                    if self._startup_ocr_preload_thread_running() and getattr(
                        self, "_startup_ocr_preload_started_at", None
                    ) is None:
                        self._set_startup_runtime_state(ocr_preload_started_at=time.monotonic())
                except Exception:
                    self._set_startup_runtime_state(
                        waiting_for_ocr_preload=False,
                        ocr_preload_deadline=None,
                        ocr_preload_started_at=None,
                        ocr_preload_phase=OCRPreloadPhase.FAILED.value,
                        ocr_preload_phase_reason="restart_error",
                    )
                    self._startup_task_done("ocr_preload")
                    return
        QtCore.QTimer.singleShot(wait_ms, self._poll_startup_ocr_preload)

    def _startup_task_map_prebuild(self) -> None:
        if not self._cfg("MAP_PREBUILD_ON_START", False):
            self._startup_task_done("map_prebuild")
            return
        if getattr(self, "_map_initialized", False) and getattr(self, "_map_lists_ready", False):
            self._startup_task_done("map_prebuild")
            return
        self._set_startup_runtime_state(waiting_for_map=True)
        max_wait_ms = max(400, int(self._cfg("STARTUP_MAP_PREBUILD_MAX_WAIT_MS", 2200)))
        self._set_startup_runtime_state(map_prebuild_deadline=time.monotonic() + (max_wait_ms / 1000.0))
        self._schedule_map_prebuild()
        self._poll_startup_map_prebuild()

    def _poll_startup_map_prebuild(self) -> None:
        if not bool(getattr(self, "_startup_waiting_for_map", False)):
            return
        if bool(getattr(self, "_map_initialized", False)) and bool(getattr(self, "_map_lists_ready", False)):
            self._set_startup_runtime_state(waiting_for_map=False, map_prebuild_deadline=None)
            self._startup_task_done("map_prebuild")
            return
        deadline = getattr(self, "_startup_map_prebuild_deadline", None)
        if deadline is not None and time.monotonic() >= float(deadline):
            self._set_startup_runtime_state(waiting_for_map=False, map_prebuild_deadline=None)
            self._map_prebuild_in_progress = False
            self._set_map_button_loading(False, reason="prebuild_timeout")
            self._set_map_button_enabled(True)
            self._trace_event("startup_warmup:map_prebuild_timeout")
            self._startup_task_done("map_prebuild")
            return
        if not bool(getattr(self, "_map_prebuild_in_progress", False)):
            self._schedule_map_prebuild()
        wait_ms = max(60, int(self._cfg("POST_CHOICE_INIT_BUSY_RETRY_MS", 220)))
        QtCore.QTimer.singleShot(wait_ms, self._poll_startup_map_prebuild)

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
            self._set_startup_runtime_state(visual_finalize_pending=True)
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
        self._set_startup_runtime_state(
            startup_phase=StartupPhase.FINALIZED.value,
            finalize_done=True,
        )

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
        if hasattr(self, "_schedule_ocr_background_preload"):
            try:
                self._schedule_ocr_background_preload(reason="post_choice_init")
            except Exception:
                pass
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
        try:
            self._ensure_map_ui()
        except Exception as exc:
            self._map_prebuild_in_progress = False
            self._set_map_button_loading(False, reason="prebuild_error")
            self._set_map_button_enabled(True)
            self._trace_event("map_prebuild:error", error=repr(exc))
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
            self._set_startup_runtime_state(waiting_for_map=False, map_prebuild_deadline=None)
            self._startup_task_done("map_prebuild")
