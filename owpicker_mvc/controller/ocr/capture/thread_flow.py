from __future__ import annotations

import time
from pathlib import Path


def create_async_job(
    mw,
    *,
    role: str,
    temp_paths: list[Path],
    runtime_cfg: dict,
    request_started_at: float,
    ocr_extract_worker_cls,
    ocr_result_relay_cls,
    qtcore,
    ocr_runtime_trace_module,
) -> tuple[dict, object, object, object]:
    thread = qtcore.QThread(mw)
    try:
        role_suffix = str(role or "").strip().casefold() or "role"
        thread.setObjectName(f"ocr_async_thread_{role_suffix}")
    except Exception:
        pass

    worker = ocr_extract_worker_cls(temp_paths, runtime_cfg)
    try:
        worker.setObjectName("ocr_async_worker")
    except Exception:
        pass
    worker.moveToThread(thread)
    relay = ocr_result_relay_cls(mw)
    job = {
        "thread": thread,
        "worker": worker,
        "relay": relay,
        "paths": list(temp_paths),
        "role": role,
        "request_started_mono": float(request_started_at),
        "worker_started_mono": None,
    }
    setattr(mw, "_ocr_async_job", job)
    ocr_runtime_trace_module.trace(
        "ocr_async_import:worker_created",
        role=str(role or ""),
        image_count=len(list(temp_paths or [])),
    )
    return job, thread, worker, relay


def connect_async_job_signals(
    *,
    job: dict,
    thread,
    worker,
    relay,
    handle_result_fn,
    handle_error_fn,
    cleanup_finished_job_fn,
    qtcore,
) -> None:
    try:
        job["worker_finished_connection"] = worker.finished.connect(
            relay.forward_result,
            qtcore.Qt.QueuedConnection,
        )
    except Exception:
        worker.finished.connect(relay.forward_result, qtcore.Qt.QueuedConnection)
        job["worker_finished_connection"] = None
    try:
        job["worker_failed_connection"] = worker.failed.connect(
            relay.forward_error,
            qtcore.Qt.QueuedConnection,
        )
    except Exception:
        worker.failed.connect(relay.forward_error, qtcore.Qt.QueuedConnection)
        job["worker_failed_connection"] = None
    try:
        job["relay_result_connection"] = relay.result.connect(handle_result_fn)
    except Exception:
        relay.result.connect(handle_result_fn)
        job["relay_result_connection"] = None
    try:
        job["relay_error_connection"] = relay.error.connect(handle_error_fn)
    except Exception:
        relay.error.connect(handle_error_fn)
        job["relay_error_connection"] = None
    try:
        job["worker_finished_quit_connection"] = worker.finished.connect(thread.quit)
    except Exception:
        worker.finished.connect(thread.quit)
        job["worker_finished_quit_connection"] = None
    try:
        job["worker_failed_quit_connection"] = worker.failed.connect(thread.quit)
    except Exception:
        worker.failed.connect(thread.quit)
        job["worker_failed_quit_connection"] = None
    try:
        job["started_connection"] = thread.started.connect(worker.run)
    except Exception:
        thread.started.connect(worker.run)
        job["started_connection"] = None
    try:
        job["worker_delete_connection"] = thread.finished.connect(worker.deleteLater)
    except Exception:
        thread.finished.connect(worker.deleteLater)
        job["worker_delete_connection"] = None
    try:
        job["thread_delete_connection"] = thread.finished.connect(thread.deleteLater)
    except Exception:
        thread.finished.connect(thread.deleteLater)
        job["thread_delete_connection"] = None
    try:
        job["cleanup_connection"] = thread.finished.connect(cleanup_finished_job_fn)
    except Exception:
        thread.finished.connect(cleanup_finished_job_fn)
        job["cleanup_connection"] = None


def start_async_job_thread(
    *,
    job: dict,
    thread,
    request_started_at: float,
    use_wait_cursor: bool,
    qtcore,
    qtwidgets,
    ocr_runtime_trace_module,
) -> None:
    if bool(use_wait_cursor):
        try:
            qtwidgets.QApplication.setOverrideCursor(qtcore.Qt.WaitCursor)
        except Exception:
            pass
    else:
        # Clear stale global override cursors from older runs so Windows keeps
        # showing the normal arrow cursor during OCR processing.
        try:
            while qtwidgets.QApplication.overrideCursor() is not None:
                qtwidgets.QApplication.restoreOverrideCursor()
        except Exception:
            pass
    try:
        thread.start(qtcore.QThread.LowPriority)
    except Exception:
        thread.start()
    job["worker_started_mono"] = float(time.monotonic())
    ocr_runtime_trace_module.trace(
        "ocr_async_import:worker_thread_started",
        role=str(job.get("role", "") or ""),
        request_to_worker_start_ms=int(
            (float(job.get("worker_started_mono") or time.monotonic()) - float(request_started_at)) * 1000.0
        ),
    )


def install_async_job_watchdog(
    mw,
    *,
    job: dict,
    thread,
    worker,
    timeout_s: float,
    terminate_after_ms: int,
    on_timeout_fn,
    qtcore,
    ocr_runtime_trace_module,
) -> None:
    try:
        timeout_ms = int(max(0.0, float(timeout_s)) * 1000.0)
    except (TypeError, ValueError):
        timeout_ms = 0
    if timeout_ms <= 0:
        return

    timer = qtcore.QTimer(mw)
    timer.setSingleShot(True)
    job["watchdog_timer"] = timer

    def _force_terminate_if_still_running() -> None:
        if not bool(job.get("_timed_out", False)):
            return
        try:
            running = bool(thread.isRunning())
        except Exception:
            running = False
        if not running:
            return
        if not hasattr(thread, "terminate"):
            return
        ocr_runtime_trace_module.trace(
            "ocr_async_import:watchdog_force_terminate",
            role=str(job.get("role", "") or ""),
        )
        try:
            thread.terminate()
        except Exception as exc:
            ocr_runtime_trace_module.trace(
                "ocr_async_import:watchdog_force_terminate_failed",
                role=str(job.get("role", "") or ""),
                error=repr(exc),
            )

    def _on_timeout() -> None:
        try:
            running = bool(thread.isRunning())
        except Exception:
            running = False
        if not running:
            return
        if bool(job.get("_timed_out", False)):
            return

        job["_timed_out"] = True
        ocr_runtime_trace_module.trace(
            "ocr_async_import:watchdog_timeout",
            role=str(job.get("role", "") or ""),
            timeout_ms=int(timeout_ms),
        )

        cancel_slot = getattr(worker, "cancel", None)
        if callable(cancel_slot):
            try:
                cancel_slot()
            except Exception as exc:
                ocr_runtime_trace_module.trace(
                    "ocr_async_import:watchdog_cancel_failed",
                    role=str(job.get("role", "") or ""),
                    error=repr(exc),
                )
        try:
            thread.requestInterruption()
        except Exception:
            pass
        try:
            thread.quit()
        except Exception:
            pass

        try:
            on_timeout_fn()
        except Exception as exc:
            ocr_runtime_trace_module.trace(
                "ocr_async_import:watchdog_timeout_handler_failed",
                role=str(job.get("role", "") or ""),
                error=repr(exc),
            )

        grace_ms = max(0, int(terminate_after_ms))
        if grace_ms <= 0:
            return
        force_timer = qtcore.QTimer(mw)
        force_timer.setSingleShot(True)
        job["watchdog_force_timer"] = force_timer
        force_timer.timeout.connect(_force_terminate_if_still_running)
        force_timer.start(grace_ms)

    timer.timeout.connect(_on_timeout)
    timer.start(timeout_ms)
