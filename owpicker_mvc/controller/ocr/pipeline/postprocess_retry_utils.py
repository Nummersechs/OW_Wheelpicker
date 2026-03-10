from __future__ import annotations


def score_candidate_set(names: list[str], cfg: dict) -> float:
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


def prefer_retry_candidates(primary: list[str], retry: list[str], cfg: dict) -> bool:
    if not retry:
        return False
    if not primary:
        return True
    return score_candidate_set(retry, cfg) > (score_candidate_set(primary, cfg) + 0.05)


def should_run_recall_retry(
    cfg: dict,
    names: list[str],
    *,
    candidate_set_looks_noisy_fn,
) -> bool:
    if not bool(cfg.get("fast_mode", True)):
        return False
    if not bool(cfg.get("recall_retry_enabled", True)):
        return False
    count = len(names)
    min_candidates = max(0, int(cfg.get("recall_retry_min_candidates", 5)))
    if min_candidates > 0 and count < min_candidates:
        if bool(cfg.get("recall_retry_skip_when_primary_clean", True)):
            shortfall = max(0, min_candidates - count)
            max_shortfall = max(
                0,
                int(cfg.get("recall_retry_skip_primary_clean_max_shortfall", 1)),
            )
            min_count = max(
                1,
                int(cfg.get("recall_retry_skip_primary_clean_min_count", 4)),
            )
            min_avg_conf = float(
                cfg.get("recall_retry_skip_primary_clean_min_avg_conf", 78.0)
            )
            primary_avg_conf = float(cfg.get("primary_line_avg_conf", -1.0))
            conf_ok = primary_avg_conf < 0.0 or primary_avg_conf >= min_avg_conf
            clean_probe_cfg = dict(cfg)
            clean_probe_cfg["expected_candidates"] = max(1, count)
            is_clean_primary = not bool(candidate_set_looks_noisy_fn(names, clean_probe_cfg))
            if (
                count >= min_count
                and shortfall <= max_shortfall
                and conf_ok
                and is_clean_primary
            ):
                return False
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


def is_low_count_candidate_set(cfg: dict, names: list[str]) -> bool:
    min_candidates = max(0, int(cfg.get("recall_retry_min_candidates", 5)))
    return min_candidates > 0 and len(names) < min_candidates


def append_unique_ints(target: list[int], values) -> None:
    for raw_value in tuple(values or ()):
        value = int(raw_value)
        if value not in target:
            target.append(value)


def build_recall_retry_cfg(cfg: dict) -> dict:
    retry_cfg = dict(cfg)
    retry_cfg["fast_mode"] = False
    retry_cfg["stop_after_variant_success"] = False
    timeout_scale = max(1.0, float(cfg.get("recall_retry_timeout_scale", 1.35)))
    retry_cfg["timeout_s"] = max(0.5, float(cfg.get("timeout_s", 8.0)) * timeout_scale)

    psm_values: list[int] = []
    append_unique_ints(psm_values, [cfg.get("psm_primary", 6)])
    if bool(cfg.get("recall_retry_use_fallback_psm", True)):
        append_unique_ints(psm_values, [cfg.get("psm_fallback", 11)])
    append_unique_ints(psm_values, cfg.get("psm_values", ()))
    append_unique_ints(psm_values, cfg.get("retry_extra_psm_values", ()))
    retry_cfg["psm_values"] = tuple(psm_values)
    return retry_cfg


def build_relaxed_support_cfg(cfg: dict) -> dict:
    relaxed = dict(cfg)
    relaxed["name_min_support"] = 1
    relaxed["name_high_count_min_support"] = 1
    return relaxed


def build_strict_extraction_cfg(cfg: dict) -> dict:
    strict = dict(cfg)
    strict["name_min_chars"] = max(3, int(cfg.get("name_min_chars", 2)))
    strict["name_max_digit_ratio"] = min(float(cfg.get("name_max_digit_ratio", 0.45)), 0.30)
    return strict
