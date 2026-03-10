from __future__ import annotations

from difflib import SequenceMatcher
import re

from . import ocr_postprocess_retry_utils as _retry_utils


def _simple_name_key(value: str) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def _trailing_noise_token_count(value: str) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    tokens = [token for token in re.findall(r"[A-Za-z0-9]+|[^A-Za-z0-9\s]", text) if token]
    if not tokens:
        return 0
    count = 0
    seen_non_alpha_tail = False
    for token in reversed(tokens):
        has_alpha = any(ch.isalpha() for ch in token)
        if not has_alpha:
            count += 1
            seen_non_alpha_tail = True
            continue
        if seen_non_alpha_tail and len(token) <= 1:
            count += 1
            continue
        break
    return count


def _suffix_looks_noisy(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if _trailing_noise_token_count(text) > 0:
        return True
    letters = sum(1 for ch in text if ch.isalpha())
    digits = sum(1 for ch in text if ch.isdigit())
    punctuation = sum(1 for ch in text if (not ch.isalnum()) and (not ch.isspace()))
    if letters <= 1 and (digits + punctuation) >= 1:
        return True
    return False


def _name_display_quality(value: str) -> tuple[int, int, int, int]:
    text = str(value or "").strip()
    tail_noise = _trailing_noise_token_count(text)
    non_letter = sum(1 for ch in text if (not ch.isalpha()) and (not ch.isspace()))
    separators = sum(1 for ch in text if not ch.isalnum())
    letters = sum(1 for ch in text if ch.isalpha())
    return (tail_noise, non_letter, separators, -letters)


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
    primary_support = int(bucket.get("primary_support", 0))
    primary_occurrences = int(bucket.get("primary_occurrences", 0))
    conf = float(bucket.get("best_conf", -1.0))
    score = 0.0
    score += support * 2.2
    score += occurrences * 0.35
    score += primary_support * 1.8
    score += primary_occurrences * 0.28
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
    names: list[str],
    cfg: dict,
    stats: dict[str, dict[str, float | int | str]],
) -> list[str]:
    if not names:
        return []
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

    # Keep recall: in default noisy-only mode, avoid shrinking below the
    # expected candidate count just because one line had low confidence.
    expected = max(1, int(cfg.get("expected_candidates", 5)))
    target_floor = min(expected, len(names))
    if noisy_only and len(names) >= target_floor and len(filtered) < target_floor:
        keep_keys = {_simple_name_key(name) for name in filtered}
        for raw in names:
            text = str(raw or "").strip()
            key = _simple_name_key(text)
            if not key or key in keep_keys:
                continue
            filtered.append(text)
            keep_keys.add(key)
            if len(filtered) >= target_floor:
                break
    return filtered


