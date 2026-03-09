from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import time
import warnings

from PySide6 import QtCore, QtGui

import i18n

from .. import shutdown_manager

_DETACHED_QTHREADS: list[object] = []


class MainWindowShutdownMixin:
    def _shutdown_force_exit_watchdog_enabled(self) -> bool:
        default_enabled = bool(sys.platform.startswith("win"))
        try:
            return bool(self._cfg("SHUTDOWN_FORCE_EXIT_WATCHDOG_ENABLED", default_enabled))
        except Exception:
            return default_enabled

    def _shutdown_force_exit_watchdog_timeout_ms(self) -> int:
        default_ms = 12000 if sys.platform.startswith("win") else 0
        try:
            value = int(self._cfg("SHUTDOWN_FORCE_EXIT_WATCHDOG_MS", default_ms))
        except Exception:
            value = default_ms
        return max(0, int(value))

    def _shutdown_force_exit_on_orphan_ms(self) -> int:
        default_ms = 2200 if sys.platform.startswith("win") else 0
        try:
            value = int(self._cfg("SHUTDOWN_FORCE_EXIT_ON_ORPHAN_MS", default_ms))
        except Exception:
            value = default_ms
        return max(0, int(value))

    def _arm_shutdown_force_exit_watchdog(
        self,
        *,
        reason: str = "",
        timeout_ms: int | None = None,
    ) -> None:
        if not self._shutdown_force_exit_watchdog_enabled():
            return
        timeout = self._shutdown_force_exit_watchdog_timeout_ms() if timeout_ms is None else int(timeout_ms)
        timeout = max(0, int(timeout))
        if timeout <= 0:
            return
        now = time.monotonic()
        deadline = now + (float(timeout) / 1000.0)
        current_deadline = getattr(self, "_shutdown_force_exit_deadline", None)
        if current_deadline is not None:
            try:
                # Keep the earliest active watchdog deadline.
                if float(current_deadline) <= deadline:
                    return
            except Exception:
                pass
        token = object()
        self._shutdown_force_exit_deadline = deadline
        self._shutdown_force_exit_watchdog_token = token

        def _watchdog(local_token: object, sleep_ms: int, fire_reason: str) -> None:
            time.sleep(max(0.0, float(sleep_ms) / 1000.0))
            active_token = getattr(self, "_shutdown_force_exit_watchdog_token", None)
            if active_token is not local_token:
                return
            py_threads_count = 0
            py_threads_preview = ""
            try:
                running_threads = list(threading.enumerate())
                py_threads_count = len(running_threads)
                names: list[str] = []
                for th in running_threads[:6]:
                    try:
                        names.append(str(getattr(th, "name", "") or "thread"))
                    except Exception:
                        names.append("thread")
                py_threads_preview = ",".join(names)
            except Exception:
                py_threads_count = 0
                py_threads_preview = ""
            if hasattr(self, "_trace_event"):
                try:
                    self._trace_event(
                        "shutdown_force_exit_watchdog_fired",
                        reason=str(fire_reason or "watchdog"),
                        timeout_ms=int(sleep_ms),
                        py_threads=int(py_threads_count),
                        py_threads_preview=str(py_threads_preview),
                    )
                except Exception:
                    pass
            # Final guard: process is still alive after close request.
            os._exit(0)

        thread = threading.Thread(
            target=_watchdog,
            args=(token, int(timeout), str(reason or "close_request")),
            name="shutdown_force_exit_watchdog",
            daemon=True,
        )
        thread.start()
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "shutdown_force_exit_watchdog_armed",
                    reason=str(reason or "close_request"),
                    timeout_ms=int(timeout),
                )
            except Exception:
                pass

    def _shutdown_force_stop_preload_immediate(self) -> bool:
        default_value = bool(sys.platform.startswith("win"))
        try:
            return bool(self._cfg("SHUTDOWN_OCR_PRELOAD_FORCE_STOP_ON_CLOSE", default_value))
        except Exception:
            return default_value

    def _warn_shutdown_suppressed_exception(self, where: str, exc: Exception) -> None:
        try:
            if bool(self._cfg("QUIET", False)):
                return
        except Exception:
            pass
        signature = (str(where or "shutdown"), type(exc).__name__, str(exc))
        seen = getattr(self, "_shutdown_suppressed_exception_seen", None)
        if not isinstance(seen, set):
            seen = set()
            setattr(self, "_shutdown_suppressed_exception_seen", seen)
        if signature in seen:
            return
        seen.add(signature)
        try:
            warnings.warn(
                f"Shutdown suppressed exception at {where}: {exc!r}",
                RuntimeWarning,
                stacklevel=2,
            )
        except Exception:
            pass
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "shutdown_suppressed_exception",
                    where=str(where or "shutdown"),
                    error=repr(exc),
                )
            except Exception:
                pass

    def _disconnect_connection(self, connection: object | None) -> None:
        if connection is None:
            return
        # Only disconnect concrete connection handles. Passing signal objects to
        # QObject.disconnect(...) can emit noisy RuntimeWarnings in PySide.
        try:
            connection_type = QtCore.QMetaObject.Connection
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("disconnect_connection:connection_type", exc)
            connection_type = None
        if connection_type is not None and not isinstance(connection, connection_type):
            return
        try:
            is_valid = getattr(connection, "isValid", None)
            if callable(is_valid) and not bool(is_valid()):
                return
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("disconnect_connection:is_valid", exc)
        try:
            if not bool(connection):
                return
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("disconnect_connection:truthy", exc)
        try:
            QtCore.QObject.disconnect(connection)
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("disconnect_connection:disconnect", exc)

    def _disconnect_signal_slots(
        self,
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
            except Exception as exc:
                self._warn_shutdown_suppressed_exception(
                    f"disconnect_signal_slots:{signal_name}",
                    exc,
                )

    def _disconnect_thread_worker_start(
        self,
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
            except Exception as exc:
                # Fallback to slot-based disconnect if connection-handle
                # disconnect is not supported by the current binding/runtime.
                self._warn_shutdown_suppressed_exception(
                    "disconnect_thread_worker_start:connection",
                    exc,
                )
        if thread is None or worker is None:
            return
        started_signal = getattr(thread, "started", None)
        run_slot = getattr(worker, "run", None)
        if started_signal is None or run_slot is None:
            return
        try:
            started_signal.disconnect(run_slot)
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("disconnect_thread_worker_start:slot", exc)

    def _detach_qthread_for_shutdown(self, thread: object | None, *, reason: str) -> None:
        if thread is None:
            return
        if thread in _DETACHED_QTHREADS:
            return
        try:
            if hasattr(thread, "setParent"):
                thread.setParent(None)
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("detach_qthread:set_parent", exc)
        try:
            thread.requestInterruption()
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("detach_qthread:request_interruption", exc)
        try:
            thread.quit()
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("detach_qthread:quit", exc)

        def _cleanup_detached() -> None:
            try:
                _DETACHED_QTHREADS.remove(thread)
            except Exception as exc:
                self._warn_shutdown_suppressed_exception("detach_qthread:cleanup_remove", exc)
            try:
                if hasattr(thread, "deleteLater"):
                    thread.deleteLater()
            except Exception as exc:
                self._warn_shutdown_suppressed_exception("detach_qthread:cleanup_delete_later", exc)

        try:
            if hasattr(thread, "finished"):
                thread.finished.connect(_cleanup_detached)
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("detach_qthread:connect_finished", exc)
        _DETACHED_QTHREADS.append(thread)
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "shutdown_orphaned_thread",
                    reason=str(reason or "detached_qthread"),
                )
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
            "lifecycle_connection",
            "cleanup_connection",
            "worker_delete_connection",
            "thread_delete_connection",
            "orphan_cleanup_connection",
        ):
            self._disconnect_connection(job.get(key))
        self._disconnect_signal_slots(worker, "finished")
        self._disconnect_signal_slots(relay, "done")
        self._disconnect_signal_slots(thread, "finished")
        for obj in (relay, worker):
            try:
                if obj is not None and hasattr(obj, "setParent"):
                    obj.setParent(None)
                if obj is not None and hasattr(obj, "deleteLater"):
                    obj.deleteLater()
            except Exception as exc:
                self._warn_shutdown_suppressed_exception("orphan_preload:cleanup_obj", exc)
        self._detach_qthread_for_shutdown(thread, reason=reason or "ocr_preload_thread")
        self._ocr_preload_job = None
        self._arm_shutdown_force_exit_watchdog(
            reason="ocr_preload_orphaned",
            timeout_ms=self._shutdown_force_exit_on_orphan_ms(),
        )

    def _orphan_running_ocr_async_job(
        self,
        job: dict[str, object],
        *,
        reason: str,
    ) -> None:
        if not isinstance(job, dict):
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
            except Exception as exc:
                self._warn_shutdown_suppressed_exception("orphan_async:unlink_path", exc)
        for obj in (relay, worker):
            try:
                if obj is not None and hasattr(obj, "setParent"):
                    obj.setParent(None)
                if obj is not None and hasattr(obj, "deleteLater"):
                    obj.deleteLater()
            except Exception as exc:
                self._warn_shutdown_suppressed_exception("orphan_async:cleanup_obj", exc)
        self._detach_qthread_for_shutdown(thread, reason=reason or "ocr_async_thread")
        self._ocr_async_job = None
        self._arm_shutdown_force_exit_watchdog(
            reason="ocr_async_orphaned",
            timeout_ms=self._shutdown_force_exit_on_orphan_ms(),
        )

    def _stop_qthread_for_close(self, thread: object | None) -> bool:
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
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("stop_qthread:request_interruption", exc)
        try:
            thread.quit()
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("stop_qthread:quit", exc)
        return _is_finished()

    def _qthread_wait_profile_ms(self, *, reason: str = "") -> tuple[int, int]:
        reason_key = str(reason or "").strip().casefold()
        if reason_key == "ocr_preload_thread":
            graceful_ms = int(self._cfg("SHUTDOWN_OCR_PRELOAD_GRACEFUL_WAIT_MS", 1400))
            terminate_ms = int(self._cfg("SHUTDOWN_OCR_PRELOAD_TERMINATE_WAIT_MS", 350))
            return max(0, graceful_ms), max(0, terminate_ms)
        if reason_key == "ocr_async_thread":
            graceful_ms = int(self._cfg("SHUTDOWN_OCR_ASYNC_GRACEFUL_WAIT_MS", 1200))
            terminate_ms = int(self._cfg("SHUTDOWN_OCR_ASYNC_TERMINATE_WAIT_MS", 700))
            return max(0, graceful_ms), max(0, terminate_ms)
        graceful_ms = int(self._cfg("SHUTDOWN_CHILD_THREAD_GRACEFUL_WAIT_MS", 350))
        terminate_ms = int(self._cfg("SHUTDOWN_CHILD_THREAD_TERMINATE_WAIT_MS", 250))
        return max(0, graceful_ms), max(0, terminate_ms)

    def _force_stop_qthread_for_close(self, thread: object | None, *, reason: str = "") -> bool:
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

        if _is_finished():
            return True

        graceful_wait_ms, terminate_wait_ms = self._qthread_wait_profile_ms(reason=reason)
        try:
            thread.requestInterruption()
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("force_stop_qthread:request_interruption", exc)
        try:
            thread.quit()
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("force_stop_qthread:quit", exc)

        graceful_stopped = False
        if graceful_wait_ms > 0 and hasattr(thread, "wait"):
            try:
                graceful_stopped = bool(thread.wait(int(graceful_wait_ms)))
            except Exception as exc:
                self._warn_shutdown_suppressed_exception("force_stop_qthread:wait_graceful", exc)
        if graceful_stopped or _is_finished():
            return True

        try:
            if hasattr(thread, "terminate"):
                thread.terminate()
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("force_stop_qthread:terminate", exc)

        terminated = False
        if terminate_wait_ms > 0 and hasattr(thread, "wait"):
            try:
                terminated = bool(thread.wait(int(terminate_wait_ms)))
            except Exception as exc:
                self._warn_shutdown_suppressed_exception("force_stop_qthread:wait_terminate", exc)

        stopped = bool(terminated or _is_finished())
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "shutdown_force_stop_qthread",
                    reason=str(reason or "thread"),
                    graceful_wait_ms=int(graceful_wait_ms),
                    terminate_wait_ms=int(terminate_wait_ms),
                    stopped=bool(stopped),
                )
            except Exception:
                pass
        return stopped

    def _force_stop_detached_qthreads(self) -> None:
        for thread in list(_DETACHED_QTHREADS):
            self._force_stop_qthread_for_close(thread, reason="child_qthread")

    def _close_thread_wait_elapsed_ms(self) -> int:
        started = getattr(self, "_close_thread_wait_started_at", None)
        if started is None:
            return 0
        try:
            return max(0, int((time.monotonic() - float(started)) * 1000.0))
        except Exception:
            return 0

    def _close_thread_wait_timeout_ms(self, *, reason: str = "") -> int:
        base_timeout_ms = max(0, int(self._cfg("SHUTDOWN_THREAD_MAX_DEFER_MS", 2500)))
        reason_key = str(reason or "").strip().casefold()
        if reason_key == "ocr_preload_thread":
            # OCR preload should not block app close for long.
            return max(0, int(self._cfg("SHUTDOWN_OCR_PRELOAD_MAX_DEFER_MS", min(base_timeout_ms, 1200))))
        if reason_key == "ocr_async_thread":
            return max(0, int(self._cfg("SHUTDOWN_OCR_ASYNC_MAX_DEFER_MS", min(base_timeout_ms, 1500))))
        if reason_key == "child_qthread":
            return max(0, int(self._cfg("SHUTDOWN_CHILD_THREAD_MAX_DEFER_MS", min(base_timeout_ms, 1200))))
        if reason_key == "python_thread":
            return max(0, int(self._cfg("SHUTDOWN_PYTHON_THREAD_MAX_DEFER_MS", min(base_timeout_ms, 1800))))
        return base_timeout_ms

    def _close_thread_wait_timed_out(self, *, reason: str = "") -> bool:
        timeout_ms = self._close_thread_wait_timeout_ms(reason=reason)
        if timeout_ms <= 0:
            return False
        return self._close_thread_wait_elapsed_ms() >= timeout_ms

    def _orphan_running_child_qthread(self, thread: object | None, *, reason: str) -> None:
        self._detach_qthread_for_shutdown(thread, reason=reason or "child_qthread_shutdown")
        self._arm_shutdown_force_exit_watchdog(
            reason="child_qthread_orphaned",
            timeout_ms=self._shutdown_force_exit_on_orphan_ms(),
        )

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

    def _prune_detached_qthreads(self) -> None:
        stale: list[object] = []
        for thread in list(_DETACHED_QTHREADS):
            running = False
            try:
                running = bool(thread is not None and thread.isRunning())
            except Exception:
                running = False
            if not running:
                stale.append(thread)
        for thread in stale:
            try:
                _DETACHED_QTHREADS.remove(thread)
            except Exception as exc:
                self._warn_shutdown_suppressed_exception("prune_detached:remove", exc)

    def _has_running_detached_qthreads(self) -> bool:
        for thread in list(_DETACHED_QTHREADS):
            try:
                if thread is not None and bool(thread.isRunning()):
                    return True
            except Exception:
                continue
        return False

    def _running_non_daemon_python_threads(self) -> list[threading.Thread]:
        running: list[threading.Thread] = []
        main_thread = threading.main_thread()
        for thread in list(threading.enumerate()):
            if thread is None or thread is main_thread:
                continue
            try:
                if bool(getattr(thread, "daemon", False)):
                    continue
            except Exception:
                continue
            running.append(thread)
        return running

    def _qthread_preview_entry(self, thread: object | None, *, label: str = "") -> str:
        if thread is None:
            return ""
        try:
            running = bool(thread.isRunning())
        except Exception:
            running = False
        try:
            finished = bool(thread.isFinished())
        except Exception:
            finished = False
        try:
            interrupted = bool(thread.isInterruptionRequested())
        except Exception:
            interrupted = False
        try:
            name = str(thread.objectName() or "").strip()
        except Exception:
            name = ""
        parts: list[str] = []
        if label:
            parts.append(str(label))
        parts.append(f"id={id(thread)}")
        if name:
            parts.append(f"name={name}")
        parts.append(f"running={1 if running else 0}")
        parts.append(f"finished={1 if finished else 0}")
        parts.append(f"interrupted={1 if interrupted else 0}")
        return ",".join(parts)

    def _python_thread_preview_entry(self, thread: threading.Thread | None) -> str:
        if thread is None:
            return ""
        try:
            name = str(getattr(thread, "name", "") or "thread")
        except Exception:
            name = "thread"
        try:
            ident = int(getattr(thread, "ident", 0) or 0)
        except Exception:
            ident = 0
        try:
            alive = bool(thread.is_alive())
        except Exception:
            alive = False
        try:
            daemon = bool(getattr(thread, "daemon", False))
        except Exception:
            daemon = False
        return f"name={name},ident={ident},alive={1 if alive else 0},daemon={1 if daemon else 0}"

    def _trace_shutdown_blockers(self, *, stage: str, reason: str = "", force: bool = False) -> None:
        tracer = getattr(self, "_trace_event", None)
        if not callable(tracer):
            return

        now = time.monotonic()
        if not force:
            try:
                interval_ms = max(0, int(self._cfg("SHUTDOWN_BLOCKER_TRACE_INTERVAL_MS", 250)))
            except Exception:
                interval_ms = 250
            if interval_ms > 0:
                last = getattr(self, "_shutdown_blocker_trace_last_at", None)
                if isinstance(last, (int, float)):
                    if (now - float(last)) * 1000.0 < float(interval_ms):
                        return
        self._shutdown_blocker_trace_last_at = now

        async_job = getattr(self, "_ocr_async_job", None)
        preload_job = getattr(self, "_ocr_preload_job", None)
        async_thread = async_job.get("thread") if isinstance(async_job, dict) else None
        preload_thread = preload_job.get("thread") if isinstance(preload_job, dict) else None

        running_children = self._running_child_qthreads(exclude=(async_thread, preload_thread))
        detached_running: list[object] = []
        for thread in list(_DETACHED_QTHREADS):
            try:
                if thread is not None and bool(thread.isRunning()):
                    detached_running.append(thread)
            except Exception:
                continue
        py_threads = self._running_non_daemon_python_threads()

        child_preview = "|".join(
            entry
            for entry in (
                self._qthread_preview_entry(thread, label="child")
                for thread in running_children[:6]
            )
            if entry
        )
        detached_preview = "|".join(
            entry
            for entry in (
                self._qthread_preview_entry(thread, label="detached")
                for thread in detached_running[:6]
            )
            if entry
        )
        py_preview = "|".join(
            entry
            for entry in (
                self._python_thread_preview_entry(thread)
                for thread in py_threads[:8]
            )
            if entry
        )
        try:
            tracer(
                "shutdown_blockers",
                stage=str(stage or "unknown"),
                reason=str(reason or ""),
                ocr_async_job=int(isinstance(async_job, dict)),
                ocr_preload_job=int(isinstance(preload_job, dict)),
                ocr_async_thread=self._qthread_preview_entry(async_thread, label="ocr_async"),
                ocr_preload_thread=self._qthread_preview_entry(preload_thread, label="ocr_preload"),
                child_qthreads=int(len(running_children)),
                child_qthreads_preview=str(child_preview),
                detached_qthreads=int(len(detached_running)),
                detached_qthreads_preview=str(detached_preview),
                py_threads=int(len(py_threads)),
                py_threads_preview=str(py_preview),
            )
        except Exception:
            pass

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
        self._trace_shutdown_blockers(stage="defer", reason=str(reason or "thread_running"))
        event.ignore()
        if not isinstance(self, QtCore.QObject):
            QtCore.QTimer.singleShot(int(retry_ms), self.close)
            return
        timer = getattr(self, "_close_retry_timer", None)
        if timer is None:
            try:
                timer = QtCore.QTimer(self)
                timer.setSingleShot(True)
                timer.timeout.connect(self.close)
                if hasattr(self, "_timers"):
                    self._timers.register(timer)
                self._close_retry_timer = timer
            except Exception:
                timer = None
        if timer is None:
            QtCore.QTimer.singleShot(int(retry_ms), self.close)
            return
        if not timer.isActive():
            timer.start(int(retry_ms))

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
        # Arm a process-level fallback immediately on close request.
        # This protects against rare cases where background threads/preload
        # jobs never finish and Qt would otherwise keep the process alive.
        self._arm_shutdown_force_exit_watchdog(reason="close_request")

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
        retry_timer = getattr(self, "_close_retry_timer", None)
        if retry_timer is not None and retry_timer.isActive():
            retry_timer.stop()
        # Mark close intent before thread checks/cancellation to block any new
        # OCR preload scheduling paths during shutdown retries.
        self._closing = True
        self._trace_shutdown_blockers(stage="close_enter", reason="close_request", force=True)

        if hasattr(self, "_cancel_ocr_background_preload"):
            try:
                self._cancel_ocr_background_preload()
            except Exception as exc:
                self._warn_shutdown_suppressed_exception("close_event:cancel_ocr_preload_timer", exc)
        if hasattr(self, "_cancel_ocr_runtime_cache_release"):
            try:
                self._cancel_ocr_runtime_cache_release()
            except Exception as exc:
                self._warn_shutdown_suppressed_exception("close_event:cancel_ocr_cache_release_timer", exc)

        job = getattr(self, "_ocr_async_job", None)
        async_thread = None
        if isinstance(job, dict):
            thread = job.get("thread")
            async_thread = thread
            worker = job.get("worker")
            cancel_slot = getattr(worker, "cancel", None)
            if callable(cancel_slot):
                try:
                    cancel_slot()
                except Exception as exc:
                    self._warn_shutdown_suppressed_exception("close_event:async_worker_cancel", exc)
            self._disconnect_thread_worker_start(
                thread,
                worker,
                job.get("started_connection"),
            )
            for path in list(job.get("paths") or []):
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception as exc:
                    self._warn_shutdown_suppressed_exception("close_event:async_unlink_path", exc)
            if not self._stop_qthread_for_close(
                thread,
            ):
                if self._close_thread_wait_timed_out(reason="ocr_async_thread"):
                    if not self._force_stop_qthread_for_close(thread, reason="ocr_async_thread"):
                        self._defer_close_for_running_thread(event, reason="ocr_async_thread")
                        return
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
                    if self._close_thread_wait_timed_out(reason="ocr_async_thread"):
                        if not self._force_stop_qthread_for_close(current_thread, reason="ocr_async_thread"):
                            self._defer_close_for_running_thread(event, reason="ocr_async_thread")
                            return
                    else:
                        self._defer_close_for_running_thread(event, reason="ocr_async_thread")
                        return
                else:
                    self._ocr_async_job = None
            self._ocr_async_job = None
        preload_job = getattr(self, "_ocr_preload_job", None)
        preload_thread = None
        if isinstance(preload_job, dict):
            force_stop_preload_immediate = self._shutdown_force_stop_preload_immediate()
            preload_thread = preload_job.get("thread")
            preload_worker = preload_job.get("worker")
            cancel_slot = getattr(preload_worker, "cancel", None)
            if callable(cancel_slot):
                try:
                    cancel_slot()
                except Exception as exc:
                    self._warn_shutdown_suppressed_exception("close_event:preload_worker_cancel", exc)
            self._disconnect_thread_worker_start(
                preload_thread,
                preload_worker,
                preload_job.get("started_connection"),
            )
            if not self._stop_qthread_for_close(
                preload_thread,
            ):
                if force_stop_preload_immediate:
                    if not self._force_stop_qthread_for_close(preload_thread, reason="ocr_preload_thread"):
                        self._defer_close_for_running_thread(event, reason="ocr_preload_thread")
                        return
                else:
                    if self._close_thread_wait_timed_out(reason="ocr_preload_thread"):
                        if not self._force_stop_qthread_for_close(preload_thread, reason="ocr_preload_thread"):
                            self._defer_close_for_running_thread(event, reason="ocr_preload_thread")
                            return
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
                    if force_stop_preload_immediate:
                        if not self._force_stop_qthread_for_close(
                            current_thread,
                            reason="ocr_preload_thread",
                        ):
                            self._defer_close_for_running_thread(event, reason="ocr_preload_thread")
                            return
                    elif self._close_thread_wait_timed_out(reason="ocr_preload_thread"):
                        if not self._force_stop_qthread_for_close(
                            current_thread,
                            reason="ocr_preload_thread",
                        ):
                            self._defer_close_for_running_thread(event, reason="ocr_preload_thread")
                            return
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
            for thread in extra_threads:
                if not self._stop_qthread_for_close(
                    thread,
                ):
                    if self._close_thread_wait_timed_out(reason="child_qthread"):
                        if not self._force_stop_qthread_for_close(thread, reason="child_qthread"):
                            self._defer_close_for_running_thread(event, reason="child_qthread")
                            return
                        continue
                    self._defer_close_for_running_thread(event, reason="child_qthread")
                    return
        # Detached threads are intentionally decoupled from the window lifetime.
        # Try to force-stop still-running detached threads so the process can
        # terminate cleanly instead of lingering in background.
        self._force_stop_detached_qthreads()
        self._prune_detached_qthreads()
        if self._has_running_detached_qthreads():
            self._defer_close_for_running_thread(event, reason="child_qthread")
            return
        running_py_threads = self._running_non_daemon_python_threads()
        if running_py_threads:
            preview = ",".join(
                str(getattr(thread, "name", "") or "thread")
                for thread in running_py_threads[:6]
            )
            if hasattr(self, "_trace_event"):
                try:
                    self._trace_event(
                        "shutdown_python_threads_running",
                        count=int(len(running_py_threads)),
                        preview=str(preview),
                    )
                except Exception:
                    pass
            if self._close_thread_wait_timed_out(reason="python_thread"):
                if hasattr(self, "_trace_event"):
                    try:
                        self._trace_event(
                            "shutdown_python_threads_timeout",
                            count=int(len(running_py_threads)),
                            preview=str(preview),
                        )
                    except Exception:
                        pass
            else:
                self._defer_close_for_running_thread(event, reason="python_thread")
                return
        self._close_thread_wait_started_at = None
        if bool(self._cfg("SHUTDOWN_RELEASE_OCR_CACHE", False)) and hasattr(
            self, "_release_ocr_runtime_cache"
        ):
            try:
                self._release_ocr_runtime_cache()
            except Exception as exc:
                self._warn_shutdown_suppressed_exception("close_event:release_ocr_runtime_cache", exc)
        self._trace_shutdown_blockers(stage="close_commit", reason="before_handle_close", force=True)
        self._set_app_event_filter_enabled(False)
        shutdown_manager.handle_close_event(self, event)
