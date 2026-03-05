from __future__ import annotations

from pathlib import Path
import tempfile

from PySide6 import QtCore, QtGui


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


def _row_image_looks_right_clipped(row_img: QtGui.QImage, cfg: dict) -> bool:
    if row_img is None or row_img.isNull():
        return False
    width = int(row_img.width())
    height = int(row_img.height())
    if width < 20 or height < 4:
        return False

    probe_ratio = max(0.02, min(0.40, float(cfg.get("row_pass_right_edge_probe_ratio", 0.08))))
    edge_px = max(2, min(10, int(width * probe_ratio)))
    edge_px = min(edge_px, width)
    if edge_px <= 0:
        return False

    bright_threshold = max(
        0,
        min(255, int(cfg.get("row_pass_brightness_threshold", 145)) - 12),
    )
    start_x = max(0, width - edge_px)
    bright_pixels = 0
    total_pixels = edge_px * height
    for y in range(height):
        for x in range(start_x, width):
            if QtGui.qGray(row_img.pixel(x, y)) >= bright_threshold:
                bright_pixels += 1
    bright_ratio = bright_pixels / max(1, total_pixels)
    min_ratio = max(0.03, min(0.90, float(cfg.get("row_pass_right_edge_bright_ratio", 0.12))))
    return bright_ratio >= min_ratio


def _row_line_passes_prefilter(line_text: str, line_conf: float, cfg: dict) -> bool:
    if not bool(cfg.get("row_pass_line_prefilter_enabled", True)):
        return True
    text = str(line_text or "").strip()
    if not text:
        return False

    try:
        confidence = float(line_conf)
    except Exception:
        confidence = -1.0
    if confidence < 0.0:
        # Unknown confidence: keep line to avoid accidental recall drops.
        return True

    high_conf_bypass = float(cfg.get("row_pass_line_prefilter_high_conf_bypass", 72.0))
    if confidence >= high_conf_bypass:
        return True

    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return False
    alnum_chars = [ch for ch in chars if ch.isalnum()]
    alpha_chars = [ch for ch in alnum_chars if ch.isalpha()]
    min_alnum = max(1, int(cfg.get("row_pass_line_prefilter_min_alnum", 2)))
    if len(alnum_chars) < min_alnum:
        return False
    if not alpha_chars:
        return False

    low_conf_threshold = float(cfg.get("row_pass_line_prefilter_low_conf", 22.0))
    if confidence >= low_conf_threshold:
        return True

    alpha_ratio = float(len(alpha_chars)) / max(1.0, float(len(alnum_chars)))
    min_alpha_ratio = max(
        0.0,
        min(1.0, float(cfg.get("row_pass_line_prefilter_min_alpha_ratio", 0.42))),
    )
    if alpha_ratio < min_alpha_ratio:
        return False

    punct_ratio = float(len(chars) - len(alnum_chars)) / max(1.0, float(len(chars)))
    max_punct_ratio = max(
        0.0,
        min(1.0, float(cfg.get("row_pass_line_prefilter_max_punct_ratio", 0.65))),
    )
    if punct_ratio > max_punct_ratio:
        return False
    return True


def _build_row_crops_for_range(
    *,
    gray: QtGui.QImage,
    top: int,
    row_h: int,
    name_width: int,
    is_pre_cropped: bool,
    cfg: dict,
    row_image_looks_right_clipped_fn=None,
) -> list[tuple[str, QtGui.QImage]]:
    clipped_fn = row_image_looks_right_clipped_fn or _row_image_looks_right_clipped
    cropped_width = min(name_width, int(gray.width()))
    row_img = gray.copy(0, top, cropped_width, row_h)
    row_crops: list[tuple[str, QtGui.QImage]] = [("name", row_img)]
    allow_full_width_fallback = bool(cfg.get("row_pass_full_width_fallback", True))
    if not allow_full_width_fallback:
        return row_crops
    if is_pre_cropped or cropped_width >= int(gray.width()):
        return row_crops

    edge_only = bool(cfg.get("row_pass_full_width_edge_only", True))
    edge_clipped = bool(clipped_fn(row_img, cfg))
    if not edge_only or edge_clipped:
        row_crops.append(("full", gray.copy(0, top, int(gray.width()), row_h)))
    return row_crops


