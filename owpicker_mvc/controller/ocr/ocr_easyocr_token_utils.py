from __future__ import annotations

import re
from typing import Any, Iterable

from logic.name_normalization import normalize_name_alnum_key


_OCR_CJK_SCRIPT_RE = re.compile(
    "["
    "\u3040-\u30ff"  # Hiragana/Katakana
    "\u3400-\u4dbf"  # CJK Ext A
    "\u4e00-\u9fff"  # CJK Unified
    "\uf900-\ufaff"  # CJK Compatibility Ideographs
    "\uac00-\ud7af"  # Hangul syllables
    "]"
)


def _contains_cjk_script(text: str) -> bool:
    token = str(text or "").strip()
    if not token:
        return False
    return bool(_OCR_CJK_SCRIPT_RE.search(token))


def _easyocr_sort_key(detection: Any) -> tuple[float, float]:
    try:
        bbox = detection[0]
    except Exception:
        return (0.0, 0.0)
    if not bbox:
        return (0.0, 0.0)
    xs: list[float] = []
    ys: list[float] = []
    try:
        for point in bbox:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            xs.append(float(point[0]))
            ys.append(float(point[1]))
    except Exception:
        return (0.0, 0.0)
    if not xs or not ys:
        return (0.0, 0.0)
    return (min(ys), min(xs))


def _easyocr_detection_to_token(
    detection: Any,
    *,
    group_index: int = 0,
) -> dict[str, float | str] | None:
    try:
        text = str(detection[1] or "").strip()
    except Exception:
        text = ""
    if not text:
        return None
    try:
        raw_conf = float(detection[2])
        confidence = raw_conf * 100.0 if raw_conf <= 1.0 else raw_conf
    except Exception:
        confidence = -1.0

    y0, x0 = _easyocr_sort_key(detection)
    x1 = x0
    y1 = y0
    try:
        bbox = detection[0]
    except Exception:
        bbox = ()
    xs: list[float] = []
    ys: list[float] = []
    try:
        for point in bbox or ():
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            xs.append(float(point[0]))
            ys.append(float(point[1]))
    except Exception:
        xs = []
        ys = []
    if xs:
        x0 = min(xs)
        x1 = max(xs)
    if ys:
        y0 = min(ys)
        y1 = max(ys)
    if x1 < x0:
        x1 = x0
    if y1 < y0:
        y1 = y0
    return {
        "text": text,
        "confidence": float(confidence),
        "x0": float(x0),
        "x1": float(x1),
        "y0": float(y0),
        "y1": float(y1),
        "group_index": float(max(0, int(group_index))),
    }


def _easyocr_token_overlap_ratio(left: dict[str, float | str], right: dict[str, float | str]) -> float:
    try:
        lx0 = float(left.get("x0", 0.0))
        lx1 = float(left.get("x1", lx0))
        ly0 = float(left.get("y0", 0.0))
        ly1 = float(left.get("y1", ly0))
        rx0 = float(right.get("x0", 0.0))
        rx1 = float(right.get("x1", rx0))
        ry0 = float(right.get("y0", 0.0))
        ry1 = float(right.get("y1", ry0))
    except Exception:
        return 0.0
    if lx1 < lx0:
        lx1 = lx0
    if ly1 < ly0:
        ly1 = ly0
    if rx1 < rx0:
        rx1 = rx0
    if ry1 < ry0:
        ry1 = ry0
    inter_w = max(0.0, min(lx1, rx1) - max(lx0, rx0))
    inter_h = max(0.0, min(ly1, ry1) - max(ly0, ry0))
    if inter_w <= 0.0 or inter_h <= 0.0:
        return 0.0
    inter_area = inter_w * inter_h
    left_area = max(1.0, (lx1 - lx0) * (ly1 - ly0))
    right_area = max(1.0, (rx1 - rx0) * (ry1 - ry0))
    return inter_area / max(1.0, min(left_area, right_area))


def _easyocr_token_quality_score(token: dict[str, float | str]) -> float:
    text = str(token.get("text", "") or "").strip()
    if not text:
        return float("-inf")
    try:
        conf = float(token.get("confidence", -1.0))
    except Exception:
        conf = -1.0
    if conf < 0.0:
        conf = 0.0
    group_index = int(float(token.get("group_index", 0.0)))
    primary_bonus = 6.0 if group_index == 0 else 0.0
    alnum = sum(1 for ch in text if ch.isalnum())
    punct = sum(1 for ch in text if (not ch.isalnum()) and (not ch.isspace()))
    return conf + primary_bonus + min(12.0, float(alnum) * 0.25) - (float(punct) * 0.35)


