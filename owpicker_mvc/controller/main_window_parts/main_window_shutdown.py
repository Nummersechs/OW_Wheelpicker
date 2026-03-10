from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
import time
import warnings

from PySide6 import QtCore, QtGui

from .. import shutdown_manager
from ..shutdown_flow_coordinator import ShutdownFlowCoordinator
from ..shutdown_thread_coordinator import ShutdownThreadCoordinator

_DETACHED_QTHREADS: list[object] = []


class MainWindowShutdownMixin:
    def _shutdown_settings(self):
        settings = getattr(self, "settings", None)
        return getattr(settings, "shutdown", None)

    def _shutdown_force_exit_watchdog_enabled(self) -> bool:
        default_enabled = bool(sys.platform.startswith("win"))
        section = self._shutdown_settings()
        if section is not None and hasattr(section, "force_exit_watchdog_enabled"):
            try:
                return bool(getattr(section, "force_exit_watchdog_enabled"))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg("SHUTDOWN_FORCE_EXIT_WATCHDOG_ENABLED", default_enabled))

    def _shutdown_force_exit_watchdog_timeout_ms(self) -> int:
        default_ms = 12000 if sys.platform.startswith("win") else 0
        section = self._shutdown_settings()
        if section is not None and hasattr(section, "force_exit_watchdog_ms"):
            try:
                return max(0, int(getattr(section, "force_exit_watchdog_ms")))
            except (TypeError, ValueError):
                pass
        try:
            value = int(self._cfg("SHUTDOWN_FORCE_EXIT_WATCHDOG_MS", default_ms))
        except (TypeError, ValueError):
            value = default_ms
        return max(0, int(value))

    def _shutdown_force_exit_on_orphan_ms(self) -> int:
        default_ms = 2200 if sys.platform.startswith("win") else 0
        section = self._shutdown_settings()
        if section is not None and hasattr(section, "force_exit_on_orphan_ms"):
            try:
                return max(0, int(getattr(section, "force_exit_on_orphan_ms")))
            except (TypeError, ValueError):
                pass
        try:
            value = int(self._cfg("SHUTDOWN_FORCE_EXIT_ON_ORPHAN_MS", default_ms))
        except (TypeError, ValueError):
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
        self._set_shutdown_runtime_state(
            shutdown_force_exit_deadline=deadline,
            shutdown_force_exit_watchdog_token=token,
        )

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
        section = self._shutdown_settings()
        if section is not None and hasattr(section, "ocr_preload_force_stop_on_close"):
            try:
                return bool(getattr(section, "ocr_preload_force_stop_on_close"))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg("SHUTDOWN_OCR_PRELOAD_FORCE_STOP_ON_CLOSE", default_value))

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

    def _shutdown_thread_coordinator(self) -> ShutdownThreadCoordinator:
        coordinator = getattr(self, "_shutdown_thread_coordinator_obj", None)
        if isinstance(coordinator, ShutdownThreadCoordinator):
            return coordinator
        coordinator = ShutdownThreadCoordinator(self)
        self._shutdown_thread_coordinator_obj = coordinator
        return coordinator

    def _shutdown_flow_coordinator(self) -> ShutdownFlowCoordinator:
        coordinator = getattr(self, "_shutdown_flow_coordinator_obj", None)
        if isinstance(coordinator, ShutdownFlowCoordinator):
            return coordinator
        coordinator = ShutdownFlowCoordinator(self)
        self._shutdown_flow_coordinator_obj = coordinator
        return coordinator

    def _disconnect_connection(self, connection: object | None) -> None:
        # Only disconnect concrete connection handles. Passing signal objects to
        # QObject.disconnect(...) can emit noisy RuntimeWarnings in PySide.
        try:
            connection_type = QtCore.QMetaObject.Connection
        except Exception as exc:
            self._warn_shutdown_suppressed_exception("disconnect_connection:connection_type", exc)
            connection_type = None
        self._shutdown_thread_coordinator().disconnect_connection(
            connection,
            connection_type=connection_type,
        )

    def _disconnect_signal_slots(
        self,
        source: object | None,
        signal_name: str,
        *slots: object | None,
    ) -> None:
        # Never call bare `signal.disconnect()` here: when no slot is connected,
        # PySide may emit noisy RuntimeWarnings during shutdown.
        self._shutdown_thread_coordinator().disconnect_signal_slots(source, signal_name, *slots)

    def _disconnect_thread_worker_start(
        self,
        thread: object | None,
        worker: object | None,
        started_connection: object | None = None,
    ) -> None:
        """Best effort: prevent delayed `thread.started -> worker.run` execution during shutdown."""
        self._shutdown_thread_coordinator().disconnect_thread_worker_start(
            thread,
            worker,
            started_connection,
            disconnect_connection_fn=self._disconnect_connection,
        )

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
        return self._shutdown_thread_coordinator().stop_qthread_for_close(thread)

    def _qthread_wait_profile_ms(self, *, reason: str = "") -> tuple[int, int]:
        return self._shutdown_thread_coordinator().qthread_wait_profile_ms(reason=reason)

    def _force_stop_qthread_for_close(self, thread: object | None, *, reason: str = "") -> bool:
        stopped = self._shutdown_thread_coordinator().force_stop_qthread_for_close(
            thread,
            reason=reason,
        )
        graceful_wait_ms, terminate_wait_ms = self._qthread_wait_profile_ms(reason=reason)
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
        section = self._shutdown_settings()
        base_timeout_ms = 2500
        if section is not None and hasattr(section, "thread_max_defer_ms"):
            try:
                base_timeout_ms = max(0, int(getattr(section, "thread_max_defer_ms")))
            except (TypeError, ValueError):
                base_timeout_ms = 2500
        else:
            try:
                base_timeout_ms = max(0, int(self._cfg("SHUTDOWN_THREAD_MAX_DEFER_MS", 2500)))
            except (TypeError, ValueError):
                base_timeout_ms = 2500
        reason_key = str(reason or "").strip().casefold()
        if reason_key == "ocr_preload_thread":
            # OCR preload should not block app close for long.
            if section is not None and hasattr(section, "ocr_preload_max_defer_ms"):
                try:
                    return max(0, int(getattr(section, "ocr_preload_max_defer_ms")))
                except (TypeError, ValueError):
                    pass
            return max(0, int(self._cfg("SHUTDOWN_OCR_PRELOAD_MAX_DEFER_MS", min(base_timeout_ms, 1200))))
        if reason_key == "ocr_async_thread":
            if section is not None and hasattr(section, "ocr_async_max_defer_ms"):
                try:
                    return max(0, int(getattr(section, "ocr_async_max_defer_ms")))
                except (TypeError, ValueError):
                    pass
            return max(0, int(self._cfg("SHUTDOWN_OCR_ASYNC_MAX_DEFER_MS", min(base_timeout_ms, 1500))))
        if reason_key == "child_qthread":
            if section is not None and hasattr(section, "child_thread_max_defer_ms"):
                try:
                    return max(0, int(getattr(section, "child_thread_max_defer_ms")))
                except (TypeError, ValueError):
                    pass
            return max(0, int(self._cfg("SHUTDOWN_CHILD_THREAD_MAX_DEFER_MS", min(base_timeout_ms, 1200))))
        if reason_key == "python_thread":
            if section is not None and hasattr(section, "python_thread_max_defer_ms"):
                try:
                    return max(0, int(getattr(section, "python_thread_max_defer_ms")))
                except (TypeError, ValueError):
                    pass
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
        self._shutdown_flow_coordinator().trace_shutdown_blockers(
            stage=stage,
            reason=reason,
            force=force,
            detached_threads=_DETACHED_QTHREADS,
        )

    def _defer_close_for_running_thread(self, event: QtGui.QCloseEvent, *, reason: str) -> None:
        self._shutdown_flow_coordinator().defer_close_for_running_thread(
            event,
            reason=reason,
        )

    def _ensure_close_overlay_timer(self) -> QtCore.QTimer:
        return self._shutdown_flow_coordinator().ensure_close_overlay_timer()

    def _continue_close_after_overlay(self) -> None:
        self._shutdown_flow_coordinator().continue_close_after_overlay()

    def _show_close_overlay(self) -> bool:
        return self._shutdown_flow_coordinator().show_close_overlay()

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
        self._set_shutdown_runtime_state(closing=True)
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
        self._set_shutdown_runtime_state(close_thread_wait_started_at=None)
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