def _merge_row_prefix_variants(votes: dict[str, dict[str, object]]) -> int:
    if len(votes) <= 1:
        return max((int(bucket.get("count", 0)) for bucket in votes.values()), default=0)

    removed: set[str] = set()
    ordered = sorted(
        list(votes.items()),
        key=lambda item: len(str((item[1] or {}).get("display", "") or "").strip()),
        reverse=True,
    )
    for long_key, _long_bucket in ordered:
        if long_key in removed or long_key not in votes:
            continue
        long_display = str((votes.get(long_key) or {}).get("display", "") or "").strip()
        if not long_display:
            continue
        long_fold = long_display.casefold()
        for short_key, short_bucket in list(votes.items()):
            if short_key == long_key or short_key in removed:
                continue
            short_display = str((short_bucket or {}).get("display", "") or "").strip()
            if len(short_display) < 6:
                continue
            short_fold = short_display.casefold()
            if not long_fold.startswith(short_fold + " "):
                continue
            target = votes.get(long_key)
            if target is None:
                continue
            target["count"] = int(target.get("count", 0)) + int(short_bucket.get("count", 0))
            target["conf_sum"] = float(target.get("conf_sum", 0.0)) + float(short_bucket.get("conf_sum", 0.0))
            target["conf_weight"] = float(target.get("conf_weight", 0.0)) + float(short_bucket.get("conf_weight", 0.0))
            removed.add(short_key)
    for key in removed:
        votes.pop(key, None)
    return max((int(bucket.get("count", 0)) for bucket in votes.values()), default=0)


