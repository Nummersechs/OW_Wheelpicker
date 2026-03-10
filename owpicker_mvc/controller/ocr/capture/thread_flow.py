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
    qtcore,
    qtwidgets,
    ocr_runtime_trace_module,
) -> None:
    qtwidgets.QApplication.setOverrideCursor(qtcore.Qt.WaitCursor)
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

