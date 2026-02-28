from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
import sys
import tempfile
import time

from PySide6 import QtCore, QtGui, QtWidgets

import i18n
from utils import qt_runtime

try:
    from controller import ocr_import as _ocr_import
except Exception:
    from . import ocr_import as _ocr_import

try:
    from view import screen_region_selector as _screen_selector
except Exception:
    # Backward-compatibility for legacy typo-based import path.
    from view import screen_redion_selector as _screen_selector


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
        if not bool(mw._cfg("OCR_INCLUDE_LEFT_CROP_VARIANTS", True)):
            return None
        ratio = float(mw._cfg("OCR_NAME_COLUMN_CROP_RATIO", 0.62))
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
    scale_factor = max(1, int(mw._cfg("OCR_SCALE_FACTOR", 2)))
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
    psm_primary = int(mw._cfg("OCR_TESSERACT_PSM", 11))
    psm_fallback = int(mw._cfg("OCR_TESSERACT_FALLBACK_PSM", 6))
    psm_values = [psm_primary]
    if (not fast_mode) and psm_fallback not in psm_values:
        psm_values.append(psm_fallback)
    retry_extra_psm_values = _parse_psm_values(mw._cfg("OCR_TESSERACT_RETRY_EXTRA_PSMS", []))
    timeout_s = float(mw._cfg("OCR_TESSERACT_TIMEOUT_S", 8.0))
    if sys.platform == "win32":
        timeout_s = float(mw._cfg("OCR_TESSERACT_TIMEOUT_S_WINDOWS", timeout_s))
    retry_min_candidates = int(mw._cfg("OCR_RECALL_RETRY_MIN_CANDIDATES", 5))
    retry_max_variants = int(mw._cfg("OCR_RECALL_RETRY_MAX_VARIANTS", 2))
    if retry_max_variants < 0:
        retry_max_variants = 0
    row_pass_psm_values = _parse_psm_values(mw._cfg("OCR_ROW_PASS_PSMS", [7, 13, 6]))
    if not row_pass_psm_values:
        row_pass_psm_values = [7, 6, 13]
    debug_show_report = bool(mw._cfg("OCR_DEBUG_SHOW_REPORT", False))
    debug_include_report_text = bool(
        mw._cfg("OCR_DEBUG_INCLUDE_REPORT_TEXT", debug_show_report)
    )
    debug_log_to_file = bool(mw._cfg("OCR_DEBUG_LOG_TO_FILE", True))
    debug_line_analysis = bool(mw._cfg("OCR_DEBUG_LINE_ANALYSIS", True))
    if bool(mw._cfg("QUIET", False)):
        debug_show_report = False
        debug_include_report_text = False
        debug_log_to_file = False
        debug_line_analysis = False
    quiet_mode = bool(mw._cfg("QUIET", False))

    easyocr_lang = str(mw._cfg("OCR_EASYOCR_LANG", "en")).strip() or None
    selected_lang = easyocr_lang

    return {
        "engine": engine,
        "fast_mode": fast_mode,
        "max_variants": max_variants,
        "stop_after_variant_success": bool(mw._cfg("OCR_STOP_AFTER_FIRST_VARIANT_SUCCESS", True)),
        "psm_primary": psm_primary,
        "psm_fallback": psm_fallback,
        "psm_values": tuple(psm_values),
        "retry_extra_psm_values": tuple(retry_extra_psm_values),
        "lang": selected_lang,
        "easyocr_lang": easyocr_lang,
        "easyocr_model_dir": str(mw._cfg("OCR_EASYOCR_MODEL_DIR", "")).strip() or None,
        "easyocr_user_network_dir": str(mw._cfg("OCR_EASYOCR_USER_NETWORK_DIR", "")).strip() or None,
        "easyocr_gpu": _parse_easyocr_gpu_value(mw._cfg("OCR_EASYOCR_GPU", "auto")),
        "easyocr_download_enabled": bool(mw._cfg("OCR_EASYOCR_DOWNLOAD_ENABLED", False)),
        "quiet_mode": quiet_mode,
        "timeout_s": timeout_s,
        "debug_show_report": debug_show_report,
        "debug_include_report_text": debug_include_report_text,
        "debug_log_to_file": debug_log_to_file,
        "debug_report_max_chars": int(mw._cfg("OCR_DEBUG_REPORT_MAX_CHARS", 12000)),
        "debug_line_analysis": debug_line_analysis,
        "debug_line_max_entries_per_run": int(mw._cfg("OCR_DEBUG_LINE_MAX_ENTRIES_PER_RUN", 40)),
        "recall_retry_enabled": bool(mw._cfg("OCR_RECALL_RETRY_ENABLED", True)),
        "recall_retry_min_candidates": retry_min_candidates,
        "recall_retry_max_candidates": int(mw._cfg("OCR_RECALL_RETRY_MAX_CANDIDATES", 7)),
        "recall_retry_short_name_max_ratio": float(
            mw._cfg("OCR_RECALL_RETRY_SHORT_NAME_MAX_RATIO", 0.34)
        ),
        "recall_retry_max_variants": retry_max_variants,
        "recall_retry_use_fallback_psm": bool(
            mw._cfg("OCR_RECALL_RETRY_USE_FALLBACK_PSM", True)
        ),
        "recall_retry_timeout_scale": float(mw._cfg("OCR_RECALL_RETRY_TIMEOUT_SCALE", 1.35)),
        "recall_relax_support_on_low_count": bool(
            mw._cfg("OCR_RECALL_RELAX_SUPPORT_ON_LOW_COUNT", True)
        ),
        "expected_candidates": int(mw._cfg("OCR_EXPECTED_CANDIDATES", 5)),
        "row_pass_enabled": bool(mw._cfg("OCR_ROW_PASS_ENABLED", True)),
        "row_pass_always_run": bool(mw._cfg("OCR_ROW_PASS_ALWAYS_RUN", True)),
        "row_pass_min_candidates": int(mw._cfg("OCR_ROW_PASS_MIN_CANDIDATES", 5)),
        "row_pass_brightness_threshold": int(mw._cfg("OCR_ROW_PASS_BRIGHTNESS_THRESHOLD", 145)),
        "row_pass_min_pixels_ratio": float(mw._cfg("OCR_ROW_PASS_MIN_PIXELS_RATIO", 0.015)),
        "row_pass_merge_gap_px": int(mw._cfg("OCR_ROW_PASS_MERGE_GAP_PX", 2)),
        "row_pass_min_height_px": int(mw._cfg("OCR_ROW_PASS_MIN_HEIGHT_PX", 7)),
        "row_pass_max_rows": int(mw._cfg("OCR_ROW_PASS_MAX_ROWS", 12)),
        "row_pass_pad_px": int(mw._cfg("OCR_ROW_PASS_PAD_PX", 2)),
        "row_pass_name_x_ratio": float(mw._cfg("OCR_ROW_PASS_NAME_X_RATIO", 0.58)),
        "row_pass_projection_x_start_ratio": float(
            mw._cfg("OCR_ROW_PASS_PROJECTION_X_START_RATIO", 0.08)
        ),
        "row_pass_projection_x_end_ratio": float(
            mw._cfg("OCR_ROW_PASS_PROJECTION_X_END_RATIO", 0.92)
        ),
        "row_pass_projection_col_max_ratio": float(
            mw._cfg("OCR_ROW_PASS_PROJECTION_COL_MAX_RATIO", 0.84)
        ),
        "row_pass_scale_factor": int(mw._cfg("OCR_ROW_PASS_SCALE_FACTOR", 4)),
        "row_pass_include_mono": bool(mw._cfg("OCR_ROW_PASS_INCLUDE_MONO", True)),
        "row_pass_timeout_scale": float(mw._cfg("OCR_ROW_PASS_TIMEOUT_SCALE", 0.55)),
        "row_pass_psm_values": tuple(row_pass_psm_values),
        "name_min_chars": int(mw._cfg("OCR_NAME_MIN_CHARS", 2)),
        "name_max_chars": int(mw._cfg("OCR_NAME_MAX_CHARS", 24)),
        "name_max_words": int(mw._cfg("OCR_NAME_MAX_WORDS", 2)),
        "name_max_digit_ratio": float(mw._cfg("OCR_NAME_MAX_DIGIT_RATIO", 0.45)),
        "name_special_char_constraint": bool(
            mw._cfg("OCR_NAME_SPECIAL_CHAR_CONSTRAINT", False)
        ),
        "name_min_support": int(mw._cfg("OCR_NAME_MIN_SUPPORT", 1)),
        "name_min_confidence": float(mw._cfg("OCR_NAME_MIN_CONFIDENCE", 43.0)),
        "name_low_confidence_min_support": int(
            mw._cfg("OCR_NAME_LOW_CONFIDENCE_MIN_SUPPORT", 2)
        ),
        "name_confidence_filter_noisy_only": bool(
            mw._cfg("OCR_NAME_CONFIDENCE_FILTER_NOISY_ONLY", True)
        ),
        "name_high_count_threshold": int(mw._cfg("OCR_NAME_HIGH_COUNT_THRESHOLD", 8)),
        "name_high_count_min_support": int(mw._cfg("OCR_NAME_HIGH_COUNT_MIN_SUPPORT", 2)),
        "name_max_candidates": int(mw._cfg("OCR_NAME_MAX_CANDIDATES", 12)),
        "name_near_dup_min_chars": int(mw._cfg("OCR_NAME_NEAR_DUP_MIN_CHARS", 8)),
        "name_near_dup_max_len_delta": int(mw._cfg("OCR_NAME_NEAR_DUP_MAX_LEN_DELTA", 1)),
        "name_near_dup_similarity": float(mw._cfg("OCR_NAME_NEAR_DUP_SIMILARITY", 0.90)),
        "name_near_dup_tail_min_chars": int(mw._cfg("OCR_NAME_NEAR_DUP_TAIL_MIN_CHARS", 3)),
        "name_near_dup_tail_head_similarity": float(
            mw._cfg("OCR_NAME_NEAR_DUP_TAIL_HEAD_SIMILARITY", 0.70)
        ),
    }


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


