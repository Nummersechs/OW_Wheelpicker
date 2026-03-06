from __future__ import annotations

from pathlib import Path
import time

from PySide6 import QtCore, QtGui

import i18n

from .. import shutdown_manager


class MainWindowShutdownMixin:
    @staticmethod
    def _disconnect_thread_worker_start(
        thread: object | None,
        worker: object | None,
        started_connection: object | None = None,
    ) -> None:
        """Best effort: prevent delayed `thread.started -> worker.run` execution during shutdown."""
        if started_connection is not None:
            try:
                # Disconnect by connection handle to avoid noisy warnings when
                # slot-based disconnect does not find a matching connection.
                QtCore.QObject.disconnect(started_connection)
                return
            except Exception:
                pass
        # For jobs without a stored connection handle, skip slot-based
        # disconnect to avoid RuntimeWarning spam during shutdown retries.
        if thread is None or worker is None:
            return

    def _defer_close_for_running_thread(self, event: QtGui.QCloseEvent, *, reason: str) -> None:
        retry_ms = max(50, int(self._cfg("SHUTDOWN_THREAD_RETRY_MS", 180)))
        now = time.monotonic()
        wait_started = getattr(self, "_close_thread_wait_started_at", None)
        if wait_started is None:
            self._close_thread_wait_started_at = now
            elapsed_ms = 0
        else:
            elapsed_ms = max(0, int((now - float(wait_started)) * 1000.0))
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "shutdown_deferred_for_thread",
                    reason=str(reason or "thread_running"),
                    retry_ms=retry_ms,
                    elapsed_ms=elapsed_ms,
                )
            except Exception:
                pass
        event.ignore()
        QtCore.QTimer.singleShot(retry_ms, self.close)

    def _stop_qthread_for_close(
        self,
        thread: object | None,
        *,
        graceful_wait_ms: int,
        terminate_wait_ms: int,
    ) -> bool:
        if thread is None:
            return True

        def _is_running() -> bool:
            try:
                return bool(thread.isRunning())
            except Exception:
                return False

        def _is_finished() -> bool:
            try:
                return bool(thread.isFinished())
            except Exception:
                return not _is_running()

        # Thread is already fully done.
        if _is_finished() and not _is_running():
            return True

        try:
            thread.requestInterruption()
        except Exception:
            pass
        try:
            thread.quit()
        except Exception:
            pass
        stopped = False
        wait_graceful_ms = int(max(0, graceful_wait_ms))
        wait_terminate_ms = int(max(0, terminate_wait_ms))
        if wait_graceful_ms > 0:
            try:
                stopped = bool(thread.wait(wait_graceful_ms))
            except Exception:
                stopped = False
        if not stopped and _is_running():
            try:
                thread.terminate()
            except Exception:
                pass
            if wait_terminate_ms > 0:
                try:
                    stopped = bool(thread.wait(wait_terminate_ms))
                except Exception:
                    stopped = False
        if not stopped and _is_running():
            return False
        if stopped:
            return True
        try:
            return not bool(thread.isRunning())
        except Exception:
            return False

    def _merge_shutdown_snapshot(self, prefix: str, payload: dict | None, target: dict) -> None:
        shutdown_manager.merge_shutdown_snapshot(prefix, payload, target)

    def _shutdown_resource_snapshot(self) -> dict:
        return shutdown_manager.shutdown_resource_snapshot(self)

    def _run_shutdown_step(self, step: str, callback) -> None:
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
        # Mark close intent early so no new background OCR preload can start
        # while shutdown overlay is shown.
        self._closing = True
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

        # Mark close intent before thread checks/cancellation to block any new
        # OCR preload scheduling paths during shutdown retries.
        self._closing = True
        close_retry_active = getattr(self, "_close_thread_wait_started_at", None) is not None

        def _thread_wait_profile(
            *,
            prefix: str,
            graceful_default: int,
            terminate_default: int,
            retry_graceful_default: int = 0,
            retry_terminate_default: int = 120,
            min_terminate_wait_ms: int = 30,
        ) -> tuple[int, int]:
            if close_retry_active:
                graceful_ms = max(
                    0,
                    int(self._cfg(f"SHUTDOWN_{prefix}_RETRY_GRACEFUL_WAIT_MS", retry_graceful_default)),
                )
                terminate_ms = max(
                    min_terminate_wait_ms,
                    int(self._cfg(f"SHUTDOWN_{prefix}_RETRY_TERMINATE_WAIT_MS", retry_terminate_default)),
                )
                return graceful_ms, terminate_ms
            graceful_ms = max(0, int(self._cfg(f"SHUTDOWN_{prefix}_GRACEFUL_WAIT_MS", graceful_default)))
            terminate_ms = max(
                min_terminate_wait_ms,
                int(self._cfg(f"SHUTDOWN_{prefix}_TERMINATE_WAIT_MS", terminate_default)),
            )
            return graceful_ms, terminate_ms

        if hasattr(self, "_cancel_ocr_background_preload"):
            try:
                self._cancel_ocr_background_preload()
            except Exception:
                pass
        if hasattr(self, "_cancel_ocr_runtime_cache_release"):
            try:
                self._cancel_ocr_runtime_cache_release()
            except Exception:
                pass

        job = getattr(self, "_ocr_async_job", None)
        if isinstance(job, dict):
            thread = job.get("thread")
            worker = job.get("worker")
            self._disconnect_thread_worker_start(
                thread,
                worker,
                job.get("started_connection"),
            )
            for path in list(job.get("paths") or []):
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass
            async_wait_ms, async_term_wait_ms = _thread_wait_profile(
                prefix="OCR_ASYNC",
                graceful_default=1200,
                terminate_default=700,
                retry_graceful_default=0,
                retry_terminate_default=120,
                min_terminate_wait_ms=50,
            )
            if not self._stop_qthread_for_close(
                thread,
                graceful_wait_ms=async_wait_ms,
                terminate_wait_ms=async_term_wait_ms,
            ):
                self._defer_close_for_running_thread(event, reason="ocr_async_thread")
                return
            self._ocr_async_job = None
        preload_job = getattr(self, "_ocr_preload_job", None)
        if isinstance(preload_job, dict):
            preload_thread = preload_job.get("thread")
            preload_worker = preload_job.get("worker")
            self._disconnect_thread_worker_start(
                preload_thread,
                preload_worker,
                preload_job.get("started_connection"),
            )
            preload_wait_ms, preload_term_wait_ms = _thread_wait_profile(
                prefix="OCR_PRELOAD",
                graceful_default=1400,
                terminate_default=350,
                retry_graceful_default=0,
                retry_terminate_default=120,
                min_terminate_wait_ms=30,
            )
            if not self._stop_qthread_for_close(
                preload_thread,
                graceful_wait_ms=preload_wait_ms,
                terminate_wait_ms=preload_term_wait_ms,
            ):
                self._defer_close_for_running_thread(event, reason="ocr_preload_thread")
                return
            self._ocr_preload_job = None
        self._close_thread_wait_started_at = None
        if hasattr(self, "_release_ocr_runtime_cache"):
            try:
                self._release_ocr_runtime_cache()
            except Exception:
                pass
        self._set_app_event_filter_enabled(False)
        shutdown_manager.handle_close_event(self, event)
