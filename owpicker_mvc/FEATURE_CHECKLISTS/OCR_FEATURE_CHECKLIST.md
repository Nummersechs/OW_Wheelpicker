# OCR Feature, Logic and Test Checklist

## Purpose
This file documents the OCR subsystem end-to-end:
- feature map
- hidden/non-obvious logic
- expected behavior/output
- practical checklist for validation and regression tests

Scope: `owpicker_mvc/controller/ocr/*`

---

## OCR Flow (Expected Behavior)
1. Capture starts via `on_role_ocr_import_clicked` in `ocr_capture_ops.py`.
2. Region is selected (`Qt selector` or `macOS native screencapture`).
3. OCR image variants are generated (`build_ocr_pixmap_variants`).
4. Runtime config snapshot is created (`_ocr_runtime_cfg_snapshot`) from `config.py`.
5. EasyOCR readiness is checked (`easyocr_available`).
6. OCR passes run:
- primary pass
- optional recall retry pass
- optional row-segmentation pass
7. Candidate extraction, merge, dedupe, and ordering are applied.
8. Final candidates are mapped into role import flow (`ocr_role_import.py`) and shown in picker.
9. Debug/trace reports and logs are written when enabled.

Expected result:
- stable candidate count near expected rows
- one logical winner per visual row
- minimal duplicates/variants
- line order preserved as much as possible

---

## Feature Map (by Module)
## `ocr_capture_ops.py`
- capture orchestration, async worker launch, busy overlay
- variant image generation
- complete OCR pass pipeline orchestration
- expected-row estimation and clamping
- ordering + slot reconciliation
- integration with debug report and role import

## `ocr_import.py`
- EasyOCR runtime setup and reader caching
- language parsing + grouping
- model directory discovery and diagnostics
- OCR token-to-line grouping
- cross-group overlap reduction
- candidate parsing/cleanup from OCR text

## `ocr_engine_utils.py`
- pass execution helper utilities
- run result normalization
- line parser context cache
- extraction merge helper between pass outputs

## `ocr_row_pass_utils.py`
- visual row detection and segmentation
- row crop generation and variants (base/scaled/mono/full-width fallback)
- row-level vote and winner selection

## `ocr_postprocess_utils.py`
- candidate stats build from OCR runs
- confidence filtering
- near-duplicate merging
- pass preference decisions (`primary` vs `retry` vs `row`)

## `ocr_ordering_utils.py`
- trace-slot mapping
- order reconstruction from trace
- duplicate collapse in same slot
- refill to target count while preserving order

## `ocr_debug_utils.py`
- debug report text
- debug logfile append
- debug dialog rendering

## `ocr_role_import.py`
- normalization and dedupe for selected names
- resolve selected OCR candidates
- add/import helpers

---

## Hidden Logic and Non-Obvious Rules
## Language + model behavior
- CJK languages are split into dedicated EasyOCR groups with English pairing.
- Multi-group OCR can return partial readiness (`some groups ready, some missing`).
- English fallback can be used when multi-language readers fail due to missing models.
- Diagnostics include `reader=ready|partial|failed` and detailed hints.

## OCR token merge behavior
- detections are sorted top-to-bottom/left-to-right by bbox.
- tokens are merged into lines via overlap + center-distance heuristics.
- overlap-based cross-group conflict resolution prefers primary group unless weak.
- low-confidence secondary group tokens are filtered to reduce noise.

## Candidate parsing behavior
- bullet/numbering prefixes are stripped.
- metadata suffix after pipe-like separators is trimmed.
- emoji/icon suffix content is ignored.
- assignment-like lines can map to left-side identifier (`A=B` -> `A`) in config-like text.
- duplicates are deduped by normalized alnum key, not only exact text.
- numeric suffix names (for example `Name`/`Name2`) are intentionally preserved when valid.

## Row-pass behavior
- rows are detected using brightness projection across multiple thresholds/ratios.
- dynamic row limits and early-abort shortcuts reduce expensive calls.
- optional full-width crop fallback is used only when uncertainty/edge clipping suggests it.
- optional mono retries are skipped when non-mono signals are already strong/empty.
- default behavior keeps one winner per detected visual row.