def _simple_name_key(value: str) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


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


def _extract_names_from_texts(ocr_import, texts: list[str], cfg: dict) -> list[str]:
    return ocr_import.extract_candidate_names_multi(
        texts,
        min_chars=int(cfg.get("name_min_chars", 2)),
        max_chars=int(cfg.get("name_max_chars", 24)),
        max_words=int(cfg.get("name_max_words", 2)),
        max_digit_ratio=float(cfg.get("name_max_digit_ratio", 0.45)),
        enforce_special_char_constraint=bool(cfg.get("name_special_char_constraint", True)),
        min_support=int(cfg.get("name_min_support", 1)),
        high_count_threshold=int(cfg.get("name_high_count_threshold", 8)),
        high_count_min_support=int(cfg.get("name_high_count_min_support", 2)),
        max_candidates=int(cfg.get("name_max_candidates", 12)),
        near_dup_min_chars=int(cfg.get("name_near_dup_min_chars", 8)),
        near_dup_max_len_delta=int(cfg.get("name_near_dup_max_len_delta", 1)),
        near_dup_similarity=float(cfg.get("name_near_dup_similarity", 0.90)),
        near_dup_tail_min_chars=int(cfg.get("name_near_dup_tail_min_chars", 3)),
        near_dup_tail_head_similarity=float(cfg.get("name_near_dup_tail_head_similarity", 0.70)),
    )


def _run_ocr_pass(
    paths: list[Path],
    *,
    pass_label: str,
    cfg: dict,
    max_variants_key: str,
    ocr_cmd: str = "",
) -> tuple[list[str], list[str], list[dict]]:
    ocr_import = _ocr_import_module()
    selected_paths = _select_variant_paths(paths, cfg, max_variants_key=max_variants_key)
    if not selected_paths:
        return [], ["no-variant-paths"], []

    all_texts: list[str] = []
    errors: list[str] = []
    runs: list[dict] = []
    engine = str(cfg.get("engine", "easyocr")).strip().casefold() or "easyocr"
    fast_mode = bool(cfg.get("fast_mode", True))
    stop_after_variant_success = bool(cfg.get("stop_after_variant_success", True)) and fast_mode
    psm_values = tuple(cfg.get("psm_values", (6, 11)))
    lang = cfg.get("lang")
    timeout_s = float(cfg.get("timeout_s", 8.0))
    run_ocr_multi = getattr(ocr_import, "run_ocr_multi", None)
    run_tesseract_multi = getattr(ocr_import, "run_tesseract_multi", None)
    if not callable(run_ocr_multi) and not callable(run_tesseract_multi):
        return [], ["ocr-runner-unavailable"], []

    for image_path in selected_paths:
        if callable(run_ocr_multi):
            run_result = run_ocr_multi(
                image_path,
                engine=engine,
                cmd=str(ocr_cmd or ""),
                psm_values=psm_values,
                timeout_s=timeout_s,
                lang=lang,
                stop_on_first_success=stop_after_variant_success,
                easyocr_model_dir=cfg.get("easyocr_model_dir"),
                easyocr_user_network_dir=cfg.get("easyocr_user_network_dir"),
                easyocr_gpu=cfg.get("easyocr_gpu", "auto"),
                easyocr_download_enabled=bool(cfg.get("easyocr_download_enabled", False)),
                easyocr_quiet=bool(cfg.get("quiet_mode", False)),
            )
        else:
            # Backward compatibility for legacy test stubs / callers.
            run_result = run_tesseract_multi(
                image_path,
                cmd=str(ocr_cmd or "auto"),
                psm_values=psm_values,
                timeout_s=timeout_s,
                lang=lang,
                stop_on_first_success=stop_after_variant_success,
            )
        line_entries: list[dict] = []
        for line_entry in tuple(getattr(run_result, "lines", ()) or ()):
            line_text = str(getattr(line_entry, "text", "") or "").strip()
            if not line_text:
                continue
            try:
                conf_value = float(getattr(line_entry, "confidence", -1.0))
            except Exception:
                conf_value = -1.0
            line_entries.append({"text": line_text, "conf": conf_value})
        if not line_entries:
            for raw_line in str(run_result.text or "").splitlines():
                line_text = raw_line.strip()
                if not line_text:
                    continue
                line_entries.append({"text": line_text, "conf": -1.0})
        runs.append(
            {
                "pass": str(pass_label),
                "image": str(image_path),
                "engine": engine,
                "psm_values": list(psm_values),
                "timeout_s": timeout_s,
                "lang": str(lang or ""),
                "fast_mode": bool(fast_mode),
                "text": str(run_result.text or ""),
                "error": str(run_result.error or ""),
                "lines": line_entries,
            }
        )
        if run_result.text:
            all_texts.append(run_result.text)
            if stop_after_variant_success:
                break
        elif run_result.error:
            errors.append(run_result.error)
    return all_texts, errors, runs


