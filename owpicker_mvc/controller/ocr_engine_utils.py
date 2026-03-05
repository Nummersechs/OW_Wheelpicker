from __future__ import annotations

from pathlib import Path


def _line_extractor_kwargs(cfg: dict) -> dict[str, object]:
    return {
        "min_chars": int(cfg.get("name_min_chars", 2)),
        "max_chars": int(cfg.get("name_max_chars", 24)),
        "max_words": int(cfg.get("name_max_words", 2)),
        "max_digit_ratio": float(cfg.get("name_max_digit_ratio", 0.45)),
        "enforce_special_char_constraint": bool(cfg.get("name_special_char_constraint", True)),
    }


def _multi_extractor_kwargs(cfg: dict) -> dict[str, object]:
    kwargs = _line_extractor_kwargs(cfg)
    kwargs.update(
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
    return kwargs


def _line_entry_text(value) -> str:
    if isinstance(value, dict):
        return str(value.get("text", "") or "").strip()
    return str(getattr(value, "text", "") or "").strip()


def _line_entry_conf(value) -> float:
    try:
        if isinstance(value, dict):
            return float(value.get("conf", value.get("confidence", -1.0)))
        return float(getattr(value, "confidence", -1.0))
    except Exception:
        return -1.0


def _run_result_text(run_result) -> str:
    return str(getattr(run_result, "text", "") or "")


def _run_result_error(run_result) -> str:
    return str(getattr(run_result, "error", "") or "")


def _ocr_engine_from_cfg(cfg: dict) -> str:
    return str(cfg.get("engine", "easyocr")).strip().casefold() or "easyocr"


def _easyocr_runner_kwargs(cfg: dict) -> dict[str, object]:
    return {
        "easyocr_model_dir": cfg.get("easyocr_model_dir"),
        "easyocr_user_network_dir": cfg.get("easyocr_user_network_dir"),
        "easyocr_gpu": cfg.get("easyocr_gpu", "auto"),
        "easyocr_download_enabled": bool(cfg.get("easyocr_download_enabled", False)),
        "easyocr_quiet": bool(cfg.get("quiet_mode", False)),
    }


def _easyocr_resolution_kwargs(cfg: dict) -> dict[str, object]:
    return {
        "lang": cfg.get("easyocr_lang"),
        "model_dir": cfg.get("easyocr_model_dir"),
        "user_network_dir": cfg.get("easyocr_user_network_dir"),
        "gpu": cfg.get("easyocr_gpu", "auto"),
        "download_enabled": bool(cfg.get("easyocr_download_enabled", False)),
        "quiet": bool(cfg.get("quiet_mode", False)),
    }


def _run_ocr_multi_with_cfg(
    run_ocr_multi,
    image_path: Path,
    *,
    cfg: dict,
    engine: str,
    ocr_cmd: str,
    psm_values: tuple[int, ...],
    timeout_s: float,
    lang,
    stop_on_first_success: bool,
):
    return run_ocr_multi(
        image_path,
        engine=engine,
        cmd=str(ocr_cmd or ""),
        psm_values=psm_values,
        timeout_s=timeout_s,
        lang=lang,
        stop_on_first_success=bool(stop_on_first_success),
        **_easyocr_runner_kwargs(cfg),
    )


def _build_ocr_run_entry(
    *,
    pass_label: str,
    image_ref: str,
    engine: str,
    psm_values: tuple[int, ...],
    timeout_s: float,
    lang,
    fast_mode: bool,
    run_result,
    line_entries: list[dict] | None = None,
) -> dict:
    payload = list(line_entries) if line_entries is not None else _line_entries_from_run_result(run_result)
    return {
        "pass": str(pass_label),
        "image": str(image_ref),
        "engine": engine,
        "psm_values": list(psm_values),
        "timeout_s": timeout_s,
        "lang": str(lang or ""),
        "fast_mode": bool(fast_mode),
        "text": _run_result_text(run_result),
        "error": _run_result_error(run_result),
        "lines": payload,
    }


def _line_entries_from_run_result(run_result) -> list[dict]:
    line_entries: list[dict] = []
    for entry in tuple(getattr(run_result, "lines", ()) or ()):
        line_text = _line_entry_text(entry)
        if not line_text:
            continue
        line_entries.append({"text": line_text, "conf": _line_entry_conf(entry)})
    if line_entries:
        return line_entries
    for raw_line in _run_result_text(run_result).splitlines():
        line_text = raw_line.strip()
        if line_text:
            line_entries.append({"text": line_text, "conf": -1.0})
    return line_entries


class _OCRLineParseContext:
    """Caches OCR line parsing/debug extraction for one import run."""

    def __init__(self, ocr_import, cfg: dict):
        self._ocr_import = ocr_import
        self._line_kwargs = _line_extractor_kwargs(cfg)
        self._line_relaxed_fallback = bool(cfg.get("line_relaxed_fallback", True))
        self._line_relaxed_kwargs = dict(self._line_kwargs)
        self._line_relaxed_kwargs["enforce_special_char_constraint"] = False
        self._line_relaxed_kwargs["max_words"] = max(
            int(self._line_kwargs.get("max_words", 2)),
            int(cfg.get("name_max_words", 2)) + 1,
        )
        self._line_relaxed_kwargs["max_chars"] = max(
            int(self._line_kwargs.get("max_chars", 24)),
            int(cfg.get("name_max_chars", 24)) + 8,
        )
        self._line_relaxed_kwargs["max_digit_ratio"] = min(
            0.85,
            max(
                float(self._line_kwargs.get("max_digit_ratio", 0.45)),
                float(cfg.get("name_max_digit_ratio", 0.45)) + 0.20,
            ),
        )
        self._line_cache: dict[str, tuple[str, ...]] = {}
        self._debug_cache: dict[str, tuple[list[str], list[dict]]] = {}

    def extract_line_candidates(self, line_text: str) -> list[str]:
        text = str(line_text or "").strip()
        if not text:
            return []
        cached = self._line_cache.get(text)
        if cached is not None:
            return list(cached)
        extractor = getattr(self._ocr_import, "extract_candidate_names", None)
        if not callable(extractor):
            self._line_cache[text] = ()
            return []

        def _extract_with(kwargs: dict[str, object]) -> list[str]:
            try:
                return [
                    str(value).strip()
                    for value in list(extractor(text, **kwargs) or [])
                    if str(value).strip()
                ]
            except Exception:
                return []

        def _looks_like_noise_candidate(value: str) -> bool:
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

        try:
            parsed = _extract_with(self._line_kwargs)
            if self._line_relaxed_fallback:
                strict_has_useful = any(not _looks_like_noise_candidate(item) for item in parsed)
                if (not parsed) or (not strict_has_useful):
                    relaxed = _extract_with(self._line_relaxed_kwargs)
                    if relaxed:
                        seen = {
                            "".join(ch.lower() for ch in item if ch.isalnum())
                            for item in parsed
                        }
                        merged = list(parsed)
                        for item in relaxed:
                            key = "".join(ch.lower() for ch in str(item) if ch.isalnum())
                            if not key or key in seen:
                                continue
                            seen.add(key)
                            merged.append(item)
                        parsed = merged if merged else relaxed
        except Exception:
            parsed = []
        cached_value = tuple(parsed)
        self._line_cache[text] = cached_value
        return list(cached_value)

    def extract_debug_for_text(self, text: str) -> tuple[list[str], list[dict]]:
        normalized = str(text or "")
        cached = self._debug_cache.get(normalized)
        if cached is not None:
            return list(cached[0]), [dict(entry) for entry in cached[1]]
        extractor = getattr(self._ocr_import, "extract_candidate_names_debug", None)
        if not callable(extractor):
            self._debug_cache[normalized] = ([], [])
            return [], []
        try:
            names, entries = extractor(normalized, **self._line_kwargs)
            resolved_names = [str(name).strip() for name in list(names or []) if str(name).strip()]
            resolved_entries = [dict(entry) for entry in list(entries or []) if isinstance(entry, dict)]
        except Exception:
            resolved_names, resolved_entries = [], []
        self._debug_cache[normalized] = (list(resolved_names), list(resolved_entries))
        return list(resolved_names), [dict(entry) for entry in resolved_entries]


def _extract_names_from_texts(ocr_import, texts: list[str], cfg: dict) -> list[str]:
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

    extractor = getattr(ocr_import, "extract_candidate_names_multi", None)
    if callable(extractor):
        extracted = list(extractor(texts, **_multi_extractor_kwargs(cfg)) or [])
        line_ctx = _OCRLineParseContext(ocr_import, cfg)
        ordered_line_candidates: list[str] = []
        line_candidate_keys: set[str] = set()
        for text in list(texts or []):
            for raw_line in str(text or "").splitlines():
                parsed = line_ctx.extract_line_candidates(raw_line)
                if not parsed:
                    continue
                chosen = _pick_best_line_candidate(parsed)
                if not chosen:
                    continue
                key = "".join(ch.lower() for ch in chosen if ch.isalnum())
                if not key or key in line_candidate_keys:
                    continue
                line_candidate_keys.add(key)
                ordered_line_candidates.append(chosen)

        if bool(cfg.get("single_name_per_line", False)):
            # Guardrail: one OCR line should contribute at most one candidate.
            if not line_candidate_keys:
                return extracted
            filtered: list[str] = []
            seen: set[str] = set()
            for candidate in extracted:
                key = "".join(ch.lower() for ch in str(candidate or "") if ch.isalnum())
                if not key or key not in line_candidate_keys or key in seen:
                    continue
                seen.add(key)
                filtered.append(str(candidate).strip())
            for candidate in ordered_line_candidates:
                key = "".join(ch.lower() for ch in str(candidate or "") if ch.isalnum())
                if not key or key in seen:
                    continue
                seen.add(key)
                filtered.append(candidate)
            return filtered or extracted

        # Recall assist: if strict multi-line extraction missed one/two lines,
        # enrich with line-level fallback candidates (strict+relaxed parser).
        if not ordered_line_candidates:
            return extracted
        if not extracted:
            return list(ordered_line_candidates)
        if len(ordered_line_candidates) <= len(extracted):
            return extracted

        max_additions = max(0, int(cfg.get("line_recall_max_additions", 2)))
        if max_additions == 0:
            return extracted

        merged = [str(candidate).strip() for candidate in extracted if str(candidate).strip()]
        merged_keys = {"".join(ch.lower() for ch in name if ch.isalnum()) for name in merged}
        additions = 0
        for candidate in ordered_line_candidates:
            key = "".join(ch.lower() for ch in str(candidate or "") if ch.isalnum())
            if not key or key in merged_keys:
                continue
            merged.append(candidate)
            merged_keys.add(key)
            additions += 1
            if additions >= max_additions:
                break
        return merged
    # Legacy fallback for lightweight test stubs without multi support.
    line_ctx = _OCRLineParseContext(ocr_import, cfg)
    seen: set[str] = set()
    resolved: list[str] = []
    for text in list(texts or []):
        for raw_line in str(text or "").splitlines():
            parsed = line_ctx.extract_line_candidates(raw_line)
            if not parsed:
                continue
            candidate = _pick_best_line_candidate(parsed)
            if not candidate:
                continue
            key = "".join(ch.lower() for ch in candidate if ch.isalnum())
            if not key or key in seen:
                continue
            seen.add(key)
            resolved.append(candidate)
    return resolved


def _run_ocr_pass(
    paths: list[Path],
    *,
    pass_label: str,
    cfg: dict,
    max_variants_key: str,
    ocr_cmd: str,
    ocr_import,
    select_variant_paths_fn,
) -> tuple[list[str], list[str], list[dict]]:
    selected_paths = select_variant_paths_fn(paths, cfg, max_variants_key=max_variants_key)
    if not selected_paths:
        return [], ["no-variant-paths"], []

    all_texts: list[str] = []
    errors: list[str] = []
    runs: list[dict] = []
    engine = _ocr_engine_from_cfg(cfg)
    fast_mode = bool(cfg.get("fast_mode", True))
    stop_after_variant_success = bool(cfg.get("stop_after_variant_success", True)) and fast_mode
    confident_line_stop = bool(cfg.get("fast_mode_confident_line_stop", True)) and fast_mode
    confident_line_min_lines_cfg = int(cfg.get("fast_mode_confident_line_min_lines", 0))
    confident_line_min_avg_conf = float(cfg.get("fast_mode_confident_line_min_avg_conf", 68.0))
    confident_line_missing_tolerance = max(
        0,
        int(cfg.get("fast_mode_confident_line_missing_tolerance", 1)),
    )
    confident_line_min_avg_conf_tolerant = float(
        cfg.get("fast_mode_confident_line_min_avg_conf_tolerant", 78.0)
    )
    psm_values = tuple(cfg.get("psm_values", (6, 11)))
    lang = cfg.get("lang")
    timeout_s = float(cfg.get("timeout_s", 8.0))
    run_ocr_multi = getattr(ocr_import, "run_ocr_multi", None)
    run_tesseract_multi = getattr(ocr_import, "run_tesseract_multi", None)
    if not callable(run_ocr_multi) and not callable(run_tesseract_multi):
        return [], ["ocr-runner-unavailable"], []

    for image_path in selected_paths:
        if callable(run_ocr_multi):
            run_result = _run_ocr_multi_with_cfg(
                run_ocr_multi,
                image_path,
                cfg=cfg,
                engine=engine,
                ocr_cmd=ocr_cmd,
                psm_values=psm_values,
                timeout_s=timeout_s,
                lang=lang,
                stop_on_first_success=stop_after_variant_success,
            )
        else:
            run_result = run_tesseract_multi(
                image_path,
                cmd=str(ocr_cmd or "auto"),
                psm_values=psm_values,
                timeout_s=timeout_s,
                lang=lang,
                stop_on_first_success=stop_after_variant_success,
            )
        line_entries = _line_entries_from_run_result(run_result)
        runs.append(
            _build_ocr_run_entry(
                pass_label=pass_label,
                image_ref=str(image_path),
                engine=engine,
                psm_values=psm_values,
                timeout_s=timeout_s,
                lang=lang,
                fast_mode=fast_mode,
                run_result=run_result,
                line_entries=line_entries,
            )
        )
        text = _run_result_text(run_result)
        if text:
            all_texts.append(text)
            if stop_after_variant_success:
                break
            if confident_line_stop and len(selected_paths) > 1:
                expected_lines = max(1, int(cfg.get("expected_candidates", 5)))
                min_lines = (
                    max(1, int(confident_line_min_lines_cfg))
                    if confident_line_min_lines_cfg > 0
                    else max(1, expected_lines - confident_line_missing_tolerance)
                )
                line_count = int(sum(1 for entry in line_entries if str(entry.get("text", "") or "").strip()))
                if line_count <= 0:
                    line_count = int(sum(1 for raw_line in str(text).splitlines() if str(raw_line).strip()))
                conf_values: list[float] = []
                for entry in line_entries:
                    try:
                        conf_value = float(entry.get("conf", -1.0))
                    except Exception:
                        conf_value = -1.0
                    if conf_value >= 0.0:
                        conf_values.append(conf_value)
                if conf_values:
                    avg_conf = sum(conf_values) / max(1, len(conf_values))
                    conf_threshold = confident_line_min_avg_conf
                    if line_count < expected_lines:
                        conf_threshold = max(conf_threshold, confident_line_min_avg_conf_tolerant)
                    confident_enough = avg_conf >= conf_threshold
                else:
                    # For text-only OCR results without per-line confidence,
                    # require one additional line over the target before
                    # stopping early.
                    confident_enough = line_count >= (min_lines + 1)
                if line_count >= min_lines and confident_enough:
                    break
        else:
            error_text = _run_result_error(run_result)
            if error_text:
                errors.append(error_text)
    return all_texts, errors, runs


def _truncate_report_text(value: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...<truncated>"


def _extract_line_debug_for_text(parse_ctx: _OCRLineParseContext, text: str) -> tuple[list[str], list[dict]]:
    return parse_ctx.extract_debug_for_text(text)


def _line_payload_from_entries(entries: list[object]) -> list[dict]:
    payload: list[dict] = []
    for entry in entries:
        line_text = _line_entry_text(entry)
        if not line_text:
            continue
        payload.append({"text": line_text, "conf": _line_entry_conf(entry)})
    return payload
