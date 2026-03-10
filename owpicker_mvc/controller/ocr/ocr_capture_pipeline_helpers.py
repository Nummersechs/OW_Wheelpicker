from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import tempfile
from PySide6 import QtGui

from services import settings_provider

from . import (
    ocr_debug_utils as _ocr_debug_utils,
    ocr_engine_utils as _ocr_engine_utils,
    ocr_import as _ocr_import,
    ocr_ordering_utils as _ocr_ordering_utils,
    ocr_postprocess_utils as _ocr_postprocess_utils,
    ocr_row_pass_utils as _ocr_row_pass_utils,
)


def _ocr_import_module():
    return _ocr_import


def _prepare_ocr_variant_files(
    mw,
    source_pixmap: QtGui.QPixmap,
    cfg: dict,
    *,
    build_ocr_pixmap_variants_fn,
) -> tuple[list[Path], list[str]]:
    variants = build_ocr_pixmap_variants_fn(mw, source_pixmap)
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
        except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as exc:
            errors.append(f"image-save-error:{exc}")
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
    return paths, errors


def _cleanup_temp_paths(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
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


def _config_identifier_hints() -> tuple[str, ...]:
    settings = settings_provider.get_settings()
    source = getattr(settings, "values", None)
    if not isinstance(source, dict) or not source:
        try:
            import config as app_config
        except ImportError:
            source = {}
        else:
            source = {
                key: value
                for key, value in vars(app_config).items()
                if isinstance(key, str) and key.isupper()
            }
    hints: set[str] = set()
    for key in source.keys():
        key_text = str(key or "")
        if not key_text.isupper():
            continue
        if _IDENTIFIER_HINT_RE.match(key_text):
            hints.add(key_text)
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
            except (TypeError, ValueError):
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
    except (AttributeError, TypeError, ValueError, RuntimeError):
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
        except (TypeError, ValueError):
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
