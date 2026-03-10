from __future__ import annotations


def restore_override_cursor(*, qtwidgets) -> None:
    try:
        while qtwidgets.QApplication.overrideCursor() is not None:
            qtwidgets.QApplication.restoreOverrideCursor()
    except RuntimeError:
        pass


def cancel_ocr_cache_release(mw) -> None:
    handler = getattr(mw, "_cancel_ocr_runtime_cache_release", None)
    if callable(handler):
        try:
            handler()
        except (RuntimeError, AttributeError, TypeError):
            pass


def schedule_ocr_cache_release(mw) -> None:
    handler = getattr(mw, "_schedule_ocr_runtime_cache_release", None)
    if callable(handler):
        try:
            handler()
        except (RuntimeError, AttributeError, TypeError):
            pass


def show_ocr_busy_overlay(mw, role: str, *, i18n_module, qtwidgets) -> bool:
    overlay = getattr(mw, "overlay", None)
    if overlay is None:
        return False
    try:
        normalized_role = str(role or "").strip().casefold()
        if normalized_role == "all":
            line1 = i18n_module.t("ocr.progress_line_all")
        else:
            role_name_fn = getattr(mw, "_ocr_role_display_name", None)
            role_name = role_name_fn(normalized_role) if callable(role_name_fn) else normalized_role.upper()
            line1 = i18n_module.t("ocr.progress_line_role", role=role_name)
        overlay.show_status_message(
            i18n_module.t("ocr.progress_title"),
            [
                line1,
                i18n_module.t("ocr.progress_line_wait"),
                "",
            ],
        )
        overlay.setEnabled(False)
        try:
            qtwidgets.QApplication.processEvents()
        except RuntimeError:
            pass
        return True
    except (RuntimeError, AttributeError, TypeError):
        return False


def hide_ocr_busy_overlay(mw, *, active: bool, i18n_module) -> None:
    if not active:
        return
    overlay = getattr(mw, "overlay", None)
    if overlay is None:
        return
    try:
        overlay.setEnabled(True)
    except (RuntimeError, AttributeError, TypeError):
        pass
    try:
        last_view = getattr(overlay, "_last_view", {}) or {}
        if last_view.get("type") != "status_message":
            return
        data = last_view.get("data") or ()
        if not data:
            return
        if str(data[0]) != str(i18n_module.t("ocr.progress_title")):
            return
        overlay.hide()
    except (RuntimeError, AttributeError, TypeError):
        pass


def mark_ocr_runtime_activated(mw) -> None:
    marker = getattr(mw, "_mark_ocr_runtime_activated", None)
    if callable(marker):
        try:
            marker()
            return
        except (RuntimeError, AttributeError, TypeError):
            pass
    try:
        setattr(mw, "_ocr_runtime_activated", True)
    except (RuntimeError, AttributeError, TypeError):
        pass


def restore_main_window_after_capture(
    mw,
    *,
    was_visible: bool,
    was_minimized: bool,
    ocr_capture_ui_helpers_module,
    qt_runtime_module,
) -> None:
    ocr_capture_ui_helpers_module.restore_main_window_after_capture(
        mw,
        was_visible=was_visible,
        was_minimized=was_minimized,
        qt_runtime_module=qt_runtime_module,
    )


def suspend_quit_on_last_window_closed(
    *,
    active: bool,
    ocr_capture_ui_helpers_module,
    ocr_runtime_trace_module,
):
    return ocr_capture_ui_helpers_module.suspend_quit_on_last_window_closed(
        active=active,
        ocr_runtime_trace_module=ocr_runtime_trace_module,
    )


def capture_region_with_qt_selector(
    mw,
    *,
    sys_platform: str,
    select_region_from_primary_screen_fn,
    suspend_quit_on_last_window_closed_fn,
    restore_main_window_after_capture_fn,
    time_module,
    i18n_module,
    ocr_capture_ui_helpers_module,
):
    return ocr_capture_ui_helpers_module.capture_region_with_qt_selector(
        mw,
        sys_platform=sys_platform,
        select_region_from_primary_screen_fn=select_region_from_primary_screen_fn,
        suspend_quit_on_last_window_closed_fn=suspend_quit_on_last_window_closed_fn,
        restore_main_window_after_capture_fn=restore_main_window_after_capture_fn,
        time_module=time_module,
        i18n_module=i18n_module,
    )


def capture_region_for_ocr(
    mw,
    *,
    sys_platform: str,
    capture_region_with_qt_selector_fn,
    select_region_with_macos_screencapture_fn,
    suspend_quit_on_last_window_closed_fn,
    restore_main_window_after_capture_fn,
    time_module,
    i18n_module,
    ocr_capture_ui_helpers_module,
):
    return ocr_capture_ui_helpers_module.capture_region_for_ocr(
        mw,
        sys_platform=sys_platform,
        capture_region_with_qt_selector_fn=capture_region_with_qt_selector_fn,
        select_region_with_macos_screencapture_fn=select_region_with_macos_screencapture_fn,
        suspend_quit_on_last_window_closed_fn=suspend_quit_on_last_window_closed_fn,
        restore_main_window_after_capture_fn=restore_main_window_after_capture_fn,
        time_module=time_module,
        i18n_module=i18n_module,
    )