def _truncate_report_text(value: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...<truncated>"


def _extract_line_debug_for_text(ocr_import, text: str, cfg: dict) -> tuple[list[str], list[dict]]:
    extractor = getattr(ocr_import, "extract_candidate_names_debug", None)
    if not callable(extractor):
        return [], []
    try:
        names, entries = extractor(
            text,
            min_chars=int(cfg.get("name_min_chars", 2)),
            max_chars=int(cfg.get("name_max_chars", 24)),
            max_words=int(cfg.get("name_max_words", 2)),
            max_digit_ratio=float(cfg.get("name_max_digit_ratio", 0.45)),
            enforce_special_char_constraint=bool(cfg.get("name_special_char_constraint", True)),
        )
    except Exception:
        return [], []
    return list(names or []), list(entries or [])


def _candidate_stats_from_runs(ocr_import, runs: list[dict], cfg: dict) -> dict[str, dict[str, float | int | str]]:
    extractor = getattr(ocr_import, "extract_candidate_names", None)
    if not callable(extractor):
        return {}
    stats: dict[str, dict[str, float | int | str]] = {}
    min_chars = int(cfg.get("name_min_chars", 2))
    max_chars = int(cfg.get("name_max_chars", 24))
    max_words = int(cfg.get("name_max_words", 2))
    max_digit_ratio = float(cfg.get("name_max_digit_ratio", 0.45))

    for run_idx, run in enumerate(runs):
        seen_in_run: set[str] = set()
        line_entries = list(run.get("lines") or [])
        if not line_entries:
            line_entries = [
                {"text": line.strip(), "conf": -1.0}
                for line in str(run.get("text", "")).splitlines()
                if line.strip()
            ]
        for line in line_entries:
            line_text = str(line.get("text", "")).strip()
            if not line_text:
                continue
            try:
                line_conf = float(line.get("conf", -1.0))
            except Exception:
                line_conf = -1.0
            parsed_names = extractor(
                line_text,
                min_chars=min_chars,
                max_chars=max_chars,
                max_words=max_words,
                max_digit_ratio=max_digit_ratio,
                enforce_special_char_constraint=bool(cfg.get("name_special_char_constraint", True)),
            )
            for parsed in parsed_names:
                key = _simple_name_key(parsed)
                if not key:
                    continue
                bucket = stats.setdefault(
                    key,
                    {
                        "display": parsed,
                        "support": 0,
                        "occurrences": 0,
                        "best_conf": -1.0,
                    },
                )
                bucket["occurrences"] = int(bucket.get("occurrences", 0)) + 1
                current_display = str(bucket.get("display", "")).strip()
                if (
                    _name_display_quality(parsed) < _name_display_quality(current_display)
                    or not current_display
                ):
                    bucket["display"] = parsed
                if line_conf >= 0.0:
                    bucket["best_conf"] = max(float(bucket.get("best_conf", -1.0)), line_conf)
                run_marker = f"{run_idx}:{key}"
                if run_marker in seen_in_run:
                    continue
                seen_in_run.add(run_marker)
                bucket["support"] = int(bucket.get("support", 0)) + 1
    return stats


def _candidate_set_looks_noisy(names: list[str], cfg: dict) -> bool:
    if not names:
        return True
    count = len(names)
    expected = max(1, int(cfg.get("expected_candidates", 5)))
    if abs(count - expected) >= 1:
        return True
    short3_count = sum(1 for name in names if len(str(name or "").strip()) <= 3)
    short3_ratio = short3_count / max(1, count)
    if short3_ratio > 0.34:
        return True
    upper_compact = 0
    for name in names:
        text = str(name or "").strip()
        if not text:
            continue
        has_alpha = any(ch.isalpha() for ch in text)
        if has_alpha and text.isupper() and len(text) <= 4:
            upper_compact += 1
    if (upper_compact / max(1, count)) > 0.50:
        return True
    return False


def _filter_low_confidence_candidates(
    ocr_import,
    names: list[str],
    runs: list[dict],
    cfg: dict,
) -> list[str]:
    if not names:
        return []
    stats = _candidate_stats_from_runs(ocr_import, runs, cfg)
    if not stats:
        return list(names)

    noisy_only = bool(cfg.get("name_confidence_filter_noisy_only", True))
    noisy = _candidate_set_looks_noisy(names, cfg)
    if noisy_only and not noisy:
        return list(names)

    min_conf = float(cfg.get("name_min_confidence", 43.0))
    min_support = max(1, int(cfg.get("name_low_confidence_min_support", 2)))

    filtered: list[str] = []
    for raw in names:
        text = str(raw or "").strip()
        if not text:
            continue
        key = _simple_name_key(text)
        if not key:
            continue
        bucket = stats.get(key)
        if not bucket:
            filtered.append(text)
            continue
        support = int(bucket.get("support", 0))
        best_conf = float(bucket.get("best_conf", -1.0))
        if best_conf >= 0.0 and best_conf >= min_conf:
            filtered.append(text)
            continue
        if support >= min_support:
            filtered.append(text)
            continue
    if not filtered:
        return list(names)
    return filtered


def _should_run_row_pass(cfg: dict, names: list[str]) -> bool:
    if not bool(cfg.get("row_pass_enabled", True)):
        return False
    if bool(cfg.get("row_pass_always_run", True)):
        return True
    row_pass_min_candidates = max(1, int(cfg.get("row_pass_min_candidates", 5)))
    if len(names) < row_pass_min_candidates:
        return True
    max_candidates = max(0, int(cfg.get("recall_retry_max_candidates", 7)))
    if max_candidates > 0 and len(names) > max_candidates:
        return True
    return _candidate_set_looks_noisy(names, cfg)


def _prefer_row_candidates(current: list[str], row_names: list[str], cfg: dict) -> bool:
    if not row_names:
        return False
    if not current:
        return True
    current_score = _score_candidate_set(current, cfg)
    row_score = _score_candidate_set(row_names, cfg)
    expected = max(1, int(cfg.get("expected_candidates", 5)))
    current_delta = abs(len(current) - expected)
    row_delta = abs(len(row_names) - expected)
    if row_delta < current_delta:
        return True
    if row_score > (current_score + 0.05):
        return True
    if row_delta == current_delta and _candidate_set_looks_noisy(current, cfg):
        return row_score >= (current_score - 0.15)
    return False


def _dedupe_names_in_order(values: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw or "").strip()
        if not text:
            continue
        key = _simple_name_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(text)
    return ordered


def _candidate_bucket_score(bucket: dict[str, float | int | str], cfg: dict) -> float:
    text = str(bucket.get("display", "") or "").strip()
    support = int(bucket.get("support", 0))
    occurrences = int(bucket.get("occurrences", 0))
    conf = float(bucket.get("best_conf", -1.0))
    score = 0.0
    score += support * 2.2
    score += occurrences * 0.35
    if conf >= 0.0:
        score += min(100.0, conf) / 42.0
    score += min(12, len(text)) * 0.08
    if len(text) <= 2:
        score -= 1.4
    if text and text.isupper() and len(text) <= 4:
        score -= 0.7
    if text and text.islower() and len(text) <= 3:
        score -= 0.9
    return score


def _select_candidate_keys_from_stats(
    stats: dict[str, dict[str, float | int | str]],
    cfg: dict,
) -> set[str]:
    min_support = max(1, int(cfg.get("name_min_support", 1)))
    min_conf = float(cfg.get("name_min_confidence", 43.0))
    low_conf_support = max(min_support, int(cfg.get("name_low_confidence_min_support", 2)))
    selected: set[str] = set()
    for key, bucket in stats.items():
        text = str(bucket.get("display", "") or "").strip()
        support = int(bucket.get("support", 0))
        conf = float(bucket.get("best_conf", -1.0))
        if support < min_support:
            continue
        keep = False
        if conf < 0.0:
            keep = True
        elif conf >= min_conf:
            keep = True
        elif support >= low_conf_support:
            keep = True
        if (
            keep
            and text
            and text.isupper()
            and len(text) <= 4
            and conf >= 0.0
            and conf < (min_conf + 12.0)
            and support < low_conf_support
        ):
            keep = False
        if keep:
            selected.add(key)
    return selected


def _build_final_names_from_runs(
    *,
    ocr_import,
    cfg: dict,
    preferred_names: list[str],
    primary_names: list[str],
    retry_names: list[str],
    row_names: list[str],
    all_runs: list[dict],
    row_preferred: bool = False,
) -> list[str]:
    stats = _candidate_stats_from_runs(ocr_import, all_runs, cfg)
    for seed_name in list(preferred_names) + list(primary_names) + list(retry_names) + list(row_names):
        text = str(seed_name or "").strip()
        key = _simple_name_key(text)
        if not key:
            continue
        bucket = stats.setdefault(
            key,
            {"display": text, "support": 1, "occurrences": 1, "best_conf": -1.0},
        )
        current_display = str(bucket.get("display", "")).strip()
        if not current_display or _name_display_quality(text) < _name_display_quality(current_display):
            bucket["display"] = text

    if not stats:
        return _dedupe_names_in_order(list(row_names) + list(retry_names) + list(primary_names))

    ranked_all = sorted(
        stats.items(),
        key=lambda kv: (
            -_candidate_bucket_score(kv[1], cfg),
            _name_display_quality(str(kv[1].get("display", ""))),
        ),
    )
    expected = max(1, int(cfg.get("expected_candidates", 5)))
    selected_keys = _select_candidate_keys_from_stats(stats, cfg)
    low_recall_trigger = False
    if not selected_keys:
        selected_keys = {key for key, _ in ranked_all[:expected]}
    else:
        selected_count = len(selected_keys)
        deduped_preferred = _dedupe_names_in_order(preferred_names)
        low_recall_trigger = (
            selected_count <= 2
            or len(deduped_preferred) <= 2
        )
        if selected_count >= expected or not low_recall_trigger:
            low_recall_trigger = False
    if selected_keys and len(selected_keys) < expected and low_recall_trigger:
        # Low-recall fallback: keep strict keys, then top-up with best remaining
        # candidates so we do not collapse to 1-2 names too aggressively.
        for key, bucket in ranked_all:
            if key in selected_keys:
                continue
            text = str(bucket.get("display", "") or "").strip()
            support = int(bucket.get("support", 0))
            conf = float(bucket.get("best_conf", -1.0))
            # Avoid topping up with classic OCR noise tokens.
            if len(text) <= 2 and support <= 1:
                continue
            if (
                text
                and text.isupper()
                and len(text) <= 4
                and support <= 1
                and conf < 55.0
            ):
                continue
            selected_keys.add(key)
            if len(selected_keys) >= expected:
                break

    preferred_keys = [_simple_name_key(name) for name in _dedupe_names_in_order(preferred_names)]
    preferred_keys = [key for key in preferred_keys if key]
    if len(preferred_keys) >= expected:
        preferred_set = set(preferred_keys)
        restricted = [key for key in preferred_keys if key in selected_keys]
        if restricted:
            selected_keys = set(restricted)
        else:
            selected_keys = preferred_set

    ordered_keys: list[str] = []
    seen_keys: set[str] = set()
    for seed in list(row_names) + list(preferred_names) + list(primary_names) + list(retry_names):
        key = _simple_name_key(seed)
        if not key or key in seen_keys or key not in selected_keys:
            continue
        seen_keys.add(key)
        ordered_keys.append(key)

    remaining = [key for key in selected_keys if key not in seen_keys]
    remaining.sort(
        key=lambda key: (
            -_candidate_bucket_score(stats.get(key, {}), cfg),
            _name_display_quality(str(stats.get(key, {}).get("display", ""))),
        )
    )
    ordered_keys.extend(remaining)

    names = [str(stats[key].get("display", "")).strip() for key in ordered_keys if key in stats]
    names = [name for name in names if name]
    names = _dedupe_names_in_order(names)

    max_candidates = max(0, int(cfg.get("name_max_candidates", 12)))
    if max_candidates > 0 and len(names) > max_candidates:
        names = names[:max_candidates]

    expected = max(1, int(cfg.get("expected_candidates", 5)))
    row_count = len(_dedupe_names_in_order(row_names))
    if row_preferred and row_count >= max(3, expected - 1):
        # If row pass was chosen and yields a plausible row count (e.g. 4 for
        # a partially filled lobby), keep that size and avoid re-inflating with
        # noise candidates from other OCR passes.
        soft_cap = row_count
    elif row_count >= 3:
        soft_cap = min(expected + 1, row_count + 1)
    else:
        soft_cap = expected + 2
    if len(names) > soft_cap:
        names = names[:soft_cap]

    return names


def _detect_text_row_ranges(gray: QtGui.QImage, cfg: dict) -> list[tuple[int, int]]:
    width = int(gray.width())
    height = int(gray.height())
    if width <= 0 or height <= 0:
        return []

    bright_threshold = max(0, min(255, int(cfg.get("row_pass_brightness_threshold", 145))))
    min_pixels_ratio = max(0.0, float(cfg.get("row_pass_min_pixels_ratio", 0.015)))
    merge_gap = max(0, int(cfg.get("row_pass_merge_gap_px", 2)))
    min_height = max(2, int(cfg.get("row_pass_min_height_px", 7)))
    max_rows = max(1, int(cfg.get("row_pass_max_rows", 12)))
    expected_rows = max(1, int(cfg.get("expected_candidates", 5)))
    x_start_ratio = max(0.0, min(0.70, float(cfg.get("row_pass_projection_x_start_ratio", 0.08))))
    x_end_ratio = max(x_start_ratio + 0.10, min(1.0, float(cfg.get("row_pass_projection_x_end_ratio", 0.92))))
    x0 = max(0, min(width - 1, int(width * x_start_ratio)))
    x1 = max(x0 + 1, min(width, int(width * x_end_ratio)))
    if (x1 - x0) < 8:
        x0 = 0
        x1 = width

    col_max_ratio = max(0.70, min(0.99, float(cfg.get("row_pass_projection_col_max_ratio", 0.84))))

    def _ranges_for(threshold_value: int, ratio_value: float) -> list[tuple[int, int]]:
        threshold = max(0, min(255, int(threshold_value)))
        ratio = max(0.002, float(ratio_value))
        min_pixels = max(2, int((x1 - x0) * ratio))

        bright_per_col: list[int] = []
        for x in range(x0, x1):
            bright_count = 0
            for y in range(height):
                if QtGui.qGray(gray.pixel(x, y)) >= threshold:
                    bright_count += 1
            bright_per_col.append(bright_count)

        blocked_cols = [
            count >= int(height * col_max_ratio)
            for count in bright_per_col
        ]
        if blocked_cols and all(blocked_cols):
            blocked_cols = [False] * len(blocked_cols)

        projection: list[int] = []
        for y in range(height):
            bright_count = 0
            for local_x, x in enumerate(range(x0, x1)):
                if blocked_cols and blocked_cols[local_x]:
                    continue
                if QtGui.qGray(gray.pixel(x, y)) >= threshold:
                    bright_count += 1
            projection.append(bright_count)

        raw_ranges: list[tuple[int, int]] = []
        start: int | None = None
        for y, count in enumerate(projection):
            if count >= min_pixels:
                if start is None:
                    start = y
            elif start is not None:
                raw_ranges.append((start, y - 1))
                start = None
        if start is not None:
            raw_ranges.append((start, height - 1))
        if not raw_ranges:
            return []

        merged: list[list[int]] = []
        for y0_raw, y1_raw in raw_ranges:
            if not merged:
                merged.append([y0_raw, y1_raw])
                continue
            prev = merged[-1]
            if y0_raw <= (prev[1] + merge_gap + 1):
                prev[1] = max(prev[1], y1_raw)
            else:
                merged.append([y0_raw, y1_raw])

        ranges_local: list[tuple[int, int]] = []
        for y0_local, y1_local in merged:
            if (y1_local - y0_local + 1) < min_height:
                continue
            ranges_local.append((y0_local, y1_local))
        return ranges_local

    threshold_values = [
        bright_threshold,
        bright_threshold - 14,
        bright_threshold - 28,
        bright_threshold - 42,
    ]
    ratio_values = [
        min_pixels_ratio,
        min_pixels_ratio * 0.80,
        min_pixels_ratio * 0.60,
    ]
    candidates: list[tuple[float, int, int, list[tuple[int, int]]]] = []
    for threshold_value in threshold_values:
        for ratio_value in ratio_values:
            ranges_candidate = _ranges_for(threshold_value, ratio_value)
            if not ranges_candidate:
                continue
            count = len(ranges_candidate)
            total_height = sum((y1 - y0 + 1) for y0, y1 in ranges_candidate)
            overflow_penalty = max(0, count - max_rows)
            score = 0.0
            score += count * 5.0
            score -= abs(count - expected_rows) * 1.5
            score -= overflow_penalty * 3.0
            score += min(height, total_height) * 0.02
            candidates.append((score, count, total_height, ranges_candidate))

    if not candidates:
        return []

    _score, _count, _height, best_ranges = max(
        candidates,
        key=lambda item: (item[0], item[1], item[2]),
    )
    best_ranges = sorted(best_ranges, key=lambda item: item[0])
    if len(best_ranges) > max_rows:
        best_ranges = best_ranges[:max_rows]
    return best_ranges


def _build_row_image_variants(row_img: QtGui.QImage, cfg: dict) -> list[tuple[str, QtGui.QImage]]:
    variants: list[tuple[str, QtGui.QImage]] = []
    seen: set[tuple[int, int, int]] = set()

    def _add(name: str, img: QtGui.QImage | None) -> None:
        if img is None or img.isNull():
            return
        key = (int(img.width()), int(img.height()), int(img.cacheKey()))
        if key in seen:
            return
        seen.add(key)
        variants.append((name, img))

    _add("base", row_img)
    scale_factor = max(1, int(cfg.get("row_pass_scale_factor", 4)))
    if scale_factor > 1:
        _add(
            f"scaled_x{scale_factor}",
            row_img.scaled(
                max(1, row_img.width() * scale_factor),
                max(1, row_img.height() * scale_factor),
                QtCore.Qt.IgnoreAspectRatio,
                QtCore.Qt.SmoothTransformation,
            ),
        )
    if bool(cfg.get("row_pass_include_mono", True)):
        mono = row_img.convertToFormat(QtGui.QImage.Format_Mono, QtCore.Qt.ThresholdDither)
        mono_gray = mono.convertToFormat(QtGui.QImage.Format_Grayscale8)
        _add("mono", mono_gray)
        if scale_factor > 1 and not mono_gray.isNull():
            _add(
                f"mono_scaled_x{scale_factor}",
                mono_gray.scaled(
                    max(1, mono_gray.width() * scale_factor),
                    max(1, mono_gray.height() * scale_factor),
                    QtCore.Qt.IgnoreAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                ),
            )
    return variants


def _name_display_quality(value: str) -> tuple[int, int]:
    text = str(value or "").strip()
    separators = sum(1 for ch in text if not ch.isalnum())
    return (separators, -len(text))


def _select_row_names_from_ranked_votes(
    ranked_votes: list[dict[str, object]],
    *,
    cfg: dict,
    best_vote_count: int,
) -> list[str]:
    if not ranked_votes:
        return []

    def _display(entry: dict[str, object]) -> str:
        return str(entry.get("display", "") or "").strip()

    top_name = _display(ranked_votes[0])
    if not top_name:
        return []

    min_vote_count = max(2, int(cfg.get("row_pass_multiline_min_vote_count", 2)))
    if int(best_vote_count) < min_vote_count:
        return [top_name]

    max_names = max(1, int(cfg.get("row_pass_max_names_per_row", 5)))
    min_avg_conf = float(cfg.get("row_pass_multiline_min_avg_conf", 40.0))
    selected: list[str] = []
    seen_keys: set[str] = set()

    for entry in ranked_votes:
        name = _display(entry)
        if not name:
            continue
        key = _simple_name_key(name)
        if not key or key in seen_keys:
            continue
        count = int(entry.get("count", 0))
        if count < min_vote_count:
            continue
        conf_weight = float(entry.get("conf_weight", 0.0))
        avg_conf = -1.0
        if conf_weight > 0.0:
            avg_conf = float(entry.get("conf_sum", 0.0)) / conf_weight
        if avg_conf >= 0.0 and avg_conf < min_avg_conf:
            continue
        selected.append(name)
        seen_keys.add(key)
        if len(selected) >= max_names:
            break

    if selected:
        return selected
    return [top_name]


def _run_row_segmentation_pass(
    paths: list[Path],
    *,
    cfg: dict,
) -> tuple[list[str], list[str], list[dict]]:
    ocr_import = _ocr_import_module()
    selected_paths = _select_variant_paths(paths, cfg, max_variants_key="max_variants")
    if not selected_paths:
        return [], [], []

    max_rows = max(1, int(cfg.get("row_pass_max_rows", 12)))
    pad_px = max(0, int(cfg.get("row_pass_pad_px", 2)))
    psm_values = tuple(cfg.get("row_pass_psm_values", (7, 6, 13)))
    timeout_s = max(0.5, float(cfg.get("timeout_s", 8.0)) * max(0.1, float(cfg.get("row_pass_timeout_scale", 0.55))))
    lang = cfg.get("lang")

    engine = str(cfg.get("engine", "easyocr")).strip().casefold() or "easyocr"
    run_ocr_multi = getattr(ocr_import, "run_ocr_multi", None)
    if not callable(run_ocr_multi):
        return [], [], []
    collected_names: list[str] = []
    seen_keys: set[str] = set()
    row_texts: list[str] = []
    runs: list[dict] = []

    def _entry_text(entry) -> str:
        if isinstance(entry, dict):
            return str(entry.get("text", "") or "").strip()
        return str(getattr(entry, "text", "") or "").strip()

    def _entry_conf(entry) -> float:
        try:
            if isinstance(entry, dict):
                return float(entry.get("conf", entry.get("confidence", -1.0)))
            return float(getattr(entry, "confidence", -1.0))
        except Exception:
            return -1.0

    source_candidates: list[tuple[Path, QtGui.QImage, int]] = []
    max_width = -1
    for candidate_path in selected_paths:
        candidate_img = QtGui.QImage(str(candidate_path))
        if candidate_img.isNull():
            continue
        width = int(candidate_img.width())
        source_candidates.append((candidate_path, candidate_img, width))
        if width > max_width:
            max_width = width
    if not source_candidates:
        return [], [], []

    source_path, source_img, source_width = max(source_candidates, key=lambda item: item[2])

    gray = source_img.convertToFormat(QtGui.QImage.Format_Grayscale8)
    row_ranges = _detect_text_row_ranges(gray, cfg)
    if not row_ranges:
        return [], [], []

    name_x_ratio = max(0.35, min(0.9, float(cfg.get("row_pass_name_x_ratio", 0.58))))
    is_pre_cropped = max_width > 0 and source_width <= int(max_width * 0.78)
    if is_pre_cropped:
        name_width = max(8, int(gray.width()))
    else:
        name_width = max(8, int(gray.width() * name_x_ratio))

    for idx, (y0, y1) in enumerate(row_ranges[:max_rows], start=1):
        top = max(0, y0 - pad_px)
        bottom = min(gray.height() - 1, y1 + pad_px)
        row_img = gray.copy(0, top, min(name_width, gray.width()), max(1, bottom - top + 1))
        row_variants = _build_row_image_variants(row_img, cfg)
        votes: dict[str, dict[str, object]] = {}
        best_vote_count = 0

        for variant_name, variant_img in row_variants:
            if variant_name.startswith("mono") and best_vote_count >= 2:
                # If base/gray variants already agree, mono variants often add noise.
                continue
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                row_path = Path(tmp.name)
            try:
                if not variant_img.save(str(row_path), "PNG"):
                    continue
                run_result = run_ocr_multi(
                    row_path,
                    engine=engine,
                    cmd="",
                    psm_values=psm_values,
                    timeout_s=timeout_s,
                    lang=lang,
                    stop_on_first_success=False,
                    easyocr_model_dir=cfg.get("easyocr_model_dir"),
                    easyocr_user_network_dir=cfg.get("easyocr_user_network_dir"),
                    easyocr_gpu=cfg.get("easyocr_gpu", "auto"),
                    easyocr_download_enabled=bool(cfg.get("easyocr_download_enabled", False)),
                    easyocr_quiet=bool(cfg.get("quiet_mode", False)),
                )
                text = str(run_result.text or "").strip()
                line_entries = list(getattr(run_result, "lines", ()) or [])
                if not line_entries and text:
                    line_entries = [{"text": ln.strip(), "conf": -1.0} for ln in text.splitlines() if ln.strip()]
                if text:
                    row_texts.append(text)
                for line_entry in line_entries:
                    line_text = _entry_text(line_entry)
                    if not line_text:
                        continue
                    parsed_names = ocr_import.extract_candidate_names(
                        line_text,
                        min_chars=int(cfg.get("name_min_chars", 2)),
                        max_chars=int(cfg.get("name_max_chars", 24)),
                        max_words=int(cfg.get("name_max_words", 2)),
                        max_digit_ratio=float(cfg.get("name_max_digit_ratio", 0.45)),
                        enforce_special_char_constraint=bool(
                            cfg.get("name_special_char_constraint", True)
                        ),
                    )
                    if not parsed_names:
                        continue
                    candidate_conf = _entry_conf(line_entry)
                    for candidate in parsed_names:
                        key = _simple_name_key(candidate)
                        if not key:
                            continue
                        bucket = votes.setdefault(
                            key,
                            {"count": 0, "display": candidate, "conf_sum": 0.0, "conf_weight": 0.0},
                        )
                        bucket["count"] = int(bucket.get("count", 0)) + 1
                        best_vote_count = max(best_vote_count, int(bucket["count"]))
                        if candidate_conf >= 0.0:
                            bucket["conf_sum"] = float(bucket.get("conf_sum", 0.0)) + candidate_conf
                            bucket["conf_weight"] = float(bucket.get("conf_weight", 0.0)) + 1.0
                        current_display = str(bucket.get("display", "")).strip()
                        if (
                            _name_display_quality(candidate) < _name_display_quality(current_display)
                            or not current_display
                        ):
                            bucket["display"] = candidate
                line_payload: list[dict] = []
                for line_entry in line_entries:
                    line_text = _entry_text(line_entry)
                    if not line_text:
                        continue
                    conf_value = _entry_conf(line_entry)
                    line_payload.append({"text": line_text, "conf": conf_value})
                runs.append(
                    {
                        "pass": "row",
                        "image": f"{source_path.name}#{idx}[{top}:{bottom}]/{variant_name}",
                        "engine": engine,
                        "psm_values": list(psm_values),
                        "timeout_s": timeout_s,
                        "lang": str(lang or ""),
                        "fast_mode": False,
                        "text": text,
                        "error": str(run_result.error or ""),
                        "lines": line_payload,
                    }
                )
            finally:
                try:
                    row_path.unlink(missing_ok=True)
                except Exception:
                    pass
            if best_vote_count >= 3:
                # Enough agreement for this row; avoid accumulating extra noise.
                break

        if votes:
            ranked = sorted(
                votes.values(),
                key=lambda entry: (
                    -int(entry.get("count", 0)),
                    -(
                        float(entry.get("conf_sum", 0.0))
                        / max(1.0, float(entry.get("conf_weight", 0.0)))
                    ),
                    _name_display_quality(str(entry.get("display", ""))),
                ),
            )
            selected_names = _select_row_names_from_ranked_votes(
                [dict(entry) for entry in ranked],
                cfg=cfg,
                best_vote_count=best_vote_count,
            )
            for best_name in selected_names:
                key = _simple_name_key(best_name)
                if key and key not in seen_keys:
                    seen_keys.add(key)
                    collected_names.append(best_name)

    return collected_names, row_texts, runs


def _build_ocr_debug_report(
    *,
    cfg: dict,
    primary_runs: list[dict],
    retry_runs: list[dict],
    row_runs: list[dict],
    primary_names: list[str],
    retry_names: list[str],
    row_names: list[str],
    final_names: list[str],
    merged_text: str,
    errors: list[str],
) -> str:
    lines: list[str] = []
    lines.append("[OCR Debug Report]")
    lines.append(
        "config: "
        f"engine={cfg.get('engine') or 'easyocr'}, "
        f"lang={cfg.get('lang') or '-'}, "
        f"psm={list(cfg.get('psm_values', ()))}, "
        f"fast_mode={bool(cfg.get('fast_mode', True))}, "
        f"max_variants={int(cfg.get('max_variants', 0))}, "
        f"retry_max_variants={int(cfg.get('recall_retry_max_variants', 0))}, "
        f"timeout={float(cfg.get('timeout_s', 0.0)):.2f}s"
    )
    lines.append(
        "candidates: "
        f"primary={len(primary_names)} {primary_names}, "
        f"retry={len(retry_names)} {retry_names}, "
        f"row={len(row_names)} {row_names}, "
        f"final={len(final_names)} {final_names}"
    )
    if errors:
        lines.append("errors: " + "; ".join(str(err) for err in errors if str(err).strip()))
    else:
        lines.append("errors: -")

    def _append_runs(label: str, runs: list[dict]) -> None:
        lines.append("")
        lines.append(f"[{label}] runs={len(runs)}")
        if not runs:
            lines.append("(none)")
            return
        for idx, run in enumerate(runs, start=1):
            image = Path(str(run.get("image", ""))).name or str(run.get("image", ""))
            psm_values = run.get("psm_values", [])
            timeout_s = float(run.get("timeout_s", 0.0))
            err = str(run.get("error", "")).strip()
            text = str(run.get("text", "")).strip()
            lines.append(
                f"run {idx}: image={image}, psm={psm_values}, timeout={timeout_s:.2f}s, "
                f"error={err or '-'}"
            )
            if text:
                lines.append(text)
            else:
                lines.append("(no text)")
            line_entries = list(run.get("lines") or [])
            if line_entries:
                conf_values: list[float] = []
                for entry in line_entries:
                    try:
                        conf = float(entry.get("conf", -1.0))
                    except Exception:
                        conf = -1.0
                    if conf >= 0.0:
                        conf_values.append(conf)
                if conf_values:
                    lines.append(
                        "line-confidence: "
                        f"min={min(conf_values):.1f}, "
                        f"avg={sum(conf_values)/max(1, len(conf_values)):.1f}, "
                        f"max={max(conf_values):.1f}, "
                        f"n={len(conf_values)}"
                    )
            if bool(cfg.get("debug_line_analysis", True)):
                ocr_import = _ocr_import_module()
                parsed_names, parsed_entries = _extract_line_debug_for_text(ocr_import, text, cfg)
                lines.append("parsed-candidates: " + (", ".join(parsed_names) if parsed_names else "-"))
                if parsed_entries:
                    max_entries = max(0, int(cfg.get("debug_line_max_entries_per_run", 40)))
                    shown_entries = parsed_entries if max_entries <= 0 else parsed_entries[:max_entries]
                    lines.append("line-analysis:")
                    for item in shown_entries:
                        raw = str(item.get("raw", "")).strip()
                        cleaned = str(item.get("cleaned", "")).strip()
                        status = str(item.get("status", "")).strip() or "unknown"
                        reason = str(item.get("reason", "")).strip() or "-"
                        candidate = str(item.get("candidate", "")).strip()
                        lines.append(
                            f"- status={status}, reason={reason}, raw={raw!r}, cleaned={cleaned!r}, "
                            f"candidate={candidate!r}"
                        )
                    if max_entries > 0 and len(parsed_entries) > max_entries:
                        lines.append(f"... {len(parsed_entries) - max_entries} more line entries")
                else:
                    lines.append("line-analysis: -")

    _append_runs("Primary Pass", primary_runs)
    _append_runs("Retry Pass", retry_runs)
    _append_runs("Row Pass", row_runs)

    lines.append("")
    lines.append("[Merged Unique Text]")
    lines.append(merged_text.strip() or "(empty)")

    report = "\n".join(lines)
    return _truncate_report_text(report, int(cfg.get("debug_report_max_chars", 12000)))


def _should_run_recall_retry(cfg: dict, names: list[str]) -> bool:
    if not bool(cfg.get("fast_mode", True)):
        return False
    if not bool(cfg.get("recall_retry_enabled", True)):
        return False
    count = len(names)
    min_candidates = max(0, int(cfg.get("recall_retry_min_candidates", 5)))
    if min_candidates > 0 and count < min_candidates:
        return True

    max_candidates = max(0, int(cfg.get("recall_retry_max_candidates", 7)))
    if max_candidates > 0 and count > max_candidates:
        return True

    if count >= 3:
        short_count = sum(1 for name in names if len(str(name or "").strip()) <= 2)
        short_ratio = short_count / max(1, count)
        short_ratio_limit = max(0.0, float(cfg.get("recall_retry_short_name_max_ratio", 0.34)))
        if short_ratio > short_ratio_limit:
            return True
    return False


def _is_low_count_candidate_set(cfg: dict, names: list[str]) -> bool:
    min_candidates = max(0, int(cfg.get("recall_retry_min_candidates", 5)))
    return min_candidates > 0 and len(names) < min_candidates


def _build_recall_retry_cfg(cfg: dict) -> dict:
    retry_cfg = dict(cfg)
    retry_cfg["fast_mode"] = False
    retry_cfg["stop_after_variant_success"] = False
    timeout_scale = max(1.0, float(cfg.get("recall_retry_timeout_scale", 1.35)))
    retry_cfg["timeout_s"] = max(0.5, float(cfg.get("timeout_s", 8.0)) * timeout_scale)

    psm_primary = int(cfg.get("psm_primary", 6))
    psm_values: list[int] = [psm_primary]
    if bool(cfg.get("recall_retry_use_fallback_psm", True)):
        psm_fallback = int(cfg.get("psm_fallback", 11))
        if psm_fallback not in psm_values:
            psm_values.append(psm_fallback)
    for psm in tuple(cfg.get("psm_values", ())):
        psm_int = int(psm)
        if psm_int not in psm_values:
            psm_values.append(psm_int)
    for psm in tuple(cfg.get("retry_extra_psm_values", ())):
        psm_int = int(psm)
        if psm_int not in psm_values:
            psm_values.append(psm_int)
    retry_cfg["psm_values"] = tuple(psm_values)
    return retry_cfg


def _build_relaxed_support_cfg(cfg: dict) -> dict:
    relaxed = dict(cfg)
    relaxed["name_min_support"] = 1
    relaxed["name_high_count_min_support"] = 1
    return relaxed


def _build_strict_extraction_cfg(cfg: dict) -> dict:
    strict = dict(cfg)
    strict["name_min_chars"] = max(3, int(cfg.get("name_min_chars", 2)))
    strict["name_max_digit_ratio"] = min(float(cfg.get("name_max_digit_ratio", 0.45)), 0.30)
    return strict


def _score_candidate_set(names: list[str], cfg: dict) -> float:
    if not names:
        return float("-inf")
    count = len(names)
    expected = max(1, int(cfg.get("expected_candidates", 5)))
    avg_len = sum(len(str(name or "").strip()) for name in names) / max(1, count)
    short_count = sum(1 for name in names if len(str(name or "").strip()) <= 2)
    short_ratio = short_count / max(1, count)
    short3_count = sum(1 for name in names if len(str(name or "").strip()) <= 3)
    short3_ratio = short3_count / max(1, count)
    compact_upper_count = 0
    for name in names:
        text = str(name or "").strip()
        if text and len(text) <= 4 and text.isupper() and any(ch.isalpha() for ch in text):
            compact_upper_count += 1
    compact_upper_ratio = compact_upper_count / max(1, count)

    score = 0.0
    score -= abs(count - expected) * 2.0
    score -= max(0, count - (expected + 2)) * 1.5
    score -= short_ratio * 4.0
    score -= short3_ratio * 1.5
    score -= compact_upper_ratio * 1.2
    score += min(10.0, avg_len) * 0.3
    return score


def _prefer_retry_candidates(primary: list[str], retry: list[str], cfg: dict) -> bool:
    if not retry:
        return False
    if not primary:
        return True
    return _score_candidate_set(retry, cfg) > (_score_candidate_set(primary, cfg) + 0.05)


def _extract_names_from_ocr_files(
    paths: list[Path],
    *,
    ocr_cmd: str = "",
    cfg: dict,
) -> tuple[list[str], str, str | None]:
    ocr_import = _ocr_import_module()
    primary_texts, errors, primary_runs = _run_ocr_pass(
        paths,
        pass_label="primary",
        cfg=cfg,
        max_variants_key="max_variants",
        ocr_cmd=ocr_cmd,
    )
    primary_names = _extract_names_from_texts(ocr_import, primary_texts, cfg)
    names = list(primary_names)
    merged_texts: list[str] = list(primary_texts)
    retry_names: list[str] = []
    retry_runs: list[dict] = []
    row_names: list[str] = []
    row_runs: list[dict] = []
    row_preferred = False

    if _should_run_recall_retry(cfg, primary_names):
        retry_cfg = _build_recall_retry_cfg(cfg)
        retry_texts, retry_errors, retry_runs = _run_ocr_pass(
            paths,
            pass_label="retry",
            cfg=retry_cfg,
            max_variants_key="recall_retry_max_variants",
            ocr_cmd=ocr_cmd,
        )
        merged_texts.extend(retry_texts)
        errors.extend(retry_errors)
        retry_names = _extract_names_from_texts(ocr_import, retry_texts, cfg)
        if _prefer_retry_candidates(primary_names, retry_names, cfg):
            names = list(retry_names)

    if len(names) > max(0, int(cfg.get("recall_retry_max_candidates", 7))):
        strict_cfg = _build_strict_extraction_cfg(cfg)
        strict_names = _extract_names_from_texts(ocr_import, merged_texts, strict_cfg)
        if _score_candidate_set(strict_names, cfg) > _score_candidate_set(names, cfg):
            names = strict_names

    if bool(cfg.get("recall_relax_support_on_low_count", True)) and _is_low_count_candidate_set(cfg, names):
        relaxed_cfg = _build_relaxed_support_cfg(cfg)
        relaxed_names = _extract_names_from_texts(ocr_import, merged_texts, relaxed_cfg)
        if _score_candidate_set(relaxed_names, cfg) > _score_candidate_set(names, cfg):
            names = relaxed_names

    if _should_run_row_pass(cfg, names):
        row_names, row_texts, row_runs = _run_row_segmentation_pass(
            paths,
            cfg=cfg,
        )
        merged_texts.extend(row_texts)
        if _prefer_row_candidates(names, row_names, cfg):
            names = list(row_names)
            row_preferred = True

    if row_preferred:
        expected = max(1, int(cfg.get("expected_candidates", 5)))
        row_deduped = _dedupe_names_in_order(row_names)
        row_trust_floor = max(3, expected - 1)
        if len(row_deduped) >= row_trust_floor:
            names = row_deduped

    all_runs = list(primary_runs) + list(retry_runs) + list(row_runs)
    names = _build_final_names_from_runs(
        ocr_import=ocr_import,
        cfg=cfg,
        preferred_names=names,
        primary_names=primary_names,
        retry_names=retry_names,
        row_names=row_names,
        all_runs=all_runs,
        row_preferred=row_preferred,
    )
    names = _expand_config_identifier_prefixes(names)

    merged_text = _merge_ocr_texts_unique_lines(merged_texts)
    debug_requested = (
        bool(cfg.get("debug_show_report", False))
        or bool(cfg.get("debug_include_report_text", False))
        or bool(cfg.get("debug_log_to_file", False))
    )
    if debug_requested:
        debug_report = _build_ocr_debug_report(
            cfg=cfg,
            primary_runs=primary_runs,
            retry_runs=retry_runs,
            row_runs=row_runs,
            primary_names=primary_names,
            retry_names=retry_names,
            row_names=row_names,
            final_names=names,
            merged_text=merged_text,
            errors=errors,
        )
    else:
        debug_report = ""
    raw_text = debug_report if bool(cfg.get("debug_include_report_text", False)) else merged_text
    error_text = "; ".join(errors) if errors else None
    return names, raw_text, error_text


class _OCRExtractWorker(QtCore.QObject):
    finished = QtCore.Signal(list, str, object)
    failed = QtCore.Signal(str)

    def __init__(self, paths: list[Path], cfg: dict):
        super().__init__()
        self._paths = [Path(p) for p in paths]
        self._cfg = dict(cfg)

    @QtCore.Slot()
    def run(self) -> None:
        try:
            names, raw_text, error = _extract_names_from_ocr_files(
                self._paths,
                ocr_cmd="",
                cfg=self._cfg,
            )
        except Exception as exc:
            self.failed.emit(repr(exc))
            return
        self.finished.emit(names, raw_text, error)


class _OCRResultRelay(QtCore.QObject):
    """Relay worker results into the GUI thread."""

    result = QtCore.Signal(list, str, object)
    error = QtCore.Signal(str)

    @QtCore.Slot(list, str, object)
    def forward_result(self, names: list[str], raw_text: str, ocr_error: object) -> None:
        self.result.emit(names, raw_text, ocr_error)

    @QtCore.Slot(str)
    def forward_error(self, reason: str) -> None:
        self.error.emit(reason)

def ocr_preview_text(text: str, max_chars: int = 420) -> str:
    if not text:
        return ""
    normalized_lines = [line.strip() for line in text.splitlines() if line.strip()]
    collapsed = "\n".join(normalized_lines)
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[:max_chars].rstrip() + "…"


def _append_ocr_debug_log(
    mw,
    *,
    role: str,
    names: list[str],
    raw_text: str,
    ocr_error: str | None,
) -> Path | None:
    if not bool(mw._cfg("OCR_DEBUG_LOG_TO_FILE", True)):
        return None
    report = str(raw_text or "").strip()
    if not report:
        return None

    configured_name = str(mw._cfg("OCR_DEBUG_LOG_FILE", "ocr_debug.log")).strip() or "ocr_debug.log"
    target_path = Path(configured_name)
    if not target_path.is_absolute():
        state_dir = getattr(mw, "_state_dir", None)
        if isinstance(state_dir, Path):
            target_path = state_dir / target_path
        else:
            target_path = Path.cwd() / target_path

    max_chars = max(0, int(mw._cfg("OCR_DEBUG_LOG_MAX_CHARS", 200000)))
    if max_chars > 0 and len(report) > max_chars:
        report = report[:max_chars].rstrip() + "\n...<truncated for log>"

    role_text = str(role or "").upper() or "-"
    candidate_count = len(list(names or []))
    error_text = str(ocr_error or "-").strip() or "-"
    ts = QtCore.QDateTime.currentDateTime().toString(QtCore.Qt.ISODate)

    lines = [
        f"=== OCR DEBUG {ts} ===",
        f"role={role_text}",
        f"candidates={candidate_count}",
        f"error={error_text}",
        report,
        "",
    ]
    payload = "\n".join(lines)
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("a", encoding="utf-8") as f:
            f.write(payload)
    except Exception:
        return None
    return target_path


def _show_ocr_debug_report(
    mw,
    *,
    role: str,
    names: list[str],
    raw_text: str,
    ocr_error: str | None,
) -> None:
    report = str(raw_text or "").strip()
    if not report:
        return

    summary_lines = [
        f"role={str(role or '').upper() or '-'}",
        f"candidates={len(list(names or []))}",
        f"error={str(ocr_error or '-').strip() or '-'}",
    ]
    summary = "\n".join(summary_lines)
    dialog = QtWidgets.QDialog(mw)
    dialog.setWindowTitle("OCR Debug")
    dialog.resize(960, 700)
    layout = QtWidgets.QVBoxLayout(dialog)

    summary_label = QtWidgets.QLabel(summary, dialog)
    summary_label.setWordWrap(True)
    layout.addWidget(summary_label)

    report_edit = QtWidgets.QPlainTextEdit(dialog)
    report_edit.setReadOnly(True)
    report_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
    report_edit.setPlainText(report)
    layout.addWidget(report_edit, 1)

    buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close, parent=dialog)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    dialog.exec()


