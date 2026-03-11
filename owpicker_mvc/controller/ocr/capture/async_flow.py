from __future__ import annotations

from pathlib import Path
import sys
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

        timeout_default_s = 38.0
        try:
            timeout_s = float(mw._cfg("OCR_ASYNC_IMPORT_TIMEOUT_S", timeout_default_s))
        except (TypeError, ValueError):
            timeout_s = timeout_default_s
        if sys.platform.startswith("win"):
            try:
                timeout_s = float(mw._cfg("OCR_ASYNC_IMPORT_TIMEOUT_S_WINDOWS", timeout_s))
            except (TypeError, ValueError):
                pass
        try:
            terminate_after_ms = int(mw._cfg("OCR_ASYNC_IMPORT_TIMEOUT_TERMINATE_MS", 1800))
        except (TypeError, ValueError):
            terminate_after_ms = 1800
        wait_cursor_default = not sys.platform.startswith("win")
        try:
            use_wait_cursor = bool(mw._cfg("OCR_ASYNC_WAIT_CURSOR", wait_cursor_default))
        except (TypeError, ValueError):
            use_wait_cursor = bool(wait_cursor_default)
        if sys.platform.startswith("win"):
            try:
                use_wait_cursor = bool(mw._cfg("OCR_ASYNC_WAIT_CURSOR_WINDOWS", False))
            except (TypeError, ValueError):
                use_wait_cursor = False

        def _handle_watchdog_timeout() -> None:
            timeout_reason = f"timeout-after-{max(0.0, float(timeout_s)):.1f}s"
            _finalize_job()
            setattr(mw, "_ocr_async_job", None)
            try:
                mw._update_role_ocr_buttons_enabled()
            except Exception:
                pass
            qtwidgets.QMessageBox.warning(
                mw,
                i18n_module.t("ocr.error_title"),
                i18n_module.t("ocr.error_run_failed", reason=timeout_reason),
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
        _ocr_capture_thread_flow.install_async_job_watchdog(
            mw,
            job=job,
            thread=thread,
            worker=worker,
            timeout_s=float(timeout_s),
            terminate_after_ms=int(terminate_after_ms),
            on_timeout_fn=_handle_watchdog_timeout,
            qtcore=qtcore,
            ocr_runtime_trace_module=ocr_runtime_trace_module,
        )
        _ocr_capture_thread_flow.start_async_job_thread(
            job=job,
            thread=thread,
            request_started_at=float(request_started_at),
            use_wait_cursor=bool(use_wait_cursor),
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
