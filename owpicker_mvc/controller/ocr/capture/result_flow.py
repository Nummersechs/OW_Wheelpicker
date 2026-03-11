from __future__ import annotations

import time


def handle_worker_result(
    mw,
    *,
    role: str,
    names: list[str],
    raw_text: str,
    ocr_error: str | None,
    runtime_cfg: dict,
    request_started_at: float,
    job: dict,
    finalize_job_fn,
    append_ocr_debug_log_fn,
    show_ocr_debug_report_fn,
    ocr_preview_text_fn,
    i18n_module,
    qtwidgets,
    ocr_runtime_trace_module,
) -> None:
    if bool(job.get("_timed_out", False)):
        ocr_runtime_trace_module.trace(
            "ocr_async_import:worker_result_ignored_after_timeout",
            role=str(role or ""),
        )
        return
    finalize_job_fn()
    ocr_runtime_trace_module.trace(
        "ocr_async_import:worker_result",
        role=str(role or ""),
        names=len(list(names or [])),
        has_error=bool(ocr_error),
        error=str(ocr_error or ""),
        request_latency_ms=int((time.monotonic() - float(job.get("request_started_mono") or request_started_at)) * 1000.0),
        worker_latency_ms=int(
            (time.monotonic() - float(job.get("worker_started_mono") or job.get("request_started_mono") or request_started_at))
            * 1000.0
        ),
    )
    debug_mode = (
        bool(runtime_cfg.get("debug_show_report", False))
        or bool(runtime_cfg.get("debug_include_report_text", False))
        or bool(runtime_cfg.get("debug_log_to_file", False))
    )
    if debug_mode:
        log_path = append_ocr_debug_log_fn(
            mw,
            role=role,
            names=names,
            raw_text=raw_text,
            ocr_error=ocr_error,
        )
        if log_path is not None and hasattr(mw, "_trace_event"):
            try:
                mw._trace_event(
                    "ocr_debug_log_written",
                    role=role,
                    path=str(log_path),
                    candidates=len(list(names or [])),
                )
            except Exception:
                pass
    if bool(runtime_cfg.get("debug_show_report", False)):
        try:
            show_ocr_debug_report_fn(
                mw,
                role=role,
                names=names,
                raw_text=raw_text,
                ocr_error=ocr_error,
            )
        except Exception:
            pass
    if not names:
        message = i18n_module.t("ocr.result_no_names")
        preview = ocr_preview_text_fn(raw_text)
        if preview:
            message += "\n\n" + i18n_module.t("ocr.result_raw_preview", preview=preview)
        elif ocr_error:
            message += "\n\n" + i18n_module.t("ocr.error_run_failed", reason=ocr_error)
        qtwidgets.QMessageBox.information(
            mw,
            i18n_module.t("ocr.result_title"),
            message,
        )
        return

    candidate_names = mw._normalize_ocr_candidate_names(names)
    if hasattr(mw, "_apply_ocr_name_hints"):
        try:
            candidate_names = mw._apply_ocr_name_hints(role, candidate_names)
        except Exception:
            pass
    if not candidate_names:
        qtwidgets.QMessageBox.information(
            mw,
            i18n_module.t("ocr.result_title"),
            i18n_module.t("ocr.result_no_names"),
        )
        return
    if mw._request_ocr_import_selection(role, candidate_names):
        return

    fallback_entries = [
        {"name": name, "assignments": [], "subroles_by_role": {}, "active": True}
        for name in candidate_names
    ]
    if role == "all":
        added, added_counts = mw._add_ocr_entries_distributed(fallback_entries)
        mw._show_ocr_import_result_distributed(
            added=added,
            total=len(candidate_names),
            counts=added_counts,
        )
    else:
        added = mw._add_ocr_entries_for_role(role, fallback_entries)
        mw._show_ocr_import_result_for_role(
            role,
            added=added,
            total=len(candidate_names),
        )


def handle_worker_error(
    mw,
    *,
    role: str,
    reason: str,
    request_started_at: float,
    job: dict,
    finalize_job_fn,
    i18n_module,
    qtwidgets,
    ocr_runtime_trace_module,
) -> None:
    if bool(job.get("_timed_out", False)):
        ocr_runtime_trace_module.trace(
            "ocr_async_import:worker_error_ignored_after_timeout",
            role=str(role or ""),
            reason=str(reason or "worker-error"),
        )
        return
    finalize_job_fn()
    ocr_runtime_trace_module.trace(
        "ocr_async_import:worker_error",
        role=str(role or ""),
        reason=str(reason or "worker-error"),
        request_latency_ms=int((time.monotonic() - float(job.get("request_started_mono") or request_started_at)) * 1000.0),
        worker_latency_ms=int(
            (time.monotonic() - float(job.get("worker_started_mono") or job.get("request_started_mono") or request_started_at))
            * 1000.0
        ),
    )
    qtwidgets.QMessageBox.warning(
        mw,
        i18n_module.t("ocr.error_title"),
        i18n_module.t("ocr.error_run_failed", reason=str(reason or "worker-error")),
    )


def build_worker_handlers(
    mw,
    *,
    role: str,
    runtime_cfg: dict,
    request_started_at: float,
    job: dict,
    finalize_job_fn,
    append_ocr_debug_log_fn,
    show_ocr_debug_report_fn,
    ocr_preview_text_fn,
    i18n_module,
    qtwidgets,
    ocr_runtime_trace_module,
) -> tuple:
    def _handle_result(names: list[str], raw_text: str, ocr_error: str | None) -> None:
        handle_worker_result(
            mw,
            role=str(role or ""),
            names=list(names or []),
            raw_text=str(raw_text or ""),
            ocr_error=(str(ocr_error) if ocr_error is not None else None),
            runtime_cfg=runtime_cfg,
            request_started_at=float(request_started_at),
            job=job,
            finalize_job_fn=finalize_job_fn,
            append_ocr_debug_log_fn=append_ocr_debug_log_fn,
            show_ocr_debug_report_fn=show_ocr_debug_report_fn,
            ocr_preview_text_fn=ocr_preview_text_fn,
            i18n_module=i18n_module,
            qtwidgets=qtwidgets,
            ocr_runtime_trace_module=ocr_runtime_trace_module,
        )

    def _handle_worker_error(reason: str) -> None:
        handle_worker_error(
            mw,
            role=str(role or ""),
            reason=str(reason or "worker-error"),
            request_started_at=float(request_started_at),
            job=job,
            finalize_job_fn=finalize_job_fn,
            i18n_module=i18n_module,
            qtwidgets=qtwidgets,
            ocr_runtime_trace_module=ocr_runtime_trace_module,
        )

    return _handle_result, _handle_worker_error
