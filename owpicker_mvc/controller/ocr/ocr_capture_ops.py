from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import sys
import tempfile
import time

from PySide6 import QtCore, QtGui, QtWidgets

import i18n
from utils import qt_runtime

from view import screen_region_selector as _screen_selector

from . import (
    ocr_async_worker_utils as _ocr_async_worker_utils,
    ocr_debug_utils as _ocr_debug_utils,
    ocr_engine_utils as _ocr_engine_utils,
    ocr_import as _ocr_import,
    ocr_ordering_utils as _ocr_ordering_utils,
    ocr_postprocess_utils as _ocr_postprocess_utils,
    ocr_row_pass_utils as _ocr_row_pass_utils,
)


def _ocr_import_module():
    return _ocr_import


def _screen_selector_module():
    return _screen_selector


def select_region_from_primary_screen(*args, **kwargs):
    return _screen_selector_module().select_region_from_primary_screen(*args, **kwargs)


def select_region_with_macos_screencapture(*args, **kwargs):
    return _screen_selector_module().select_region_with_macos_screencapture(*args, **kwargs)


def _restore_override_cursor() -> None:
    try:
        while QtWidgets.QApplication.overrideCursor() is not None:
            QtWidgets.QApplication.restoreOverrideCursor()
    except Exception:
        pass


def _cancel_ocr_cache_release(mw) -> None:
    handler = getattr(mw, "_cancel_ocr_runtime_cache_release", None)
    if callable(handler):
        try:
            handler()
        except Exception:
            pass


def _schedule_ocr_cache_release(mw) -> None:
    handler = getattr(mw, "_schedule_ocr_runtime_cache_release", None)
    if callable(handler):
        try:
            handler()
        except Exception:
            pass


def _show_ocr_busy_overlay(mw, role: str) -> bool:
    overlay = getattr(mw, "overlay", None)
    if overlay is None:
        return False
    try:
        normalized_role = str(role or "").strip().casefold()
        if normalized_role == "all":
            line1 = i18n.t("ocr.progress_line_all")
        else:
            role_name_fn = getattr(mw, "_ocr_role_display_name", None)
            role_name = role_name_fn(normalized_role) if callable(role_name_fn) else normalized_role.upper()
            line1 = i18n.t("ocr.progress_line_role", role=role_name)
        overlay.show_status_message(
            i18n.t("ocr.progress_title"),
            [
                line1,
                i18n.t("ocr.progress_line_wait"),
                "",
            ],
        )
        overlay.setEnabled(False)
        # Force a paint pass before CPU-heavy OCR checks/work so users see
        # immediate feedback right after the screenshot selection.
        try:
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass
        return True
    except Exception:
        return False


def _hide_ocr_busy_overlay(mw, *, active: bool) -> None:
    if not active:
        return
    overlay = getattr(mw, "overlay", None)
    if overlay is None:
        return
    try:
        overlay.setEnabled(True)
    except Exception:
        pass
    try:
        last_view = getattr(overlay, "_last_view", {}) or {}
        if last_view.get("type") != "status_message":
            return
        data = last_view.get("data") or ()
        if not data:
            return
        if str(data[0]) != str(i18n.t("ocr.progress_title")):
            return
        overlay.hide()
    except Exception:
        pass


def _mark_ocr_runtime_activated(mw) -> None:
    marker = getattr(mw, "_mark_ocr_runtime_activated", None)
    if callable(marker):
        try:
            marker()
            return
        except Exception:
            pass
    try:
        setattr(mw, "_ocr_runtime_activated", True)
    except Exception:
        pass


def _capture_region_with_qt_selector(mw) -> tuple[QtGui.QPixmap | None, str | None]:
    hide_for_capture = bool(mw._cfg("OCR_HIDE_MAIN_WINDOW_FOR_CAPTURE", True))
    if sys.platform == "win32":
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
        mw._cfg("OCR_QT_SELECTOR_AUTO_ACCEPT_ON_RELEASE", sys.platform == "win32")
    )
    was_visible = mw.isVisible()
    was_minimized = mw.isMinimized()

    if hide_for_capture and was_visible:
        mw.hide()
        QtWidgets.QApplication.processEvents()
        if prepare_delay_ms > 0:
            time.sleep(max(0, prepare_delay_ms) / 1000.0)

    try:
        return select_region_from_primary_screen(
            hint_text=i18n.t("ocr.select_hint"),
            auto_accept_on_release=auto_accept_on_release,
            parent=None if (hide_for_capture and was_visible) else mw,
        )
    finally:
        if hide_for_capture and was_visible and not getattr(mw, "_closing", False):
            if was_minimized:
                mw.showMinimized()
            else:
                mw.show()
                qt_runtime.safe_raise(mw)
                qt_runtime.safe_activate_window(mw)
            QtWidgets.QApplication.processEvents()


def capture_region_for_ocr(mw) -> tuple[QtGui.QPixmap | None, str | None]:
    use_native_mac_capture = bool(mw._cfg("OCR_USE_NATIVE_MAC_CAPTURE", True)) and sys.platform == "darwin"
    if not use_native_mac_capture:
        return _capture_region_with_qt_selector(mw)

    QtWidgets.QMessageBox.information(
        mw,
        i18n.t("ocr.capture_title"),
        i18n.t("ocr.capture_prepare_hint"),
    )

    was_visible = mw.isVisible()
    was_minimized = mw.isMinimized()
    if was_visible:
        mw.hide()
        QtWidgets.QApplication.processEvents()

    delay_ms = max(0, int(mw._cfg("OCR_CAPTURE_PREPARE_DELAY_MS", 120)))
    if delay_ms > 0:
        time.sleep(delay_ms / 1000.0)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        capture_path = Path(tmp.name)

    try:
        selected_pixmap, select_error = select_region_with_macos_screencapture(
            capture_path,
            timeout_s=float(mw._cfg("OCR_CAPTURE_TIMEOUT_S", 45.0)),
        )
    finally:
        try:
            capture_path.unlink(missing_ok=True)
        except Exception:
            pass
        if was_visible and not getattr(mw, "_closing", False):
            if was_minimized:
                mw.showMinimized()
            else:
                mw.show()
                qt_runtime.safe_raise(mw)
                qt_runtime.safe_activate_window(mw)
            QtWidgets.QApplication.processEvents()

    if selected_pixmap is None and select_error == "screencapture-not-found":
        return _capture_region_with_qt_selector(mw)
    return selected_pixmap, select_error


def build_ocr_pixmap_variants(mw, source: QtGui.QPixmap) -> list[QtGui.QPixmap]:
    variants: list[QtGui.QPixmap] = []
    seen: set[tuple[int, int, int]] = set()

    def _add_variant(pix: QtGui.QPixmap | None) -> None:
        if pix is None or pix.isNull():
            return
        key = (pix.width(), pix.height(), int(pix.cacheKey()))
        if key in seen:
            return
        seen.add(key)
        variants.append(pix)

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

    # Start with full image first so right-side truncation is less likely for
    # long identifiers. Left-crop is still used as an additional variant.
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
    return variants


def extract_names_from_ocr_pixmap(
    mw,
    pixmap: QtGui.QPixmap,
    *,
    ocr_cmd: str = "",
) -> tuple[list[str], str, str | None]:
    runtime_cfg = _ocr_runtime_cfg_snapshot(mw)
    temp_paths, prep_errors = _prepare_ocr_variant_files(mw, pixmap, runtime_cfg)
    if not temp_paths:
        reason = "; ".join(prep_errors) if prep_errors else "image-save-failed"
        return [], "", reason

    try:
        names, merged_text, error_text = _extract_names_from_ocr_files(
            temp_paths,
            ocr_cmd=ocr_cmd,
            cfg=runtime_cfg,
        )
    finally:
        _cleanup_temp_paths(temp_paths)

    if prep_errors:
        if error_text:
            error_text = "; ".join(prep_errors + [error_text])
        else:
            error_text = "; ".join(prep_errors)
    return names, merged_text, error_text


