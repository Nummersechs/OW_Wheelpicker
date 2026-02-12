from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time

from PySide6 import QtCore, QtGui, QtWidgets

import i18n
from controller import ocr_import
from view.screen_region_selector import (
    select_region_from_primary_screen,
    select_region_with_macos_screencapture,
)


def capture_region_for_ocr(mw) -> tuple[QtGui.QPixmap | None, str | None]:
    use_native_mac_capture = bool(mw._cfg("OCR_USE_NATIVE_MAC_CAPTURE", True)) and sys.platform == "darwin"
    if not use_native_mac_capture:
        return select_region_from_primary_screen(
            hint_text=i18n.t("ocr.select_hint"),
            parent=mw,
        )

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
                mw.raise_()
                mw.activateWindow()
            QtWidgets.QApplication.processEvents()

    if selected_pixmap is None and select_error == "screencapture-not-found":
        return select_region_from_primary_screen(
            hint_text=i18n.t("ocr.select_hint"),
            parent=mw,
        )
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

    _add_variant(source)
    scale_factor = max(1, int(mw._cfg("OCR_SCALE_FACTOR", 2)))
    if scale_factor > 1 and not source.isNull():
        scaled = source.scaled(
            max(1, source.width() * scale_factor),
            max(1, source.height() * scale_factor),
            QtCore.Qt.IgnoreAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        _add_variant(scaled)

    if not source.isNull():
        gray_image = source.toImage().convertToFormat(QtGui.QImage.Format_Grayscale8)
        gray_pix = QtGui.QPixmap.fromImage(gray_image)
        _add_variant(gray_pix)
        if scale_factor > 1 and not gray_pix.isNull():
            gray_scaled = gray_pix.scaled(
                max(1, gray_pix.width() * scale_factor),
                max(1, gray_pix.height() * scale_factor),
                QtCore.Qt.IgnoreAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            _add_variant(gray_scaled)
    return variants


def extract_names_from_ocr_pixmap(
    mw,
    pixmap: QtGui.QPixmap,
    *,
    tesseract_cmd: str,
) -> tuple[list[str], str, str | None]:
    all_texts: list[str] = []
    errors: list[str] = []
    psm_primary = int(mw._cfg("OCR_TESSERACT_PSM", 6))
    psm_fallback = int(mw._cfg("OCR_TESSERACT_FALLBACK_PSM", 11))
    psm_values = [psm_primary]
    if psm_fallback not in psm_values:
        psm_values.append(psm_fallback)
    lang = str(mw._cfg("OCR_TESSERACT_LANG", "eng")).strip() or None
    timeout_s = float(mw._cfg("OCR_TESSERACT_TIMEOUT_S", 8.0))

    for variant in build_ocr_pixmap_variants(mw, pixmap):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            if not variant.save(str(tmp_path), "PNG"):
                errors.append("image-save-failed")
                continue
            run_result = ocr_import.run_tesseract_multi(
                tmp_path,
                cmd=tesseract_cmd,
                psm_values=psm_values,
                timeout_s=timeout_s,
                lang=lang,
            )
            if run_result.text:
                all_texts.append(run_result.text)
            elif run_result.error:
                errors.append(run_result.error)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    merged_lines: list[str] = []
    seen_lines: set[str] = set()
    for text in all_texts:
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            key = line.lower()
            if key in seen_lines:
                continue
            seen_lines.add(key)
            merged_lines.append(line)
    merged_text = "\n".join(merged_lines)

    names = ocr_import.extract_candidate_names_multi(
        all_texts,
        min_chars=int(mw._cfg("OCR_NAME_MIN_CHARS", 2)),
        max_chars=int(mw._cfg("OCR_NAME_MAX_CHARS", 24)),
        max_words=int(mw._cfg("OCR_NAME_MAX_WORDS", 2)),
        max_digit_ratio=float(mw._cfg("OCR_NAME_MAX_DIGIT_RATIO", 0.45)),
        min_support=int(mw._cfg("OCR_NAME_MIN_SUPPORT", 1)),
        high_count_threshold=int(mw._cfg("OCR_NAME_HIGH_COUNT_THRESHOLD", 8)),
        high_count_min_support=int(mw._cfg("OCR_NAME_HIGH_COUNT_MIN_SUPPORT", 2)),
        max_candidates=int(mw._cfg("OCR_NAME_MAX_CANDIDATES", 12)),
        near_dup_min_chars=int(mw._cfg("OCR_NAME_NEAR_DUP_MIN_CHARS", 8)),
        near_dup_max_len_delta=int(mw._cfg("OCR_NAME_NEAR_DUP_MAX_LEN_DELTA", 1)),
        near_dup_similarity=float(mw._cfg("OCR_NAME_NEAR_DUP_SIMILARITY", 0.90)),
        near_dup_tail_min_chars=int(mw._cfg("OCR_NAME_NEAR_DUP_TAIL_MIN_CHARS", 3)),
        near_dup_tail_head_similarity=float(
            mw._cfg("OCR_NAME_NEAR_DUP_TAIL_HEAD_SIMILARITY", 0.70)
        ),
    )
    error_text = "; ".join(errors) if errors else None
    return names, merged_text, error_text


def ocr_preview_text(text: str, max_chars: int = 420) -> str:
    if not text:
        return ""
    normalized_lines = [line.strip() for line in text.splitlines() if line.strip()]
    collapsed = "\n".join(normalized_lines)
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[:max_chars].rstrip() + "…"


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


def on_role_ocr_import_clicked(mw, role_key: str) -> None:
    role = str(role_key or "").strip().casefold()
    if not mw._role_ocr_import_available(role):
        return
    mw._update_role_ocr_button_enabled(role)
    btn = mw._role_ocr_buttons.get(role)
    if btn is None:
        return
    btn.setEnabled(False)
    try:
        selected_pixmap, select_error = capture_region_for_ocr(mw)
        if selected_pixmap is None:
            _handle_ocr_selection_error(mw, select_error)
            return

        tesseract_cmd = str(mw._cfg("OCR_TESSERACT_CMD", "tesseract"))
        if not ocr_import.tesseract_available(tesseract_cmd):
            QtWidgets.QMessageBox.warning(
                mw,
                i18n.t("ocr.error_title"),
                i18n.t("ocr.error_tesseract_missing", cmd=tesseract_cmd),
            )
            return

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            names, raw_text, ocr_error = extract_names_from_ocr_pixmap(
                mw,
                selected_pixmap,
                tesseract_cmd=tesseract_cmd,
            )
        finally:
            try:
                QtWidgets.QApplication.restoreOverrideCursor()
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
        fallback_entries = [{"name": name, "subroles": [], "active": True} for name in candidate_names]
        added, added_counts = mw._add_ocr_entries_distributed(fallback_entries)
        mw._show_ocr_import_result_distributed(
            added=added,
            total=len(candidate_names),
            counts=added_counts,
        )
    except Exception as exc:
        QtWidgets.QMessageBox.warning(
            mw,
            i18n.t("ocr.error_title"),
            i18n.t("ocr.error_unexpected", reason=repr(exc)),
        )
    finally:
        mw._update_role_ocr_buttons_enabled()
