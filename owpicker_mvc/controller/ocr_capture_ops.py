from __future__ import annotations

import importlib
from pathlib import Path
import sys
import tempfile
import time

from PySide6 import QtCore, QtGui, QtWidgets

import i18n
from utils import qt_runtime


def _ocr_import_module():
    return importlib.import_module(".ocr_import", package=__package__)


def _screen_selector_module():
    return importlib.import_module("view.screen_region_selector")


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
    ocr_import = _ocr_import_module()
    all_texts: list[str] = []
    errors: list[str] = []
    fast_mode = bool(mw._cfg("OCR_FAST_MODE", True))
    max_variants = int(mw._cfg("OCR_MAX_VARIANTS", 2 if fast_mode else 0))
    stop_after_variant_success = bool(mw._cfg("OCR_STOP_AFTER_FIRST_VARIANT_SUCCESS", True))
    psm_primary = int(mw._cfg("OCR_TESSERACT_PSM", 6))
    psm_fallback = int(mw._cfg("OCR_TESSERACT_FALLBACK_PSM", 11))
    psm_values = [psm_primary]
    if (not fast_mode) and psm_fallback not in psm_values:
        psm_values.append(psm_fallback)
    lang = str(mw._cfg("OCR_TESSERACT_LANG", "deu+eng")).strip() or None
    timeout_s = float(mw._cfg("OCR_TESSERACT_TIMEOUT_S", 8.0))

    variants = build_ocr_pixmap_variants(mw, pixmap)
    if max_variants > 0:
        variants = variants[:max_variants]

    for variant in variants:
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
                stop_on_first_success=fast_mode,
            )
            if run_result.text:
                all_texts.append(run_result.text)
                if fast_mode and stop_after_variant_success:
                    break
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


