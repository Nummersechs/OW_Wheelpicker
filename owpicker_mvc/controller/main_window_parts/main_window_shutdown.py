from __future__ import annotations

from pathlib import Path
import time
import warnings

from PySide6 import QtCore, QtGui

import i18n

from .. import shutdown_manager

_ORPHANED_OCR_PRELOAD_JOBS: list[dict[str, object]] = []
_ORPHANED_OCR_ASYNC_JOBS: list[dict[str, object]] = []


class MainWindowShutdownMixin:
    @staticmethod
    def _disconnect_connection(connection: object | None) -> None:
        if connection is None:
            return
        try:
            QtCore.QObject.disconnect(connection)
        except Exception:
            pass

    @staticmethod
    def _disconnect_signal_slots(source: object | None, signal_name: str) -> None:
        if source is None:
            return
        signal = getattr(source, signal_name, None)
        if signal is None:
            return
        try:
            signal.disconnect()
        except Exception:
            pass

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
                # Fallback to slot-based disconnect if connection-handle
                # disconnect is not supported by the current binding/runtime.
                pass
        if thread is None or worker is None:
            return
        started_signal = getattr(thread, "started", None)
        run_slot = getattr(worker, "run", None)
        if started_signal is None or run_slot is None:
            return
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                started_signal.disconnect(run_slot)
            except Exception:
                pass

    def _orphan_running_ocr_preload_job(
        self,
        job: dict[str, object],
        *,
        reason: str,
    ) -> None:
        if not isinstance(job, dict):
            return
        if bool(job.get("_orphaned", False)):
            return
        thread = job.get("thread")
        worker = job.get("worker")
        relay = job.get("relay")
        self._disconnect_thread_worker_start(
            thread,
            worker,
            job.get("started_connection"),
        )
        for key in (
            "started_connection",
            "worker_done_connection",
            "done_connection",
            "worker_quit_connection",
            "cleanup_connection",
            "worker_delete_connection",
            "thread_delete_connection",
            "orphan_cleanup_connection",
        ):
            self._disconnect_connection(job.get(key))
        self._disconnect_signal_slots(worker, "finished")
        self._disconnect_signal_slots(relay, "done")
        self._disconnect_signal_slots(thread, "finished")
        for obj in (relay, worker, thread):
            try:
                if obj is not None and hasattr(obj, "setParent"):
                    obj.setParent(None)
            except Exception:
                pass
        if thread is not None:
            try:
                thread.requestInterruption()
            except Exception:
                pass
            try:
                thread.quit()
            except Exception:
                pass
            try:
                thread.terminate()
            except Exception:
                pass

        def _orphan_cleanup() -> None:
            try:
                _ORPHANED_OCR_PRELOAD_JOBS.remove(job)
            except Exception:
                pass

        if thread is not None and hasattr(thread, "finished"):
            try:
                job["orphan_cleanup_connection"] = thread.finished.connect(_orphan_cleanup)
            except Exception:
                pass
        job["_orphaned"] = True
        _ORPHANED_OCR_PRELOAD_JOBS.append(job)
        self._ocr_preload_job = None
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "shutdown_orphaned_thread",
                    reason=str(reason or "ocr_preload_thread"),
                )
            except Exception:
                pass

    def _orphan_running_ocr_async_job(
        self,
        job: dict[str, object],
        *,
        reason: str,
    ) -> None:
        if not isinstance(job, dict):
            return
        if bool(job.get("_orphaned", False)):
            return
        thread = job.get("thread")
        worker = job.get("worker")
        relay = job.get("relay")
        self._disconnect_thread_worker_start(
            thread,
            worker,
            job.get("started_connection"),
        )
        for key in (
            "started_connection",
            "worker_finished_connection",
            "worker_failed_connection",
            "relay_result_connection",
            "relay_error_connection",
            "worker_finished_quit_connection",
            "worker_failed_quit_connection",
            "worker_delete_connection",
            "thread_delete_connection",
            "orphan_cleanup_connection",
        ):
            self._disconnect_connection(job.get(key))
        self._disconnect_signal_slots(worker, "finished")
        self._disconnect_signal_slots(worker, "failed")
        self._disconnect_signal_slots(relay, "result")
        self._disconnect_signal_slots(relay, "error")
        self._disconnect_signal_slots(thread, "finished")
        for path in list(job.get("paths") or []):
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
        for obj in (relay, worker, thread):
            try:
                if obj is not None and hasattr(obj, "setParent"):
                    obj.setParent(None)
            except Exception:
                pass
        if thread is not None:
            try:
                thread.requestInterruption()
            except Exception:
                pass
            try:
                thread.quit()
            except Exception:
                pass
            try:
                thread.terminate()
            except Exception:
                pass

        def _orphan_cleanup() -> None:
            try:
                _ORPHANED_OCR_ASYNC_JOBS.remove(job)
            except Exception:
                pass

        if thread is not None and hasattr(thread, "finished"):
            try:
                job["orphan_cleanup_connection"] = thread.finished.connect(_orphan_cleanup)
            except Exception:
                pass
        job["_orphaned"] = True
        _ORPHANED_OCR_ASYNC_JOBS.append(job)
        self._ocr_async_job = None
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "shutdown_orphaned_thread",
                    reason=str(reason or "ocr_async_thread"),
                )
            except Exception:
                pass

    def _defer_close_for_running_thread(self, event: QtGui.QCloseEvent, *, reason: str) -> None:
        base_retry_ms = max(50, int(self._cfg("SHUTDOWN_THREAD_RETRY_MS", 180)))
        if str(reason or "") == "ocr_preload_thread":
            # OCR preload is non-critical during app close. Use a faster retry
            # cadence by default so shutdown does not feel stuck.
            ocr_default_retry_ms = max(30, min(base_retry_ms, 60))
            retry_ms = max(
                30,
                int(self._cfg("SHUTDOWN_OCR_PRELOAD_RETRY_MS", ocr_default_retry_ms)),
            )
        else:
            retry_ms = base_retry_ms
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
            graceful_key: str,
            terminate_key: str,
            retry_graceful_key: str,
            retry_terminate_key: str,
            graceful_default: int,
            terminate_default: int,
            retry_graceful_default: int = 0,
            retry_terminate_default: int = 120,
            min_terminate_wait_ms: int = 30,
            max_graceful_wait_ms: int | None = None,
            max_terminate_wait_ms: int | None = None,
        ) -> tuple[int, int]:
            def _cap(value: int, cap: int | None) -> int:
                if cap is None:
                    return value
                return min(value, max(0, int(cap)))

            if close_retry_active:
                graceful_ms = max(
                    0,
                    int(self._cfg(retry_graceful_key, retry_graceful_default)),
                )
                terminate_ms = max(
                    min_terminate_wait_ms,
                    int(self._cfg(retry_terminate_key, retry_terminate_default)),
                )
                graceful_ms = _cap(graceful_ms, max_graceful_wait_ms)
                terminate_ms = max(
                    min_terminate_wait_ms,
                    _cap(terminate_ms, max_terminate_wait_ms),
                )
                return graceful_ms, terminate_ms
            graceful_ms = max(0, int(self._cfg(graceful_key, graceful_default)))
            terminate_ms = max(
                min_terminate_wait_ms,
                int(self._cfg(terminate_key, terminate_default)),
            )
            graceful_ms = _cap(graceful_ms, max_graceful_wait_ms)
            terminate_ms = max(
                min_terminate_wait_ms,
                _cap(terminate_ms, max_terminate_wait_ms),
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
                graceful_key="SHUTDOWN_OCR_ASYNC_GRACEFUL_WAIT_MS",
                terminate_key="SHUTDOWN_OCR_ASYNC_TERMINATE_WAIT_MS",
                retry_graceful_key="SHUTDOWN_OCR_ASYNC_RETRY_GRACEFUL_WAIT_MS",
                retry_terminate_key="SHUTDOWN_OCR_ASYNC_RETRY_TERMINATE_WAIT_MS",
                graceful_default=150,
                terminate_default=180,
                retry_graceful_default=0,
                retry_terminate_default=80,
                min_terminate_wait_ms=50,
                max_graceful_wait_ms=260,
                max_terminate_wait_ms=220,
            )
            if not self._stop_qthread_for_close(
                thread,
                graceful_wait_ms=async_wait_ms,
                terminate_wait_ms=async_term_wait_ms,
            ):
                # OCR import is optional while app closes. Avoid close-retry
                # loops and continue shutdown with detached cleanup.
                self._orphan_running_ocr_async_job(
                    job,
                    reason="ocr_async_thread_shutdown",
                )
            current_async_job = getattr(self, "_ocr_async_job", None)
            if isinstance(current_async_job, dict):
                current_thread = current_async_job.get("thread")
                current_running = False
                if current_thread is not None and hasattr(current_thread, "isRunning"):
                    try:
                        current_running = bool(current_thread.isRunning())
                    except Exception:
                        current_running = False
                if current_running:
                    self._orphan_running_ocr_async_job(
                        current_async_job,
                        reason="ocr_async_thread_still_running",
                    )
                else:
                    self._ocr_async_job = None
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
                graceful_key="SHUTDOWN_OCR_PRELOAD_GRACEFUL_WAIT_MS",
                terminate_key="SHUTDOWN_OCR_PRELOAD_TERMINATE_WAIT_MS",
                retry_graceful_key="SHUTDOWN_OCR_PRELOAD_RETRY_GRACEFUL_WAIT_MS",
                retry_terminate_key="SHUTDOWN_OCR_PRELOAD_RETRY_TERMINATE_WAIT_MS",
                graceful_default=120,
                terminate_default=220,
                retry_graceful_default=0,
                retry_terminate_default=90,
                min_terminate_wait_ms=20,
                max_graceful_wait_ms=300,
                max_terminate_wait_ms=260,
            )
            if not self._stop_qthread_for_close(
                preload_thread,
                graceful_wait_ms=preload_wait_ms,
                terminate_wait_ms=preload_term_wait_ms,
            ):
                # OCR preload is optional during shutdown. Do not keep the UI
                # open in a retry loop; detach this job and continue closing.
                self._orphan_running_ocr_preload_job(
                    preload_job,
                    reason="ocr_preload_thread_shutdown",
                )
            current_preload_job = getattr(self, "_ocr_preload_job", None)
            if isinstance(current_preload_job, dict):
                current_thread = current_preload_job.get("thread")
                current_running = False
                if current_thread is not None and hasattr(current_thread, "isRunning"):
                    try:
                        current_running = bool(current_thread.isRunning())
                    except Exception:
                        current_running = False
                if current_running:
                    self._orphan_running_ocr_preload_job(
                        current_preload_job,
                        reason="ocr_preload_thread_still_running",
                    )
                else:
                    self._ocr_preload_job = None
            self._ocr_preload_job = None
        self._close_thread_wait_started_at = None
        if bool(self._cfg("SHUTDOWN_RELEASE_OCR_CACHE", False)) and hasattr(
            self, "_release_ocr_runtime_cache"
        ):
            try:
                self._release_ocr_runtime_cache()
            except Exception:
                pass
        self._set_app_event_filter_enabled(False)
        shutdown_manager.handle_close_event(self, event)