def _ocr_runtime_cfg_snapshot(mw) -> dict:
    def _parse_psm_values(raw) -> list[int]:
        values: list[int] = []
        if isinstance(raw, str):
            parts = raw.replace(";", ",").split(",")
        elif isinstance(raw, (list, tuple, set)):
            parts = list(raw)
        else:
            parts = []
        for part in parts:
            try:
                value = int(str(part).strip())
            except Exception:
                continue
            if value < 0 or value in values:
                continue
            values.append(value)
        return values

    def _parse_easyocr_gpu_value(raw) -> str:
        if isinstance(raw, str):
            token = raw.strip().lower()
            if token in {"", "auto", "best", "gpu", "true", "1", "yes", "on"}:
                return "auto"
            if token in {"cpu", "false", "0", "off", "no"}:
                return "cpu"
            if token in {"mps", "cuda"}:
                return token
            return "auto"
        return "auto" if bool(raw) else "cpu"

    def _cfg_bool_map(entries: list[tuple[str, str, bool]]) -> dict[str, bool]:
        values: dict[str, bool] = {}
        for key, cfg_key, default in entries:
            values[key] = bool(mw._cfg(cfg_key, default))
        return values

    def _cfg_int_map(entries: list[tuple[str, str, int]]) -> dict[str, int]:
        values: dict[str, int] = {}
        for key, cfg_key, default in entries:
            values[key] = int(mw._cfg(cfg_key, default))
        return values

    def _cfg_float_map(entries: list[tuple[str, str, float]]) -> dict[str, float]:
        values: dict[str, float] = {}
        for key, cfg_key, default in entries:
            values[key] = float(mw._cfg(cfg_key, default))
        return values

    def _cfg_optional_str(cfg_key: str, default: str = "") -> str | None:
        return str(mw._cfg(cfg_key, default)).strip() or None

    engine = str(mw._cfg("OCR_ENGINE", "easyocr")).strip().casefold()
    if engine in {"easy", "easy-ocr", "easy_ocr"}:
        engine = "easyocr"
    if engine != "easyocr":
        engine = "easyocr"

    fast_mode = bool(mw._cfg("OCR_FAST_MODE", True))
    default_max_variants = 2 if fast_mode else 0
    if sys.platform == "win32" and fast_mode:
        default_max_variants = 1
    max_variants = int(mw._cfg("OCR_MAX_VARIANTS", default_max_variants))
    if sys.platform == "win32":
        max_variants = int(mw._cfg("OCR_MAX_VARIANTS_WINDOWS", max_variants))
    psm_primary = int(mw._cfg("OCR_PRIMARY_PSM", 11))
    psm_fallback = int(mw._cfg("OCR_FALLBACK_PSM", 6))
    psm_values = [psm_primary]
    if (not fast_mode) and psm_fallback not in psm_values:
        psm_values.append(psm_fallback)
    retry_extra_psm_values = _parse_psm_values(mw._cfg("OCR_RETRY_EXTRA_PSMS", [7, 13]))
    timeout_s = float(mw._cfg("OCR_TIMEOUT_S", 8.0))
    if sys.platform == "win32":
        timeout_s = float(mw._cfg("OCR_TIMEOUT_S_WINDOWS", timeout_s))
    retry_min_candidates = int(mw._cfg("OCR_RECALL_RETRY_MIN_CANDIDATES", 5))
    retry_max_variants = int(mw._cfg("OCR_RECALL_RETRY_MAX_VARIANTS", 4))
    if retry_max_variants < 0:
        retry_max_variants = 0
    row_pass_psm_values = _parse_psm_values(mw._cfg("OCR_ROW_PASS_PSMS", [7, 13, 6]))
    if not row_pass_psm_values:
        row_pass_psm_values = [7, 6, 13]
    quiet_mode = bool(mw._cfg("QUIET", False))
    debug_show_report = bool(mw._cfg("OCR_DEBUG_SHOW_REPORT", False))
    debug_include_report_text = bool(mw._cfg("OCR_DEBUG_INCLUDE_REPORT_TEXT", debug_show_report))
    debug_log_to_file = bool(mw._cfg("OCR_DEBUG_LOG_TO_FILE", True))
    debug_line_analysis = bool(mw._cfg("OCR_DEBUG_LINE_ANALYSIS", True))
    if quiet_mode:
        debug_show_report = False
        debug_include_report_text = False
        debug_log_to_file = False
        debug_line_analysis = False

    easyocr_lang = str(mw._cfg("OCR_EASYOCR_LANG", "en,de,ja,ch_sim,ko")).strip() or None
    cfg = {
        "engine": engine,
        "fast_mode": fast_mode,
        "max_variants": max_variants,
        "psm_primary": psm_primary,
        "psm_fallback": psm_fallback,
        "psm_values": tuple(psm_values),
        "retry_extra_psm_values": tuple(retry_extra_psm_values),
        "lang": easyocr_lang,
        "easyocr_lang": easyocr_lang,
        "easyocr_model_dir": _cfg_optional_str("OCR_EASYOCR_MODEL_DIR"),
        "easyocr_user_network_dir": _cfg_optional_str("OCR_EASYOCR_USER_NETWORK_DIR"),
        "easyocr_gpu": _parse_easyocr_gpu_value(mw._cfg("OCR_EASYOCR_GPU", "auto")),
        "quiet_mode": quiet_mode,
        "timeout_s": timeout_s,
        "debug_show_report": debug_show_report,
        "debug_include_report_text": debug_include_report_text,
        "debug_log_to_file": debug_log_to_file,
        "debug_line_analysis": debug_line_analysis,
        "recall_retry_min_candidates": retry_min_candidates,
        "recall_retry_max_variants": retry_max_variants,
        "row_pass_psm_values": tuple(row_pass_psm_values),
    }
    cfg.update(
        _cfg_bool_map(
            [
                ("stop_after_variant_success", "OCR_STOP_AFTER_FIRST_VARIANT_SUCCESS", True),
                ("fast_mode_confident_line_stop", "OCR_FAST_MODE_CONFIDENT_LINE_STOP", True),
                ("precount_fast_probe_enabled", "OCR_PRECOUNT_FAST_PROBE_ENABLED", True),
                (
                    "precount_fast_probe_single_expected",
                    "OCR_PRECOUNT_FAST_PROBE_SINGLE_EXPECTED",
                    True,
                ),
                ("easyocr_download_enabled", "OCR_EASYOCR_DOWNLOAD_ENABLED", False),
                ("debug_trace_line_mapping", "OCR_DEBUG_TRACE_LINE_MAPPING", True),
                ("recall_retry_enabled", "OCR_RECALL_RETRY_ENABLED", True),
                (
                    "recall_retry_skip_when_primary_clean",
                    "OCR_RECALL_RETRY_SKIP_WHEN_PRIMARY_CLEAN",
                    True,
                ),
                ("recall_retry_use_fallback_psm", "OCR_RECALL_RETRY_USE_FALLBACK_PSM", True),
                ("recall_relax_support_on_low_count", "OCR_RECALL_RELAX_SUPPORT_ON_LOW_COUNT", True),
                ("row_pass_enabled", "OCR_ROW_PASS_ENABLED", True),
                ("row_pass_always_run", "OCR_ROW_PASS_ALWAYS_RUN", True),
                ("row_pass_skip_when_primary_stable", "OCR_ROW_PASS_SKIP_WHEN_PRIMARY_STABLE", True),
                ("row_pass_full_width_fallback", "OCR_ROW_PASS_FULL_WIDTH_FALLBACK", True),
                ("row_pass_full_width_edge_only", "OCR_ROW_PASS_FULL_WIDTH_EDGE_ONLY", True),
                ("row_pass_full_only_when_name_uncertain", "OCR_ROW_PASS_FULL_ONLY_WHEN_NAME_UNCERTAIN", True),
                ("row_pass_skip_full_when_name_empty", "OCR_ROW_PASS_SKIP_FULL_WHEN_NAME_EMPTY", True),
                ("row_pass_skip_full_when_name_low_conf", "OCR_ROW_PASS_SKIP_FULL_WHEN_NAME_LOW_CONF", True),
                ("row_pass_include_mono", "OCR_ROW_PASS_INCLUDE_MONO", True),
                ("row_pass_skip_mono_when_non_mono_empty", "OCR_ROW_PASS_SKIP_MONO_WHEN_NON_MONO_EMPTY", True),
                ("row_pass_skip_mono_when_non_mono_low_conf", "OCR_ROW_PASS_SKIP_MONO_WHEN_NON_MONO_LOW_CONF", True),
                ("row_pass_single_name_per_row", "OCR_ROW_PASS_SINGLE_NAME_PER_ROW", True),
                ("row_pass_confident_single_vote_stop", "OCR_ROW_PASS_CONFIDENT_SINGLE_VOTE_STOP", True),
                (
                    "row_pass_confident_single_vote_stop_when_primary_complete",
                    "OCR_ROW_PASS_CONFIDENT_SINGLE_VOTE_STOP_WHEN_PRIMARY_COMPLETE",
                    True,
                ),
                (
                    "row_pass_single_psm_when_primary_complete",
                    "OCR_ROW_PASS_SINGLE_PSM_WHEN_PRIMARY_COMPLETE",
                    True,
                ),
                ("row_pass_line_prefilter_enabled", "OCR_ROW_PASS_LINE_PREFILTER_ENABLED", True),
                ("row_pass_mono_retry_only_when_uncertain", "OCR_ROW_PASS_MONO_RETRY_ONLY_WHEN_UNCERTAIN", True),
                ("row_pass_extra_rows_light_mode", "OCR_ROW_PASS_EXTRA_ROWS_LIGHT_MODE", True),
                ("row_pass_stop_when_expected_reached", "OCR_ROW_PASS_STOP_WHEN_EXPECTED_REACHED", True),
                ("row_pass_adaptive_max_rows", "OCR_ROW_PASS_ADAPTIVE_MAX_ROWS", True),
                ("row_pass_early_abort_on_primary_strong", "OCR_ROW_PASS_EARLY_ABORT_ON_PRIMARY_STRONG", True),
                ("single_name_per_line", "OCR_SINGLE_NAME_PER_LINE", False),
                ("line_relaxed_fallback", "OCR_LINE_RELAXED_FALLBACK", True),
                ("name_special_char_constraint", "OCR_NAME_SPECIAL_CHAR_CONSTRAINT", False),
                ("name_confidence_filter_noisy_only", "OCR_NAME_CONFIDENCE_FILTER_NOISY_ONLY", True),
            ]
        )
    )
    cfg.update(
        _cfg_int_map(
            [
                ("fast_mode_confident_line_min_lines", "OCR_FAST_MODE_CONFIDENT_LINE_MIN_LINES", 0),
                (
                    "fast_mode_confident_line_missing_tolerance",
                    "OCR_FAST_MODE_CONFIDENT_LINE_MISSING_TOLERANCE",
                    1,
                ),
                (
                    "precount_fast_probe_max_variants",
                    "OCR_PRECOUNT_FAST_PROBE_MAX_VARIANTS",
                    1,
                ),
                ("debug_report_max_chars", "OCR_DEBUG_REPORT_MAX_CHARS", 12000),
                ("debug_line_max_entries_per_run", "OCR_DEBUG_LINE_MAX_ENTRIES_PER_RUN", 40),
                ("debug_trace_max_entries", "OCR_DEBUG_TRACE_MAX_ENTRIES", 220),
                ("recall_retry_max_candidates", "OCR_RECALL_RETRY_MAX_CANDIDATES", 7),
                (
                    "recall_retry_skip_primary_clean_min_count",
                    "OCR_RECALL_RETRY_SKIP_PRIMARY_CLEAN_MIN_COUNT",
                    4,
                ),
                (
                    "recall_retry_skip_primary_clean_max_shortfall",
                    "OCR_RECALL_RETRY_SKIP_PRIMARY_CLEAN_MAX_SHORTFALL",
                    1,
                ),
                ("row_pass_primary_stable_min_candidates", "OCR_ROW_PASS_PRIMARY_STABLE_MIN_CANDIDATES", 0),
                ("row_pass_min_candidates", "OCR_ROW_PASS_MIN_CANDIDATES", 5),
                ("row_pass_brightness_threshold", "OCR_ROW_PASS_BRIGHTNESS_THRESHOLD", 145),
                ("row_pass_merge_gap_px", "OCR_ROW_PASS_MERGE_GAP_PX", 2),
                ("row_pass_min_height_px", "OCR_ROW_PASS_MIN_HEIGHT_PX", 7),
                ("row_pass_max_rows", "OCR_ROW_PASS_MAX_ROWS", 12),
                ("row_pass_pad_px", "OCR_ROW_PASS_PAD_PX", 2),
                ("row_pass_scale_factor", "OCR_ROW_PASS_SCALE_FACTOR", 4),
                ("row_pass_vote_target_single_name", "OCR_ROW_PASS_VOTE_TARGET_SINGLE_NAME", 2),
                (
                    "row_pass_vote_target_single_name_when_primary_complete",
                    "OCR_ROW_PASS_VOTE_TARGET_SINGLE_NAME_WHEN_PRIMARY_COMPLETE",
                    1,
                ),
                ("row_pass_vote_target_multi_name", "OCR_ROW_PASS_VOTE_TARGET_MULTI_NAME", 3),
                ("row_pass_line_prefilter_min_alnum", "OCR_ROW_PASS_LINE_PREFILTER_MIN_ALNUM", 2),
                ("row_pass_primary_complete_margin", "OCR_ROW_PASS_PRIMARY_COMPLETE_MARGIN", 1),
                (
                    "row_pass_primary_stable_relaxed_expected_gap",
                    "OCR_ROW_PASS_PRIMARY_STABLE_RELAXED_EXPECTED_GAP",
                    3,
                ),
                ("row_pass_early_abort_probe_rows", "OCR_ROW_PASS_EARLY_ABORT_PROBE_ROWS", 3),
                (
                    "row_pass_early_abort_probe_rows_when_primary_complete",
                    "OCR_ROW_PASS_EARLY_ABORT_PROBE_ROWS_WHEN_PRIMARY_COMPLETE",
                    2,
                ),
                ("row_pass_early_abort_primary_min_candidates", "OCR_ROW_PASS_EARLY_ABORT_PRIMARY_MIN_CANDIDATES", 0),
                ("row_pass_extra_rows_light_mode_min_collected", "OCR_ROW_PASS_EXTRA_ROWS_LIGHT_MODE_MIN_COLLECTED", 0),
                ("row_pass_adaptive_extra_rows", "OCR_ROW_PASS_ADAPTIVE_EXTRA_ROWS", 2),
                ("row_pass_consecutive_empty_row_stop", "OCR_ROW_PASS_CONSECUTIVE_EMPTY_ROW_STOP", 2),
                ("row_pass_empty_row_stop_min_collected", "OCR_ROW_PASS_EMPTY_ROW_STOP_MIN_COLLECTED", 0),
                ("name_min_chars", "OCR_NAME_MIN_CHARS", 2),
                ("name_max_chars", "OCR_NAME_MAX_CHARS", 24),
                ("name_max_words", "OCR_NAME_MAX_WORDS", 2),
                ("line_recall_max_additions", "OCR_LINE_RECALL_MAX_ADDITIONS", 2),
                ("name_min_support", "OCR_NAME_MIN_SUPPORT", 1),
                ("name_low_confidence_min_support", "OCR_NAME_LOW_CONFIDENCE_MIN_SUPPORT", 2),
                ("name_high_count_threshold", "OCR_NAME_HIGH_COUNT_THRESHOLD", 8),
                ("name_high_count_min_support", "OCR_NAME_HIGH_COUNT_MIN_SUPPORT", 2),
                ("name_max_candidates", "OCR_NAME_MAX_CANDIDATES", 12),
                ("name_near_dup_min_chars", "OCR_NAME_NEAR_DUP_MIN_CHARS", 8),
                ("name_near_dup_max_len_delta", "OCR_NAME_NEAR_DUP_MAX_LEN_DELTA", 1),
                ("name_near_dup_tail_min_chars", "OCR_NAME_NEAR_DUP_TAIL_MIN_CHARS", 3),
            ]
        )
    )
    cfg.update(
        _cfg_float_map(
            [
                ("fast_mode_confident_line_min_avg_conf", "OCR_FAST_MODE_CONFIDENT_LINE_MIN_AVG_CONF", 68.0),
                (
                    "fast_mode_confident_line_min_avg_conf_tolerant",
                    "OCR_FAST_MODE_CONFIDENT_LINE_MIN_AVG_CONF_TOLERANT",
                    78.0,
                ),
                ("recall_retry_short_name_max_ratio", "OCR_RECALL_RETRY_SHORT_NAME_MAX_RATIO", 0.34),
                (
                    "recall_retry_skip_primary_clean_min_avg_conf",
                    "OCR_RECALL_RETRY_SKIP_PRIMARY_CLEAN_MIN_AVG_CONF",
                    78.0,
                ),
                ("recall_retry_timeout_scale", "OCR_RECALL_RETRY_TIMEOUT_SCALE", 1.35),
                ("row_pass_min_pixels_ratio", "OCR_ROW_PASS_MIN_PIXELS_RATIO", 0.015),
                ("row_pass_name_x_ratio", "OCR_ROW_PASS_NAME_X_RATIO", 0.58),
                ("row_pass_projection_x_start_ratio", "OCR_ROW_PASS_PROJECTION_X_START_RATIO", 0.08),
                ("row_pass_projection_x_end_ratio", "OCR_ROW_PASS_PROJECTION_X_END_RATIO", 0.92),
                ("row_pass_projection_col_max_ratio", "OCR_ROW_PASS_PROJECTION_COL_MAX_RATIO", 0.84),
                ("row_pass_full_only_when_name_uncertain_min_conf", "OCR_ROW_PASS_FULL_ONLY_WHEN_NAME_UNCERTAIN_MIN_CONF", 68.0),
                ("row_pass_skip_full_when_name_low_conf_max_conf", "OCR_ROW_PASS_SKIP_FULL_WHEN_NAME_LOW_CONF_MAX_CONF", 12.0),
                ("row_pass_skip_mono_when_non_mono_low_conf_max_conf", "OCR_ROW_PASS_SKIP_MONO_WHEN_NON_MONO_LOW_CONF_MAX_CONF", 12.0),
                ("row_pass_timeout_scale", "OCR_ROW_PASS_TIMEOUT_SCALE", 0.55),
                ("row_pass_confident_single_vote_min_conf", "OCR_ROW_PASS_CONFIDENT_SINGLE_VOTE_MIN_CONF", 96.0),
                (
                    "row_pass_confident_single_vote_min_conf_when_primary_complete",
                    "OCR_ROW_PASS_CONFIDENT_SINGLE_VOTE_MIN_CONF_WHEN_PRIMARY_COMPLETE",
                    72.0,
                ),
                ("row_pass_line_prefilter_low_conf", "OCR_ROW_PASS_LINE_PREFILTER_LOW_CONF", 22.0),
                ("row_pass_line_prefilter_high_conf_bypass", "OCR_ROW_PASS_LINE_PREFILTER_HIGH_CONF_BYPASS", 72.0),
                ("row_pass_line_prefilter_min_alpha_ratio", "OCR_ROW_PASS_LINE_PREFILTER_MIN_ALPHA_RATIO", 0.42),
                ("row_pass_line_prefilter_max_punct_ratio", "OCR_ROW_PASS_LINE_PREFILTER_MAX_PUNCT_RATIO", 0.65),
                ("row_pass_line_stats_min_conf", "OCR_ROW_PASS_LINE_STATS_MIN_CONF", 8.0),
                ("row_pass_mono_retry_min_conf", "OCR_ROW_PASS_MONO_RETRY_MIN_CONF", 70.0),
                ("row_pass_early_abort_low_conf", "OCR_ROW_PASS_EARLY_ABORT_LOW_CONF", 22.0),
                (
                    "row_pass_primary_stable_relaxed_min_avg_conf",
                    "OCR_ROW_PASS_PRIMARY_STABLE_RELAXED_MIN_AVG_CONF",
                    76.0,
                ),
                ("name_max_digit_ratio", "OCR_NAME_MAX_DIGIT_RATIO", 0.45),
                ("name_min_confidence", "OCR_NAME_MIN_CONFIDENCE", 43.0),
                ("name_near_dup_similarity", "OCR_NAME_NEAR_DUP_SIMILARITY", 0.90),
                ("name_near_dup_tail_head_similarity", "OCR_NAME_NEAR_DUP_TAIL_HEAD_SIMILARITY", 0.70),
            ]
        )
    )
    return cfg


