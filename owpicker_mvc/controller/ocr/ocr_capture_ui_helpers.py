from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile

from PySide6 import QtCore, QtGui, QtWidgets


def _responsive_delay_ms(delay_ms: int, *, time_module) -> None:
    wait_ms = max(0, int(delay_ms))
    if wait_ms <= 0:
        return
    app = QtWidgets.QApplication.instance()
    if app is None:
        time_module.sleep(wait_ms / 1000.0)
        return
    try:
        target_mono = float(time_module.monotonic()) + (wait_ms / 1000.0)
    except Exception:
        time_module.sleep(wait_ms / 1000.0)
        return

    while True:
        now_mono = float(time_module.monotonic())
        remaining_s = target_mono - now_mono
        if remaining_s <= 0:
            break
        try:
            max_time_ms = max(1, min(25, int(remaining_s * 1000.0)))
            app.processEvents(QtCore.QEventLoop.AllEvents, max_time_ms)
        except Exception:
            QtWidgets.QApplication.processEvents()
        sleep_s = min(0.02, max(0.0, remaining_s))
        if sleep_s > 0:
            time_module.sleep(sleep_s)


def restore_main_window_after_capture(
    mw,
    *,
    was_visible: bool,
    was_minimized: bool,
    qt_runtime_module,
) -> None:
    def _is_closing_or_gone() -> bool:
        try:
            return bool(getattr(mw, "_closing", False))
        except Exception:
            return True

    if not was_visible:
        return
    if _is_closing_or_gone():
        return

    def _restore_once(*, force_normal: bool = False) -> None:
        if _is_closing_or_gone():
            return
        try:
            if was_minimized and (not force_normal):
                mw.showMinimized()
            else:
                try:
                    state = QtCore.Qt.WindowStates(mw.windowState())
                    if bool(state & QtCore.Qt.WindowMinimized):
                        state = QtCore.Qt.WindowStates(state & ~QtCore.Qt.WindowMinimized)
                        state = QtCore.Qt.WindowStates(state | QtCore.Qt.WindowActive)
                        mw.setWindowState(state)
                except Exception:
                    pass
                restored = False
                try:
                    mw.showNormal()
                    restored = True
                except Exception:
                    mw.show()
                    restored = True
                if not restored:
                    mw.show()
                qt_runtime_module.safe_raise(mw)
                qt_runtime_module.safe_activate_window(mw)
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass

    _restore_once(force_normal=False)
    if not was_minimized:
        QtCore.QTimer.singleShot(0, lambda: _restore_once(force_normal=True))
        QtCore.QTimer.singleShot(120, lambda: _restore_once(force_normal=True))


@contextmanager
def suspend_quit_on_last_window_closed(
    *,
    active: bool,
    ocr_runtime_trace_module,
):
    app = QtWidgets.QApplication.instance()
    if (not active) or app is None:
        yield
        return

    previous = None
    try:
        previous = bool(app.quitOnLastWindowClosed())
    except Exception:
        previous = None
    try:
        if previous:
            app.setQuitOnLastWindowClosed(False)
            ocr_runtime_trace_module.trace("ocr_capture:quit_guard_on")
    except Exception:
        previous = None

    try:
        yield
    finally:
        if previous is not None:
            try:
                app.setQuitOnLastWindowClosed(previous)
                ocr_runtime_trace_module.trace("ocr_capture:quit_guard_off", restored=bool(previous))
            except Exception:
                pass