## Ordering behavior
- slot-aware ordering can prioritize row trace or primary trace depending on mode.
- alias logic can keep positions stable for OCR variants of the same logical name.
- same-slot duplicates are collapsed using similarity/prefix/suffix heuristics.

---

## Expected Output and Error Patterns
## `run_easyocr(...)` expected output
- Success: `OCRRunResult(text="<line1>\\n<line2>...", error=None, lines=(...))`
- No text found: `OCRRunResult(text="", error=None, lines=())`
- Reader/model issue: `OCRRunResult(text="", error="easyocr-init-error:...")`
- Runtime issue: `OCRRunResult(text="", error="easyocr-run-error[<group>]:...")`

## `easyocr_resolution_diagnostics(...)` expected fields
- `engine=easyocr`
- `requested_lang=...`
- `normalized_langs=...`
- `lang_groups=...`
- `reader=ready|partial|failed`
- `reader_groups_ready=...` (when any groups are ready)
- `reader_error=...` (when any groups fail)
- `hint=...` and `hint_action=...` for actionable remediation

## Import behavior
- If OCR is not ready, import aborts with user-facing message and diagnostics.
- If OCR is ready, async extraction starts and overlay state is restored on completion.

---

## Configuration Checklist (Core OCR Keys)
- [ ] `OCR_ENGINE` is `easyocr`.
- [ ] `OCR_EASYOCR_LANG` matches your real language need (avoid unnecessary languages).
- [ ] `OCR_EASYOCR_DOWNLOAD_ENABLED` matches strategy:
- [ ] `True` for first-time model download.
- [ ] `False` for strict offline runtime.
- [ ] `OCR_EASYOCR_MODEL_DIR` is set if shipping bundled offline models.
- [ ] `OCR_FAST_MODE` is enabled for responsiveness.
- [ ] `OCR_ROW_PASS_*` values are tuned for your capture style.
- [ ] `OCR_DEBUG_LOG_TO_FILE` is enabled while tuning; disabled in quiet release if needed.

---

## Functional Test Checklist
## A. Environment and models
- [ ] `easyocr` imports without errors.
- [ ] model folder exists and contains required `.pth` files for configured languages.
- [ ] diagnostics show `reader=ready` (or `partial` with intended fallback behavior).

## B. Capture and startup
- [ ] region capture works on current OS path (Qt selector/macOS native).
- [ ] busy overlay appears during OCR and always closes.
- [ ] no stuck cursor or blocked UI after cancel/failure.

## C. Core OCR quality
- [ ] all visible rows are detected in clean screenshot.
- [ ] long lines are not truncated unexpectedly.
- [ ] duplicate lines are not produced at list end.
- [ ] one visual row does not create two final names unless explicitly allowed.

## D. Language behavior
- [ ] mixed Latin + CJK names are recognized in correct rows.
- [ ] missing CJK model does not break complete OCR flow when fallback should apply.
- [ ] enabling extra languages does not regress baseline Latin recognition too much.

## E. Ordering behavior
- [ ] final output order matches visual row order.
- [ ] swapped tail rows are not present after stabilization.
- [ ] dropped row (if any) is replaced by best alternative without large reorder.

## F. Postprocess behavior
- [ ] near-duplicate variants collapse correctly.
- [ ] genuine numeric suffix variants (for example `Name`/`Name2`) are preserved when from different rows.
- [ ] noisy one-off low-confidence tokens are filtered.

## G. Role import mapping
- [ ] selected OCR names map correctly into target role(s).
- [ ] all-role import respects assignment/subrole flags.
- [ ] duplicate selected names are handled as expected.

## H. Logs and diagnostics
- [ ] `ocr_debug.log` contains run traces and actionable hints.
- [ ] flow trace aligns with visible OCR behavior.
- [ ] debug report does not exceed configured limits unexpectedly.

## I. Performance
- [ ] first run latency acceptable.
- [ ] repeated run latency stable.
- [ ] no major freeze during row pass / retry pass.

