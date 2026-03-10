from __future__ import annotations

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