def _ocr_runtime_cfg_snapshot(mw) -> dict:
    fast_mode = bool(mw._cfg("OCR_FAST_MODE", True))
    default_max_variants = 2 if fast_mode else 0
    if sys.platform == "win32" and fast_mode:
        default_max_variants = 1
    max_variants = int(mw._cfg("OCR_MAX_VARIANTS", default_max_variants))
    if sys.platform == "win32":
        max_variants = int(mw._cfg("OCR_MAX_VARIANTS_WINDOWS", max_variants))
    psm_primary = int(mw._cfg("OCR_TESSERACT_PSM", 6))
    psm_fallback = int(mw._cfg("OCR_TESSERACT_FALLBACK_PSM", 11))
    psm_values = [psm_primary]
    if (not fast_mode) and psm_fallback not in psm_values:
        psm_values.append(psm_fallback)
    timeout_s = float(mw._cfg("OCR_TESSERACT_TIMEOUT_S", 8.0))
    if sys.platform == "win32":
        timeout_s = float(mw._cfg("OCR_TESSERACT_TIMEOUT_S_WINDOWS", timeout_s))
    return {
        "fast_mode": fast_mode,
        "max_variants": max_variants,
        "stop_after_variant_success": bool(mw._cfg("OCR_STOP_AFTER_FIRST_VARIANT_SUCCESS", True)),
        "psm_values": tuple(psm_values),
        "lang": str(mw._cfg("OCR_TESSERACT_LANG", "deu+eng")).strip() or None,
        "timeout_s": timeout_s,
        "name_min_chars": int(mw._cfg("OCR_NAME_MIN_CHARS", 2)),
        "name_max_chars": int(mw._cfg("OCR_NAME_MAX_CHARS", 24)),
        "name_max_words": int(mw._cfg("OCR_NAME_MAX_WORDS", 2)),
        "name_max_digit_ratio": float(mw._cfg("OCR_NAME_MAX_DIGIT_RATIO", 0.45)),
        "name_min_support": int(mw._cfg("OCR_NAME_MIN_SUPPORT", 1)),
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
    max_variants = int(cfg.get("max_variants", 0))
    if max_variants > 0:
        variants = variants[:max_variants]

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


def _extract_names_from_ocr_files(
    paths: list[Path],
    *,
    tesseract_cmd: str,
    cfg: dict,
) -> tuple[list[str], str, str | None]:
    ocr_import = _ocr_import_module()
    all_texts: list[str] = []
    errors: list[str] = []
    fast_mode = bool(cfg.get("fast_mode", True))
    stop_after_variant_success = bool(cfg.get("stop_after_variant_success", True))
    psm_values = tuple(cfg.get("psm_values", (6, 11)))
    lang = cfg.get("lang")
    timeout_s = float(cfg.get("timeout_s", 8.0))

    for image_path in paths:
        run_result = ocr_import.run_tesseract_multi(
            image_path,
            cmd=tesseract_cmd,
            psm_values=psm_values,
            timeout_s=timeout_s,
            lang=lang,
            stop_on_first_success=fast_mode,
        )
        if run_result.text:
            all_texts.append(run_result.text)
            if fast_mode and stop_after_variant_success:
                break
        elif run_result.error:
            errors.append(run_result.error)

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
        min_chars=int(cfg.get("name_min_chars", 2)),
        max_chars=int(cfg.get("name_max_chars", 24)),
        max_words=int(cfg.get("name_max_words", 2)),
        max_digit_ratio=float(cfg.get("name_max_digit_ratio", 0.45)),
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
    error_text = "; ".join(errors) if errors else None
    return names, merged_text, error_text


class _OCRExtractWorker(QtCore.QObject):
    finished = QtCore.Signal(list, str, object)
    failed = QtCore.Signal(str)

    def __init__(self, paths: list[Path], tesseract_cmd: str, cfg: dict):
        super().__init__()
        self._paths = [Path(p) for p in paths]
        self._tesseract_cmd = str(tesseract_cmd)
        self._cfg = dict(cfg)

    @QtCore.Slot()
    def run(self) -> None:
        try:
            names, raw_text, error = _extract_names_from_ocr_files(
                self._paths,
                tesseract_cmd=self._tesseract_cmd,
                cfg=self._cfg,
            )
        except Exception as exc:
            self.failed.emit(repr(exc))
            return
        self.finished.emit(names, raw_text, error)


def _resolve_tesseract_cmd_cached(mw, configured_cmd: str) -> str | None:
    cache = getattr(mw, "_ocr_tesseract_cmd_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        setattr(mw, "_ocr_tesseract_cmd_cache", cache)
    key = str(configured_cmd or "").strip() or "auto"
    if key in cache:
        return cache.get(key)
    ocr_import = _ocr_import_module()
    resolved = ocr_import.resolve_tesseract_cmd(key)
    cache[key] = resolved
    return resolved


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
    if getattr(mw, "_ocr_async_job", None):
        return
    mw._update_role_ocr_button_enabled(role)
    btn = mw._role_ocr_buttons.get(role)
    if btn is not None:
        btn.setEnabled(False)
    temp_paths: list[Path] = []
    try:
        selected_pixmap, select_error = capture_region_for_ocr(mw)
        if selected_pixmap is None:
            _handle_ocr_selection_error(mw, select_error)
            return

        configured_tesseract_cmd = str(mw._cfg("OCR_TESSERACT_CMD", "auto"))
        resolved_tesseract_cmd = _resolve_tesseract_cmd_cached(mw, configured_tesseract_cmd)
        ocr_import = _ocr_import_module()
        if not resolved_tesseract_cmd:
            diag = ocr_import.tesseract_resolution_diagnostics(configured_tesseract_cmd)
            QtWidgets.QMessageBox.warning(
                mw,
                i18n.t("ocr.error_title"),
                i18n.t("ocr.error_tesseract_missing", cmd=configured_tesseract_cmd)
                + "\n\n"
                + i18n.t("ocr.error_tesseract_bundle_hint")
                + "\n\n"
                + diag,
            )
            return

        runtime_cfg = _ocr_runtime_cfg_snapshot(mw)
        temp_paths, prep_errors = _prepare_ocr_variant_files(mw, selected_pixmap, runtime_cfg)
        if not temp_paths:
            reason = "; ".join(prep_errors) if prep_errors else "image-save-failed"
            QtWidgets.QMessageBox.warning(
                mw,
                i18n.t("ocr.error_title"),
                i18n.t("ocr.error_run_failed", reason=reason),
            )
            return

        thread = QtCore.QThread(mw)
        worker = _OCRExtractWorker(temp_paths, resolved_tesseract_cmd, runtime_cfg)
        worker.moveToThread(thread)
        job = {
            "thread": thread,
            "worker": worker,
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
            _restore_override_cursor()
            try:
                if thread.isRunning():
                    thread.quit()
                    thread.wait(1000)
            except Exception:
                pass
            try:
                worker.deleteLater()
            except Exception:
                pass
            try:
                thread.deleteLater()
            except Exception:
                pass
            mw._update_role_ocr_buttons_enabled()

        def _handle_result(names: list[str], raw_text: str, ocr_error: str | None) -> None:
            _finalize_job()
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

        worker.finished.connect(_handle_result)
        worker.failed.connect(_handle_worker_error)
        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        thread.start()
        return
    except Exception as exc:
        _cleanup_temp_paths(temp_paths)
        _restore_override_cursor()
        setattr(mw, "_ocr_async_job", None)
        QtWidgets.QMessageBox.warning(
            mw,
            i18n.t("ocr.error_title"),
            i18n.t("ocr.error_unexpected", reason=repr(exc)),
        )
        mw._update_role_ocr_buttons_enabled()
        return