---

## Automated Regression Commands
- [ ] `PYTHONPATH=owpicker_mvc python3 -m unittest owpicker_mvc.tests.test_ocr_import -q`
- [ ] `PYTHONPATH=owpicker_mvc python3 -m unittest owpicker_mvc.tests.test_ocr_capture_ops -q`
- [ ] `PYTHONPATH=owpicker_mvc python3 -m unittest owpicker_mvc.tests.test_main_window_ocr_import -q`

---

## Full Function/Class Index (OCR Package)
### ocr_role_import.py
- class `PendingOCRImport`
- def `normalize_name_key`
- def `name_key_set`
- def `collect_new_names`
- def `resolve_selected_candidates`
- def `add_names`

### ocr_async_worker_utils.py
- class `_OCRExtractWorker`
- class `_OCRResultRelay`

### ocr_row_pass_utils.py
- def `_detect_text_row_ranges`
- def `_build_row_image_variants`
- def `_row_image_looks_right_clipped`
- def `_row_line_passes_prefilter`
- def `_build_row_crops_for_range`
- def `_merge_row_prefix_variants`
- def `_select_row_names_from_ranked_votes`
- def `_run_row_segmentation_pass`

### ocr_import.py
- class `OCRRunResult`
- class `OCRLineResult`
- def `_parse_ocr_lang_tokens`
- def `_parse_easyocr_langs`
- def `_build_easyocr_lang_groups`
- def `_normalize_easyocr_gpu_mode`
- def `_torch_device_support`
- def `_resolve_easyocr_device`
- def `_apply_torch_warning_filters`
- def `_patch_dataloader_pin_memory`
- def `_resolve_optional_directory`
- def `_looks_like_easyocr_model_dir`
- def `_discover_easyocr_model_dir`
- def `_import_easyocr_module`
- def `_runtime_search_roots`
- def `_cached_easyocr_reader`
- def `_resolve_easyocr_reader`
- def `_resolve_easyocr_group_readers`
- def `_reader_errors_indicate_missing_models`
- def `_should_try_easyocr_english_fallback`
- def `_resolve_easyocr_english_fallback_reader`
- def `easyocr_resolution_diagnostics`
- def `easyocr_available`
- def `clear_ocr_runtime_caches`
- def `_easyocr_sort_key`
- def `_easyocr_detection_to_token`
- def `_easyocr_token_overlap_ratio`
- def `_easyocr_token_quality_score`
- def `_easyocr_should_replace_overlapping_token`
- def `_easyocr_reduce_cross_group_tokens`
- def `_easyocr_group_tokens_to_lines`
- def `run_easyocr`
- def `run_ocr_multi`
- def `_strip_after_first_emoji`
- def `_strip_trailing_short_noise_suffix`
- def `_strip_metadata_suffix_ocr_token`
- def `_looks_like_constant_identifier`
- def `_strip_assignment_suffix_ocr_token`
- def `_looks_like_name`
- def `_candidate_key`
- def `_display_name_quality`
- def `_should_prefer_display_name`
- def `_normalized_tokens`
- def `_is_numeric_suffix_variant`
- def `_is_constant_prefix_variant`
- def `_find_near_duplicate_key`
- def `_extract_candidate_names_impl`
- def `extract_candidate_names`
- def `extract_candidate_names_debug`
- def `extract_candidate_names_multi`

### ocr_postprocess_utils.py
- def `_simple_name_key`
- def `_trailing_noise_token_count`
- def `_suffix_looks_noisy`
- def `_name_display_quality`
- def `_dedupe_names_in_order`
- def `_candidate_bucket_score`
- def `_select_candidate_keys_from_stats`
- def `_candidate_set_looks_noisy`
- def `_filter_low_confidence_candidates`
- def `_merge_prefix_candidate_stats`
- def `_common_prefix_len`
- def `_name_similarity`
- def `_is_numeric_suffix_variant`
- def `_merge_near_duplicate_candidate_stats`
- def `_should_run_row_pass`
- def `_score_candidate_set`
- def `_prefer_row_candidates`
- def `_prefer_retry_candidates`
- def `_candidate_stats_from_runs`
- def `_build_final_names_from_runs`
- def `_should_run_recall_retry`
- def `_is_low_count_candidate_set`
- def `_append_unique_ints`
- def `_build_recall_retry_cfg`
- def `_build_relaxed_support_cfg`
- def `_build_strict_extraction_cfg`

