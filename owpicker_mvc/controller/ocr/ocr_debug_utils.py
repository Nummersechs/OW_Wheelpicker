from __future__ import annotations

from pathlib import Path
import sys

from PySide6 import QtCore, QtWidgets

import i18n


def _build_ocr_debug_report(
    *,
    cfg: dict,
    parse_ctx,
    primary_runs: list[dict],
    retry_runs: list[dict],
    row_runs: list[dict],
    primary_names: list[str],
    retry_names: list[str],
    row_names: list[str],
    final_names: list[str],
    merged_text: str,
    errors: list[str],
    line_map_trace: list[dict],
    extract_line_debug_for_text_fn,
    truncate_report_text_fn,
) -> str:
    def _simple_name_key(value: str) -> str:
        return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())

    def _short_text(value: str, limit: int = 120) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"

    def _safe_int(value, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    def _append_line_mapping_trace(trace_entries: list[dict]) -> None:
        if not bool(cfg.get("debug_trace_line_mapping", True)):
            return
        lines.append("")
        lines.append(f"[Line Mapping Trace] entries={len(trace_entries)}")
        if not trace_entries:
            lines.append("(none)")
            return
        max_entries = max(0, int(cfg.get("debug_trace_max_entries", 220)))
        shown_entries = trace_entries if max_entries <= 0 else trace_entries[:max_entries]
        final_keys = {
            _simple_name_key(name)
            for name in list(final_names or [])
            if _simple_name_key(name)
        }
        for entry in shown_entries:
            line_text = _short_text(str(entry.get("line", "") or ""))
            parsed = [str(name).strip() for name in list(entry.get("parsed_candidates") or []) if str(name).strip()]
            parsed_preview = ", ".join(repr(_short_text(name, 42)) for name in parsed[:3]) if parsed else "-"
            if len(parsed) > 3:
                parsed_preview += f", +{len(parsed) - 3} more"

            selected = str(entry.get("selected_candidate", "") or "").strip()
            selected_key = str(entry.get("selected_key", "") or "").strip()
            selected_flag = (
                "yes" if selected_key and selected_key in final_keys else "no"
            )
            selection_reason = str(entry.get("selection_reason", "") or "").strip() or "-"
            support_incremented = bool(entry.get("support_incremented", False))
            drop_reason = str(entry.get("drop_reason", "") or "").strip() or "-"

            strict_status = str(entry.get("strict_status", "") or "").strip() or "-"
            strict_reason = str(entry.get("strict_reason", "") or "").strip() or "-"
            strict_cleaned = _short_text(str(entry.get("strict_cleaned", "") or ""), 60)

            pass_name = str(entry.get("pass", "") or "").strip() or "-"
            run_index = _safe_int(entry.get("run_index", 0), 0)
            line_index = _safe_int(entry.get("line_index", 0), 0)
            image_name = Path(str(entry.get("image", "") or "")).name
            conf_raw = entry.get("line_conf", -1.0)
            try:
                conf_value = float(conf_raw)
                conf_text = f"{conf_value:.1f}" if conf_value >= 0.0 else "-"
            except Exception:
                conf_text = "-"

            lines.append(
                f"- pass={pass_name}, run={run_index}, line={line_index}, image={image_name}, "
                f"conf={conf_text}, strict={strict_status}/{strict_reason}, "
                f"parsed={len(parsed)}[{parsed_preview}], selected={selected!r}, "
                f"selection={selection_reason}, support={support_incremented}, final={selected_flag}, "
                f"drop={drop_reason}, cleaned={strict_cleaned!r}, raw={line_text!r}"
            )
        if max_entries > 0 and len(trace_entries) > max_entries:
            lines.append(f"... {len(trace_entries) - max_entries} more trace entries")

    lines: list[str] = []
    lines.append("[OCR Debug Report]")
    lines.append(
        "config: "
        f"engine={cfg.get('engine') or 'easyocr'}, "
        f"lang={cfg.get('lang') or '-'}, "
        f"psm={list(cfg.get('psm_values', ()))}, "
        f"pre_rows={int(cfg.get('precount_rows', 0)) or '-'}, "
        f"pre_rows_visual={int(cfg.get('precount_rows_visual', 0)) or '-'}, "
        f"pre_rows_primary={int(cfg.get('precount_rows_primary_stable', 0)) or '-'}, "
        f"pre_rows_min={int(cfg.get('precount_rows_min', 0)) or '-'}, "
        f"pre_rows_max={int(cfg.get('precount_rows_max', 0)) or '-'}, "
        f"pre_rows_max_eff={int(cfg.get('precount_rows_max_effective', 0)) or '-'}, "
        f"pre_rows_refill={int(cfg.get('precount_rows_refill_target', 0)) or '-'}, "
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
                parsed_names, parsed_entries = extract_line_debug_for_text_fn(parse_ctx, text)
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
    _append_line_mapping_trace(list(line_map_trace or []))

    lines.append("")
    lines.append("[Merged Unique Text]")
    lines.append(merged_text.strip() or "(empty)")

    report = "\n".join(lines)
    return truncate_report_text_fn(report, int(cfg.get("debug_report_max_chars", 12000)))


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
        log_dir = getattr(mw, "_log_dir", None)
        if not isinstance(log_dir, Path):
            state_dir = getattr(mw, "_state_dir", None)
            if isinstance(state_dir, Path):
                configured_log_dir = str(mw._cfg("LOG_OUTPUT_DIR", "logs")).strip()
                if configured_log_dir:
                    configured_log_path = Path(configured_log_dir)
                    if configured_log_path.is_absolute():
                        log_dir = configured_log_path
                    else:
                        log_dir = state_dir / configured_log_path
                else:
                    log_dir = state_dir
        if not isinstance(log_dir, Path):
            log_dir = Path.cwd()
        target_path = log_dir / target_path

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
