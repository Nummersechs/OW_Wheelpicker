from __future__ import annotations


def build_runtime_cfg_snapshot(mw, *, sys_platform: str) -> dict:
    def _parse_psm_values(raw) -> list[int]:
        values: list[int] = []
        if isinstance(raw, str):
            parts = raw.replace(";", ",").split(",")
        elif isinstance(raw, (list, tuple, set)):
            parts = list(raw)
        else:
            parts = []
        for part in parts:
            try:
                value = int(str(part).strip())
            except Exception:
                continue
            if value < 0 or value in values:
                continue
            values.append(value)
        return values

    def _parse_easyocr_gpu_value(raw) -> str:
        if isinstance(raw, str):
            token = raw.strip().lower()
            if token in {"", "auto", "best", "gpu", "true", "1", "yes", "on"}:
                return "auto"
            if token in {"cpu", "false", "0", "off", "no"}:
                return "cpu"
            if token in {"mps", "cuda"}:
                return token
            return "auto"
        return "auto" if bool(raw) else "cpu"

    def _cfg_bool_map(entries: list[tuple[str, str, bool]]) -> dict[str, bool]:
        values: dict[str, bool] = {}
        for key, cfg_key, default in entries:
            values[key] = bool(mw._cfg(cfg_key, default))
        return values

    def _cfg_int_map(entries: list[tuple[str, str, int]]) -> dict[str, int]:
        values: dict[str, int] = {}
        for key, cfg_key, default in entries:
            values[key] = int(mw._cfg(cfg_key, default))
        return values

    def _cfg_float_map(entries: list[tuple[str, str, float]]) -> dict[str, float]:
        values: dict[str, float] = {}
        for key, cfg_key, default in entries:
            values[key] = float(mw._cfg(cfg_key, default))
        return values

    def _cfg_optional_str(cfg_key: str, default: str = "") -> str | None:
        return str(mw._cfg(cfg_key, default)).strip() or None

    engine = str(mw._cfg("OCR_ENGINE", "easyocr")).strip().casefold()
    if engine in {"easy", "easy-ocr", "easy_ocr"}:
        engine = "easyocr"
    if engine != "easyocr":
        engine = "easyocr"

    fast_mode = bool(mw._cfg("OCR_FAST_MODE", True))
    default_max_variants = 2 if fast_mode else 0
    if sys_platform == "win32" and fast_mode:
        default_max_variants = 1
    max_variants = int(mw._cfg("OCR_MAX_VARIANTS", default_max_variants))
    if sys_platform == "win32":
        max_variants = int(mw._cfg("OCR_MAX_VARIANTS_WINDOWS", max_variants))
    psm_primary = int(mw._cfg("OCR_PRIMARY_PSM", 11))
    psm_fallback = int(mw._cfg("OCR_FALLBACK_PSM", 6))
    psm_values = [psm_primary]
    if (not fast_mode) and psm_fallback not in psm_values:
        psm_values.append(psm_fallback)
    retry_extra_psm_values = _parse_psm_values(mw._cfg("OCR_RETRY_EXTRA_PSMS", [7, 13]))
    timeout_s = float(mw._cfg("OCR_TIMEOUT_S", 8.0))
    if sys_platform == "win32":
        timeout_s = float(mw._cfg("OCR_TIMEOUT_S_WINDOWS", timeout_s))
    retry_min_candidates = int(mw._cfg("OCR_RECALL_RETRY_MIN_CANDIDATES", 5))
    retry_max_variants = int(mw._cfg("OCR_RECALL_RETRY_MAX_VARIANTS", 4))
    if retry_max_variants < 0:
        retry_max_variants = 0
    row_pass_psm_values = _parse_psm_values(mw._cfg("OCR_ROW_PASS_PSMS", [7, 13, 6]))
    if not row_pass_psm_values:
        row_pass_psm_values = [7, 6, 13]
    quiet_mode = bool(mw._cfg("QUIET", False))
    debug_show_report = bool(mw._cfg("OCR_DEBUG_SHOW_REPORT", False))
    debug_include_report_text = bool(mw._cfg("OCR_DEBUG_INCLUDE_REPORT_TEXT", debug_show_report))
    debug_log_to_file = bool(mw._cfg("OCR_DEBUG_LOG_TO_FILE", True))
    debug_line_analysis = bool(mw._cfg("OCR_DEBUG_LINE_ANALYSIS", True))
    if quiet_mode:
        debug_show_report = False
        debug_include_report_text = False
        debug_log_to_file = False
        debug_line_analysis = False

    easyocr_lang = str(mw._cfg("OCR_EASYOCR_LANG", "en,de,ja,ch_sim,ko")).strip() or None
    cfg = {
        "engine": engine,
        "fast_mode": fast_mode,
        "max_variants": max_variants,
        "psm_primary": psm_primary,
        "psm_fallback": psm_fallback,
        "psm_values": tuple(psm_values),
        "retry_extra_psm_values": tuple(retry_extra_psm_values),
        "lang": easyocr_lang,
        "easyocr_lang": easyocr_lang,
        "easyocr_model_dir": _cfg_optional_str("OCR_EASYOCR_MODEL_DIR"),
        "easyocr_user_network_dir": _cfg_optional_str("OCR_EASYOCR_USER_NETWORK_DIR"),
        "easyocr_gpu": _parse_easyocr_gpu_value(mw._cfg("OCR_EASYOCR_GPU", "auto")),
        "quiet_mode": quiet_mode,
        "timeout_s": timeout_s,
        "debug_show_report": debug_show_report,
        "debug_include_report_text": debug_include_report_text,
        "debug_log_to_file": debug_log_to_file,
        "debug_line_analysis": debug_line_analysis,
        "recall_retry_min_candidates": retry_min_candidates,
        "recall_retry_max_variants": retry_max_variants,
        "row_pass_psm_values": tuple(row_pass_psm_values),
    }
    cfg.update(
        _cfg_bool_map(
            [
                ("stop_after_variant_success", "OCR_STOP_AFTER_FIRST_VARIANT_SUCCESS", True),
                ("fast_mode_confident_line_stop", "OCR_FAST_MODE_CONFIDENT_LINE_STOP", True),
                ("precount_fast_probe_enabled", "OCR_PRECOUNT_FAST_PROBE_ENABLED", True),
                (
                    "precount_fast_probe_single_expected",
                    "OCR_PRECOUNT_FAST_PROBE_SINGLE_EXPECTED",
                    True,
                ),
                ("easyocr_download_enabled", "OCR_EASYOCR_DOWNLOAD_ENABLED", False),
                ("debug_trace_line_mapping", "OCR_DEBUG_TRACE_LINE_MAPPING", True),
                ("recall_retry_enabled", "OCR_RECALL_RETRY_ENABLED", True),
                (
                    "recall_retry_skip_when_primary_clean",
                    "OCR_RECALL_RETRY_SKIP_WHEN_PRIMARY_CLEAN",
                    True,
                ),
                ("recall_retry_use_fallback_psm", "OCR_RECALL_RETRY_USE_FALLBACK_PSM", True),
                ("recall_relax_support_on_low_count", "OCR_RECALL_RELAX_SUPPORT_ON_LOW_COUNT", True),
                ("row_pass_enabled", "OCR_ROW_PASS_ENABLED", True),
                ("row_pass_always_run", "OCR_ROW_PASS_ALWAYS_RUN", True),
                ("row_pass_skip_when_primary_stable", "OCR_ROW_PASS_SKIP_WHEN_PRIMARY_STABLE", True),
                ("row_pass_full_width_fallback", "OCR_ROW_PASS_FULL_WIDTH_FALLBACK", True),
                ("row_pass_full_width_edge_only", "OCR_ROW_PASS_FULL_WIDTH_EDGE_ONLY", True),
                ("row_pass_full_only_when_name_uncertain", "OCR_ROW_PASS_FULL_ONLY_WHEN_NAME_UNCERTAIN", True),
                ("row_pass_skip_full_when_name_empty", "OCR_ROW_PASS_SKIP_FULL_WHEN_NAME_EMPTY", True),
                ("row_pass_skip_full_when_name_low_conf", "OCR_ROW_PASS_SKIP_FULL_WHEN_NAME_LOW_CONF", True),
                ("row_pass_include_mono", "OCR_ROW_PASS_INCLUDE_MONO", True),
                ("row_pass_skip_mono_when_non_mono_empty", "OCR_ROW_PASS_SKIP_MONO_WHEN_NON_MONO_EMPTY", True),
                ("row_pass_skip_mono_when_non_mono_low_conf", "OCR_ROW_PASS_SKIP_MONO_WHEN_NON_MONO_LOW_CONF", True),
                ("row_pass_single_name_per_row", "OCR_ROW_PASS_SINGLE_NAME_PER_ROW", True),
                ("row_pass_confident_single_vote_stop", "OCR_ROW_PASS_CONFIDENT_SINGLE_VOTE_STOP", True),
                (
                    "row_pass_confident_single_vote_stop_when_primary_complete",
                    "OCR_ROW_PASS_CONFIDENT_SINGLE_VOTE_STOP_WHEN_PRIMARY_COMPLETE",
                    True,
                ),
                (
                    "row_pass_single_psm_when_primary_complete",
                    "OCR_ROW_PASS_SINGLE_PSM_WHEN_PRIMARY_COMPLETE",
                    True,
                ),
                ("row_pass_line_prefilter_enabled", "OCR_ROW_PASS_LINE_PREFILTER_ENABLED", True),
                ("row_pass_mono_retry_only_when_uncertain", "OCR_ROW_PASS_MONO_RETRY_ONLY_WHEN_UNCERTAIN", True),
                ("row_pass_extra_rows_light_mode", "OCR_ROW_PASS_EXTRA_ROWS_LIGHT_MODE", True),
                ("row_pass_stop_when_expected_reached", "OCR_ROW_PASS_STOP_WHEN_EXPECTED_REACHED", True),
                ("row_pass_adaptive_max_rows", "OCR_ROW_PASS_ADAPTIVE_MAX_ROWS", True),
                ("row_pass_early_abort_on_primary_strong", "OCR_ROW_PASS_EARLY_ABORT_ON_PRIMARY_STRONG", True),
                ("single_name_per_line", "OCR_SINGLE_NAME_PER_LINE", False),
                ("line_relaxed_fallback", "OCR_LINE_RELAXED_FALLBACK", True),
                ("name_special_char_constraint", "OCR_NAME_SPECIAL_CHAR_CONSTRAINT", False),
                ("name_confidence_filter_noisy_only", "OCR_NAME_CONFIDENCE_FILTER_NOISY_ONLY", True),
            ]
        )
    )
    cfg.update(
        _cfg_int_map(
            [
                ("fast_mode_confident_line_min_lines", "OCR_FAST_MODE_CONFIDENT_LINE_MIN_LINES", 0),
                (
                    "fast_mode_confident_line_missing_tolerance",
                    "OCR_FAST_MODE_CONFIDENT_LINE_MISSING_TOLERANCE",
                    1,
                ),
                (
                    "precount_fast_probe_max_variants",
                    "OCR_PRECOUNT_FAST_PROBE_MAX_VARIANTS",
                    1,
                ),
                ("debug_report_max_chars", "OCR_DEBUG_REPORT_MAX_CHARS", 12000),
                ("debug_line_max_entries_per_run", "OCR_DEBUG_LINE_MAX_ENTRIES_PER_RUN", 40),
                ("debug_trace_max_entries", "OCR_DEBUG_TRACE_MAX_ENTRIES", 220),
                ("recall_retry_max_candidates", "OCR_RECALL_RETRY_MAX_CANDIDATES", 7),
                (
                    "recall_retry_skip_primary_clean_min_count",
                    "OCR_RECALL_RETRY_SKIP_PRIMARY_CLEAN_MIN_COUNT",
                    4,
                ),
                (
                    "recall_retry_skip_primary_clean_max_shortfall",
                    "OCR_RECALL_RETRY_SKIP_PRIMARY_CLEAN_MAX_SHORTFALL",
                    1,
                ),
                ("row_pass_primary_stable_min_candidates", "OCR_ROW_PASS_PRIMARY_STABLE_MIN_CANDIDATES", 0),
                ("row_pass_min_candidates", "OCR_ROW_PASS_MIN_CANDIDATES", 5),
                ("row_pass_brightness_threshold", "OCR_ROW_PASS_BRIGHTNESS_THRESHOLD", 145),
                ("row_pass_merge_gap_px", "OCR_ROW_PASS_MERGE_GAP_PX", 2),
                ("row_pass_min_height_px", "OCR_ROW_PASS_MIN_HEIGHT_PX", 7),
                ("row_pass_max_rows", "OCR_ROW_PASS_MAX_ROWS", 12),
                ("row_pass_pad_px", "OCR_ROW_PASS_PAD_PX", 2),
                ("row_pass_scale_factor", "OCR_ROW_PASS_SCALE_FACTOR", 4),
                ("row_pass_vote_target_single_name", "OCR_ROW_PASS_VOTE_TARGET_SINGLE_NAME", 2),
                (
                    "row_pass_vote_target_single_name_when_primary_complete",
                    "OCR_ROW_PASS_VOTE_TARGET_SINGLE_NAME_WHEN_PRIMARY_COMPLETE",
                    1,
                ),
                ("row_pass_vote_target_multi_name", "OCR_ROW_PASS_VOTE_TARGET_MULTI_NAME", 3),
                ("row_pass_line_prefilter_min_alnum", "OCR_ROW_PASS_LINE_PREFILTER_MIN_ALNUM", 2),
                ("row_pass_primary_complete_margin", "OCR_ROW_PASS_PRIMARY_COMPLETE_MARGIN", 1),
                (
                    "row_pass_primary_stable_relaxed_expected_gap",
                    "OCR_ROW_PASS_PRIMARY_STABLE_RELAXED_EXPECTED_GAP",
                    3,
                ),
                ("row_pass_early_abort_probe_rows", "OCR_ROW_PASS_EARLY_ABORT_PROBE_ROWS", 3),
                (
                    "row_pass_early_abort_probe_rows_when_primary_complete",
                    "OCR_ROW_PASS_EARLY_ABORT_PROBE_ROWS_WHEN_PRIMARY_COMPLETE",
                    2,
                ),
                ("row_pass_early_abort_primary_min_candidates", "OCR_ROW_PASS_EARLY_ABORT_PRIMARY_MIN_CANDIDATES", 0),
                ("row_pass_extra_rows_light_mode_min_collected", "OCR_ROW_PASS_EXTRA_ROWS_LIGHT_MODE_MIN_COLLECTED", 0),
                ("row_pass_adaptive_extra_rows", "OCR_ROW_PASS_ADAPTIVE_EXTRA_ROWS", 2),
                ("row_pass_consecutive_empty_row_stop", "OCR_ROW_PASS_CONSECUTIVE_EMPTY_ROW_STOP", 2),
                ("row_pass_empty_row_stop_min_collected", "OCR_ROW_PASS_EMPTY_ROW_STOP_MIN_COLLECTED", 0),
                ("name_min_chars", "OCR_NAME_MIN_CHARS", 2),
                ("name_max_chars", "OCR_NAME_MAX_CHARS", 24),
                ("name_max_words", "OCR_NAME_MAX_WORDS", 2),
                ("line_recall_max_additions", "OCR_LINE_RECALL_MAX_ADDITIONS", 2),
                ("name_min_support", "OCR_NAME_MIN_SUPPORT", 1),
                ("name_low_confidence_min_support", "OCR_NAME_LOW_CONFIDENCE_MIN_SUPPORT", 2),
                ("name_high_count_threshold", "OCR_NAME_HIGH_COUNT_THRESHOLD", 8),
                ("name_high_count_min_support", "OCR_NAME_HIGH_COUNT_MIN_SUPPORT", 2),
                ("name_max_candidates", "OCR_NAME_MAX_CANDIDATES", 12),
                ("name_near_dup_min_chars", "OCR_NAME_NEAR_DUP_MIN_CHARS", 8),
                ("name_near_dup_max_len_delta", "OCR_NAME_NEAR_DUP_MAX_LEN_DELTA", 1),
                ("name_near_dup_tail_min_chars", "OCR_NAME_NEAR_DUP_TAIL_MIN_CHARS", 3),
            ]
        )
    )
    cfg.update(
        _cfg_float_map(
            [
                ("fast_mode_confident_line_min_avg_conf", "OCR_FAST_MODE_CONFIDENT_LINE_MIN_AVG_CONF", 68.0),
                (
                    "fast_mode_confident_line_min_avg_conf_tolerant",
                    "OCR_FAST_MODE_CONFIDENT_LINE_MIN_AVG_CONF_TOLERANT",
                    78.0,
                ),
                ("recall_retry_short_name_max_ratio", "OCR_RECALL_RETRY_SHORT_NAME_MAX_RATIO", 0.34),
                (
                    "recall_retry_skip_primary_clean_min_avg_conf",
                    "OCR_RECALL_RETRY_SKIP_PRIMARY_CLEAN_MIN_AVG_CONF",
                    78.0,
                ),
                ("recall_retry_timeout_scale", "OCR_RECALL_RETRY_TIMEOUT_SCALE", 1.35),
                ("row_pass_min_pixels_ratio", "OCR_ROW_PASS_MIN_PIXELS_RATIO", 0.015),
                ("row_pass_name_x_ratio", "OCR_ROW_PASS_NAME_X_RATIO", 0.58),
                ("row_pass_projection_x_start_ratio", "OCR_ROW_PASS_PROJECTION_X_START_RATIO", 0.08),
                ("row_pass_projection_x_end_ratio", "OCR_ROW_PASS_PROJECTION_X_END_RATIO", 0.92),
                ("row_pass_projection_col_max_ratio", "OCR_ROW_PASS_PROJECTION_COL_MAX_RATIO", 0.84),
                ("row_pass_full_only_when_name_uncertain_min_conf", "OCR_ROW_PASS_FULL_ONLY_WHEN_NAME_UNCERTAIN_MIN_CONF", 68.0),
                ("row_pass_skip_full_when_name_low_conf_max_conf", "OCR_ROW_PASS_SKIP_FULL_WHEN_NAME_LOW_CONF_MAX_CONF", 12.0),
                ("row_pass_skip_mono_when_non_mono_low_conf_max_conf", "OCR_ROW_PASS_SKIP_MONO_WHEN_NON_MONO_LOW_CONF_MAX_CONF", 12.0),
                ("row_pass_timeout_scale", "OCR_ROW_PASS_TIMEOUT_SCALE", 0.55),
                ("row_pass_confident_single_vote_min_conf", "OCR_ROW_PASS_CONFIDENT_SINGLE_VOTE_MIN_CONF", 96.0),
                (
                    "row_pass_confident_single_vote_min_conf_when_primary_complete",
                    "OCR_ROW_PASS_CONFIDENT_SINGLE_VOTE_MIN_CONF_WHEN_PRIMARY_COMPLETE",
                    72.0,
                ),
                ("row_pass_line_prefilter_low_conf", "OCR_ROW_PASS_LINE_PREFILTER_LOW_CONF", 22.0),
                ("row_pass_line_prefilter_high_conf_bypass", "OCR_ROW_PASS_LINE_PREFILTER_HIGH_CONF_BYPASS", 72.0),
                ("row_pass_line_prefilter_min_alpha_ratio", "OCR_ROW_PASS_LINE_PREFILTER_MIN_ALPHA_RATIO", 0.42),
                ("row_pass_line_prefilter_max_punct_ratio", "OCR_ROW_PASS_LINE_PREFILTER_MAX_PUNCT_RATIO", 0.65),
                ("row_pass_line_stats_min_conf", "OCR_ROW_PASS_LINE_STATS_MIN_CONF", 8.0),
                ("row_pass_mono_retry_min_conf", "OCR_ROW_PASS_MONO_RETRY_MIN_CONF", 70.0),
                ("row_pass_early_abort_low_conf", "OCR_ROW_PASS_EARLY_ABORT_LOW_CONF", 22.0),
                (
                    "row_pass_primary_stable_relaxed_min_avg_conf",
                    "OCR_ROW_PASS_PRIMARY_STABLE_RELAXED_MIN_AVG_CONF",
                    76.0,
                ),
                ("name_max_digit_ratio", "OCR_NAME_MAX_DIGIT_RATIO", 0.45),
                ("name_min_confidence", "OCR_NAME_MIN_CONFIDENCE", 43.0),
                ("name_near_dup_similarity", "OCR_NAME_NEAR_DUP_SIMILARITY", 0.90),
                ("name_near_dup_tail_head_similarity", "OCR_NAME_NEAR_DUP_TAIL_HEAD_SIMILARITY", 0.70),
            ]
        )
    )
    return cfg
