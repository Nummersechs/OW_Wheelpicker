from __future__ import annotations


def start_ocr_async_import(
    mw,
    *,
    role: str,
    selected_pixmap,
    busy_overlay_shown: bool,
    start_ocr_async_import_impl,
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
    start_ocr_async_import_impl(
        mw,
        role=role,
        selected_pixmap=selected_pixmap,
        busy_overlay_shown=busy_overlay_shown,
        ocr_runtime_trace_module=ocr_runtime_trace_module,
        runtime_cfg_snapshot_fn=runtime_cfg_snapshot_fn,
        ocr_import_module_fn=ocr_import_module_fn,
        easyocr_resolution_kwargs_fn=easyocr_resolution_kwargs_fn,
        prepare_ocr_variant_files_fn=prepare_ocr_variant_files_fn,
        hide_ocr_busy_overlay_fn=hide_ocr_busy_overlay_fn,
        restore_override_cursor_fn=restore_override_cursor_fn,
        cleanup_temp_paths_fn=cleanup_temp_paths_fn,
        ocr_extract_worker_cls=ocr_extract_worker_cls,
        ocr_result_relay_cls=ocr_result_relay_cls,
        append_ocr_debug_log_fn=append_ocr_debug_log_fn,
        show_ocr_debug_report_fn=show_ocr_debug_report_fn,
        ocr_preview_text_fn=ocr_preview_text_fn,
        schedule_ocr_cache_release_fn=schedule_ocr_cache_release_fn,
        i18n_module=i18n_module,
        qtcore=qtcore,
        qtwidgets=qtwidgets,
    )


def on_role_ocr_import_clicked(
    mw,
    role_key: str,
    *,
    ocr_runtime_trace_module,
    role_ocr_import_available_fn,
    mark_ocr_runtime_activated_fn,
    cancel_ocr_cache_release_fn,
    update_role_ocr_button_enabled_fn,
    capture_region_for_ocr_fn,
    show_ocr_busy_overlay_fn,
    start_ocr_async_import_fn,
    handle_ocr_selection_error_fn,
    restore_override_cursor_fn,
    schedule_ocr_cache_release_fn,
    i18n_module,
    qtcore,
    qtgui,
    qtwidgets,
) -> None:
    role = str(role_key or "").strip().casefold()
    ocr_runtime_trace_module.trace("ocr_button_clicked", role=role)
    if not role_ocr_import_available_fn(role):
        ocr_runtime_trace_module.trace("ocr_button_click_ignored", role=role, reason="not_available")
        return
    if getattr(mw, "_ocr_async_job", None):
        ocr_runtime_trace_module.trace("ocr_button_click_ignored", role=role, reason="async_job_running")
        return
    mark_ocr_runtime_activated_fn(mw)
    cancel_ocr_cache_release_fn(mw)
    update_role_ocr_button_enabled_fn(role)
    btn = getattr(mw, "_role_ocr_buttons", {}).get(role)
    if btn is not None:
        btn.setEnabled(False)

    async_dispatched = False
    try:
        selected_pixmap, select_error = capture_region_for_ocr_fn(mw)
        if selected_pixmap is None:
            ocr_runtime_trace_module.trace(
                "ocr_capture_cancelled_or_failed",
                role=role,
                reason=str(select_error or "cancelled"),
            )
            handle_ocr_selection_error_fn(mw, select_error)
            mw._update_role_ocr_buttons_enabled()
            return

        busy_overlay_shown = show_ocr_busy_overlay_fn(mw, role)
        # Defer OCR setup to the next event-loop tick so the status overlay can
        # be painted before any heavy OCR pre-processing starts.
        qtcore.QTimer.singleShot(
            0,
            lambda role=role, pixmap=qtgui.QPixmap(selected_pixmap), shown=busy_overlay_shown: start_ocr_async_import_fn(
                mw,
                role=role,
                selected_pixmap=pixmap,
                busy_overlay_shown=shown,
            ),
        )
        async_dispatched = True
    except Exception as exc:
        ocr_runtime_trace_module.trace("ocr_button_handler_exception", role=role, error=repr(exc))
        restore_override_cursor_fn()
        setattr(mw, "_ocr_async_job", None)
        qtwidgets.QMessageBox.warning(
            mw,
            i18n_module.t("ocr.error_title"),
            i18n_module.t("ocr.error_unexpected", reason=repr(exc)),
        )
        mw._update_role_ocr_buttons_enabled()
    finally:
        if not async_dispatched and not getattr(mw, "_ocr_async_job", None):
            schedule_ocr_cache_release_fn(mw)