### ocr_debug_utils.py
- def `_build_ocr_debug_report`
- def `ocr_preview_text`
- def `_append_ocr_debug_log`
- def `_show_ocr_debug_report`
- def `_handle_ocr_selection_error`

### ocr_ordering_utils.py
- def `_safe_int`
- def `_entry_participates_in_order`
- def `_trace_slot_index`
- def `_build_trace_order_context`
- def `order_names_by_line_trace`
- def `collapse_slot_duplicates`
- def `refill_names_to_target`

### ocr_engine_utils.py
- def `_line_extractor_kwargs`
- def `_multi_extractor_kwargs`
- def `_line_entry_text`
- def `_line_entry_conf`
- def `_run_result_text`
- def `_run_result_error`
- def `_ocr_engine_from_cfg`
- def `_easyocr_runner_kwargs`
- def `_easyocr_resolution_kwargs`
- def `_run_ocr_multi_with_cfg`
- def `_build_ocr_run_entry`
- def `_line_entries_from_run_result`
- class `_OCRLineParseContext`
- def `_extract_names_from_texts`
- def `_run_ocr_pass`
- def `_truncate_report_text`
- def `_extract_line_debug_for_text`
- def `_line_payload_from_entries`

### ocr_capture_ops.py
- def `_ocr_import_module`
- def `_screen_selector_module`
- def `select_region_from_primary_screen`
- def `select_region_with_macos_screencapture`
- def `_restore_override_cursor`
- def `_cancel_ocr_cache_release`
- def `_schedule_ocr_cache_release`
- def `_show_ocr_busy_overlay`
- def `_hide_ocr_busy_overlay`
- def `_mark_ocr_runtime_activated`
- def `_capture_region_with_qt_selector`
- def `capture_region_for_ocr`
- def `build_ocr_pixmap_variants`
- def `extract_names_from_ocr_pixmap`
- def `_ocr_runtime_cfg_snapshot`
- def `_prepare_ocr_variant_files`
- def `_cleanup_temp_paths`
- def `_select_variant_paths`
- def `_merge_ocr_texts_unique_lines`
- def `_config_identifier_hints`
- def `_normalize_identifier_candidate`
- def `_looks_like_identifier_candidate`
- def `_expand_config_identifier_prefixes`
- def `_run_ocr_pass`
- def `_build_row_crops_for_range`
- def `_select_row_names_from_ranked_votes`
- def `_run_row_segmentation_pass`
- def `_estimate_expected_rows_from_paths`
- def `_run_line_count`
- def `_stable_primary_line_count`
- def `_primary_line_count_bounds`
- def `_primary_avg_line_confidence`
- def `_resolve_effective_precount_rows`
- def `_resolve_precount_row_bounds`
- def `_precount_extra_allowance_from_stats`
- def `_clamp_names_to_expected_count`
- def `_refill_names_to_target`
- def `_order_names_by_line_trace`
- def `_collapse_names_by_trace_slots`
- def `_order_names_by_seed_sequence`
- def `_reconcile_row_overflow_with_primary_slots`
- def `_build_ocr_debug_report`
- class `_OCRPassFlowState`
- def `_replace_names_if_better`
- def `_order_and_collapse_by_trace`
- def `_primary_order_inversions`
- def `_collect_optional_pass_flow`
- def `_build_effective_cfg_and_seed_names`
- def `_build_names_from_candidate_runs`
- def `_stabilize_row_preferred_names`
- def `_extract_names_from_ocr_files`
- class `_OCRExtractWorker`
- def `_start_ocr_async_import`
- def `on_role_ocr_import_clicked`