def capture_region_with_qt_selector(
    mw,
    *,
    sys_platform: str,
    select_region_from_primary_screen_fn,
    suspend_quit_on_last_window_closed_fn,
    restore_main_window_after_capture_fn,
    time_module,
    i18n_module,
) -> tuple[QtGui.QPixmap | None, str | None]:
    hide_for_capture = bool(mw._cfg("OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE", True))
    minimize_before_selector = bool(
        mw._cfg("OCR_CAPTURE_MINIMIZE_BEFORE_SELECTOR", sys_platform == "win32")
    )
    if sys_platform == "win32":
        default_minimize_delay_ms = 170
    else:
        default_minimize_delay_ms = 0
    minimize_delay_ms = int(
        mw._cfg(
            "OCR_CAPTURE_MINIMIZE_DELAY_MS",
            mw._cfg("OCR_CAPTURE_MINIMIZE_DELAY_MS_WINDOWS", default_minimize_delay_ms),
        )
    )
    if sys_platform == "win32":
        default_prepare_delay_ms = 70
    else:
        default_prepare_delay_ms = 120
    prepare_delay_ms = int(
        mw._cfg(
            "OCR_CAPTURE_PREPARE_DELAY_MS",
            mw._cfg("OCR_CAPTURE_PREPARE_DELAY_MS_WINDOWS", default_prepare_delay_ms),
        )
    )
    auto_accept_on_release = bool(
        mw._cfg("OCR_QT_SELECTOR_AUTO_ACCEPT_ON_RELEASE", sys_platform == "win32")
    )
    was_visible = mw.isVisible()
    was_minimized = mw.isMinimized()

    with suspend_quit_on_last_window_closed_fn(active=bool(hide_for_capture and was_visible)):
        if hide_for_capture and was_visible:
            if minimize_before_selector and (not was_minimized):
                mw.showMinimized()
                QtWidgets.QApplication.processEvents()
                if minimize_delay_ms > 0:
                    _responsive_delay_ms(minimize_delay_ms, time_module=time_module)
            mw.hide()
            QtWidgets.QApplication.processEvents()
            if prepare_delay_ms > 0:
                _responsive_delay_ms(prepare_delay_ms, time_module=time_module)

        try:
            return select_region_from_primary_screen_fn(
                hint_text=i18n_module.t("ocr.select_hint"),
                auto_accept_on_release=auto_accept_on_release,
                parent=None if (hide_for_capture and was_visible) else mw,
            )
        finally:
            if hide_for_capture:
                restore_main_window_after_capture_fn(
                    mw,
                    was_visible=was_visible,
                    was_minimized=was_minimized,
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
) -> tuple[QtGui.QPixmap | None, str | None]:
    use_native_mac_capture = bool(mw._cfg("OCR_USE_NATIVE_MAC_CAPTURE", True)) and sys_platform == "darwin"
    if not use_native_mac_capture:
        return capture_region_with_qt_selector_fn(mw)

    QtWidgets.QMessageBox.information(
        mw,
        i18n_module.t("ocr.capture_title"),
        i18n_module.t("ocr.capture_prepare_hint"),
    )

    hide_for_capture = bool(mw._cfg("OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE", True))
    was_visible = mw.isVisible()
    was_minimized = mw.isMinimized()
    with suspend_quit_on_last_window_closed_fn(active=bool(hide_for_capture and was_visible)):
        if hide_for_capture and was_visible:
            if not was_minimized:
                mw.showMinimized()
                QtWidgets.QApplication.processEvents()
            mw.hide()
            QtWidgets.QApplication.processEvents()

        delay_ms = max(0, int(mw._cfg("OCR_CAPTURE_PREPARE_DELAY_MS", 120)))
        if delay_ms > 0:
            _responsive_delay_ms(delay_ms, time_module=time_module)

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            capture_path = Path(tmp.name)

        try:
            selected_pixmap, select_error = select_region_with_macos_screencapture_fn(
                capture_path,
                timeout_s=float(mw._cfg("OCR_CAPTURE_TIMEOUT_S", 45.0)),
            )
        finally:
            try:
                capture_path.unlink(missing_ok=True)
            except Exception:
                pass
            if hide_for_capture:
                restore_main_window_after_capture_fn(
                    mw,
                    was_visible=was_visible,
                    was_minimized=was_minimized,
                )

    if selected_pixmap is None and select_error == "screencapture-not-found":
        return capture_region_with_qt_selector_fn(mw)
    return selected_pixmap, select_error