def _handle_ocr_selection_error(mw, select_error: str | None) -> bool:
    if select_error == "cancelled":
        QtWidgets.QMessageBox.information(
            mw,
            i18n.t("ocr.result_title"),
            i18n.t("ocr.capture_cancelled"),
        )
        return True
    if select_error == "selection-too-small":
        QtWidgets.QMessageBox.warning(
            mw,
            i18n.t("ocr.error_title"),
            i18n.t("ocr.capture_selection_too_small"),
        )
        return True
    if select_error == "no-screen":
        QtWidgets.QMessageBox.warning(
            mw,
            i18n.t("ocr.error_title"),
            i18n.t("ocr.error_no_screen"),
        )
        return True
    extra_hint = ""
    if sys.platform == "darwin":
        extra_hint = "\n\n" + i18n.t("ocr.error_screen_permission_hint")
    detail = ""
    if isinstance(select_error, str) and select_error:
        detail = f"\n\n[{select_error}]"
    QtWidgets.QMessageBox.warning(
        mw,
        i18n.t("ocr.error_title"),
        i18n.t("ocr.error_selection_failed") + extra_hint + detail,
    )
    return True


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
        availability_fn = getattr(ocr_import, "easyocr_available", None)
        if callable(availability_fn):
            ready = bool(
                availability_fn(
                    lang=runtime_cfg.get("easyocr_lang"),
                    model_dir=runtime_cfg.get("easyocr_model_dir"),
                    user_network_dir=runtime_cfg.get("easyocr_user_network_dir"),
                    gpu=runtime_cfg.get("easyocr_gpu", "auto"),
                    download_enabled=bool(runtime_cfg.get("easyocr_download_enabled", False)),
                    quiet=bool(runtime_cfg.get("quiet_mode", False)),
                )
            )
        else:
            ready = False
        if not ready:
            diag_fn = getattr(ocr_import, "easyocr_resolution_diagnostics", None)
            if callable(diag_fn):
                diag = str(
                    diag_fn(
                        lang=runtime_cfg.get("easyocr_lang"),
                        model_dir=runtime_cfg.get("easyocr_model_dir"),
                        user_network_dir=runtime_cfg.get("easyocr_user_network_dir"),
                        gpu=runtime_cfg.get("easyocr_gpu", "auto"),
                        download_enabled=bool(runtime_cfg.get("easyocr_download_enabled", False)),
                        quiet=bool(runtime_cfg.get("quiet_mode", False)),
                    )
                )
            else:
                diag = "easyocr-diagnostics-unavailable"
            QtWidgets.QMessageBox.warning(
                mw,
                i18n.t("ocr.error_title"),
                i18n.t(
                    "ocr.error_run_failed",
                    reason="easyocr-not-ready (package/models missing?)",
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
