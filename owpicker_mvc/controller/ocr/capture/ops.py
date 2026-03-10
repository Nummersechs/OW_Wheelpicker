from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import time

from PySide6 import QtCore, QtGui, QtWidgets

import i18n
from utils import qt_runtime

from view import screen_region_selector as _screen_selector

from . import (
    async_import as _ocr_capture_async_import,
    async_worker_utils as _ocr_async_worker_utils,
    click_flow as _ocr_capture_click_flow,
    entry_helpers as _ocr_capture_entry_helpers,
    pipeline_helpers as _ocr_capture_pipeline_helpers,
    runtime_cfg as _ocr_capture_runtime_cfg,
    ui_helpers as _ocr_capture_ui_helpers,
)
from ..pipeline import (
    debug_utils as _ocr_debug_utils,
    engine_utils as _ocr_engine_utils,
    importer as _ocr_import,
    ordering_utils as _ocr_ordering_utils,
    postprocess_utils as _ocr_postprocess_utils,
    row_pass_utils as _ocr_row_pass_utils,
)
from ..runtime import trace as _ocr_runtime_trace


def _ocr_import_module():
    return _ocr_import


def _screen_selector_module():
    return _screen_selector


def select_region_from_primary_screen(*args, **kwargs):
    return _screen_selector_module().select_region_from_primary_screen(*args, **kwargs)


def select_region_with_macos_screencapture(*args, **kwargs):
    return _screen_selector_module().select_region_with_macos_screencapture(*args, **kwargs)


def _restore_override_cursor() -> None:
    _ocr_capture_entry_helpers.restore_override_cursor(qtwidgets=QtWidgets)


def _cancel_ocr_cache_release(mw) -> None:
    _ocr_capture_entry_helpers.cancel_ocr_cache_release(mw)


def _schedule_ocr_cache_release(mw) -> None:
    _ocr_capture_entry_helpers.schedule_ocr_cache_release(mw)


def _show_ocr_busy_overlay(mw, role: str) -> bool:
    return _ocr_capture_entry_helpers.show_ocr_busy_overlay(
        mw,
        role,
        i18n_module=i18n,
        qtwidgets=QtWidgets,
    )


def _hide_ocr_busy_overlay(mw, *, active: bool) -> None:
    _ocr_capture_entry_helpers.hide_ocr_busy_overlay(
        mw,
        active=active,
        i18n_module=i18n,
    )


def _mark_ocr_runtime_activated(mw) -> None:
    _ocr_capture_entry_helpers.mark_ocr_runtime_activated(mw)


def _restore_main_window_after_capture(
    mw,
    *,
    was_visible: bool,
    was_minimized: bool,
) -> None:
    _ocr_capture_entry_helpers.restore_main_window_after_capture(
        mw,
        was_visible=was_visible,
        was_minimized=was_minimized,
        ocr_capture_ui_helpers_module=_ocr_capture_ui_helpers,
        qt_runtime_module=qt_runtime,
    )


def _suspend_quit_on_last_window_closed(*, active: bool):
    return _ocr_capture_entry_helpers.suspend_quit_on_last_window_closed(
        active=active,
        ocr_capture_ui_helpers_module=_ocr_capture_ui_helpers,
        ocr_runtime_trace_module=_ocr_runtime_trace,
    )


def _capture_region_with_qt_selector(mw) -> tuple[QtGui.QPixmap | None, str | None]:
    return _ocr_capture_entry_helpers.capture_region_with_qt_selector(
        mw,
        sys_platform=sys.platform,
        select_region_from_primary_screen_fn=select_region_from_primary_screen,
        suspend_quit_on_last_window_closed_fn=_suspend_quit_on_last_window_closed,
        restore_main_window_after_capture_fn=_restore_main_window_after_capture,
        time_module=time,
        i18n_module=i18n,
        ocr_capture_ui_helpers_module=_ocr_capture_ui_helpers,
    )


def capture_region_for_ocr(mw) -> tuple[QtGui.QPixmap | None, str | None]:
    return _ocr_capture_entry_helpers.capture_region_for_ocr(
        mw,
        sys_platform=sys.platform,
        capture_region_with_qt_selector_fn=_capture_region_with_qt_selector,
        select_region_with_macos_screencapture_fn=select_region_with_macos_screencapture,
        suspend_quit_on_last_window_closed_fn=_suspend_quit_on_last_window_closed,
        restore_main_window_after_capture_fn=_restore_main_window_after_capture,
        time_module=time,
        i18n_module=i18n,
        ocr_capture_ui_helpers_module=_ocr_capture_ui_helpers,
    )