def _merge_prefix_candidate_stats(
    stats: dict[str, dict[str, float | int | str]],
) -> dict[str, dict[str, float | int | str]]:
    """Merge truncated prefix variants into their longer candidate."""
    merged: dict[str, dict[str, float | int | str]] = {
        str(key): dict(value or {})
        for key, value in dict(stats or {}).items()
        if str(key).strip()
    }
    if len(merged) <= 1:
        return merged

    keys_by_length = sorted(
        list(merged.keys()),
        key=lambda key: len(str((merged.get(key) or {}).get("display", "") or "").strip()),
        reverse=True,
    )
    removed: set[str] = set()
    for long_key in keys_by_length:
        if long_key in removed or long_key not in merged:
            continue
        long_bucket = merged.get(long_key) or {}
        long_display = str(long_bucket.get("display", "") or "").strip()
        if not long_display:
            continue
        long_fold = long_display.casefold()
        long_norm = _simple_name_key(long_display)
        consumed_long_key = False
        for short_key, short_bucket in list(merged.items()):
            if short_key == long_key or short_key in removed:
                continue
            short_display = str((short_bucket or {}).get("display", "") or "").strip()
            if len(short_display) < 6:
                continue
            if (len(long_display) - len(short_display)) > 20:
                continue
            short_fold = short_display.casefold()
            strict_prefix_match = long_fold.startswith(short_fold + " ")
            suffix_fragment = ""
            if not strict_prefix_match:
                # Tolerant fallback on normalized keys. This catches OCR
                # variants like "baue ic" vs "baue ich dir ...", while
                # keeping explicit numeric suffix variants distinct.
                short_norm = _simple_name_key(short_display)
                if not short_norm or not long_norm:
                    continue
                if len(short_norm) < 8:
                    continue
                if len(long_norm) <= len(short_norm):
                    continue
                if not long_norm.startswith(short_norm):
                    continue
                suffix = long_norm[len(short_norm):]
                if not suffix or suffix.isdigit():
                    continue
                if len(suffix) > 12:
                    continue
                suffix_fragment = str(suffix or "")
                short_words = len([token for token in short_display.split() if token])
                long_words = len([token for token in long_display.split() if token])
                if short_words < 2 or long_words < short_words:
                    continue
            else:
                suffix_fragment = str(long_display[len(short_display):] or "").strip()

            # If the added suffix mostly looks like OCR tail garbage (e.g.
            # "\"0 ^" / "4 W ^"), keep the shorter cleaner base as canonical.
            if _suffix_looks_noisy(suffix_fragment):
                target_key = short_key
                source_key = long_key
            else:
                target_key = long_key
                source_key = short_key

            target = merged.get(target_key)
            source = merged.get(source_key)
            if target is None:
                continue
            if source is None:
                continue
            target["support"] = int(target.get("support", 0)) + int(source.get("support", 0))
            target["occurrences"] = int(target.get("occurrences", 0)) + int(source.get("occurrences", 0))
            target["primary_support"] = int(target.get("primary_support", 0)) + int(
                source.get("primary_support", 0)
            )
            target["primary_occurrences"] = int(target.get("primary_occurrences", 0)) + int(
                source.get("primary_occurrences", 0)
            )
            target["best_conf"] = max(
                float(target.get("best_conf", -1.0)),
                float(source.get("best_conf", -1.0)),
            )
            target_display = str(target.get("display", "") or "").strip()
            source_display = str(source.get("display", "") or "").strip()
            if (
                source_display
                and (
                    _name_display_quality(source_display) < _name_display_quality(target_display)
                    or not target_display
                )
            ):
                target["display"] = source_display
            removed.add(source_key)
            if source_key == long_key:
                consumed_long_key = True
                break
        if consumed_long_key:
            continue
    for key in removed:
        merged.pop(key, None)
    return merged