def build_ocr_pixmap_variants(mw, source: QtGui.QPixmap) -> list[QtGui.QPixmap]:
    variants: list[QtGui.QPixmap] = []
    seen: set[tuple[int, int, int]] = set()
    yield_events = bool(mw._cfg("OCR_UI_YIELD_DURING_VARIANT_BUILD", sys.platform.startswith("win")))
    try:
        yield_max_ms = max(1, int(mw._cfg("OCR_UI_YIELD_MAX_MS", 8)))
    except (TypeError, ValueError):
        yield_max_ms = 8

    def _yield_ui_events() -> None:
        if not yield_events:
            return
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        try:
            app.processEvents(QtCore.QEventLoop.AllEvents, int(yield_max_ms))
        except Exception:
            try:
                QtWidgets.QApplication.processEvents()
            except Exception:
                pass

    def _add_variant(pix: QtGui.QPixmap | None) -> None:
        if pix is None or pix.isNull():
            return
        key = (pix.width(), pix.height(), int(pix.cacheKey()))
        if key in seen:
            return
        seen.add(key)
        variants.append(pix)
        _yield_ui_events()

    def _left_crop_variant(pix: QtGui.QPixmap) -> QtGui.QPixmap | None:
        if pix.isNull():
            return None
        if not bool(mw._cfg("OCR_INCLUDE_LEFT_CROP_VARIANTS", False)):
            return None
        ratio = float(mw._cfg("OCR_NAME_COLUMN_CROP_RATIO", 0.50))
        ratio = max(0.35, min(0.95, ratio))
        crop_w = int(pix.width() * ratio)
        if crop_w <= 0 or crop_w >= pix.width():
            return None
        return pix.copy(0, 0, crop_w, pix.height())

    def _mono_variant(pix: QtGui.QPixmap) -> QtGui.QPixmap | None:
        if pix.isNull():
            return None
        if not bool(mw._cfg("OCR_INCLUDE_MONO_VARIANTS", True)):
            return None
        gray = pix.toImage().convertToFormat(QtGui.QImage.Format_Grayscale8)
        mono = gray.convertToFormat(QtGui.QImage.Format_Mono, QtCore.Qt.ThresholdDither)
        mono_gray = mono.convertToFormat(QtGui.QImage.Format_Grayscale8)
        return QtGui.QPixmap.fromImage(mono_gray)

    _add_variant(source)
    _add_variant(_left_crop_variant(source))
    scale_factor = max(1, int(mw._cfg("OCR_SCALE_FACTOR", 3)))
    if scale_factor > 1 and not source.isNull():
        scaled_smooth = source.scaled(
            max(1, source.width() * scale_factor),
            max(1, source.height() * scale_factor),
            QtCore.Qt.IgnoreAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        _add_variant(scaled_smooth)
        _add_variant(_left_crop_variant(scaled_smooth))
        scaled_fast = source.scaled(
            max(1, source.width() * scale_factor),
            max(1, source.height() * scale_factor),
            QtCore.Qt.IgnoreAspectRatio,
            QtCore.Qt.FastTransformation,
        )
        _add_variant(scaled_fast)
        _add_variant(_left_crop_variant(scaled_fast))

    if not source.isNull():
        gray_image = source.toImage().convertToFormat(QtGui.QImage.Format_Grayscale8)
        gray_pix = QtGui.QPixmap.fromImage(gray_image)
        _add_variant(gray_pix)
        _add_variant(_left_crop_variant(gray_pix))
        _add_variant(_mono_variant(source))
        if scale_factor > 1 and not gray_pix.isNull():
            gray_scaled_smooth = gray_pix.scaled(
                max(1, gray_pix.width() * scale_factor),
                max(1, gray_pix.height() * scale_factor),
                QtCore.Qt.IgnoreAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            _add_variant(gray_scaled_smooth)
            _add_variant(_left_crop_variant(gray_scaled_smooth))
            _add_variant(_mono_variant(gray_scaled_smooth))
            gray_scaled_fast = gray_pix.scaled(
                max(1, gray_pix.width() * scale_factor),
                max(1, gray_pix.height() * scale_factor),
                QtCore.Qt.IgnoreAspectRatio,
                QtCore.Qt.FastTransformation,
            )
            _add_variant(gray_scaled_fast)
            _add_variant(_left_crop_variant(gray_scaled_fast))
            _add_variant(_mono_variant(gray_scaled_fast))
    _yield_ui_events()
    return variants