def _select_row_names_from_ranked_votes(
    ranked_votes: list[dict[str, object]],
    *,
    cfg: dict,
    best_vote_count: int,
    simple_name_key_fn,
) -> list[str]:
    if not ranked_votes:
        return []

    def _display(entry: dict[str, object]) -> str:
        return str(entry.get("display", "") or "").strip()

    top_name = _display(ranked_votes[0])
    if not top_name:
        return []

    # OCR row segmentation represents one visual row; keep one winner by default.
    if bool(cfg.get("row_pass_single_name_per_row", True)):
        return [top_name]

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
        key = simple_name_key_fn(name)
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
    parse_ctx,
    ocr_import,
    select_variant_paths_fn,
    detect_text_row_ranges_fn,
    build_row_crops_for_range_fn,
    build_row_image_variants_fn,
    merge_row_prefix_variants_fn,
    select_row_names_from_ranked_votes_fn,
    simple_name_key_fn,
    name_display_quality_fn,
    ocr_engine_from_cfg_fn,
    run_ocr_multi_with_cfg_fn,
    run_result_text_fn,
    line_entries_from_run_result_fn,
    line_payload_from_entries_fn,
    build_ocr_run_entry_fn,
) -> tuple[list[str], list[str], list[dict]]:
    selected_paths = select_variant_paths_fn(paths, cfg, max_variants_key="max_variants")
    if not selected_paths:
        return [], [], []

    max_rows = max(1, int(cfg.get("row_pass_max_rows", 12)))
    pad_px = max(0, int(cfg.get("row_pass_pad_px", 2)))
    psm_values = tuple(cfg.get("row_pass_psm_values", (7, 6, 13)))
    timeout_s = max(0.5, float(cfg.get("timeout_s", 8.0)) * max(0.1, float(cfg.get("row_pass_timeout_scale", 0.55))))
    lang = cfg.get("lang")

    engine = ocr_engine_from_cfg_fn(cfg)
    run_ocr_multi = getattr(ocr_import, "run_ocr_multi", None)
    if not callable(run_ocr_multi):
        return [], [], []
    single_name_per_row = bool(cfg.get("row_pass_single_name_per_row", True))
    expected_rows = max(1, int(cfg.get("expected_candidates", 5)))
    primary_candidate_count = max(0, int(cfg.get("primary_candidate_count", 0)))
    primary_complete_margin = max(0, int(cfg.get("row_pass_primary_complete_margin", 1)))
    primary_is_completeish = primary_candidate_count >= max(1, expected_rows - primary_complete_margin)
    if single_name_per_row:
        if primary_is_completeish:
            row_vote_target = max(
                1,
                int(cfg.get("row_pass_vote_target_single_name_when_primary_complete", 1)),
            )
        else:
            row_vote_target = max(1, int(cfg.get("row_pass_vote_target_single_name", 2)))
    else:
        row_vote_target = max(2, int(cfg.get("row_pass_vote_target_multi_name", 3)))
    if (
        primary_is_completeish
        and bool(cfg.get("row_pass_single_psm_when_primary_complete", True))
        and len(psm_values) > 1
    ):
        psm_values = (int(psm_values[0]),)
    stop_when_expected_reached = bool(
        cfg.get("row_pass_stop_when_expected_reached", True)
    )
    full_only_when_name_uncertain = bool(
        cfg.get("row_pass_full_only_when_name_uncertain", True)
    )
    full_only_when_name_uncertain_min_conf = float(
        cfg.get("row_pass_full_only_when_name_uncertain_min_conf", 68.0)
    )
    skip_full_when_name_empty = bool(
        cfg.get("row_pass_skip_full_when_name_empty", True)
    )
    skip_full_when_name_low_conf = bool(
        cfg.get("row_pass_skip_full_when_name_low_conf", True)
    )
    skip_full_when_name_low_conf_max_conf = float(
        cfg.get("row_pass_skip_full_when_name_low_conf_max_conf", 12.0)
    )
    skip_mono_when_non_mono_empty = bool(
        cfg.get("row_pass_skip_mono_when_non_mono_empty", True)
    )
    skip_mono_when_non_mono_low_conf = bool(
        cfg.get("row_pass_skip_mono_when_non_mono_low_conf", True)
    )
    skip_mono_when_non_mono_low_conf_max_conf = float(
        cfg.get("row_pass_skip_mono_when_non_mono_low_conf_max_conf", 12.0)
    )
    row_line_stats_min_conf = float(cfg.get("row_pass_line_stats_min_conf", 8.0))
    early_abort_on_primary_strong = bool(
        cfg.get("row_pass_early_abort_on_primary_strong", True)
    )
    early_abort_probe_rows = max(1, int(cfg.get("row_pass_early_abort_probe_rows", 3)))
    early_abort_probe_rows_when_primary_complete = int(
        cfg.get("row_pass_early_abort_probe_rows_when_primary_complete", 2)
    )
    early_abort_low_conf = float(cfg.get("row_pass_early_abort_low_conf", 22.0))
    early_abort_primary_min_cfg = int(
        cfg.get("row_pass_early_abort_primary_min_candidates", 0)
    )
    if early_abort_primary_min_cfg > 0:
        early_abort_primary_min = max(1, early_abort_primary_min_cfg)
    else:
        early_abort_primary_min = max(4, expected_rows - 2)
    primary_is_strong = primary_candidate_count >= early_abort_primary_min
    if (
        early_abort_probe_rows_when_primary_complete > 0
        and primary_candidate_count >= expected_rows
    ):
        early_abort_probe_rows = min(
            int(early_abort_probe_rows),
            max(1, int(early_abort_probe_rows_when_primary_complete)),
        )
    extra_rows_light_mode = bool(cfg.get("row_pass_extra_rows_light_mode", True))
    extra_rows_light_mode_min_collected_cfg = int(
        cfg.get("row_pass_extra_rows_light_mode_min_collected", 0)
    )
    if extra_rows_light_mode_min_collected_cfg > 0:
        extra_rows_light_mode_min_collected = max(1, extra_rows_light_mode_min_collected_cfg)
    else:
        extra_rows_light_mode_min_collected = max(3, expected_rows - 2)
    mono_retry_only_when_uncertain = bool(
        cfg.get("row_pass_mono_retry_only_when_uncertain", True)
    )
    mono_retry_min_conf = float(cfg.get("row_pass_mono_retry_min_conf", 70.0))
    confident_single_vote_stop = bool(cfg.get("row_pass_confident_single_vote_stop", False))
    if primary_is_completeish and bool(
        cfg.get("row_pass_confident_single_vote_stop_when_primary_complete", True)
    ):
        confident_single_vote_stop = True
    confident_single_vote_min_conf = float(
        cfg.get("row_pass_confident_single_vote_min_conf", 96.0)
    )
    if primary_is_completeish:
        confident_single_vote_min_conf = float(
            cfg.get(
                "row_pass_confident_single_vote_min_conf_when_primary_complete",
                min(96.0, confident_single_vote_min_conf, 72.0),
            )
        )
    consecutive_empty_row_stop = max(0, int(cfg.get("row_pass_consecutive_empty_row_stop", 0)))
    empty_row_stop_min_collected_cfg = int(cfg.get("row_pass_empty_row_stop_min_collected", 0))
    if empty_row_stop_min_collected_cfg > 0:
        empty_row_stop_min_collected = max(1, empty_row_stop_min_collected_cfg)
    else:
        empty_row_stop_min_collected = max(3, int(cfg.get("expected_candidates", 5)) - 1)
    collected_names: list[str] = []
    seen_keys: set[str] = set()
    row_texts: list[str] = []
    runs: list[dict] = []
    consecutive_empty_rows = 0
    cached_candidates_by_line_key: dict[str, str] = {}
    rejected_line_keys: set[str] = set()
    prefix_rows_all_weak = True

    def _pick_best_line_candidate(candidates: list[str]) -> str:
        options = [str(raw or "").strip() for raw in list(candidates or []) if str(raw or "").strip()]
        if not options:
            return ""

        def _looks_like_noise(value: str) -> bool:
            token = "".join(ch for ch in str(value or "") if ch.isalnum())
            if not token:
                return True
            if not any(ch.isalpha() for ch in token):
                return True
            if len(token) <= 2:
                return True
            if str(value).isupper() and len(token) <= 3:
                return True
            return False

        first = options[0]
        if not _looks_like_noise(first):
            return first
        for candidate in options[1:]:
            if not _looks_like_noise(candidate):
                return candidate
        return first

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
    row_ranges = detect_text_row_ranges_fn(gray, cfg)
    if not row_ranges:
        return [], [], []

    effective_max_rows = int(max_rows)
    if bool(cfg.get("fast_mode", True)) and bool(cfg.get("row_pass_adaptive_max_rows", True)):
        expected = max(1, int(cfg.get("expected_candidates", 5)))
        extra_rows = max(0, int(cfg.get("row_pass_adaptive_extra_rows", 2)))
        adaptive_limit = max(5, expected + extra_rows)
        effective_max_rows = min(int(max_rows), int(adaptive_limit))

    name_x_ratio = max(0.35, min(0.9, float(cfg.get("row_pass_name_x_ratio", 0.58))))
    is_pre_cropped = max_width > 0 and source_width <= int(max_width * 0.78)
    if is_pre_cropped:
        name_width = max(8, int(gray.width()))
    else:
        name_width = max(8, int(gray.width() * name_x_ratio))

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        row_path = Path(tmp.name)
    try:
        for idx, (y0, y1) in enumerate(row_ranges[:effective_max_rows], start=1):
            top = max(0, y0 - pad_px)
            bottom = min(gray.height() - 1, y1 + pad_px)
            row_h = max(1, bottom - top + 1)
            is_extra_row_light = (
                extra_rows_light_mode
                and idx > expected_rows
                and len(collected_names) >= extra_rows_light_mode_min_collected
            )
            row_crops = build_row_crops_for_range_fn(
                gray=gray,
                top=top,
                row_h=row_h,
                name_width=name_width,
                is_pre_cropped=is_pre_cropped,
                cfg=cfg,
            )
            if is_extra_row_light and row_crops:
                row_crops = row_crops[:1]
            votes: dict[str, dict[str, object]] = {}
            best_vote_count = 0
            row_finished = False
            row_vote_target_local = 1 if is_extra_row_light else row_vote_target
            name_non_mono_attempts = 0
            name_non_mono_with_text = 0
            name_non_mono_best_conf = -1.0
            name_non_mono_raw_best_conf = -1.0
            row_had_text = False
            row_best_conf = -1.0

            for crop_name, crop_img in row_crops:
                if row_finished:
                    break
                if (
                    crop_name == "full"
                    and full_only_when_name_uncertain
                    and votes
                ):
                    top_best_conf = max(
                        float((bucket or {}).get("best_conf", -1.0))
                        for bucket in votes.values()
                    )
                    if top_best_conf >= full_only_when_name_uncertain_min_conf:
                        continue
                if (
                    crop_name == "full"
                    and skip_full_when_name_empty
                    and not votes
                    and name_non_mono_attempts >= 2
                    and name_non_mono_with_text <= 0
                ):
                    continue
                if (
                    crop_name == "full"
                    and skip_full_when_name_low_conf
                    and not votes
                    and name_non_mono_attempts >= 2
                    and name_non_mono_with_text > 0
                    and 0.0
                    <= float(max(name_non_mono_best_conf, name_non_mono_raw_best_conf))
                    < skip_full_when_name_low_conf_max_conf
                ):
                    continue
                row_variants = build_row_image_variants_fn(crop_img, cfg)
                crop_non_mono_attempts = 0
                crop_non_mono_with_text = 0
                crop_non_mono_best_conf = -1.0
                for variant_name, variant_img in row_variants:
                    is_mono_variant = variant_name.startswith("mono")
                    if is_extra_row_light and variant_name.startswith("mono"):
                        continue
                    if variant_name.startswith("mono") and best_vote_count >= 2:
                        continue
                    if (
                        is_mono_variant
                        and skip_mono_when_non_mono_empty
                        and crop_non_mono_attempts >= 2
                        and crop_non_mono_with_text <= 0
                    ):
                        continue
                    if (
                        is_mono_variant
                        and skip_mono_when_non_mono_low_conf
                        and not votes
                        and crop_non_mono_attempts >= 2
                        and crop_non_mono_with_text > 0
                        and 0.0 <= float(crop_non_mono_best_conf) < skip_mono_when_non_mono_low_conf_max_conf
                    ):
                        continue
                    if (
                        variant_name.startswith("mono")
                        and mono_retry_only_when_uncertain
                        and votes
                        and best_vote_count >= 1
                    ):
                        top_best_conf = max(
                            float((bucket or {}).get("best_conf", -1.0))
                            for bucket in votes.values()
                        )
                        if top_best_conf >= mono_retry_min_conf:
                            continue
                    if not variant_img.save(str(row_path), "PNG"):
                        continue
                    run_result = run_ocr_multi_with_cfg_fn(
                        run_ocr_multi,
                        row_path,
                        cfg=cfg,
                        engine=engine,
                        ocr_cmd="",
                        psm_values=psm_values,
                        timeout_s=timeout_s,
                        lang=lang,
                        stop_on_first_success=False,
                    )
                    text = run_result_text_fn(run_result).strip()
                    if text:
                        row_had_text = True
                    if not is_mono_variant:
                        crop_non_mono_attempts += 1
                        if text:
                            crop_non_mono_with_text += 1
                    if crop_name == "name" and not is_mono_variant:
                        name_non_mono_attempts += 1
                        if text:
                            name_non_mono_with_text += 1
                    line_entries = line_entries_from_run_result_fn(run_result)
                    line_payload = line_payload_from_entries_fn(line_entries)
                    if text:
                        row_texts.append(text)
                    for line_entry in line_payload:
                        line_text = str(line_entry.get("text", "") or "").strip()
                        if not line_text:
                            continue
                        candidate_conf = float(line_entry.get("conf", -1.0))
                        if candidate_conf >= 0.0:
                            row_best_conf = max(row_best_conf, candidate_conf)
                            if not is_mono_variant:
                                crop_non_mono_best_conf = max(crop_non_mono_best_conf, candidate_conf)
                                if crop_name == "name":
                                    name_non_mono_raw_best_conf = max(
                                        name_non_mono_raw_best_conf,
                                        candidate_conf,
                                    )
                        line_entry["parsed_candidates_locked"] = True
                        line_key = simple_name_key_fn(line_text)
                        if line_key and line_key in rejected_line_keys:
                            line_entry["skip_candidate_stats"] = True
                            line_entry["skip_reason"] = "rejected-line-key"
                            line_entry["parsed_candidates"] = []
                            continue
                        cached_candidate = (
                            str(cached_candidates_by_line_key.get(line_key, "")).strip()
                            if line_key
                            else ""
                        )
                        if (
                            candidate_conf >= 0.0
                            and candidate_conf < row_line_stats_min_conf
                            and not cached_candidate
                        ):
                            line_entry["skip_candidate_stats"] = True
                            line_entry["skip_reason"] = "row-low-conf"
                            line_entry["parsed_candidates"] = []
                            if line_key:
                                rejected_line_keys.add(line_key)
                            continue
                        if cached_candidate:
                            candidate = cached_candidate
                            line_entry["parsed_candidates"] = [cached_candidate]
                        else:
                            if not _row_line_passes_prefilter(line_text, candidate_conf, cfg):
                                line_entry["skip_candidate_stats"] = True
                                line_entry["skip_reason"] = "row-prefilter-rejected"
                                line_entry["parsed_candidates"] = []
                                if line_key:
                                    rejected_line_keys.add(line_key)
                                continue
                            parsed_names = parse_ctx.extract_line_candidates(line_text)
                            if not parsed_names:
                                line_entry["skip_candidate_stats"] = True
                                line_entry["skip_reason"] = "row-no-line-candidates"
                                line_entry["parsed_candidates"] = []
                                if line_key:
                                    rejected_line_keys.add(line_key)
                                continue
                            candidate = _pick_best_line_candidate(parsed_names)
                            if not candidate:
                                line_entry["skip_candidate_stats"] = True
                                line_entry["skip_reason"] = "row-empty-best-candidate"
                                line_entry["parsed_candidates"] = []
                                if line_key:
                                    rejected_line_keys.add(line_key)
                                continue
                            if line_key:
                                cached_candidates_by_line_key[line_key] = candidate
                            line_entry["parsed_candidates"] = list(parsed_names)
                        key = simple_name_key_fn(candidate)
                        if not key:
                            continue
                        bucket = votes.setdefault(
                            key,
                            {
                                "count": 0,
                                "display": candidate,
                                "conf_sum": 0.0,
                                "conf_weight": 0.0,
                                "best_conf": -1.0,
                            },
                        )
                        bucket["count"] = int(bucket.get("count", 0)) + 1
                        best_vote_count = max(best_vote_count, int(bucket["count"]))
                        if candidate_conf >= 0.0:
                            bucket["conf_sum"] = float(bucket.get("conf_sum", 0.0)) + candidate_conf
                            bucket["conf_weight"] = float(bucket.get("conf_weight", 0.0)) + 1.0
                            bucket["best_conf"] = max(float(bucket.get("best_conf", -1.0)), candidate_conf)
                        current_display = str(bucket.get("display", "")).strip()
                        if (
                            name_display_quality_fn(candidate) < name_display_quality_fn(current_display)
                            or not current_display
                        ):
                            bucket["display"] = candidate
                        if crop_name == "name" and (not is_mono_variant) and candidate_conf >= 0.0:
                            name_non_mono_best_conf = max(name_non_mono_best_conf, candidate_conf)
                    runs.append(
                        build_ocr_run_entry_fn(
                            pass_label="row",
                            image_ref=f"{source_path.name}#{idx}[{top}:{bottom}]/{crop_name}.{variant_name}",
                            engine=engine,
                            psm_values=psm_values,
                            timeout_s=timeout_s,
                            lang=lang,
                            fast_mode=False,
                            run_result=run_result,
                            line_entries=line_payload,
                        )
                    )
                    if best_vote_count >= row_vote_target_local:
                        row_finished = True
                        break
                    if (
                        confident_single_vote_stop
                        and single_name_per_row
                        and best_vote_count >= 1
                        and votes
                    ):
                        top_bucket = max(
                            votes.values(),
                            key=lambda entry: (
                                int(entry.get("count", 0)),
                                float(entry.get("best_conf", -1.0)),
                            ),
                        )
                        if float(top_bucket.get("best_conf", -1.0)) >= confident_single_vote_min_conf:
                            row_finished = True
                            break

            row_added_name = False
            if votes:
                best_vote_count = merge_row_prefix_variants_fn(votes)
                ranked = sorted(
                    votes.values(),
                    key=lambda entry: (
                        -int(entry.get("count", 0)),
                        -(
                            float(entry.get("conf_sum", 0.0))
                            / max(1.0, float(entry.get("conf_weight", 0.0)))
                        ),
                        name_display_quality_fn(str(entry.get("display", ""))),
                    ),
                )
                selected_names = select_row_names_from_ranked_votes_fn(
                    [dict(entry) for entry in ranked],
                    cfg=cfg,
                    best_vote_count=best_vote_count,
                )
                for best_name in selected_names:
                    key = simple_name_key_fn(best_name)
                    if key and key not in seen_keys:
                        seen_keys.add(key)
                        collected_names.append(best_name)
                        row_added_name = True

            if row_added_name:
                consecutive_empty_rows = 0
            else:
                consecutive_empty_rows += 1
                if (
                    consecutive_empty_row_stop > 0
                    and consecutive_empty_rows >= consecutive_empty_row_stop
                    and len(collected_names) >= empty_row_stop_min_collected
                ):
                    break
            if (
                early_abort_on_primary_strong
                and primary_is_strong
                and idx <= early_abort_probe_rows
            ):
                row_has_strong_signal = bool(
                    row_added_name
                    or (row_had_text and row_best_conf >= early_abort_low_conf)
                )
                if row_has_strong_signal:
                    prefix_rows_all_weak = False
                if (
                    idx >= early_abort_probe_rows
                    and prefix_rows_all_weak
                    and len(collected_names) <= 0
                ):
                    break
            if (
                stop_when_expected_reached
                and idx >= expected_rows
                and len(collected_names) >= expected_rows
            ):
                break
    finally:
        try:
            row_path.unlink(missing_ok=True)
        except Exception:
            pass

    return collected_names, row_texts, runs