def _common_prefix_len(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    idx = 0
    while idx < limit and left[idx] == right[idx]:
        idx += 1
    return idx


def _name_similarity(left: str, right: str) -> float:
    return float(SequenceMatcher(None, left, right).ratio())


def _is_numeric_suffix_variant(left: str, right: str) -> bool:
    left_key = str(left or "").strip()
    right_key = str(right or "").strip()
    if not left_key or not right_key or left_key == right_key:
        return False
    shorter, longer = (left_key, right_key) if len(left_key) <= len(right_key) else (right_key, left_key)
    if not longer.startswith(shorter):
        return False
    suffix = longer[len(shorter):]
    return bool(suffix) and suffix.isdigit()


def _merge_near_duplicate_candidate_stats(
    stats: dict[str, dict[str, float | int | str]],
    cfg: dict,
) -> dict[str, dict[str, float | int | str]]:
    """
    Merge minor OCR spelling variants (especially low-support repass noise)
    into the stronger candidate bucket.
    """
    merged: dict[str, dict[str, float | int | str]] = {
        str(key): dict(value or {})
        for key, value in dict(stats or {}).items()
        if str(key).strip()
    }
    if len(merged) <= 1:
        return merged

    min_chars_cfg = max(2, int(cfg.get("name_near_dup_min_chars", 8)))
    min_chars = max(5, min_chars_cfg - 2)
    base_len_delta = max(0, int(cfg.get("name_near_dup_max_len_delta", 1)))
    base_similarity = max(0.0, min(1.0, float(cfg.get("name_near_dup_similarity", 0.90))))
    strict_similarity = min(0.99, max(base_similarity, 0.95))
    low_support_similarity = max(0.78, min(base_similarity, 0.92) - 0.08)

    def _strength(key: str) -> tuple[int, int, int, int, float, tuple[int, int], int]:
        bucket = merged.get(key) or {}
        display = str(bucket.get("display", "") or "").strip()
        return (
            int(bucket.get("primary_support", 0)),
            int(bucket.get("primary_occurrences", 0)),
            int(bucket.get("support", 0)),
            int(bucket.get("occurrences", 0)),
            float(bucket.get("best_conf", -1.0)),
            tuple(-x for x in _name_display_quality(display)),
            len(display),
        )

    changed = True
    while changed and len(merged) > 1:
        changed = False
        keys = list(merged.keys())
        keys.sort(key=lambda key: _strength(key), reverse=True)

        for idx, left_key in enumerate(keys):
            if left_key not in merged:
                continue
            left_bucket = merged.get(left_key) or {}
            left_norm = _simple_name_key(str(left_bucket.get("display", "") or ""))
            if len(left_norm) < min_chars:
                continue
            left_support = int(left_bucket.get("support", 0))
            left_strength = _strength(left_key)
            for right_key in keys[idx + 1:]:
                if right_key not in merged or right_key == left_key:
                    continue
                right_bucket = merged.get(right_key) or {}
                right_norm = _simple_name_key(str(right_bucket.get("display", "") or ""))
                if len(right_norm) < min_chars:
                    continue
                if _is_numeric_suffix_variant(left_norm, right_norm):
                    # Keep explicit numeric suffix variants as distinct names,
                    # e.g. "player" vs "player2" from separate rows.
                    continue
                support_floor = min(left_support, int(right_bucket.get("support", 0)))
                len_delta_cap = base_len_delta + (1 if support_floor <= 1 else 0)
                if abs(len(left_norm) - len(right_norm)) > len_delta_cap:
                    continue
                similarity = _name_similarity(left_norm, right_norm)
                if support_floor <= 1:
                    threshold = low_support_similarity
                else:
                    threshold = strict_similarity
                if similarity < threshold:
                    continue
                if similarity < strict_similarity:
                    # For looser low-support merges, require a meaningful shared
                    # prefix so distinct names with similar shape are preserved.
                    if _common_prefix_len(left_norm, right_norm) < 4:
                        continue

                right_strength = _strength(right_key)
                if right_strength > left_strength:
                    target_key, source_key = right_key, left_key
                else:
                    target_key, source_key = left_key, right_key

                target = merged.get(target_key)
                source = merged.get(source_key)
                if target is None or source is None:
                    continue
                target["support"] = int(target.get("support", 0)) + int(source.get("support", 0))
                target["occurrences"] = int(target.get("occurrences", 0)) + int(source.get("occurrences", 0))
                target["primary_support"] = int(target.get("primary_support", 0)) + int(
                    source.get("primary_support", 0)
                )
                target["primary_occurrences"] = int(target.get("primary_occurrences", 0)) + int(
                    source.get("primary_occurrences", 0)
                )
                target["best_conf"] = max(
                    float(target.get("best_conf", -1.0)),
                    float(source.get("best_conf", -1.0)),
                )
                target_display = str(target.get("display", "") or "").strip()
                source_display = str(source.get("display", "") or "").strip()
                if (
                    source_display
                    and (
                        _name_display_quality(source_display) < _name_display_quality(target_display)
                        or not target_display
                    )
                ):
                    target["display"] = source_display
                merged.pop(source_key, None)
                changed = True
                break
            if changed:
                break
    return merged


def _should_run_row_pass(cfg: dict, names: list[str]) -> bool:
    def _looks_clean_for_expected(expected_count: int) -> bool:
        probe_cfg = dict(cfg)
        probe_cfg["expected_candidates"] = max(1, int(expected_count))
        return not _candidate_set_looks_noisy(names, probe_cfg)

    if not bool(cfg.get("row_pass_enabled", True)):
        return False
    if bool(cfg.get("row_pass_always_run", True)):
        if bool(cfg.get("row_pass_skip_when_primary_stable", False)):
            expected = max(1, int(cfg.get("expected_candidates", 5)))
            stable_min_default = max(3, expected - 1)
            stable_min = max(
                1,
                int(cfg.get("row_pass_primary_stable_min_candidates", stable_min_default)),
            )
            if len(names) >= stable_min and _looks_clean_for_expected(expected):
                return False
            primary_count = max(0, int(cfg.get("primary_candidate_count", 0)))
            relaxed_gap = max(
                0,
                int(cfg.get("row_pass_primary_stable_relaxed_expected_gap", 3)),
            )
            primary_avg_conf = float(cfg.get("primary_line_avg_conf", -1.0))
            relaxed_min_avg_conf = float(
                cfg.get("row_pass_primary_stable_relaxed_min_avg_conf", 76.0)
            )
            confidence_is_reliable = (
                primary_avg_conf < 0.0 or primary_avg_conf >= relaxed_min_avg_conf
            )
            expected_gap = expected - primary_count
            if (
                primary_count > 0
                and expected_gap > 0
                and expected_gap <= relaxed_gap
                and len(names) >= max(3, primary_count - 1)
                and confidence_is_reliable
                and _looks_clean_for_expected(primary_count)
            ):
                return False
        return True
    row_pass_min_candidates = max(1, int(cfg.get("row_pass_min_candidates", 5)))
    if len(names) < row_pass_min_candidates:
        return True
    max_candidates = max(0, int(cfg.get("recall_retry_max_candidates", 7)))
    if max_candidates > 0 and len(names) > max_candidates:
        return True
    return _candidate_set_looks_noisy(names, cfg)


def _score_candidate_set(names: list[str], cfg: dict) -> float:
    return _retry_utils.score_candidate_set(names, cfg)


def _prefer_row_candidates(current: list[str], row_names: list[str], cfg: dict) -> bool:
    if not row_names:
        return False
    if not current:
        return True
    expected = max(1, int(cfg.get("expected_candidates", 5)))
    current_count = len(current)
    row_count = len(row_names)
    if row_count < current_count:
        # Preserve recall when the primary pass is already near target and not
        # obviously noisy; row-pass is allowed to replace only if primary
        # looks unstable.
        stable_primary_rows = max(0, int(cfg.get("precount_rows_primary_stable", 0)))
        primary_near_target = current_count >= max(3, expected - 1)
        if primary_near_target and (
            stable_primary_rows >= current_count
            or not _candidate_set_looks_noisy(current, cfg)
        ):
            return False
    current_score = _score_candidate_set(current, cfg)
    row_score = _score_candidate_set(row_names, cfg)
    current_delta = abs(current_count - expected)
    row_delta = abs(row_count - expected)
    if row_delta < current_delta:
        return True
    if row_score > (current_score + 0.05):
        return True
    if row_delta == current_delta and _candidate_set_looks_noisy(current, cfg):
        return row_score >= (current_score - 0.15)
    return False


def _prefer_retry_candidates(primary: list[str], retry: list[str], cfg: dict) -> bool:
    return _retry_utils.prefer_retry_candidates(primary, retry, cfg)


def _candidate_stats_from_runs(
    runs: list[dict],
    parse_ctx,
    *,
    trace_entries: list[dict] | None = None,
    include_debug_meta: bool = False,
) -> dict[str, dict[str, float | int | str]]:
    stats: dict[str, dict[str, float | int | str]] = {}
    slot_best: dict[str, dict[str, object]] = {}

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

        # Keep parser order by default; only demote obvious noise candidates.
        # This preserves parser ranking semantics and still avoids trivial junk.
        for candidate in options:
            if not _looks_like_noise(candidate):
                return candidate
        return options[0]

    def _pick_candidate_for_run(candidates: list[str], seen_keys: set[str]) -> tuple[str, str]:
        options = [str(raw or "").strip() for raw in list(candidates or []) if str(raw or "").strip()]
        if not options:
            return "", "no-options"

        best = _pick_best_line_candidate(options)
        best_key = _simple_name_key(best)
        if best and best_key and best_key not in seen_keys:
            return best, "best"

        # If the strongest option is already consumed in this run, prefer the
        # next valid alternative to preserve one distinct candidate per line.
        for candidate in options:
            key = _simple_name_key(candidate)
            if not key or key in seen_keys:
                continue
            return candidate, "alternate-after-duplicate"
        return best, "best-duplicate"

    def _line_debug_meta(line_text: str) -> dict[str, str]:
        if trace_entries is None or (not include_debug_meta):
            return {}
        debug_fn = getattr(parse_ctx, "extract_debug_for_text", None)
        if not callable(debug_fn):
            return {}
        try:
            _names, entries = debug_fn(line_text)
        except Exception:
            return {}
        if not entries:
            return {}
        entry = dict(entries[0] or {})
        return {
            "strict_status": str(entry.get("status", "") or "").strip(),
            "strict_reason": str(entry.get("reason", "") or "").strip(),
            "strict_cleaned": str(entry.get("cleaned", "") or "").strip(),
        }

    def _support_slot_id(
        *,
        pass_name: str,
        image_ref: str,
        run_index: int,
        line_index: int,
    ) -> str:
        normalized_pass = str(pass_name or "").strip().casefold()
        # Use one shared line-slot namespace across passes so row-pass
        # alternatives compete with already observed primary/retry line winners
        # instead of inflating support as additional independent lines.
        if normalized_pass in {"primary", "retry"}:
            return f"line:{int(line_index)}"
        if normalized_pass == "row":
            match = re.search(r"#(\d+)\[", str(image_ref or ""))
            if match:
                row_index = int(match.group(1))
                # Some row runs can still contain multiple text lines for one
                # crop; preserve their relative line positions.
                return f"line:{int(row_index + max(0, int(line_index) - 1))}"
        return f"{normalized_pass}:run:{int(run_index)}:line:{int(line_index)}"

    def _support_entry_score(
        *,
            pass_name: str,
            candidate: str,
            line_conf: float,
            run_index: int,
            selection_reason: str,
    ) -> tuple[int, int, int, int, int, int, int, int, int, float, int]:
        quality = _name_display_quality(candidate)
        text = str(candidate or "").strip()
        letters = sum(1 for ch in text if ch.isalpha())
        alnum_len = sum(1 for ch in text if ch.isalnum())
        digit_count = sum(1 for ch in text if ch.isdigit())
        normalized_pass = str(pass_name or "").strip().casefold()
        if normalized_pass in {"primary", "retry"}:
            pass_priority = 2
        elif normalized_pass == "row":
            pass_priority = 1
        else:
            pass_priority = 0
        short_token_penalty = 1 if letters <= 2 else 0
        conf_known = 1 if line_conf >= 0.0 else 0
        best_choice = 1 if str(selection_reason or "") == "best" else 0
        # Slot ranking should keep stable primary/retry winners over row-pass
        # overrides and avoid short/noisy variants winning solely by confidence.
        return (
            pass_priority,
            best_choice,
            -int(quality[0]),
            -int(short_token_penalty),
            -int(digit_count),
            int(letters),
            int(alnum_len),
            -int(quality[2]),
            conf_known,
            float(line_conf),
            -int(run_index),
        )

    for run_index, run in enumerate(runs, start=1):
        seen_in_run: set[str] = set()
        pass_name = str(run.get("pass", "") or "").strip()
        normalized_pass_name = pass_name.casefold()
        image_ref = str(run.get("image", "") or "").strip()
        line_entries = list(run.get("lines") or [])
        if not line_entries:
            line_entries = [
                {"text": line.strip(), "conf": -1.0}
                for line in str(run.get("text", "")).splitlines()
                if line.strip()
            ]
        for line_index, line in enumerate(line_entries, start=1):
            line_text = str(line.get("text", "")).strip()
            if not line_text:
                continue
            try:
                line_conf = float(line.get("conf", -1.0))
            except Exception:
                line_conf = -1.0
            skip_candidate_stats = bool(line.get("skip_candidate_stats", False))
            skip_reason = str(line.get("skip_reason", "") or "").strip()
            parsed_candidates_locked = bool(line.get("parsed_candidates_locked", False))
            trace_payload: dict[str, object] | None = None
            if trace_entries is not None:
                trace_payload = {
                    "pass": str(run.get("pass", "") or "").strip(),
                    "image": str(run.get("image", "") or "").strip(),
                    "run_index": run_index,
                    "line_index": line_index,
                    "line": line_text,
                    "line_conf": line_conf,
                }
                trace_payload.update(_line_debug_meta(line_text))
            if skip_candidate_stats:
                if trace_payload is not None:
                    trace_payload["parsed_candidates_locked"] = parsed_candidates_locked
                    trace_payload["parsed_candidates"] = []
                    trace_payload["drop_reason"] = skip_reason or "skip-candidate-stats"
                    trace_entries.append(trace_payload)
                continue
            parsed_candidates_hint = line.get("parsed_candidates")
            if isinstance(parsed_candidates_hint, (list, tuple)):
                parsed_names = [
                    str(raw or "").strip()
                    for raw in list(parsed_candidates_hint)
                    if str(raw or "").strip()
                ]
            else:
                parsed_names = []
            if (not parsed_names) and (not parsed_candidates_locked):
                parsed_names = parse_ctx.extract_line_candidates(line_text)
            if trace_payload is not None:
                trace_payload["parsed_candidates_locked"] = parsed_candidates_locked
                trace_payload["parsed_candidates"] = list(parsed_names)
            if not parsed_names:
                if trace_payload is not None:
                    if parsed_candidates_locked:
                        trace_payload["drop_reason"] = "locked-empty-candidates"
                    else:
                        trace_payload["drop_reason"] = "no-line-candidates"
                    trace_entries.append(trace_payload)
                continue
            parsed, selection_reason = _pick_candidate_for_run(parsed_names, seen_in_run)
            key = _simple_name_key(parsed)
            if not key:
                if trace_payload is not None:
                    trace_payload["selected_candidate"] = parsed
                    trace_payload["selection_reason"] = selection_reason
                    trace_payload["drop_reason"] = "invalid-selected-key"
                    trace_entries.append(trace_payload)
                continue
            bucket = stats.setdefault(
                key,
                {
                    "display": parsed,
                    "support": 0,
                    "occurrences": 0,
                    "primary_support": 0,
                    "primary_occurrences": 0,
                    "best_conf": -1.0,
                },
            )
            bucket["occurrences"] = int(bucket.get("occurrences", 0)) + 1
            if normalized_pass_name in {"primary", "retry"}:
                bucket["primary_occurrences"] = int(bucket.get("primary_occurrences", 0)) + 1
            current_display = str(bucket.get("display", "")).strip()
            if (
                _name_display_quality(parsed) < _name_display_quality(current_display)
                or not current_display
            ):
                bucket["display"] = parsed
            if line_conf >= 0.0:
                bucket["best_conf"] = max(float(bucket.get("best_conf", -1.0)), line_conf)
            if key not in seen_in_run:
                seen_in_run.add(key)

            slot_id = _support_slot_id(
                pass_name=pass_name,
                image_ref=image_ref,
                run_index=run_index,
                line_index=line_index,
            )
            score = _support_entry_score(
                pass_name=pass_name,
                candidate=parsed,
                line_conf=line_conf,
                run_index=run_index,
                selection_reason=selection_reason,
            )
            current_slot_best = slot_best.get(slot_id)
            if (current_slot_best is None) or (
                score > tuple(current_slot_best.get("score", ()))
            ):
                slot_best[slot_id] = {
                    "key": key,
                    "pass_name": normalized_pass_name,
                    "score": score,
                    "trace_payload": trace_payload,
                }
            if trace_payload is not None:
                trace_payload["selected_candidate"] = parsed
                trace_payload["selected_key"] = key
                trace_payload["selection_reason"] = selection_reason
                trace_payload["occurrence_incremented"] = True
                trace_payload["support_incremented"] = False
                trace_entries.append(trace_payload)

    for slot_payload in slot_best.values():
        key = str(slot_payload.get("key", "") or "").strip()
        if not key:
            continue
        bucket = stats.get(key)
        if bucket is not None:
            bucket["support"] = int(bucket.get("support", 0)) + 1
            slot_pass_name = str(slot_payload.get("pass_name", "") or "").strip().casefold()
            if slot_pass_name in {"primary", "retry"}:
                bucket["primary_support"] = int(bucket.get("primary_support", 0)) + 1
        trace_payload = slot_payload.get("trace_payload")
        if isinstance(trace_payload, dict):
            trace_payload["support_incremented"] = True
    return stats


def _build_final_names_from_runs(
    *,
    cfg: dict,
    stats: dict[str, dict[str, float | int | str]],
    preferred_names: list[str],
    primary_names: list[str],
    retry_names: list[str],
    row_names: list[str],
    row_preferred: bool = False,
) -> list[str]:
    stats = {
        str(key): dict(bucket or {})
        for key, bucket in dict(stats or {}).items()
        if str(key).strip()
    }
    for seed_name in list(preferred_names) + list(primary_names) + list(retry_names) + list(row_names):
        text = str(seed_name or "").strip()
        key = _simple_name_key(text)
        if not key:
            continue
        bucket = stats.setdefault(
            key,
            {
                "display": text,
                "support": 1,
                "occurrences": 1,
                "primary_support": 0,
                "primary_occurrences": 0,
                "best_conf": -1.0,
            },
        )
        current_display = str(bucket.get("display", "")).strip()
        if not current_display or _name_display_quality(text) < _name_display_quality(current_display):
            bucket["display"] = text

    # Seed names from row/retry/preferred can reintroduce low-support OCR variants.
    # Re-merge after seeding so minor repass spellings collapse into stronger buckets.
    stats = _merge_prefix_candidate_stats(stats)
    stats = _merge_near_duplicate_candidate_stats(stats, cfg)

    if not stats:
        ordered_seeds = list(preferred_names)
        if row_preferred:
            ordered_seeds.extend(list(row_names))
            ordered_seeds.extend(list(primary_names))
            ordered_seeds.extend(list(retry_names))
        else:
            ordered_seeds.extend(list(primary_names))
            ordered_seeds.extend(list(retry_names))
            ordered_seeds.extend(list(row_names))
        return _dedupe_names_in_order(ordered_seeds)

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
        for key, bucket in ranked_all:
            if key in selected_keys:
                continue
            text = str(bucket.get("display", "") or "").strip()
            support = int(bucket.get("support", 0))
            conf = float(bucket.get("best_conf", -1.0))
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
        restricted: list[str] = []
        restricted_set: set[str] = set()

        def _resolve_preferred_key(preferred_key: str) -> str | None:
            if preferred_key in selected_keys and preferred_key not in restricted_set:
                return preferred_key
            stripped_preferred = re.sub(r"\d+$", "", str(preferred_key or ""))
            best_key: str | None = None
            best_score = -1.0
            for candidate_key in selected_keys:
                if candidate_key in restricted_set:
                    continue
                candidate = str(candidate_key or "")
                similarity = _name_similarity(str(preferred_key or ""), candidate)
                if similarity < 0.86:
                    continue
                prefix_len = _common_prefix_len(str(preferred_key or ""), candidate)
                stripped_candidate = re.sub(r"\d+$", "", candidate)
                stripped_match = bool(
                    stripped_preferred
                    and stripped_candidate
                    and stripped_preferred == stripped_candidate
                )
                if (not stripped_match) and prefix_len < 6 and similarity < 0.92:
                    continue
                score = similarity + (0.05 if stripped_match else 0.0) + min(0.06, prefix_len * 0.003)
                if score > best_score:
                    best_score = score
                    best_key = candidate_key
            return best_key

        for key in preferred_keys:
            resolved_key = _resolve_preferred_key(key)
            if not resolved_key:
                continue
            restricted.append(resolved_key)
            restricted_set.add(resolved_key)

        if restricted:
            # Keep preferred order, but do not shrink below expected just
            # because merged/canonicalized keys differ from seed key forms.
            if len(restricted) < expected:
                for key, _bucket in ranked_all:
                    if key not in selected_keys or key in restricted_set:
                        continue
                    restricted.append(key)
                    restricted_set.add(key)
                    if len(restricted) >= expected:
                        break
            selected_keys = set(restricted)
        else:
            selected_keys = preferred_set

    seed_sequences: list[list[str]] = [list(preferred_names)]
    if row_preferred:
        seed_sequences.extend([list(row_names), list(primary_names), list(retry_names)])
    else:
        seed_sequences.extend([list(primary_names), list(retry_names), list(row_names)])

    seed_key_order: list[str] = []
    seen_seed_keys: set[str] = set()
    for sequence in seed_sequences:
        for seed in sequence:
            key = _simple_name_key(seed)
            if not key or key in seen_seed_keys:
                continue
            seen_seed_keys.add(key)
            seed_key_order.append(key)
    for key in stats.keys():
        if key in seen_seed_keys:
            continue
        seen_seed_keys.add(key)
        seed_key_order.append(key)

    ordered_keys = [key for key in seed_key_order if key in selected_keys]
    ordered_key_set = set(ordered_keys)
    if len(ordered_keys) < len(selected_keys):
        remaining = [key for key in selected_keys if key not in ordered_key_set]
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
        soft_cap = row_count
    elif row_count >= 3:
        soft_cap = min(expected + 1, row_count + 1)
    else:
        soft_cap = expected + 2
    if len(names) > soft_cap:
        names = names[:soft_cap]

    return names


def _should_run_recall_retry(cfg: dict, names: list[str]) -> bool:
    return _retry_utils.should_run_recall_retry(
        cfg,
        names,
        candidate_set_looks_noisy_fn=_candidate_set_looks_noisy,
    )


def _is_low_count_candidate_set(cfg: dict, names: list[str]) -> bool:
    return _retry_utils.is_low_count_candidate_set(cfg, names)


def _append_unique_ints(target: list[int], values) -> None:
    _retry_utils.append_unique_ints(target, values)


def _build_recall_retry_cfg(cfg: dict) -> dict:
    return _retry_utils.build_recall_retry_cfg(cfg)


def _build_relaxed_support_cfg(cfg: dict) -> dict:
    return _retry_utils.build_relaxed_support_cfg(cfg)


def _build_strict_extraction_cfg(cfg: dict) -> dict:
    return _retry_utils.build_strict_extraction_cfg(cfg)