def build_ocr_pixmap_variants(mw, source: QtGui.QPixmap) -> list[QtGui.QPixmap]:
    return _ocr_capture_ui_helpers.build_ocr_pixmap_variants(mw, source)


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
    return _ocr_capture_runtime_cfg.build_runtime_cfg_snapshot(
        mw,
        sys_platform=sys.platform,
    )


def _prepare_ocr_variant_files(
    mw,
    source_pixmap: QtGui.QPixmap,
    cfg: dict,
) -> tuple[list[Path], list[str]]:
    return _ocr_capture_pipeline_helpers._prepare_ocr_variant_files(
        mw,
        source_pixmap,
        cfg,
        build_ocr_pixmap_variants_fn=build_ocr_pixmap_variants,
    )


_cleanup_temp_paths = _ocr_capture_pipeline_helpers._cleanup_temp_paths
_select_variant_paths = _ocr_capture_pipeline_helpers._select_variant_paths
_merge_ocr_texts_unique_lines = _ocr_capture_pipeline_helpers._merge_ocr_texts_unique_lines
_simple_name_key = _ocr_capture_pipeline_helpers._simple_name_key
_config_identifier_hints = _ocr_capture_pipeline_helpers._config_identifier_hints
_normalize_identifier_candidate = _ocr_capture_pipeline_helpers._normalize_identifier_candidate
_looks_like_identifier_candidate = _ocr_capture_pipeline_helpers._looks_like_identifier_candidate
_expand_config_identifier_prefixes = _ocr_capture_pipeline_helpers._expand_config_identifier_prefixes


_line_extractor_kwargs = _ocr_capture_pipeline_helpers._line_extractor_kwargs
_multi_extractor_kwargs = _ocr_capture_pipeline_helpers._multi_extractor_kwargs
_line_entry_text = _ocr_capture_pipeline_helpers._line_entry_text
_line_entry_conf = _ocr_capture_pipeline_helpers._line_entry_conf
_run_result_text = _ocr_capture_pipeline_helpers._run_result_text
_run_result_error = _ocr_capture_pipeline_helpers._run_result_error
_ocr_engine_from_cfg = _ocr_capture_pipeline_helpers._ocr_engine_from_cfg
_easyocr_runner_kwargs = _ocr_capture_pipeline_helpers._easyocr_runner_kwargs
_easyocr_resolution_kwargs = _ocr_capture_pipeline_helpers._easyocr_resolution_kwargs
_run_ocr_multi_with_cfg = _ocr_capture_pipeline_helpers._run_ocr_multi_with_cfg
_build_ocr_run_entry = _ocr_capture_pipeline_helpers._build_ocr_run_entry
_line_entries_from_run_result = _ocr_capture_pipeline_helpers._line_entries_from_run_result
_OCRLineParseContext = _ocr_capture_pipeline_helpers._OCRLineParseContext
_extract_names_from_texts = _ocr_capture_pipeline_helpers._extract_names_from_texts
_truncate_report_text = _ocr_capture_pipeline_helpers._truncate_report_text
_extract_line_debug_for_text = _ocr_capture_pipeline_helpers._extract_line_debug_for_text
_line_payload_from_entries = _ocr_capture_pipeline_helpers._line_payload_from_entries


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


_candidate_stats_from_runs = _ocr_capture_pipeline_helpers._candidate_stats_from_runs
_candidate_set_looks_noisy = _ocr_capture_pipeline_helpers._candidate_set_looks_noisy
_filter_low_confidence_candidates = _ocr_capture_pipeline_helpers._filter_low_confidence_candidates
_merge_prefix_candidate_stats = _ocr_capture_pipeline_helpers._merge_prefix_candidate_stats
_merge_near_duplicate_candidate_stats = _ocr_capture_pipeline_helpers._merge_near_duplicate_candidate_stats
_should_run_row_pass = _ocr_capture_pipeline_helpers._should_run_row_pass
_prefer_row_candidates = _ocr_capture_pipeline_helpers._prefer_row_candidates
_dedupe_names_in_order = _ocr_capture_pipeline_helpers._dedupe_names_in_order
_candidate_bucket_score = _ocr_capture_pipeline_helpers._candidate_bucket_score
_select_candidate_keys_from_stats = _ocr_capture_pipeline_helpers._select_candidate_keys_from_stats
_build_final_names_from_runs = _ocr_capture_pipeline_helpers._build_final_names_from_runs


