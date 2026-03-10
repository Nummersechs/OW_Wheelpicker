from __future__ import annotations

from pathlib import Path
import time

from . import error_flow as _ocr_capture_error_flow
from . import job_flow as _ocr_capture_job_flow
from . import preflight_flow as _ocr_capture_preflight_flow
from . import result_flow as _ocr_capture_result_flow
from . import thread_flow as _ocr_capture_thread_flow


def start_ocr_async_import(
    mw,
    *,
    role: str,
    selected_pixmap,
    busy_overlay_shown: bool,
    ocr_runtime_trace_module,
    runtime_cfg_snapshot_fn,
    ocr_import_module_fn,
    easyocr_resolution_kwargs_fn,
    prepare_ocr_variant_files_fn,
    hide_ocr_busy_overlay_fn,
    restore_override_cursor_fn,
    cleanup_temp_paths_fn,
    ocr_extract_worker_cls,
    ocr_result_relay_cls,
    append_ocr_debug_log_fn,
    show_ocr_debug_report_fn,
    ocr_preview_text_fn,
    schedule_ocr_cache_release_fn,
    i18n_module,
    qtcore,
    qtwidgets,
) -> None:
    request_started_at = time.monotonic()
    temp_paths: list[Path] = []
    async_started = False
    ocr_runtime_trace_module.trace(
        "ocr_async_import:start",
        role=str(role or ""),
        closing=bool(getattr(mw, "_closing", False)),
        overlay=bool(busy_overlay_shown),
    )
    try:
        preflight_result = _ocr_capture_preflight_flow.run_preflight(
            mw,
            role=str(role or ""),
            selected_pixmap=selected_pixmap,
            busy_overlay_shown=bool(busy_overlay_shown),
            request_started_at=float(request_started_at),
            runtime_cfg_snapshot_fn=runtime_cfg_snapshot_fn,
            ocr_import_module_fn=ocr_import_module_fn,
            easyocr_resolution_kwargs_fn=easyocr_resolution_kwargs_fn,
            prepare_ocr_variant_files_fn=prepare_ocr_variant_files_fn,
            hide_ocr_busy_overlay_fn=hide_ocr_busy_overlay_fn,
            restore_override_cursor_fn=restore_override_cursor_fn,
            i18n_module=i18n_module,
            qtwidgets=qtwidgets,
            ocr_runtime_trace_module=ocr_runtime_trace_module,
        )
        if not preflight_result.should_continue:
            return
        runtime_cfg = dict(preflight_result.runtime_cfg)
        temp_paths = list(preflight_result.temp_paths)

        job, thread, worker, relay = _ocr_capture_thread_flow.create_async_job(
            mw,
            role=str(role or ""),
            temp_paths=list(temp_paths),
            runtime_cfg=runtime_cfg,
            request_started_at=float(request_started_at),
            ocr_extract_worker_cls=ocr_extract_worker_cls,
            ocr_result_relay_cls=ocr_result_relay_cls,
            qtcore=qtcore,
            ocr_runtime_trace_module=ocr_runtime_trace_module,
        )

        _finalize_job, _cleanup_finished_job = _ocr_capture_job_flow.build_job_callbacks(
            mw,
            job=job,
            thread=thread,
            busy_overlay_shown=bool(busy_overlay_shown),
            cleanup_temp_paths_fn=cleanup_temp_paths_fn,
            hide_ocr_busy_overlay_fn=hide_ocr_busy_overlay_fn,
            restore_override_cursor_fn=restore_override_cursor_fn,
            schedule_ocr_cache_release_fn=schedule_ocr_cache_release_fn,
            qtcore=qtcore,
        )

        _handle_result, _handle_worker_error = _ocr_capture_result_flow.build_worker_handlers(
            mw,
            role=str(role or ""),
            runtime_cfg=runtime_cfg,
            request_started_at=float(request_started_at),
            job=job,
            finalize_job_fn=_finalize_job,
            append_ocr_debug_log_fn=append_ocr_debug_log_fn,
            show_ocr_debug_report_fn=show_ocr_debug_report_fn,
            ocr_preview_text_fn=ocr_preview_text_fn,
            i18n_module=i18n_module,
            qtwidgets=qtwidgets,
            ocr_runtime_trace_module=ocr_runtime_trace_module,
        )

        _ocr_capture_thread_flow.connect_async_job_signals(
            job=job,
            thread=thread,
            worker=worker,
            relay=relay,
            handle_result_fn=_handle_result,
            handle_error_fn=_handle_worker_error,
            cleanup_finished_job_fn=_cleanup_finished_job,
            qtcore=qtcore,
        )
        _ocr_capture_thread_flow.start_async_job_thread(
            job=job,
            thread=thread,
            request_started_at=float(request_started_at),
            qtcore=qtcore,
            qtwidgets=qtwidgets,
            ocr_runtime_trace_module=ocr_runtime_trace_module,
        )
        async_started = True
        return
    except Exception as exc:
        _ocr_capture_error_flow.handle_async_import_exception(
            mw,
            role=str(role or ""),
            exc=exc,
            request_started_at=float(request_started_at),
            temp_paths=list(temp_paths),
            busy_overlay_shown=bool(busy_overlay_shown),
            cleanup_temp_paths_fn=cleanup_temp_paths_fn,
            hide_ocr_busy_overlay_fn=hide_ocr_busy_overlay_fn,
            restore_override_cursor_fn=restore_override_cursor_fn,
            i18n_module=i18n_module,
            qtwidgets=qtwidgets,
            ocr_runtime_trace_module=ocr_runtime_trace_module,
        )
        return
    finally:
        _ocr_capture_error_flow.finalize_async_import_dispatch(
            mw,
            async_started=bool(async_started),
            schedule_ocr_cache_release_fn=schedule_ocr_cache_release_fn,
        )