def _easyocr_should_replace_overlapping_token(
    existing: dict[str, float | str],
    candidate: dict[str, float | str],
) -> bool:
    existing_text = str(existing.get("text", "") or "").strip()
    candidate_text = str(candidate.get("text", "") or "").strip()
    existing_has_cjk = _contains_cjk_script(existing_text)
    candidate_has_cjk = _contains_cjk_script(candidate_text)
    try:
        existing_group = int(float(existing.get("group_index", 0.0)))
    except Exception:
        existing_group = 0
    try:
        candidate_group = int(float(candidate.get("group_index", 0.0)))
    except Exception:
        candidate_group = 0

    try:
        existing_conf = float(existing.get("confidence", -1.0))
    except Exception:
        existing_conf = -1.0
    try:
        candidate_conf = float(candidate.get("confidence", -1.0))
    except Exception:
        candidate_conf = -1.0

    if existing_group == 0 and candidate_group > 0:
        if candidate_has_cjk and not existing_has_cjk:
            # Keep script-specific OCR (ja/ko/ch_*) when primary latin reader
            # produced an overlapping non-CJK fallback token.
            return candidate_conf >= max(45.0, existing_conf - 8.0)
        # Keep primary-group text unless it is very weak and the secondary
        # candidate is clearly stronger at the same position.
        return existing_conf < 30.0 and candidate_conf >= (existing_conf + 18.0)
    if existing_group > 0 and candidate_group == 0:
        if existing_has_cjk and not candidate_has_cjk:
            return candidate_conf >= (existing_conf + 25.0)
        # Prefer primary group whenever it is not significantly worse.
        return candidate_conf >= (existing_conf - 5.0)

    return _easyocr_token_quality_score(candidate) > _easyocr_token_quality_score(existing)


def _easyocr_reduce_cross_group_tokens(
    tokens: list[dict[str, float | str]],
    *,
    min_secondary_conf: float = 22.0,
) -> list[dict[str, float | str]]:
    if len(tokens) <= 1:
        return list(tokens)

    reduced: list[dict[str, float | str]] = []
    for token in tokens:
        text = str(token.get("text", "") or "").strip()
        if not text:
            continue
        try:
            group_index = int(float(token.get("group_index", 0.0)))
        except Exception:
            group_index = 0
        try:
            confidence = float(token.get("confidence", -1.0))
        except Exception:
            confidence = -1.0
        if group_index > 0 and confidence >= 0.0 and confidence < float(min_secondary_conf):
            # Secondary-language low-confidence matches are a major source of
            # noisy variants when multiple readers are merged.
            continue

        overlapping_index = -1
        for idx, existing in enumerate(reduced):
            overlap_ratio = _easyocr_token_overlap_ratio(existing, token)
            if overlap_ratio >= 0.58:
                overlapping_index = idx
                break

        if overlapping_index < 0:
            reduced.append(token)
            continue

        existing = reduced[overlapping_index]
        if _easyocr_should_replace_overlapping_token(existing, token):
            reduced[overlapping_index] = token

    return reduced


