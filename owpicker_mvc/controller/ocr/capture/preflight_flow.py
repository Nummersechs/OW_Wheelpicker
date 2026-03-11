from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import time
from typing import Any


@dataclass
class OCRCapturePreflightResult:
    should_continue: bool
    runtime_cfg: dict[str, Any]
    temp_paths: list[Path]


def _availability_reason_from_diag(diag: str) -> str:
    diag_l = str(diag or "").lower()
    if "import=failed" in diag_l or "import_error=" in diag_l:
        return "easyocr-import-failed"
    if "reader=failed" in diag_l:
        if "missing " in diag_l and "download" in diag_l and "disabled" in diag_l:
            return "easyocr-models-missing-offline"
        return "easyocr-reader-failed"
    return "easyocr-not-ready"


def _availability_diagnostics(ocr_import, **easyocr_kwargs) -> str:
    diag_fn = getattr(ocr_import, "easyocr_resolution_diagnostics", None)
    if callable(diag_fn):
        return str(diag_fn(**easyocr_kwargs))
    return "easyocr-diagnostics-unavailable"


def run_preflight(
    mw,
    *,
    role: str,
    selected_pixmap,
    busy_overlay_shown: bool,
    request_started_at: float,
    runtime_cfg_snapshot_fn,
    ocr_import_module_fn,
    easyocr_resolution_kwargs_fn,
    prepare_ocr_variant_files_fn,
    hide_ocr_busy_overlay_fn,
    restore_override_cursor_fn,
    i18n_module,
    qtwidgets,
    ocr_runtime_trace_module,
) -> OCRCapturePreflightResult:
    def _yield_ui_events() -> None:
        app = qtwidgets.QApplication.instance()
        if app is None:
            return
        try:
            app.processEvents()
        except Exception:
            try:
                qtwidgets.QApplication.processEvents()
            except Exception:
                pass

    if bool(getattr(mw, "_closing", False)):
        ocr_runtime_trace_module.trace(
            "ocr_async_import:abort_closing",
            role=str(role or ""),
        )
        hide_ocr_busy_overlay_fn(mw, active=busy_overlay_shown)
        restore_override_cursor_fn()
        setattr(mw, "_ocr_async_job", None)
        return OCRCapturePreflightResult(False, {}, [])

    cancel_preload = getattr(mw, "_cancel_ocr_background_preload", None)
    if callable(cancel_preload):
        try:
            cancel_preload()
        except Exception as exc:
            ocr_runtime_trace_module.trace(
                "ocr_async_import:cancel_preload_failed",
                role=str(role or ""),
                error=repr(exc),
            )
    stop_preload_job = getattr(mw, "_stop_ocr_background_preload_job", None)
    if callable(stop_preload_job):
        wait_default_ms = 700 if sys.platform.startswith("win") else 1600
        try:
            wait_ms = max(0, int(mw._cfg("OCR_PRELOAD_STOP_WAIT_MS", wait_default_ms)))
        except (TypeError, ValueError):
            wait_ms = int(wait_default_ms)
        try:
            stop_preload_job(reason="active_ocr_capture", wait_ms=wait_ms)
        except Exception as exc:
            ocr_runtime_trace_module.trace(
                "ocr_async_import:stop_preload_failed",
                role=str(role or ""),
                error=repr(exc),
            )

    runtime_cfg = runtime_cfg_snapshot_fn(mw)
    _yield_ui_events()
    ocr_import = ocr_import_module_fn()
    easyocr_kwargs = easyocr_resolution_kwargs_fn(runtime_cfg)
    preload_runtime_ready = (
        str(runtime_cfg.get("engine", "easyocr")).strip().casefold() == "easyocr"
        and bool(getattr(mw, "_ocr_preload_done", False))
        and bool(getattr(mw, "_ocr_runtime_activated", False))
        and bool(mw._cfg("OCR_PRELOAD_INPROCESS_CACHE_WARMUP", True))
    )
    probe_default = False if sys.platform.startswith("win") else True
    probe_on_click = bool(mw._cfg("OCR_AVAILABILITY_PROBE_ON_CLICK", probe_default))
    if preload_runtime_ready:
        ready = True
        ocr_runtime_trace_module.trace("ocr_availability_probe:skipped", reason="preload_runtime_ready")
    elif not probe_on_click:
        # Avoid blocking the GUI thread on weaker systems. OCR runtime/import
        # checks then happen in the async worker path.
        ready = True
        ocr_runtime_trace_module.trace("ocr_availability_probe:skipped", reason="probe_disabled")
    else:
        availability_fn = getattr(ocr_import, "easyocr_available", None)
        if callable(availability_fn):
            _yield_ui_events()
            ready = bool(availability_fn(**easyocr_kwargs))
        else:
            ready = False
    ocr_runtime_trace_module.trace(
        "ocr_availability_probe:done",
        ready=bool(ready),
        probe_ms=int((time.monotonic() - request_started_at) * 1000.0),
    )
    if not ready:
        diag = _availability_diagnostics(ocr_import, **easyocr_kwargs)
        reason = _availability_reason_from_diag(diag)
        ocr_runtime_trace_module.trace("ocr_availability_probe:not_ready", reason=reason, diag=diag)
        qtwidgets.QMessageBox.warning(
            mw,
            i18n_module.t("ocr.error_title"),
            i18n_module.t("ocr.error_run_failed", reason=reason)
            + "\n\n"
            + diag,
        )
        hide_ocr_busy_overlay_fn(mw, active=busy_overlay_shown)
        return OCRCapturePreflightResult(False, {}, [])

    _yield_ui_events()
    temp_paths, prep_errors = prepare_ocr_variant_files_fn(mw, selected_pixmap, runtime_cfg)
    _yield_ui_events()
    if not temp_paths:
        reason = "; ".join(prep_errors) if prep_errors else "image-save-failed"
        ocr_runtime_trace_module.trace("ocr_async_import:image_prepare_failed", reason=reason)
        qtwidgets.QMessageBox.warning(
            mw,
            i18n_module.t("ocr.error_title"),
            i18n_module.t("ocr.error_run_failed", reason=reason),
        )
        hide_ocr_busy_overlay_fn(mw, active=busy_overlay_shown)
        return OCRCapturePreflightResult(False, {}, [])

    return OCRCapturePreflightResult(
        True,
        dict(runtime_cfg),
        list(temp_paths),
    )
