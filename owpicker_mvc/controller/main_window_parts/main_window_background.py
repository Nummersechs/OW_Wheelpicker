from __future__ import annotations

from PySide6 import QtCore


class MainWindowBackgroundMixin:
    def _pause_background_ui_services(self) -> None:
        if not bool(self._cfg("PAUSE_BACKGROUND_UI_SERVICES_DURING_SPIN", True)):
            return
        if getattr(self, "_background_services_paused", False):
            return
        self._background_services_paused = True
        self._paused_background_timers = []

        def _pause_timer(timer) -> None:
            if timer is None:
                return
            try:
                if not timer.isActive():
                    return
                remaining_ms = int(timer.remainingTime())
                is_single_shot = bool(timer.isSingleShot())
                self._paused_background_timers.append((timer, max(0, remaining_ms), is_single_shot))
                timer.stop()
            except Exception:
                pass

        for name in (
            "_hover_pump_timer",
            "_hover_watchdog_timer",
            "_deferred_hover_rearm_timer",
            "_deferred_tooltip_refresh_timer",
            "_focus_trace_snapshot_timer",
            "_startup_drain_timer",
            "_post_choice_timer",
            "_startup_visual_finalize_timer",
            "_stack_switch_timer",
        ):
            _pause_timer(getattr(self, name, None))

        state_sync = getattr(self, "state_sync", None)
        if state_sync is not None:
            _pause_timer(getattr(state_sync, "_save_timer", None))
            _pause_timer(getattr(state_sync, "_sync_timer", None))

        player_list_panel = getattr(self, "player_list_panel", None)
        if player_list_panel is not None:
            _pause_timer(getattr(player_list_panel, "_sync_timer", None))

        map_ui = getattr(self, "map_ui", None)
        if map_ui is not None:
            _pause_timer(getattr(map_ui, "_update_timer", None))
            _pause_timer(getattr(map_ui, "_list_build_timer", None))

        manager = getattr(self, "_tooltip_manager", None)
        if manager is not None and hasattr(manager, "pause"):
            try:
                manager.pause()
            except Exception:
                pass
        if hasattr(self, "_cancel_ocr_runtime_cache_release"):
            try:
                self._cancel_ocr_runtime_cache_release()
            except Exception:
                pass
        if hasattr(self, "_cancel_ocr_background_preload"):
            try:
                self._cancel_ocr_background_preload()
            except Exception:
                pass
        cancel_running = bool(self._cfg("OCR_PRELOAD_CANCEL_RUNNING_ON_SPIN", False))
        if cancel_running and hasattr(self, "_stop_ocr_background_preload_job"):
            try:
                self._stop_ocr_background_preload_job(reason="background_pause")
            except Exception:
                pass
        self._pause_sound_background_warmup()

    def _resume_background_ui_services(self) -> None:
        if not bool(self._cfg("PAUSE_BACKGROUND_UI_SERVICES_DURING_SPIN", True)):
            return
        if not getattr(self, "_background_services_paused", False):
            return
        self._background_services_paused = False
        paused_timers = list(getattr(self, "_paused_background_timers", []))
        self._paused_background_timers = []

        for timer, remaining_ms, is_single_shot in paused_timers:
            try:
                if timer is None or timer.isActive():
                    continue
                if is_single_shot:
                    # Resume single-shot timers near their previous remaining time.
                    timer.start(max(0, int(remaining_ms)))
                else:
                    # For periodic timers keep the configured interval; using
                    # remainingTime() as new interval can create ultra-fast loops.
                    timer.start()
            except Exception:
                pass

        manager = getattr(self, "_tooltip_manager", None)
        if manager is not None and hasattr(manager, "resume"):
            try:
                manager.resume()
            except Exception:
                pass
        reason = getattr(self, "_deferred_hover_rearm_reason", None)
        force = bool(getattr(self, "_deferred_hover_rearm_force", False))
        if reason:
            self._schedule_hover_rearm(reason, force=force)
        if getattr(self, "_hover_watchdog_started", False):
            timer = getattr(self, "_hover_watchdog_timer", None)
            if timer is not None:
                try:
                    if not timer.isActive():
                        timer.start()
                except Exception:
                    pass
        refresh_reason = getattr(self, "_deferred_tooltip_refresh_reason", None)
        if refresh_reason:
            self._schedule_tooltip_refresh(refresh_reason)
        if hasattr(self, "_schedule_ocr_runtime_cache_release"):
            try:
                if not getattr(self, "_ocr_async_job", None):
                    self._schedule_ocr_runtime_cache_release()
            except Exception:
                pass
        if hasattr(self, "_schedule_ocr_background_preload"):
            try:
                if not getattr(self, "_ocr_async_job", None):
                    self._schedule_ocr_background_preload(reason="background_resume")
            except Exception:
                pass
        if bool(getattr(self, "_startup_visual_finalize_pending", False)):
            self._schedule_startup_visual_finalize(delay_ms=0)
        self._resume_sound_background_warmup()

    def _ensure_wheel_cache_warmup_timer(self) -> QtCore.QTimer:
        timer = getattr(self, "_wheel_cache_warmup_timer", None)
        if timer is not None:
            return timer
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._run_wheel_cache_warmup_step)
        if hasattr(self, "_timers"):
            self._timers.register(timer)
        self._wheel_cache_warmup_timer = timer
        return timer

    def _schedule_wheel_cache_warmup(self, delay_ms: int = 0) -> None:
        if getattr(self, "_closing", False):
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

        self._wheel_cache_warmup_queue = queue
        timer = self._ensure_wheel_cache_warmup_timer()
        timer.start(max(0, int(delay_ms)))

    def _run_wheel_cache_warmup_step(self) -> None:
        if getattr(self, "_closing", False):
            self._wheel_cache_warmup_queue = []
            return
        if int(getattr(self, "pending", 0) or 0) > 0 or getattr(self, "_background_services_paused", False):
            timer = self._ensure_wheel_cache_warmup_timer()
            timer.start(300)
            return
        if not self._wheel_cache_warmup_queue:
            return
        wheel_view = self._wheel_cache_warmup_queue.pop(0)
        wheel_disc = getattr(wheel_view, "wheel", None)
        if wheel_disc is not None and hasattr(wheel_disc, "_ensure_cache"):
            try:
                wheel_disc._ensure_cache(force=False)
            except Exception:
                pass
        if self._wheel_cache_warmup_queue:
            timer = self._ensure_wheel_cache_warmup_timer()
            timer.start(0)
