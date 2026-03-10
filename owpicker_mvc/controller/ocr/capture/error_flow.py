from __future__ import annotations

import time
from pathlib import Path


def handle_async_import_exception(
    mw,
    *,
    role: str,
    exc: Exception,
    request_started_at: float,
    temp_paths: list[Path],
    busy_overlay_shown: bool,
    cleanup_temp_paths_fn,
    hide_ocr_busy_overlay_fn,
    restore_override_cursor_fn,
    i18n_module,
    qtwidgets,
    ocr_runtime_trace_module,
) -> None:
    ocr_runtime_trace_module.trace(
        "ocr_async_import:exception",
        role=str(role or ""),
        error=repr(exc),
        request_latency_ms=int((time.monotonic() - request_started_at) * 1000.0),
    )
    cleanup_temp_paths_fn(list(temp_paths or []))
    hide_ocr_busy_overlay_fn(mw, active=busy_overlay_shown)
    restore_override_cursor_fn()
    setattr(mw, "_ocr_async_job", None)
    qtwidgets.QMessageBox.warning(
        mw,
        i18n_module.t("ocr.error_title"),
        i18n_module.t("ocr.error_unexpected", reason=repr(exc)),
    )
    mw._update_role_ocr_buttons_enabled()


def finalize_async_import_dispatch(
    mw,
    *,
    async_started: bool,
    schedule_ocr_cache_release_fn,
) -> None:
    if not async_started and not getattr(mw, "_ocr_async_job", None):
        schedule_ocr_cache_release_fn(mw)