def _easyocr_group_tokens_to_text_conf_lines(
    tokens: Iterable[dict[str, float | str]],
) -> tuple[tuple[str, float], ...]:
    prepared: list[dict[str, float | str]] = []
    for token in tokens:
        text = str(token.get("text", "") or "").strip()
        if not text:
            continue
        try:
            x0 = float(token.get("x0", 0.0))
            x1 = float(token.get("x1", x0))
            y0 = float(token.get("y0", 0.0))
            y1 = float(token.get("y1", y0))
            confidence = float(token.get("confidence", -1.0))
        except Exception:
            continue
        if x1 < x0:
            x1 = x0
        if y1 < y0:
            y1 = y0
        prepared.append(
            {
                "text": text,
                "x0": x0,
                "x1": x1,
                "y0": y0,
                "y1": y1,
                "confidence": confidence,
            }
        )
    if not prepared:
        return ()

    token_heights = sorted(max(1.0, float(item["y1"]) - float(item["y0"])) for item in prepared)
    median_height = token_heights[len(token_heights) // 2] if token_heights else 12.0
    # Avoid chaining nearby rows into one giant line on noisy detections.
    max_line_height = max(8.0, median_height * 1.85)

    prepared.sort(key=lambda item: (float(item["y0"]), float(item["x0"])))
    line_groups: list[dict[str, Any]] = []

    for token in prepared:
        token_y0 = float(token["y0"])
        token_y1 = float(token["y1"])
        token_h = max(1.0, token_y1 - token_y0)
        token_center = (token_y0 + token_y1) * 0.5

        best_idx = -1
        best_score = float("-inf")
        for idx, line in enumerate(line_groups):
            line_y0 = float(line["y0"])
            line_y1 = float(line["y1"])
            line_h = max(1.0, line_y1 - line_y0)
            line_center = float(line["center"])

            prospective_h = max(line_y1, token_y1) - min(line_y0, token_y0)
            if len(line["tokens"]) >= 1 and prospective_h > max_line_height:
                continue

            overlap = max(0.0, min(token_y1, line_y1) - max(token_y0, line_y0))
            overlap_ratio = overlap / max(1.0, min(token_h, line_h))
            center_delta = abs(token_center - line_center)
            center_limit = max(token_h, line_h) * 0.55 + 1.0
            if overlap_ratio < 0.34 and center_delta > center_limit:
                continue

            score = (overlap_ratio * 2.0) - (center_delta / max(1.0, center_limit))
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx < 0:
            line_groups.append(
                {
                    "y0": token_y0,
                    "y1": token_y1,
                    "center": token_center,
                    "tokens": [token],
                }
            )
            continue

        line = line_groups[best_idx]
        line["tokens"].append(token)
        line["y0"] = min(float(line["y0"]), token_y0)
        line["y1"] = max(float(line["y1"]), token_y1)
        line["center"] = (float(line["y0"]) + float(line["y1"])) * 0.5

    line_groups.sort(key=lambda item: float(item["y0"]))
    lines: list[tuple[str, float]] = []
    for line in line_groups:
        ordered_tokens = sorted(line["tokens"], key=lambda item: float(item["x0"]))
        merged_tokens: list[dict[str, float | str]] = []
        for token in ordered_tokens:
            token_text = str(token.get("text", "") or "").strip()
            if not token_text:
                continue
            token_key = normalize_name_alnum_key(token_text)
            if merged_tokens:
                prev = merged_tokens[-1]
                prev_text = str(prev.get("text", "") or "").strip()
                prev_key = normalize_name_alnum_key(prev_text)
                try:
                    token_x0 = float(token.get("x0", 0.0))
                    token_x1 = float(token.get("x1", token_x0))
                    prev_x0 = float(prev.get("x0", 0.0))
                    prev_x1 = float(prev.get("x1", prev_x0))
                    overlap = max(0.0, min(token_x1, prev_x1) - max(token_x0, prev_x0))
                    min_width = max(1.0, min(token_x1 - token_x0, prev_x1 - prev_x0))
                    overlap_ratio = overlap / min_width
                except Exception:
                    overlap_ratio = 0.0
                if token_key and token_key == prev_key and overlap_ratio >= 0.45:
                    if float(token.get("confidence", -1.0)) > float(prev.get("confidence", -1.0)):
                        merged_tokens[-1] = token
                    continue
            merged_tokens.append(token)

        if not merged_tokens:
            continue

        text = " ".join(str(item.get("text", "") or "").strip() for item in merged_tokens).strip()
        text = re.sub(r"\s+", " ", text)
        if not text:
            continue
        conf_sum = 0.0
        conf_weight = 0.0
        for item in merged_tokens:
            conf = float(item.get("confidence", -1.0))
            if conf < 0.0:
                continue
            weight = max(1.0, float(len(str(item.get("text", "") or "").strip())))
            conf_sum += conf * weight
            conf_weight += weight
        confidence = (conf_sum / conf_weight) if conf_weight > 0.0 else -1.0
        lines.append((text, float(confidence)))

    if not lines:
        return ()

    deduped_lines: list[tuple[str, float]] = []
    seen_index_by_key: dict[str, int] = {}
    for text, confidence in lines:
        token = str(text or "").strip()
        if not token:
            continue
        key = token.lower()
        existing_idx = seen_index_by_key.get(key)
        if existing_idx is None:
            seen_index_by_key[key] = len(deduped_lines)
            deduped_lines.append((token, float(confidence)))
            continue
        existing_text, existing_conf = deduped_lines[existing_idx]
        if float(confidence) > float(existing_conf):
            deduped_lines[existing_idx] = (existing_text, float(confidence))
    return tuple(deduped_lines)