def _prepare_ocr_variant_files(
    mw,
    source_pixmap: QtGui.QPixmap,
    cfg: dict,
) -> tuple[list[Path], list[str]]:
    variants = build_ocr_pixmap_variants(mw, source_pixmap)
    primary_limit = int(cfg.get("max_variants", 0))
    retry_limit = int(cfg.get("recall_retry_max_variants", 0))
    if primary_limit <= 0 or retry_limit <= 0:
        variant_cap = 0
    else:
        variant_cap = max(primary_limit, retry_limit)
    if variant_cap > 0:
        variants = variants[:variant_cap]

    paths: list[Path] = []
    errors: list[str] = []
    for variant in variants:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            if not variant.save(str(tmp_path), "PNG"):
                errors.append("image-save-failed")
                tmp_path.unlink(missing_ok=True)
                continue
            paths.append(tmp_path)
        except Exception as exc:
            errors.append(f"image-save-error:{exc}")
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
    return paths, errors


def _cleanup_temp_paths(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def _select_variant_paths(paths: list[Path], cfg: dict, *, max_variants_key: str) -> list[Path]:
    max_variants = int(cfg.get(max_variants_key, 0))
    if max_variants > 0:
        return list(paths[:max_variants])
    return list(paths)


def _merge_ocr_texts_unique_lines(texts: list[str]) -> str:
    merged_lines: list[str] = []
    seen_lines: set[str] = set()
    for text in texts:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            key = line.lower()
            if key in seen_lines:
                continue
            seen_lines.add(key)
            merged_lines.append(line)
    return "\n".join(merged_lines)


_simple_name_key = _ocr_postprocess_utils._simple_name_key


_IDENTIFIER_HINT_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,95}$")


