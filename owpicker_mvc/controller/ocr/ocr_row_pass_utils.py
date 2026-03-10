from __future__ import annotations

from pathlib import Path
import tempfile

from PySide6 import QtGui

from . import ocr_row_pass_helpers as _row_helpers


_detect_text_row_ranges = _row_helpers._detect_text_row_ranges
_build_row_image_variants = _row_helpers._build_row_image_variants
_row_image_looks_right_clipped = _row_helpers._row_image_looks_right_clipped
_row_line_passes_prefilter = _row_helpers._row_line_passes_prefilter
_build_row_crops_for_range = _row_helpers._build_row_crops_for_range
_merge_row_prefix_variants = _row_helpers._merge_row_prefix_variants
_select_row_names_from_ranked_votes = _row_helpers._select_row_names_from_ranked_votes


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

        ranked = sorted(
            options,
            key=lambda value: (
                _looks_like_noise(value),
                sum(1 for ch in str(value or "") if (not ch.isalpha()) and (not ch.isspace())),
                sum(1 for ch in str(value or "") if not ch.isalnum()),
                -sum(1 for ch in str(value or "") if ch.isalpha()),
                -len(str(value or "").strip()),
            ),
        )
        return ranked[0]

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