_detect_text_row_ranges = _ocr_capture_pipeline_helpers._detect_text_row_ranges
_build_row_image_variants = _ocr_capture_pipeline_helpers._build_row_image_variants
_row_image_looks_right_clipped = _ocr_capture_pipeline_helpers._row_image_looks_right_clipped
_name_display_quality = _ocr_capture_pipeline_helpers._name_display_quality
_name_similarity = _ocr_capture_pipeline_helpers._name_similarity
_common_prefix_len = _ocr_capture_pipeline_helpers._common_prefix_len
_merge_row_prefix_variants = _ocr_capture_pipeline_helpers._merge_row_prefix_variants


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
        except TypeError:
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


_run_line_count = _ocr_capture_pipeline_helpers._run_line_count
_stable_primary_line_count = _ocr_capture_pipeline_helpers._stable_primary_line_count
_primary_line_count_bounds = _ocr_capture_pipeline_helpers._primary_line_count_bounds
_primary_avg_line_confidence = _ocr_capture_pipeline_helpers._primary_avg_line_confidence
_resolve_effective_precount_rows = _ocr_capture_pipeline_helpers._resolve_effective_precount_rows
_resolve_precount_row_bounds = _ocr_capture_pipeline_helpers._resolve_precount_row_bounds
_precount_extra_allowance_from_stats = _ocr_capture_pipeline_helpers._precount_extra_allowance_from_stats
_clamp_names_to_expected_count = _ocr_capture_pipeline_helpers._clamp_names_to_expected_count
_refill_names_to_target = _ocr_capture_pipeline_helpers._refill_names_to_target
_order_names_by_line_trace = _ocr_capture_pipeline_helpers._order_names_by_line_trace
_collapse_names_by_trace_slots = _ocr_capture_pipeline_helpers._collapse_names_by_trace_slots
_order_names_by_seed_sequence = _ocr_capture_pipeline_helpers._order_names_by_seed_sequence
_reconcile_row_overflow_with_primary_slots = _ocr_capture_pipeline_helpers._reconcile_row_overflow_with_primary_slots
_build_ocr_debug_report = _ocr_capture_pipeline_helpers._build_ocr_debug_report


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
        except (TypeError, ValueError):
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
    cancel_check=None,
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
    _ocr_capture_click_flow.start_ocr_async_import(
        mw,
        role=role,
        selected_pixmap=selected_pixmap,
        busy_overlay_shown=busy_overlay_shown,
        start_ocr_async_import_impl=_ocr_capture_async_import.start_ocr_async_import,
        ocr_runtime_trace_module=_ocr_runtime_trace,
        runtime_cfg_snapshot_fn=_ocr_runtime_cfg_snapshot,
        ocr_import_module_fn=_ocr_import_module,
        easyocr_resolution_kwargs_fn=_easyocr_resolution_kwargs,
        prepare_ocr_variant_files_fn=_prepare_ocr_variant_files,
        hide_ocr_busy_overlay_fn=_hide_ocr_busy_overlay,
        restore_override_cursor_fn=_restore_override_cursor,
        cleanup_temp_paths_fn=_cleanup_temp_paths,
        ocr_extract_worker_cls=_OCRExtractWorker,
        ocr_result_relay_cls=_OCRResultRelay,
        append_ocr_debug_log_fn=_append_ocr_debug_log,
        show_ocr_debug_report_fn=_show_ocr_debug_report,
        ocr_preview_text_fn=ocr_preview_text,
        schedule_ocr_cache_release_fn=_schedule_ocr_cache_release,
        i18n_module=i18n,
        qtcore=QtCore,
        qtwidgets=QtWidgets,
    )


def on_role_ocr_import_clicked(mw, role_key: str) -> None:
    _ocr_capture_click_flow.on_role_ocr_import_clicked(
        mw,
        role_key,
        ocr_runtime_trace_module=_ocr_runtime_trace,
        role_ocr_import_available_fn=mw._role_ocr_import_available,
        mark_ocr_runtime_activated_fn=_mark_ocr_runtime_activated,
        cancel_ocr_cache_release_fn=_cancel_ocr_cache_release,
        update_role_ocr_button_enabled_fn=mw._update_role_ocr_button_enabled,
        capture_region_for_ocr_fn=capture_region_for_ocr,
        show_ocr_busy_overlay_fn=_show_ocr_busy_overlay,
        start_ocr_async_import_fn=_start_ocr_async_import,
        handle_ocr_selection_error_fn=_handle_ocr_selection_error,
        restore_override_cursor_fn=_restore_override_cursor,
        schedule_ocr_cache_release_fn=_schedule_ocr_cache_release,
        i18n_module=i18n,
        qtcore=QtCore,
        qtgui=QtGui,
        qtwidgets=QtWidgets,
    )