@lru_cache(maxsize=1)
def _config_identifier_hints() -> tuple[str, ...]:
    try:
        import config as app_config
    except Exception:
        return ()
    hints: set[str] = set()
    for key in dir(app_config):
        if not key.isupper():
            continue
        if _IDENTIFIER_HINT_RE.match(str(key)):
            hints.add(str(key))
    return tuple(sorted(hints))


def _normalize_identifier_candidate(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_ ]+", " ", str(value or ""))
    tokens = [tok for tok in re.split(r"[\s_]+", cleaned) if tok]
    if not tokens:
        return ""
    return "_".join(tokens).upper()


def _looks_like_identifier_candidate(value: str, normalized: str) -> bool:
    if not normalized or normalized.count("_") < 1:
        return False
    if len(normalized) < 6:
        return False
    letters = [ch for ch in str(value or "") if ch.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(1 for ch in letters if ch.isupper()) / max(1, len(letters))
    return upper_ratio >= 0.7


def _expand_config_identifier_prefixes(names: list[str]) -> list[str]:
    hints = _config_identifier_hints()
    if not hints:
        return list(names or [])
    hint_set = set(hints)
    resolved: list[str] = []
    seen: set[str] = set()
    for raw_name in list(names or []):
        candidate = str(raw_name or "").strip()
        if not candidate:
            continue
        normalized = _normalize_identifier_candidate(candidate)
        if _looks_like_identifier_candidate(candidate, normalized):
            if normalized in hint_set:
                candidate = normalized
            else:
                matches = [hint for hint in hints if hint.startswith(normalized)]
                if len(matches) == 1:
                    candidate = matches[0]
        key = _simple_name_key(candidate)
        if not key or key in seen:
            continue
        seen.add(key)
        resolved.append(candidate)
    return resolved


_line_extractor_kwargs = _ocr_engine_utils._line_extractor_kwargs
_multi_extractor_kwargs = _ocr_engine_utils._multi_extractor_kwargs
_line_entry_text = _ocr_engine_utils._line_entry_text
_line_entry_conf = _ocr_engine_utils._line_entry_conf
_run_result_text = _ocr_engine_utils._run_result_text
_run_result_error = _ocr_engine_utils._run_result_error
_ocr_engine_from_cfg = _ocr_engine_utils._ocr_engine_from_cfg
_easyocr_runner_kwargs = _ocr_engine_utils._easyocr_runner_kwargs
_easyocr_resolution_kwargs = _ocr_engine_utils._easyocr_resolution_kwargs
_run_ocr_multi_with_cfg = _ocr_engine_utils._run_ocr_multi_with_cfg
_build_ocr_run_entry = _ocr_engine_utils._build_ocr_run_entry
_line_entries_from_run_result = _ocr_engine_utils._line_entries_from_run_result
_OCRLineParseContext = _ocr_engine_utils._OCRLineParseContext
_extract_names_from_texts = _ocr_engine_utils._extract_names_from_texts
_truncate_report_text = _ocr_engine_utils._truncate_report_text
_extract_line_debug_for_text = _ocr_engine_utils._extract_line_debug_for_text
_line_payload_from_entries = _ocr_engine_utils._line_payload_from_entries


def _run_ocr_pass(
    paths: list[Path],
    *,
    pass_label: str,
    cfg: dict,
    max_variants_key: str,
    ocr_cmd: str = "",
) -> tuple[list[str], list[str], list[dict]]:
    return _ocr_engine_utils._run_ocr_pass(
        paths,
        pass_label=pass_label,
        cfg=cfg,
        max_variants_key=max_variants_key,
        ocr_cmd=ocr_cmd,
        ocr_import=_ocr_import_module(),
        select_variant_paths_fn=_select_variant_paths,
    )


_candidate_stats_from_runs = _ocr_postprocess_utils._candidate_stats_from_runs
_candidate_set_looks_noisy = _ocr_postprocess_utils._candidate_set_looks_noisy
_filter_low_confidence_candidates = _ocr_postprocess_utils._filter_low_confidence_candidates
_merge_prefix_candidate_stats = _ocr_postprocess_utils._merge_prefix_candidate_stats
_merge_near_duplicate_candidate_stats = _ocr_postprocess_utils._merge_near_duplicate_candidate_stats
_should_run_row_pass = _ocr_postprocess_utils._should_run_row_pass
_prefer_row_candidates = _ocr_postprocess_utils._prefer_row_candidates
_dedupe_names_in_order = _ocr_postprocess_utils._dedupe_names_in_order
_candidate_bucket_score = _ocr_postprocess_utils._candidate_bucket_score
_select_candidate_keys_from_stats = _ocr_postprocess_utils._select_candidate_keys_from_stats
_build_final_names_from_runs = _ocr_postprocess_utils._build_final_names_from_runs


_detect_text_row_ranges = _ocr_row_pass_utils._detect_text_row_ranges
_build_row_image_variants = _ocr_row_pass_utils._build_row_image_variants
_row_image_looks_right_clipped = _ocr_row_pass_utils._row_image_looks_right_clipped
_name_display_quality = _ocr_postprocess_utils._name_display_quality
_name_similarity = _ocr_postprocess_utils._name_similarity
_common_prefix_len = _ocr_postprocess_utils._common_prefix_len
_merge_row_prefix_variants = _ocr_row_pass_utils._merge_row_prefix_variants


def _build_row_crops_for_range(
    *,
    gray: QtGui.QImage,
    top: int,
    row_h: int,
    name_width: int,
    is_pre_cropped: bool,
    cfg: dict,
) -> list[tuple[str, QtGui.QImage]]:
    return _ocr_row_pass_utils._build_row_crops_for_range(
        gray=gray,
        top=top,
        row_h=row_h,
        name_width=name_width,
        is_pre_cropped=is_pre_cropped,
        cfg=cfg,
        row_image_looks_right_clipped_fn=_row_image_looks_right_clipped,
    )


def _select_row_names_from_ranked_votes(
    ranked_votes: list[dict[str, object]],
    *,
    cfg: dict,
    best_vote_count: int,
) -> list[str]:
    return _ocr_row_pass_utils._select_row_names_from_ranked_votes(
        ranked_votes,
        cfg=cfg,
        best_vote_count=best_vote_count,
        simple_name_key_fn=_simple_name_key,
    )


def _run_row_segmentation_pass(
    paths: list[Path],
    *,
    cfg: dict,
    parse_ctx: _OCRLineParseContext,
) -> tuple[list[str], list[str], list[dict]]:
    return _ocr_row_pass_utils._run_row_segmentation_pass(
        paths,
        cfg=cfg,
        parse_ctx=parse_ctx,
        ocr_import=_ocr_import_module(),
        select_variant_paths_fn=_select_variant_paths,
        detect_text_row_ranges_fn=_detect_text_row_ranges,
        build_row_crops_for_range_fn=_build_row_crops_for_range,
        build_row_image_variants_fn=_build_row_image_variants,
        merge_row_prefix_variants_fn=_merge_row_prefix_variants,
        select_row_names_from_ranked_votes_fn=_select_row_names_from_ranked_votes,
        simple_name_key_fn=_simple_name_key,
        name_display_quality_fn=_name_display_quality,
        ocr_engine_from_cfg_fn=_ocr_engine_from_cfg,
        run_ocr_multi_with_cfg_fn=_run_ocr_multi_with_cfg,
        run_result_text_fn=_run_result_text,
        line_entries_from_run_result_fn=_line_entries_from_run_result,
        line_payload_from_entries_fn=_line_payload_from_entries,
        build_ocr_run_entry_fn=_build_ocr_run_entry,
    )


def _estimate_expected_rows_from_paths(paths: list[Path], cfg: dict) -> int | None:
    selected_paths = _select_variant_paths(paths, cfg, max_variants_key="max_variants")
    if not selected_paths:
        return None

    base_expected = max(1, int(cfg.get("expected_candidates", 5)))
    fast_probe_enabled = bool(cfg.get("precount_fast_probe_enabled", True)) and bool(
        cfg.get("fast_mode", True)
    )
    single_expected_probe = bool(cfg.get("precount_fast_probe_single_expected", True))
    max_probe_variants = max(1, int(cfg.get("precount_fast_probe_max_variants", 1)))
    if fast_probe_enabled:
        selected_paths = list(selected_paths[:max_probe_variants])
    probe_seed_values: list[int]
    if fast_probe_enabled and single_expected_probe:
        probe_seed_values = [base_expected]
    else:
        probe_seed_values = [base_expected, max(1, base_expected - 2), base_expected + 2]
    probe_expected_values: list[int] = []
    for value in probe_seed_values:
        if value not in probe_expected_values:
            probe_expected_values.append(value)

    gray_images: list[QtGui.QImage] = []
    for image_path in selected_paths:
        image = QtGui.QImage(str(image_path))
        if image.isNull():
            continue
        gray = image.convertToFormat(QtGui.QImage.Format_Grayscale8)
        if gray.isNull():
            continue
        gray_images.append(gray)
    if not gray_images:
        return None

    def _range_count(value) -> int:
        if value is None:
            return 0
        try:
            return len(value)
        except Exception:
            return len(list(value or ()))

    def _collect_counts(expected_values: list[int]) -> list[int]:
        found_counts: list[int] = []
        for gray in gray_images:
            for probe_expected in expected_values:
                probe_cfg = dict(cfg)
                probe_cfg["expected_candidates"] = probe_expected
                ranges = _detect_text_row_ranges(gray, probe_cfg)
                count = _range_count(ranges)
                if count > 0:
                    found_counts.append(count)
        return found_counts

    counts = _collect_counts(probe_expected_values)
    if not counts:
        if fast_probe_enabled and single_expected_probe:
            # Fallback: if the lightweight probe found nothing, run one legacy
            # pass to avoid false negatives from a single expected-row guess.
            legacy_values = [base_expected, max(1, base_expected - 2), base_expected + 2]
            counts = _collect_counts(legacy_values)
            if not counts:
                return None
        else:
            return None

    frequency: dict[int, int] = {}
    for count in counts:
        frequency[count] = int(frequency.get(count, 0)) + 1
    max_rows = max(1, int(cfg.get("row_pass_max_rows", 12)))
    best_count = max(
        frequency.items(),
        key=lambda item: (int(item[1]), int(item[0])),
    )[0]
    return max(1, min(max_rows, int(best_count)))


def _run_line_count(run: dict) -> int:
    line_entries = list(run.get("lines") or [])
    count = 0
    for entry in line_entries:
        if str(entry.get("text", "") or "").strip():
            count += 1
    if count > 0:
        return int(count)
    text = str(run.get("text", "") or "")
    return int(sum(1 for line in text.splitlines() if str(line).strip()))


def _stable_primary_line_count(primary_runs: list[dict]) -> int | None:
    counts = [count for count in (_run_line_count(run) for run in list(primary_runs or [])) if count > 0]
    if len(counts) < 2:
        return None
    if min(counts) != max(counts):
        return None
    return int(counts[0])


def _primary_line_count_bounds(primary_runs: list[dict]) -> tuple[int | None, int | None]:
    counts = [count for count in (_run_line_count(run) for run in list(primary_runs or [])) if count > 0]
    if not counts:
        return None, None
    return int(min(counts)), int(max(counts))


def _primary_avg_line_confidence(primary_runs: list[dict]) -> float | None:
    values: list[float] = []
    for run in list(primary_runs or []):
        for entry in list(run.get("lines") or []):
            try:
                conf = float(entry.get("conf", -1.0))
            except Exception:
                conf = -1.0
            if conf >= 0.0:
                values.append(conf)
    if not values:
        return None
    return float(sum(values) / max(1, len(values)))


def _resolve_effective_precount_rows(
    visual_precount_rows: int | None,
    primary_runs: list[dict],
) -> int | None:
    visual = int(visual_precount_rows) if visual_precount_rows is not None else None
    stable_primary = _stable_primary_line_count(primary_runs)
    _primary_min, primary_max = _primary_line_count_bounds(primary_runs)
    undercount_tolerance = 1
    if visual is None or visual <= 0:
        return stable_primary
    if stable_primary is None or stable_primary <= 0:
        # With a single primary run, visual row projection can occasionally
        # under-estimate heavily. Use observed OCR line count as fallback.
        if primary_max is not None and primary_max > 0:
            if visual < (primary_max - undercount_tolerance):
                return primary_max
        return visual
    # If visual projection overestimates while primary OCR line count is stable
    # across variants, trust the stable textual line count.
    if visual > stable_primary:
        return stable_primary
    if visual < (stable_primary - undercount_tolerance):
        return stable_primary
    return visual


def _resolve_precount_row_bounds(
    *,
    effective_precount_rows: int | None,
    stable_primary_rows: int | None,
) -> tuple[int | None, int | None, int | None]:
    expected = int(effective_precount_rows) if effective_precount_rows is not None else 0
    if expected <= 0:
        return None, None, None
    min_rows = max(1, expected - 1)
    refill_target = expected
    stable = int(stable_primary_rows) if stable_primary_rows is not None else 0
    # With a stable primary line count across OCR variants, keep the upper
    # bound strict to avoid re-inflating with repass noise duplicates.
    if stable > 0:
        max_rows = expected
    else:
        max_rows = expected + 1
    return min_rows, max_rows, refill_target


def _precount_extra_allowance_from_stats(
    *,
    base_max_rows: int,
    stats: dict[str, dict[str, float | int | str]],
    cfg: dict,
) -> int:
    base_max = max(1, int(base_max_rows))
    ranked = sorted(
        list(stats.items()),
        key=lambda kv: (
            -_candidate_bucket_score(kv[1], cfg),
            _name_display_quality(str(kv[1].get("display", ""))),
        ),
    )
    if len(ranked) <= base_max:
        return 0

    max_extra = max(0, int(cfg.get("precount_max_extra_allowance", 1)))
    if max_extra <= 0:
        return 0

    min_conf = float(cfg.get("name_min_confidence", 43.0))
    min_support = max(2, int(cfg.get("name_low_confidence_min_support", 2)))
    allowance = 0
    for _key, bucket in ranked[base_max:]:
        if allowance >= max_extra:
            break
        text = str(bucket.get("display", "") or "").strip()
        if len(text) <= 2:
            continue
        support = int(bucket.get("support", 0))
        conf = float(bucket.get("best_conf", -1.0))
        # Keep obvious compact/low-support uppercase noise blocked.
        if text.isupper() and len(text) <= 4 and support <= 1 and conf < 55.0:
            continue
        strong = False
        if support >= min_support:
            strong = True
        elif conf >= (min_conf + 8.0):
            strong = True
        elif support >= 2 and conf >= min_conf:
            strong = True
        if not strong:
            continue
        allowance += 1
    return allowance


def _clamp_names_to_expected_count(
    names: list[str],
    *,
    expected_count: int,
    stats: dict[str, dict[str, float | int | str]],
    cfg: dict,
) -> list[str]:
    expected = max(1, int(expected_count))
    deduped = _dedupe_names_in_order(names)
    if len(deduped) <= expected:
        return deduped

    ranked_keys = sorted(
        stats.keys(),
        key=lambda key: (
            -_candidate_bucket_score(stats.get(key, {}), cfg),
            _name_display_quality(str(stats.get(key, {}).get("display", ""))),
        ),
    )
    rank_index = {key: idx for idx, key in enumerate(ranked_keys)}
    large_rank = len(ranked_keys) + 1000

    ranked_names = sorted(
        list(enumerate(deduped)),
        key=lambda item: (
            rank_index.get(_simple_name_key(item[1]), large_rank),
            item[0],
        ),
    )
    keep_keys: set[str] = set()
    for _idx, name in ranked_names:
        key = _simple_name_key(name)
        if not key or key in keep_keys:
            continue
        keep_keys.add(key)
        if len(keep_keys) >= expected:
            break
    clamped = [name for name in deduped if _simple_name_key(name) in keep_keys]
    return clamped[:expected]


def _refill_names_to_target(
    names: list[str],
    *,
    refill_target: int,
    candidate_stats: dict[str, dict[str, float | int | str]],
    cfg: dict,
    trace_entries: list[dict] | None,
    row_preferred: bool,
) -> list[str]:
    return _ocr_ordering_utils.refill_names_to_target(
        names,
        refill_target=refill_target,
        candidate_stats=candidate_stats,
        cfg=cfg,
        trace_entries=trace_entries,
        row_preferred=row_preferred,
        dedupe_names_in_order_fn=_dedupe_names_in_order,
        candidate_bucket_score_fn=_candidate_bucket_score,
        name_display_quality_fn=_name_display_quality,
        simple_name_key_fn=_simple_name_key,
        order_names_by_line_trace_fn=_order_names_by_line_trace,
    )


def _order_names_by_line_trace(
    names: list[str],
    trace_entries: list[dict] | None,
    *,
    row_preferred: bool = False,
) -> list[str]:
    return _ocr_ordering_utils.order_names_by_line_trace(
        names,
        trace_entries,
        row_preferred=row_preferred,
        dedupe_names_in_order_fn=_dedupe_names_in_order,
        simple_name_key_fn=_simple_name_key,
        name_similarity_fn=_name_similarity,
        common_prefix_len_fn=_common_prefix_len,
    )


def _collapse_names_by_trace_slots(
    names: list[str],
    *,
    trace_entries: list[dict] | None,
    row_preferred: bool,
    candidate_stats: dict[str, dict[str, float | int | str]],
    cfg: dict,
) -> list[str]:
    return _ocr_ordering_utils.collapse_slot_duplicates(
        names,
        trace_entries=trace_entries,
        row_preferred=row_preferred,
        candidate_stats=candidate_stats,
        cfg=cfg,
        dedupe_names_in_order_fn=_dedupe_names_in_order,
        simple_name_key_fn=_simple_name_key,
        name_similarity_fn=_name_similarity,
        common_prefix_len_fn=_common_prefix_len,
        candidate_bucket_score_fn=_candidate_bucket_score,
        name_display_quality_fn=_name_display_quality,
    )


def _order_names_by_seed_sequence(
    names: list[str],
    seed_names: list[str],
) -> list[str]:
    deduped = _dedupe_names_in_order(names)
    if not deduped:
        return []
    if not seed_names:
        return deduped

    key_to_name: dict[str, str] = {}
    for name in deduped:
        key = _simple_name_key(name)
        if not key or key in key_to_name:
            continue
        key_to_name[key] = name

    ordered: list[str] = []
    used: set[str] = set()
    for raw_seed in list(seed_names or []):
        key = _simple_name_key(raw_seed)
        if not key or key in used:
            continue
        resolved = key_to_name.get(key)
        if not resolved:
            continue
        used.add(key)
        ordered.append(resolved)
    if not ordered:
        return deduped

    # Keep names that are not covered by seed keys at their original indices.
    # Only remap positions already occupied by known seed keys.
    replacement_keys = [_simple_name_key(name) for name in ordered if _simple_name_key(name)]
    known_set = set(replacement_keys)
    replacement_idx = 0
    remapped: list[str] = []
    for name in deduped:
        key = _simple_name_key(name)
        if key and key in known_set and replacement_idx < len(replacement_keys):
            replacement_key = replacement_keys[replacement_idx]
            replacement_idx += 1
            replacement_name = key_to_name.get(replacement_key)
            if replacement_name:
                remapped.append(replacement_name)
                continue
        remapped.append(name)
    return _dedupe_names_in_order(remapped)


def _reconcile_row_overflow_with_primary_slots(
    names: list[str],
    *,
    trace_entries: list[dict] | None,
    primary_names: list[str],
    candidate_stats: dict[str, dict[str, float | int | str]],
    cfg: dict,
    stable_primary_rows: int,
) -> list[str]:
    deduped = _dedupe_names_in_order(names)
    if len(deduped) <= 1:
        return deduped
    if not trace_entries:
        return deduped

    stable_rows = max(0, int(stable_primary_rows or 0))
    if stable_rows < 3:
        return deduped

    try:
        context = _ocr_ordering_utils._build_trace_order_context(
            trace_entries=trace_entries,
            row_preferred=False,
            simple_name_key_fn=_simple_name_key,
            name_similarity_fn=_name_similarity,
            common_prefix_len_fn=_common_prefix_len,
        )
    except Exception:
        return deduped

    effective_position = dict(context.get("effective_position") or {})
    if not effective_position:
        return deduped

    primary_name_by_key: dict[str, str] = {}
    for raw_name in list(primary_names or []):
        name = str(raw_name or "").strip()
        key = _simple_name_key(name)
        if not key or key in primary_name_by_key:
            continue
        primary_name_by_key[key] = name

    primary_slot_keys: dict[int, list[str]] = {}
    for entry in list(trace_entries or []):
        if str(entry.get("pass", "") or "").strip().casefold() != "primary":
            continue
        if not (
            bool(entry.get("support_incremented", False))
            or bool(entry.get("occurrence_incremented", False))
        ):
            continue
        key = _simple_name_key(str(entry.get("selected_key", "") or ""))
        if not key:
            continue
        try:
            slot_idx = int(entry.get("line_index", 0) or 0)
        except Exception:
            slot_idx = 0
        if slot_idx <= 0:
            pos = effective_position.get(key)
            if pos:
                slot_idx = int(pos[1])
        if slot_idx <= 0:
            continue
        slot_bucket = primary_slot_keys.setdefault(int(slot_idx), [])
        if key not in slot_bucket:
            slot_bucket.append(key)

    if not primary_slot_keys:
        for key in list(primary_name_by_key.keys()):
            pos = effective_position.get(key)
            if not pos:
                continue
            slot_idx = int(pos[1])
            if slot_idx <= 0:
                continue
            slot_bucket = primary_slot_keys.setdefault(int(slot_idx), [])
            if key not in slot_bucket:
                slot_bucket.append(key)

    if not primary_slot_keys:
        return deduped

    primary_slots = sorted(primary_slot_keys.keys())
    if len(primary_slots) < max(3, stable_rows - 1):
        return deduped
    primary_max_slot = max(primary_slots)

    current_records: list[tuple[int, str, str, int]] = []
    for idx, raw_name in enumerate(deduped):
        name = str(raw_name or "").strip()
        key = _simple_name_key(name)
        pos = effective_position.get(key) if key else None
        slot_idx = int(pos[1]) if pos else 0
        current_records.append((idx, name, key, slot_idx))

    covered_primary_slots = {
        int(slot_idx)
        for _idx, _name, _key, slot_idx in current_records
        if int(slot_idx) in primary_slot_keys
    }
    missing_primary_slots = [
        int(slot_idx)
        for slot_idx in primary_slots
        if int(slot_idx) not in covered_primary_slots
    ]
    if not missing_primary_slots:
        return deduped

    overflow_indices = [
        int(idx)
        for idx, _name, _key, slot_idx in current_records
        if int(slot_idx) > int(primary_max_slot)
    ]
    if not overflow_indices:
        return deduped

    def _slot_key_score(key: str) -> tuple[float, int, int, int]:
        bucket = candidate_stats.get(str(key or ""), {}) if candidate_stats else {}
        display = str(bucket.get("display", "") or "").strip() or primary_name_by_key.get(str(key or ""), "")
        quality = _name_display_quality(display)
        return (
            float(_candidate_bucket_score(bucket, cfg)),
            int(bucket.get("support", 0)),
            int(bucket.get("occurrences", 0)),
            -int(quality[0]),
        )

    current_keys = {
        key
        for _idx, _name, key, _slot_idx in current_records
        if str(key or "").strip()
    }

    replacement_names: list[str] = []
    for slot_idx in missing_primary_slots:
        slot_candidates = list(primary_slot_keys.get(int(slot_idx), []))
        if not slot_candidates:
            continue
        best_key = max(slot_candidates, key=_slot_key_score)
        if best_key in current_keys:
            continue
        bucket = candidate_stats.get(str(best_key or ""), {}) if candidate_stats else {}
        display = str(bucket.get("display", "") or "").strip() or primary_name_by_key.get(best_key, "")
        if not display:
            continue
        current_keys.add(best_key)
        replacement_names.append(display)

    if not replacement_names:
        return deduped

    removable = sorted(overflow_indices, reverse=True)[: len(replacement_names)]
    if len(removable) < len(replacement_names):
        return deduped
    remove_idx_set = set(removable)

    reconciled = [
        name
        for idx, name, _key, _slot_idx in current_records
        if idx not in remove_idx_set
    ]
    reconciled.extend(replacement_names)
    reconciled = _order_names_by_line_trace(
        reconciled,
        trace_entries,
        row_preferred=False,
    )
    reconciled = _collapse_names_by_trace_slots(
        reconciled,
        trace_entries=trace_entries,
        row_preferred=False,
        candidate_stats=candidate_stats,
        cfg=cfg,
    )
    if not reconciled:
        return deduped

    reconciled_covered_slots: set[int] = set()
    for raw_name in list(reconciled or []):
        key = _simple_name_key(raw_name)
        pos = effective_position.get(key)
        if not pos:
            continue
        slot_idx = int(pos[1])
        if slot_idx in primary_slot_keys:
            reconciled_covered_slots.add(int(slot_idx))
    if len(reconciled_covered_slots) <= len(covered_primary_slots):
        return deduped

    return reconciled


def _build_ocr_debug_report(
    *,
    cfg: dict,
    parse_ctx: _OCRLineParseContext,
    primary_runs: list[dict],
    retry_runs: list[dict],
    row_runs: list[dict],
    primary_names: list[str],
    retry_names: list[str],
    row_names: list[str],
    final_names: list[str],
    merged_text: str,
    errors: list[str],
    line_map_trace: list[dict] | None = None,
) -> str:
    return _ocr_debug_utils._build_ocr_debug_report(
        cfg=cfg,
        parse_ctx=parse_ctx,
        primary_runs=primary_runs,
        retry_runs=retry_runs,
        row_runs=row_runs,
        primary_names=primary_names,
        retry_names=retry_names,
        row_names=row_names,
        final_names=final_names,
        merged_text=merged_text,
        errors=errors,
        line_map_trace=list(line_map_trace or []),
        extract_line_debug_for_text_fn=_extract_line_debug_for_text,
        truncate_report_text_fn=_truncate_report_text,
    )


_should_run_recall_retry = _ocr_postprocess_utils._should_run_recall_retry
_is_low_count_candidate_set = _ocr_postprocess_utils._is_low_count_candidate_set
_append_unique_ints = _ocr_postprocess_utils._append_unique_ints
_build_recall_retry_cfg = _ocr_postprocess_utils._build_recall_retry_cfg
_build_relaxed_support_cfg = _ocr_postprocess_utils._build_relaxed_support_cfg
_build_strict_extraction_cfg = _ocr_postprocess_utils._build_strict_extraction_cfg
_score_candidate_set = _ocr_postprocess_utils._score_candidate_set
_prefer_retry_candidates = _ocr_postprocess_utils._prefer_retry_candidates


@dataclass
class _OCRPassFlowState:
    names: list[str]
    merged_texts: list[str]
    errors: list[str]
    retry_names: list[str]
    retry_runs: list[dict]
    row_names: list[str]
    row_runs: list[dict]
    row_preferred: bool


def _replace_names_if_better(
    current: list[str],
    proposed: list[str],
    *,
    cfg: dict,
) -> list[str]:
    if _score_candidate_set(proposed, cfg) > _score_candidate_set(current, cfg):
        return list(proposed)
    return list(current)


def _order_and_collapse_by_trace(
    names: list[str],
    *,
    trace_entries: list[dict] | None,
    row_preferred: bool,
    candidate_stats: dict[str, dict[str, float | int | str]],
    cfg: dict,
) -> list[str]:
    ordered = _order_names_by_line_trace(
        names,
        trace_entries,
        row_preferred=row_preferred,
    )
    return _collapse_names_by_trace_slots(
        ordered,
        trace_entries=trace_entries,
        row_preferred=row_preferred,
        candidate_stats=candidate_stats,
        cfg=cfg,
    )


def _primary_order_inversions(values: list[str], trace_entries: list[dict] | None) -> int | None:
    primary_line_index_by_key: dict[str, int] = {}
    for entry in list(trace_entries or []):
        if str(entry.get("pass", "") or "").strip().casefold() != "primary":
            continue
        if not (
            bool(entry.get("support_incremented", False))
            or bool(entry.get("occurrence_incremented", False))
        ):
            continue
        key = _simple_name_key(str(entry.get("selected_key", "") or ""))
        if not key:
            continue
        try:
            line_index = int(entry.get("line_index", 0) or 0)
        except Exception:
            line_index = 0
        if line_index <= 0:
            continue
        current = primary_line_index_by_key.get(key)
        if current is None or line_index < current:
            primary_line_index_by_key[key] = line_index
    if len(primary_line_index_by_key) < 2:
        return None

    positions: list[int] = []
    for name in list(values or []):
        key = _simple_name_key(name)
        if not key:
            continue
        pos = primary_line_index_by_key.get(key)
        if pos is None:
            continue
        positions.append(int(pos))
    if len(positions) < 2:
        return None

    inversions = 0
    for left_idx, left in enumerate(positions):
        for right in positions[left_idx + 1 :]:
            if left > right:
                inversions += 1
    return int(inversions)


def _collect_optional_pass_flow(
    *,
    paths: list[Path],
    ocr_cmd: str,
    runtime_cfg: dict,
    ocr_import,
    line_parse_ctx: _OCRLineParseContext,
    primary_names: list[str],
    primary_texts: list[str],
    primary_errors: list[str],
) -> _OCRPassFlowState:
    state = _OCRPassFlowState(
        names=list(primary_names),
        merged_texts=list(primary_texts),
        errors=list(primary_errors),
        retry_names=[],
        retry_runs=[],
        row_names=[],
        row_runs=[],
        row_preferred=False,
    )

    if _should_run_recall_retry(runtime_cfg, primary_names):
        retry_cfg = _build_recall_retry_cfg(runtime_cfg)
        retry_texts, retry_errors, retry_runs = _run_ocr_pass(
            paths,
            pass_label="retry",
            cfg=retry_cfg,
            max_variants_key="recall_retry_max_variants",
            ocr_cmd=ocr_cmd,
        )
        state.merged_texts.extend(retry_texts)
        state.errors.extend(retry_errors)
        state.retry_runs = list(retry_runs)
        state.retry_names = _extract_names_from_texts(ocr_import, retry_texts, runtime_cfg)
        if _prefer_retry_candidates(primary_names, state.retry_names, runtime_cfg):
            state.names = list(state.retry_names)

    if len(state.names) > max(0, int(runtime_cfg.get("recall_retry_max_candidates", 7))):
        strict_cfg = _build_strict_extraction_cfg(runtime_cfg)
        strict_names = _extract_names_from_texts(ocr_import, state.merged_texts, strict_cfg)
        state.names = _replace_names_if_better(state.names, strict_names, cfg=runtime_cfg)

    if bool(runtime_cfg.get("recall_relax_support_on_low_count", True)) and _is_low_count_candidate_set(runtime_cfg, state.names):
        relaxed_cfg = _build_relaxed_support_cfg(runtime_cfg)
        relaxed_names = _extract_names_from_texts(ocr_import, state.merged_texts, relaxed_cfg)
        state.names = _replace_names_if_better(state.names, relaxed_names, cfg=runtime_cfg)

    row_cfg = dict(runtime_cfg)
    row_cfg["primary_candidate_count"] = len(list(primary_names or []))
    if _should_run_row_pass(row_cfg, state.names):
        row_names, row_texts, row_runs = _run_row_segmentation_pass(
            paths,
            cfg=row_cfg,
            parse_ctx=line_parse_ctx,
        )
        state.row_names = list(row_names)
        state.row_runs = list(row_runs)
        state.merged_texts.extend(list(row_texts))
        if _prefer_row_candidates(state.names, state.row_names, row_cfg):
            state.names = list(state.row_names)
            state.row_preferred = True

    return state


def _build_effective_cfg_and_seed_names(
    *,
    runtime_cfg: dict,
    names: list[str],
    row_names: list[str],
    row_preferred: bool,
) -> tuple[dict, list[str]]:
    working_names = list(names)
    adaptive_expected = max(
        1,
        int(runtime_cfg.get("expected_candidates", 5)),
        len(_dedupe_names_in_order(working_names)),
        (len(_dedupe_names_in_order(row_names)) if row_preferred else 0),
    )
    cfg_effective = dict(runtime_cfg)
    cfg_effective["expected_candidates"] = adaptive_expected

    if row_preferred:
        expected = max(1, int(cfg_effective.get("expected_candidates", 5)))
        row_deduped = _dedupe_names_in_order(row_names)
        row_trust_floor = max(3, expected - 1)
        if len(row_deduped) >= row_trust_floor:
            working_names = row_deduped

    return cfg_effective, working_names


def _build_names_from_candidate_runs(
    *,
    cfg_effective: dict,
    runtime_cfg: dict,
    names: list[str],
    primary_names: list[str],
    retry_names: list[str],
    row_names: list[str],
    row_preferred: bool,
    primary_runs: list[dict],
    retry_runs: list[dict],
    row_runs: list[dict],
    line_parse_ctx: _OCRLineParseContext,
    line_map_trace_all: list[dict],
    debug_requested: bool,
    trace_enabled: bool,
    precount_max_rows: int | None,
    precount_refill_target: int | None,
) -> tuple[list[str], dict[str, dict[str, float | int | str]]]:
    def _normalize_names(values: list[str]) -> list[str]:
        return _order_and_collapse_by_trace(
            values,
            trace_entries=line_map_trace_all,
            row_preferred=row_preferred,
            candidate_stats=candidate_stats,
            cfg=cfg_effective,
        )

    all_runs = list(primary_runs) + list(retry_runs) + list(row_runs)
    candidate_stats = _candidate_stats_from_runs(
        all_runs,
        line_parse_ctx,
        trace_entries=line_map_trace_all,
        include_debug_meta=bool(debug_requested and trace_enabled),
    )
    candidate_stats = _merge_prefix_candidate_stats(candidate_stats)
    candidate_stats = _merge_near_duplicate_candidate_stats(candidate_stats, runtime_cfg)

    effective_precount_max_rows = int(precount_max_rows or 0) if (precount_max_rows is not None) else 0
    if effective_precount_max_rows > 0:
        extra_allowance = _precount_extra_allowance_from_stats(
            base_max_rows=effective_precount_max_rows,
            stats=candidate_stats,
            cfg=cfg_effective,
        )
        effective_precount_max_rows += int(extra_allowance)
    cfg_effective["precount_rows_max_effective"] = int(effective_precount_max_rows or 0)

    names = _build_final_names_from_runs(
        cfg=cfg_effective,
        stats=candidate_stats,
        preferred_names=names,
        primary_names=primary_names,
        retry_names=retry_names,
        row_names=row_names,
        row_preferred=row_preferred,
    )
    names = _filter_low_confidence_candidates(
        names,
        cfg_effective,
        candidate_stats,
    )
    names = _normalize_names(names)

    expected = max(1, int(cfg_effective.get("expected_candidates", 5)))
    refill_target = expected
    if precount_refill_target is not None and precount_refill_target > 0:
        refill_target = min(refill_target, int(precount_refill_target))

    if (
        bool(cfg_effective.get("name_confidence_filter_noisy_only", True))
        and (not row_preferred)
        and len(names) < refill_target
        and candidate_stats
    ):
        names = _refill_names_to_target(
            names,
            refill_target=refill_target,
            candidate_stats=candidate_stats,
            cfg=cfg_effective,
            trace_entries=line_map_trace_all,
            row_preferred=row_preferred,
        )

    if effective_precount_max_rows > 0 and len(names) > int(effective_precount_max_rows):
        names = _clamp_names_to_expected_count(
            names,
            expected_count=int(effective_precount_max_rows),
            stats=candidate_stats,
            cfg=cfg_effective,
        )

    names = _normalize_names(names)
    return names, candidate_stats


def _stabilize_row_preferred_names(
    names: list[str],
    *,
    row_preferred: bool,
    row_names: list[str],
    trace_entries: list[dict] | None,
    candidate_stats: dict[str, dict[str, float | int | str]],
    cfg_effective: dict,
    primary_names: list[str],
) -> list[str]:
    if not row_preferred:
        return list(names or [])

    names = _order_names_by_seed_sequence(list(names or []), row_names)

    # Seed ordering can preserve row-pass noise slot offsets in some cases.
    # Compute a primary-biased fallback and only apply it when it clearly
    # improves primary line monotonicity.
    stabilized_primary = _order_and_collapse_by_trace(
        names,
        trace_entries=trace_entries,
        row_preferred=False,
        candidate_stats=candidate_stats,
        cfg=cfg_effective,
    )
    current_inv = _primary_order_inversions(names, trace_entries)
    fallback_inv = _primary_order_inversions(stabilized_primary, trace_entries)
    if (
        fallback_inv is not None
        and (current_inv is None or fallback_inv < current_inv)
    ):
        names = stabilized_primary

    names = _reconcile_row_overflow_with_primary_slots(
        names,
        trace_entries=trace_entries,
        primary_names=primary_names,
        candidate_stats=candidate_stats,
        cfg=cfg_effective,
        stable_primary_rows=int(cfg_effective.get("precount_rows_primary_stable", 0)),
    )
    return names


def _extract_names_from_ocr_files(
    paths: list[Path],
    *,
    ocr_cmd: str = "",
    cfg: dict,
) -> tuple[list[str], str, str | None]:
    ocr_import = _ocr_import_module()
    visual_precount_rows = _estimate_expected_rows_from_paths(paths, cfg)
    runtime_cfg = dict(cfg)
    runtime_cfg["precount_rows_visual"] = int(visual_precount_rows or 0)
    runtime_cfg["precount_rows"] = int(visual_precount_rows or 0)
    runtime_cfg["precount_rows_primary_stable"] = 0
    line_parse_ctx = _OCRLineParseContext(ocr_import, runtime_cfg)
    debug_requested = (
        bool(runtime_cfg.get("debug_show_report", False))
        or bool(runtime_cfg.get("debug_include_report_text", False))
        or bool(runtime_cfg.get("debug_log_to_file", False))
    )
    trace_enabled = bool(runtime_cfg.get("debug_trace_line_mapping", True))
    line_map_trace_all: list[dict] = []
    primary_texts, primary_errors, primary_runs = _run_ocr_pass(
        paths,
        pass_label="primary",
        cfg=runtime_cfg,
        max_variants_key="max_variants",
        ocr_cmd=ocr_cmd,
    )
    stable_primary_rows = _stable_primary_line_count(primary_runs)
    primary_avg_conf = _primary_avg_line_confidence(primary_runs)
    effective_precount_rows = _resolve_effective_precount_rows(
        visual_precount_rows,
        primary_runs,
    )
    precount_min_rows, precount_max_rows, precount_refill_target = _resolve_precount_row_bounds(
        effective_precount_rows=effective_precount_rows,
        stable_primary_rows=stable_primary_rows,
    )
    runtime_cfg["precount_rows_primary_stable"] = int(stable_primary_rows or 0)
    runtime_cfg["primary_line_avg_conf"] = float(primary_avg_conf or -1.0)
    runtime_cfg["precount_rows"] = int(effective_precount_rows or 0)
    runtime_cfg["precount_rows_min"] = int(precount_min_rows or 0)
    runtime_cfg["precount_rows_max"] = int(precount_max_rows or 0)
    runtime_cfg["precount_rows_refill_target"] = int(precount_refill_target or 0)
    if effective_precount_rows is not None and int(effective_precount_rows) > 0:
        runtime_cfg["expected_candidates"] = max(
            1,
            int(runtime_cfg.get("expected_candidates", 5)),
            int(effective_precount_rows),
        )

    primary_names = _extract_names_from_texts(ocr_import, primary_texts, runtime_cfg)
    flow_state = _collect_optional_pass_flow(
        paths=paths,
        ocr_cmd=ocr_cmd,
        runtime_cfg=runtime_cfg,
        ocr_import=ocr_import,
        line_parse_ctx=line_parse_ctx,
        primary_names=primary_names,
        primary_texts=primary_texts,
        primary_errors=primary_errors,
    )

    cfg_effective, seed_names = _build_effective_cfg_and_seed_names(
        runtime_cfg=runtime_cfg,
        names=flow_state.names,
        row_names=flow_state.row_names,
        row_preferred=flow_state.row_preferred,
    )
    names, candidate_stats = _build_names_from_candidate_runs(
        cfg_effective=cfg_effective,
        runtime_cfg=runtime_cfg,
        names=seed_names,
        primary_names=primary_names,
        retry_names=flow_state.retry_names,
        row_names=flow_state.row_names,
        row_preferred=flow_state.row_preferred,
        primary_runs=primary_runs,
        retry_runs=flow_state.retry_runs,
        row_runs=flow_state.row_runs,
        line_parse_ctx=line_parse_ctx,
        line_map_trace_all=line_map_trace_all,
        debug_requested=debug_requested,
        trace_enabled=trace_enabled,
        precount_max_rows=precount_max_rows,
        precount_refill_target=precount_refill_target,
    )
    names = _stabilize_row_preferred_names(
        names,
        row_preferred=flow_state.row_preferred,
        row_names=flow_state.row_names,
        trace_entries=line_map_trace_all,
        candidate_stats=candidate_stats,
        cfg_effective=cfg_effective,
        primary_names=primary_names,
    )

    names = _expand_config_identifier_prefixes(names)

    merged_text = _merge_ocr_texts_unique_lines(flow_state.merged_texts)
    if debug_requested:
        debug_report = _build_ocr_debug_report(
            cfg=cfg_effective,
            parse_ctx=line_parse_ctx,
            primary_runs=primary_runs,
            retry_runs=flow_state.retry_runs,
            row_runs=flow_state.row_runs,
            primary_names=primary_names,
            retry_names=flow_state.retry_names,
            row_names=flow_state.row_names,
            final_names=names,
            merged_text=merged_text,
            errors=flow_state.errors,
            line_map_trace=(line_map_trace_all if trace_enabled else []),
        )
    else:
        debug_report = ""
    raw_text = debug_report if bool(cfg.get("debug_include_report_text", False)) else merged_text
    error_text = "; ".join(flow_state.errors) if flow_state.errors else None
    return names, raw_text, error_text


class _OCRExtractWorker(_ocr_async_worker_utils._OCRExtractWorker):
    def __init__(self, paths: list[Path], cfg: dict):
        super().__init__(paths, cfg, extract_names_fn=_extract_names_from_ocr_files)


_OCRResultRelay = _ocr_async_worker_utils._OCRResultRelay
ocr_preview_text = _ocr_debug_utils.ocr_preview_text
_append_ocr_debug_log = _ocr_debug_utils._append_ocr_debug_log
_show_ocr_debug_report = _ocr_debug_utils._show_ocr_debug_report
_handle_ocr_selection_error = _ocr_debug_utils._handle_ocr_selection_error


def _start_ocr_async_import(
    mw,
    *,
    role: str,
    selected_pixmap: QtGui.QPixmap,
    busy_overlay_shown: bool,
) -> None:
    temp_paths: list[Path] = []
    async_started = False
    try:
        runtime_cfg = _ocr_runtime_cfg_snapshot(mw)
        ocr_import = _ocr_import_module()
        easyocr_kwargs = _easyocr_resolution_kwargs(runtime_cfg)
        availability_fn = getattr(ocr_import, "easyocr_available", None)
        if callable(availability_fn):
            ready = bool(availability_fn(**easyocr_kwargs))
        else:
            ready = False
        if not ready:
            diag_fn = getattr(ocr_import, "easyocr_resolution_diagnostics", None)
            if callable(diag_fn):
                diag = str(diag_fn(**easyocr_kwargs))
            else:
                diag = "easyocr-diagnostics-unavailable"
            QtWidgets.QMessageBox.warning(
                mw,
                i18n.t("ocr.error_title"),
                i18n.t(
                    "ocr.error_run_failed",
                    reason="easyocr-not-ready (missing language models / downloads disabled?)",
                )
                + "\n\n"
                + diag,
            )
            _hide_ocr_busy_overlay(mw, active=busy_overlay_shown)
            return

        temp_paths, prep_errors = _prepare_ocr_variant_files(mw, selected_pixmap, runtime_cfg)
        if not temp_paths:
            reason = "; ".join(prep_errors) if prep_errors else "image-save-failed"
            QtWidgets.QMessageBox.warning(
                mw,
                i18n.t("ocr.error_title"),
                i18n.t("ocr.error_run_failed", reason=reason),
            )
            _hide_ocr_busy_overlay(mw, active=busy_overlay_shown)
            return

        thread = QtCore.QThread(mw)
        worker = _OCRExtractWorker(temp_paths, runtime_cfg)
        worker.moveToThread(thread)
        relay = _OCRResultRelay(mw)
        job = {
            "thread": thread,
            "worker": worker,
            "relay": relay,
            "paths": list(temp_paths),
            "role": role,
        }
        setattr(mw, "_ocr_async_job", job)

        def _finalize_job() -> None:
            current = getattr(mw, "_ocr_async_job", None)
            if current is not job:
                return
            setattr(mw, "_ocr_async_job", None)
            _cleanup_temp_paths(list(job.get("paths") or []))
            _hide_ocr_busy_overlay(mw, active=busy_overlay_shown)
            _restore_override_cursor()
            try:
                if thread.isRunning() and QtCore.QThread.currentThread() is not thread:
                    thread.quit()
            except Exception:
                pass
            mw._update_role_ocr_buttons_enabled()
            _schedule_ocr_cache_release(mw)

        def _handle_result(names: list[str], raw_text: str, ocr_error: str | None) -> None:
            _finalize_job()
            debug_mode = (
                bool(runtime_cfg.get("debug_show_report", False))
                or bool(runtime_cfg.get("debug_include_report_text", False))
                or bool(runtime_cfg.get("debug_log_to_file", False))
            )
            if debug_mode:
                log_path = _append_ocr_debug_log(
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
                    _show_ocr_debug_report(
                        mw,
                        role=role,
                        names=names,
                        raw_text=raw_text,
                        ocr_error=ocr_error,
                    )
                except Exception:
                    pass
            if not names:
                message = i18n.t("ocr.result_no_names")
                preview = ocr_preview_text(raw_text)
                if preview:
                    message += "\n\n" + i18n.t("ocr.result_raw_preview", preview=preview)
                elif ocr_error:
                    message += "\n\n" + i18n.t("ocr.error_run_failed", reason=ocr_error)
                QtWidgets.QMessageBox.information(
                    mw,
                    i18n.t("ocr.result_title"),
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
                QtWidgets.QMessageBox.information(
                    mw,
                    i18n.t("ocr.result_title"),
                    i18n.t("ocr.result_no_names"),
                )
                return
            if mw._request_ocr_import_selection(role, candidate_names):
                return

            # Fallback if overlay is not available.
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
            QtWidgets.QMessageBox.warning(
                mw,
                i18n.t("ocr.error_title"),
                i18n.t("ocr.error_run_failed", reason=str(reason or "worker-error")),
            )

        # Always deliver worker results back to the GUI thread.
        worker.finished.connect(relay.forward_result, QtCore.Qt.QueuedConnection)
        worker.failed.connect(relay.forward_error, QtCore.Qt.QueuedConnection)
        relay.result.connect(_handle_result)
        relay.error.connect(_handle_worker_error)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.started.connect(worker.run)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            thread.start(QtCore.QThread.LowPriority)
        except Exception:
            thread.start()
        async_started = True
        return
    except Exception as exc:
        _cleanup_temp_paths(temp_paths)
        _hide_ocr_busy_overlay(mw, active=busy_overlay_shown)
        _restore_override_cursor()
        setattr(mw, "_ocr_async_job", None)
        QtWidgets.QMessageBox.warning(
            mw,
            i18n.t("ocr.error_title"),
            i18n.t("ocr.error_unexpected", reason=repr(exc)),
        )
        mw._update_role_ocr_buttons_enabled()
        return
    finally:
        if not async_started and not getattr(mw, "_ocr_async_job", None):
            _schedule_ocr_cache_release(mw)


def on_role_ocr_import_clicked(mw, role_key: str) -> None:
    role = str(role_key or "").strip().casefold()
    if not mw._role_ocr_import_available(role):
        return
    if getattr(mw, "_ocr_async_job", None):
        return
    _mark_ocr_runtime_activated(mw)
    _cancel_ocr_cache_release(mw)
    mw._update_role_ocr_button_enabled(role)
    btn = mw._role_ocr_buttons.get(role)
    if btn is not None:
        btn.setEnabled(False)

    async_dispatched = False
    try:
        selected_pixmap, select_error = capture_region_for_ocr(mw)
        if selected_pixmap is None:
            _handle_ocr_selection_error(mw, select_error)
            mw._update_role_ocr_buttons_enabled()
            return

        busy_overlay_shown = _show_ocr_busy_overlay(mw, role)
        # Defer OCR setup to the next event-loop tick so the status overlay can
        # be painted before any heavy OCR pre-processing starts.
        QtCore.QTimer.singleShot(
            0,
            lambda role=role, pixmap=QtGui.QPixmap(selected_pixmap), shown=busy_overlay_shown: _start_ocr_async_import(
                mw,
                role=role,
                selected_pixmap=pixmap,
                busy_overlay_shown=shown,
            ),
        )
        async_dispatched = True
    except Exception as exc:
        _restore_override_cursor()
        setattr(mw, "_ocr_async_job", None)
        QtWidgets.QMessageBox.warning(
            mw,
            i18n.t("ocr.error_title"),
            i18n.t("ocr.error_unexpected", reason=repr(exc)),
        )
        mw._update_role_ocr_buttons_enabled()
    finally:
        if not async_dispatched and not getattr(mw, "_ocr_async_job", None):
            _schedule_ocr_cache_release(mw)
