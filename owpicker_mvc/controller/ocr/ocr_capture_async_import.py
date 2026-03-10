from __future__ import annotations

from pathlib import Path


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
    temp_paths: list[Path] = []
    async_started = False
    ocr_runtime_trace_module.trace(
        "ocr_async_import:start",
        role=str(role or ""),
        closing=bool(getattr(mw, "_closing", False)),
        overlay=bool(busy_overlay_shown),
    )
    try:
        if bool(getattr(mw, "_closing", False)):
            ocr_runtime_trace_module.trace("ocr_async_import:abort_closing")
            hide_ocr_busy_overlay_fn(mw, active=busy_overlay_shown)
            restore_override_cursor_fn()
            try:
                setattr(mw, "_ocr_async_job", None)
            except Exception:
                pass
            return

        cancel_preload = getattr(mw, "_cancel_ocr_background_preload", None)
        if callable(cancel_preload):
            try:
                cancel_preload()
            except Exception:
                pass
        stop_preload_job = getattr(mw, "_stop_ocr_background_preload_job", None)
        if callable(stop_preload_job):
            try:
                stop_preload_job(reason="active_ocr_capture", wait_ms=1600)
            except Exception:
                pass

        runtime_cfg = runtime_cfg_snapshot_fn(mw)
        ocr_import = ocr_import_module_fn()
        easyocr_kwargs = easyocr_resolution_kwargs_fn(runtime_cfg)
        preload_runtime_ready = (
            str(runtime_cfg.get("engine", "easyocr")).strip().casefold() == "easyocr"
            and bool(getattr(mw, "_ocr_preload_done", False))
            and bool(getattr(mw, "_ocr_runtime_activated", False))
            and bool(mw._cfg("OCR_PRELOAD_INPROCESS_CACHE_WARMUP", True))
        )
        if preload_runtime_ready:
            ready = True
            ocr_runtime_trace_module.trace("ocr_availability_probe:skipped", reason="preload_runtime_ready")
        else:
            availability_fn = getattr(ocr_import, "easyocr_available", None)
            if callable(availability_fn):
                ready = bool(availability_fn(**easyocr_kwargs))
            else:
                ready = False
        ocr_runtime_trace_module.trace("ocr_availability_probe:done", ready=bool(ready))
        if not ready:
            diag_fn = getattr(ocr_import, "easyocr_resolution_diagnostics", None)
            if callable(diag_fn):
                diag = str(diag_fn(**easyocr_kwargs))
            else:
                diag = "easyocr-diagnostics-unavailable"
            diag_l = diag.lower()
            if "import=failed" in diag_l or "import_error=" in diag_l:
                reason = "easyocr-import-failed"
            elif "reader=failed" in diag_l:
                if "missing " in diag_l and "download" in diag_l and "disabled" in diag_l:
                    reason = "easyocr-models-missing-offline"
                else:
                    reason = "easyocr-reader-failed"
            else:
                reason = "easyocr-not-ready"
            ocr_runtime_trace_module.trace("ocr_availability_probe:not_ready", reason=reason, diag=diag)
            qtwidgets.QMessageBox.warning(
                mw,
                i18n_module.t("ocr.error_title"),
                i18n_module.t("ocr.error_run_failed", reason=reason)
                + "\n\n"
                + diag,
            )
            hide_ocr_busy_overlay_fn(mw, active=busy_overlay_shown)
            return

        temp_paths, prep_errors = prepare_ocr_variant_files_fn(mw, selected_pixmap, runtime_cfg)
        if not temp_paths:
            reason = "; ".join(prep_errors) if prep_errors else "image-save-failed"
            ocr_runtime_trace_module.trace("ocr_async_import:image_prepare_failed", reason=reason)
            qtwidgets.QMessageBox.warning(
                mw,
                i18n_module.t("ocr.error_title"),
                i18n_module.t("ocr.error_run_failed", reason=reason),
            )
            hide_ocr_busy_overlay_fn(mw, active=busy_overlay_shown)
            return

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
        }
        setattr(mw, "_ocr_async_job", job)
        ocr_runtime_trace_module.trace(
            "ocr_async_import:worker_created",
            role=str(role or ""),
            image_count=len(list(temp_paths or [])),
        )

        def _finalize_job() -> None:
            current = getattr(mw, "_ocr_async_job", None)
            if current is not None and current is not job:
                return
            if bool(job.get("_finalized", False)):
                return
            job["_finalized"] = True
            cleanup_temp_paths_fn(list(job.get("paths") or []))
            hide_ocr_busy_overlay_fn(mw, active=busy_overlay_shown)
            restore_override_cursor_fn()
            try:
                if thread.isRunning() and qtcore.QThread.currentThread() is not thread:
                    thread.quit()
            except Exception:
                pass
            mw._update_role_ocr_buttons_enabled()
            schedule_ocr_cache_release_fn(mw)
            if current is job:
                running = False
                try:
                    running = bool(thread.isRunning())
                except Exception:
                    running = False
                if not running:
                    setattr(mw, "_ocr_async_job", None)

        def _cleanup_finished_job() -> None:
            current = getattr(mw, "_ocr_async_job", None)
            if current is job:
                setattr(mw, "_ocr_async_job", None)

        def _handle_result(names: list[str], raw_text: str, ocr_error: str | None) -> None:
            _finalize_job()
            ocr_runtime_trace_module.trace(
                "ocr_async_import:worker_result",
                role=str(role or ""),
                names=len(list(names or [])),
                has_error=bool(ocr_error),
                error=str(ocr_error or ""),
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

        def _handle_worker_error(reason: str) -> None:
            _finalize_job()
            ocr_runtime_trace_module.trace(
                "ocr_async_import:worker_error",
                role=str(role or ""),
                reason=str(reason or "worker-error"),
            )
            qtwidgets.QMessageBox.warning(
                mw,
                i18n_module.t("ocr.error_title"),
                i18n_module.t("ocr.error_run_failed", reason=str(reason or "worker-error")),
            )

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
            job["relay_result_connection"] = relay.result.connect(_handle_result)
        except Exception:
            relay.result.connect(_handle_result)
            job["relay_result_connection"] = None
        try:
            job["relay_error_connection"] = relay.error.connect(_handle_worker_error)
        except Exception:
            relay.error.connect(_handle_worker_error)
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
            job["cleanup_connection"] = thread.finished.connect(_cleanup_finished_job)
        except Exception:
            thread.finished.connect(_cleanup_finished_job)
            job["cleanup_connection"] = None
        qtwidgets.QApplication.setOverrideCursor(qtcore.Qt.WaitCursor)
        try:
            thread.start(qtcore.QThread.LowPriority)
        except Exception:
            thread.start()
        ocr_runtime_trace_module.trace("ocr_async_import:worker_thread_started", role=str(role or ""))
        async_started = True
        return
    except Exception as exc:
        ocr_runtime_trace_module.trace("ocr_async_import:exception", role=str(role or ""), error=repr(exc))
        cleanup_temp_paths_fn(temp_paths)
        hide_ocr_busy_overlay_fn(mw, active=busy_overlay_shown)
        restore_override_cursor_fn()
        setattr(mw, "_ocr_async_job", None)
        qtwidgets.QMessageBox.warning(
            mw,
            i18n_module.t("ocr.error_title"),
            i18n_module.t("ocr.error_unexpected", reason=repr(exc)),
        )
        mw._update_role_ocr_buttons_enabled()
        return
    finally:
        if not async_started and not getattr(mw, "_ocr_async_job", None):
            schedule_ocr_cache_release_fn(mw)
