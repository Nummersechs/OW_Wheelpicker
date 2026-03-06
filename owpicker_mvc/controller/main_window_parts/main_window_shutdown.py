from __future__ import annotations

from pathlib import Path
import time

from PySide6 import QtCore, QtGui

import i18n

from .. import shutdown_manager

_ORPHANED_OCR_PRELOAD_JOBS: list[dict[str, object]] = []
_ORPHANED_OCR_ASYNC_JOBS: list[dict[str, object]] = []
_ORPHANED_CHILD_QTHREADS: list[object] = []


class MainWindowShutdownMixin:
    @staticmethod
    def _disconnect_connection(connection: object | None) -> None:
        if connection is None:
            return
        try:
            is_valid = getattr(connection, "isValid", None)
            if callable(is_valid) and not bool(is_valid()):
                return
        except Exception:
            pass
        try:
            if not bool(connection):
                return
        except Exception:
            pass
        try:
            QtCore.QObject.disconnect(connection)
        except Exception:
            pass

    @staticmethod
    def _disconnect_signal_slots(
        source: object | None,
        signal_name: str,
        *slots: object | None,
    ) -> None:
        if source is None:
            return
        signal = getattr(source, signal_name, None)
        if signal is None:
            return
        # Never call bare `signal.disconnect()` here: when no slot is connected,
        # PySide may emit noisy RuntimeWarnings during shutdown.
        if not slots:
            return
        for slot in slots:
            if slot is None:
                continue
            try:
                signal.disconnect(slot)
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
            "cleanup_connection",
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

        # Treat only a truly finished thread as stopped. A thread can be
        # temporarily "not running" while startup/teardown is still in flight.
        if _is_finished():
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
        if stopped:
            return True
        # If the thread is not yet `finished`, keep deferring close instead of
        # proceeding and risking QThread destruction while still alive.
        if _is_finished():
            return True
        return False

    def _close_thread_wait_elapsed_ms(self) -> int:
        started = getattr(self, "_close_thread_wait_started_at", None)
        if started is None:
            return 0
        try:
            return max(0, int((time.monotonic() - float(started)) * 1000.0))
        except Exception:
            return 0

    def _close_thread_wait_timed_out(self) -> bool:
        timeout_ms = max(0, int(self._cfg("SHUTDOWN_THREAD_MAX_DEFER_MS", 2500)))
        if timeout_ms <= 0:
            return False
        return self._close_thread_wait_elapsed_ms() >= timeout_ms

    def _orphan_running_child_qthread(self, thread: object | None, *, reason: str) -> None:
        if thread is None:
            return
        try:
            if hasattr(thread, "setParent"):
                thread.setParent(None)
        except Exception:
            pass
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

        def _cleanup() -> None:
            try:
                _ORPHANED_CHILD_QTHREADS.remove(thread)
            except Exception:
                pass

        try:
            if hasattr(thread, "finished"):
                thread.finished.connect(_cleanup)
        except Exception:
            pass
        _ORPHANED_CHILD_QTHREADS.append(thread)
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "shutdown_orphaned_thread",
                    reason=str(reason or "child_qthread_shutdown"),
                )
            except Exception:
                pass

    def _running_child_qthreads(self, *, exclude: tuple[object | None, ...] = ()) -> list[QtCore.QThread]:
        try:
            threads = list(self.findChildren(QtCore.QThread))
        except Exception:
            return []
        if not threads:
            return []
        exclude_ids = {id(thread) for thread in exclude if thread is not None}
        current_thread = None
        try:
            current_thread = QtCore.QThread.currentThread()
        except Exception:
            current_thread = None
        running: list[QtCore.QThread] = []
        seen: set[int] = set()
        for thread in threads:
            if thread is None:
                continue
            tid = id(thread)
            if tid in seen or tid in exclude_ids:
                continue
            seen.add(tid)
            if current_thread is not None and thread is current_thread:
                continue
            try:
                if not bool(thread.isRunning()):
                    continue
            except Exception:
                continue
            running.append(thread)
        return running

    @staticmethod
    def _thread_is_running(thread: object | None) -> bool:
        if thread is None:
            return False
        try:
            return bool(thread.isRunning())
        except Exception:
            return False

    def _running_orphaned_qthreads(self) -> list[object]:
        running: list[object] = []
        seen: set[int] = set()
        stale_preload: list[dict[str, object]] = []
        stale_async: list[dict[str, object]] = []
        stale_child: list[object] = []

        for job in list(_ORPHANED_OCR_PRELOAD_JOBS):
            thread = job.get("thread") if isinstance(job, dict) else None
            if not self._thread_is_running(thread):
                stale_preload.append(job)
                continue
            tid = id(thread)
            if tid in seen:
                continue
            seen.add(tid)
            running.append(thread)

        for job in list(_ORPHANED_OCR_ASYNC_JOBS):
            thread = job.get("thread") if isinstance(job, dict) else None
            if not self._thread_is_running(thread):
                stale_async.append(job)
                continue
            tid = id(thread)
            if tid in seen:
                continue
            seen.add(tid)
            running.append(thread)

        for thread in list(_ORPHANED_CHILD_QTHREADS):
            if not self._thread_is_running(thread):
                stale_child.append(thread)
                continue
            tid = id(thread)
            if tid in seen:
                continue
            seen.add(tid)
            running.append(thread)

        for job in stale_preload:
            try:
                _ORPHANED_OCR_PRELOAD_JOBS.remove(job)
            except Exception:
                pass
        for job in stale_async:
            try:
                _ORPHANED_OCR_ASYNC_JOBS.remove(job)
            except Exception:
                pass
        for thread in stale_child:
            try:
                _ORPHANED_CHILD_QTHREADS.remove(thread)
            except Exception:
                pass
        return running

    def _defer_close_for_running_thread(self, event: QtGui.QCloseEvent, *, reason: str) -> None:
        retry_ms = 80 if str(reason or "") == "ocr_preload_thread" else 120
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
                    retry_ms=int(retry_ms),
                    elapsed_ms=int(elapsed_ms),
                )
            except Exception:
                pass
        event.ignore()
        QtCore.QTimer.singleShot(int(retry_ms), self.close)

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
            graceful_default: int,
            terminate_default: int,
            min_terminate_wait_ms: int = 30,
            max_graceful_wait_ms: int | None = None,
            max_terminate_wait_ms: int | None = None,
        ) -> tuple[int, int]:
            def _cap(value: int, cap: int | None) -> int:
                if cap is None:
                    return value
                return min(value, max(0, int(cap)))

            graceful_ms = max(0, int(self._cfg(graceful_key, graceful_default)))
            terminate_ms = max(
                min_terminate_wait_ms,
                int(self._cfg(terminate_key, terminate_default)),
            )
            if close_retry_active:
                # Keep close retries responsive: skip graceful wait and clamp
                # terminate wait to a short window on repeated attempts.
                graceful_ms = 0
                terminate_ms = min(terminate_ms, 120)
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
        async_thread = None
        if isinstance(job, dict):
            thread = job.get("thread")
            async_thread = thread
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
                graceful_default=80,
                terminate_default=120,
                min_terminate_wait_ms=50,
                max_graceful_wait_ms=120,
                max_terminate_wait_ms=140,
            )
            if not self._stop_qthread_for_close(
                thread,
                graceful_wait_ms=async_wait_ms,
                terminate_wait_ms=async_term_wait_ms,
            ):
                if self._close_thread_wait_timed_out():
                    self._orphan_running_ocr_async_job(
                        job,
                        reason="ocr_async_thread_timeout",
                    )
                else:
                    self._defer_close_for_running_thread(event, reason="ocr_async_thread")
                    return
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
                    if self._close_thread_wait_timed_out():
                        self._orphan_running_ocr_async_job(
                            current_async_job,
                            reason="ocr_async_thread_still_running_timeout",
                        )
                    else:
                        self._defer_close_for_running_thread(event, reason="ocr_async_thread")
                        return
                else:
                    self._ocr_async_job = None
            self._ocr_async_job = None
        preload_job = getattr(self, "_ocr_preload_job", None)
        preload_thread = None
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
                graceful_default=60,
                terminate_default=120,
                min_terminate_wait_ms=20,
                max_graceful_wait_ms=100,
                max_terminate_wait_ms=140,
            )
            if not self._stop_qthread_for_close(
                preload_thread,
                graceful_wait_ms=preload_wait_ms,
                terminate_wait_ms=preload_term_wait_ms,
            ):
                if self._close_thread_wait_timed_out():
                    self._orphan_running_ocr_preload_job(
                        preload_job,
                        reason="ocr_preload_thread_timeout",
                    )
                else:
                    self._defer_close_for_running_thread(event, reason="ocr_preload_thread")
                    return
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
                    if self._close_thread_wait_timed_out():
                        self._orphan_running_ocr_preload_job(
                            current_preload_job,
                            reason="ocr_preload_thread_still_running_timeout",
                        )
                    else:
                        self._defer_close_for_running_thread(event, reason="ocr_preload_thread")
                        return
                else:
                    self._ocr_preload_job = None
            self._ocr_preload_job = None

        # Guard against race windows where OCR job dicts are already cleared but
        # child QThreads are still alive and would crash on parent destruction.
        extra_threads = self._running_child_qthreads(exclude=(async_thread, preload_thread))
        if extra_threads:
            extra_wait_ms = 0 if close_retry_active else 80
            extra_terminate_wait_ms = 120
            for thread in extra_threads:
                if not self._stop_qthread_for_close(
                    thread,
                    graceful_wait_ms=extra_wait_ms,
                    terminate_wait_ms=extra_terminate_wait_ms,
                ):
                    if self._close_thread_wait_timed_out():
                        self._orphan_running_child_qthread(
                            thread,
                            reason="child_qthread_timeout",
                        )
                        continue
                    self._defer_close_for_running_thread(event, reason="child_qthread")
                    return
        orphan_threads = self._running_orphaned_qthreads()
        if orphan_threads:
            for thread in list(orphan_threads):
                self._stop_qthread_for_close(
                    thread,
                    graceful_wait_ms=0,
                    terminate_wait_ms=120,
                )
            if self._running_orphaned_qthreads():
                self._defer_close_for_running_thread(event, reason="orphaned_qthread")
                return
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
