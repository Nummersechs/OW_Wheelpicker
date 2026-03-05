from __future__ import annotations

import re


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _entry_participates_in_order(entry: dict) -> bool:
    # Keep ordering robust even when support assignment changes due to
    # slot-level winner selection. Occurrence indicates the line was
    # actually observed and selected for this run/line.
    return bool(entry.get("support_incremented", False)) or bool(
        entry.get("occurrence_incremented", False)
    )


def _trace_slot_index(
    entry: dict,
    *,
    pass_name: str,
    run_index: int,
    line_index: int,
) -> int:
    normalized_pass = str(pass_name or "").strip().casefold()
    if normalized_pass == "row":
        image_ref = str(entry.get("image", "") or "")
        match = re.search(r"#(\d+)\[", image_ref)
        if match:
            try:
                row_index = max(1, int(match.group(1)))
                return max(1, int(row_index + max(0, int(line_index) - 1)))
            except Exception:
                return max(1, int(run_index))
        return max(1, int(run_index))
    if normalized_pass in {"primary", "retry"}:
        return max(1, int(line_index))
    return max(1, int(run_index))


def _build_trace_order_context(
    *,
    trace_entries: list[dict] | None,
    row_preferred: bool,
    simple_name_key_fn,
    name_similarity_fn,
    common_prefix_len_fn,
) -> dict[str, object]:
    if row_preferred:
        pass_order = {"row": 0, "primary": 1, "retry": 2}
    else:
        pass_order = {"primary": 0, "retry": 1, "row": 2}

    trace_list = list(trace_entries or [])

    # Infer row slot index even when image refs are plain variant labels
    # (`name.base`, `full.base`) without explicit `#<row>[...]`.
    row_key_slot: dict[str, int] = {}
    row_fallback_slot_by_trace_idx: dict[int, int] = {}
    next_row_slot = 1
    for idx, entry in enumerate(trace_list):
        if not _entry_participates_in_order(entry):
            continue
        pass_name = str(entry.get("pass", "") or "").strip().casefold()
        if pass_name != "row":
            continue
        image_ref = str(entry.get("image", "") or "")
        selected_key = simple_name_key_fn(str(entry.get("selected_key", "") or ""))
        match = re.search(r"#(\d+)\[", image_ref)
        if match:
            line_index = _safe_int(entry.get("line_index", 1), 1)
            slot_idx = _safe_int(match.group(1), next_row_slot)
            slot_idx = int(slot_idx + max(0, int(line_index) - 1))
            slot_idx = max(1, int(slot_idx))
            row_fallback_slot_by_trace_idx[idx] = int(slot_idx)
            if selected_key and selected_key not in row_key_slot:
                row_key_slot[selected_key] = int(slot_idx)
            next_row_slot = max(int(next_row_slot), int(slot_idx) + 1)
            continue
        if selected_key and selected_key in row_key_slot:
            row_fallback_slot_by_trace_idx[idx] = int(row_key_slot[selected_key])
            continue
        slot_idx = int(next_row_slot)
        row_fallback_slot_by_trace_idx[idx] = int(slot_idx)
        if selected_key:
            row_key_slot[selected_key] = int(slot_idx)
        next_row_slot += 1

    # Hashmap: key -> earliest trace position tuple.
    key_trace_position: dict[str, tuple[int, int, int, int]] = {}
    key_best_pass: dict[str, str] = {}
    key_seen_passes: dict[str, set[str]] = {}
    # Array: keep key insertion order from trace for deterministic ties.
    trace_key_order: list[str] = []
    for idx, entry in enumerate(trace_list):
        if not _entry_participates_in_order(entry):
            continue
        selected_key = simple_name_key_fn(str(entry.get("selected_key", "") or ""))
        if not selected_key:
            continue
        pass_name = str(entry.get("pass", "") or "").strip().casefold()
        pass_rank = int(pass_order.get(pass_name, 99))
        run_index = _safe_int(entry.get("run_index", 9999), 9999)
        line_index = _safe_int(entry.get("line_index", 9999), 9999)
        if pass_name == "row" and idx in row_fallback_slot_by_trace_idx:
            slot_index = int(row_fallback_slot_by_trace_idx[idx])
        else:
            slot_index = _trace_slot_index(
                entry,
                pass_name=pass_name,
                run_index=run_index,
                line_index=line_index,
            )
        seen_passes = key_seen_passes.setdefault(selected_key, set())
        if pass_name:
            seen_passes.add(pass_name)
        current_position = key_trace_position.get(selected_key)
        new_position = (pass_rank, slot_index, run_index, idx)
        if current_position is None or new_position < current_position:
            key_trace_position[selected_key] = new_position
            key_best_pass[selected_key] = pass_name
        if selected_key not in trace_key_order:
            trace_key_order.append(selected_key)

    if not key_trace_position:
        return {"trace_key_order": [], "effective_position": {}}

    primary_trace_keys = [
        key
        for key, pass_name in key_best_pass.items()
        if pass_name == "primary" and key in key_trace_position
    ]

    def _promote_primary_only_position(
        key: str,
        pos: tuple[int, int, int, int] | None,
    ) -> tuple[int, int, int, int] | None:
        if pos is None or (not row_preferred):
            return pos
        passes = key_seen_passes.get(str(key or ""), set())
        if "row" in passes:
            return pos
        # In row-preferred mode, if a key has no row observation but does have
        # primary evidence (or only fuzzy primary alias), keep it aligned to
        # the primary row order instead of pushing it to the tail.
        if ("primary" in passes) or (not passes):
            return (0, int(pos[1]), int(pos[2]), int(pos[3]))
        return pos

    def _alias_primary_position(key: str) -> tuple[int, int, int, int] | None:
        if row_preferred and ("row" in key_seen_passes.get(str(key or ""), set())):
            return None
        if str(key_best_pass.get(key, "") or "") == "primary":
            return None
        if not primary_trace_keys:
            return None
        key_str = str(key or "")
        stripped_key = re.sub(r"\d+$", "", key_str)
        matches: list[tuple[float, int, tuple[int, int, int, int]]] = []
        for primary_key in primary_trace_keys:
            primary_key_str = str(primary_key or "")
            similarity = float(name_similarity_fn(key_str, primary_key_str))
            if similarity < 0.86:
                continue
            prefix_len = common_prefix_len_fn(key_str, primary_key_str)
            strong_prefix = prefix_len >= 8
            # Allow either a stable shared prefix or very high similarity.
            if (not strong_prefix) and similarity < 0.92:
                continue
            stripped_primary = re.sub(r"\d+$", "", primary_key_str)
            stripped_match = bool(
                stripped_key
                and stripped_primary
                and stripped_key == stripped_primary
            )
            if (not stripped_match) and (not strong_prefix) and similarity < 0.94:
                continue
            base_score = similarity + (0.05 if stripped_match else 0.0) + min(0.06, prefix_len * 0.003)
            pos = key_trace_position.get(primary_key)
            if pos is None:
                continue
            matches.append((base_score, prefix_len, pos))
        if not matches:
            return None
        matches.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if len(matches) >= 2 and (matches[0][0] - matches[1][0]) < 0.03:
            # Two near-identical aliases can happen for one logical line
            # (e.g. primary run variants with/without a leading quote/marker).
            # If the close matches resolve to the same slot, keep that slot.
            top_score = float(matches[0][0])
            top_pos = matches[0][2]
            close_matches = [item for item in matches if (top_score - float(item[0])) < 0.03]
            same_slot_positions = [item[2] for item in close_matches if item[2][:2] == top_pos[:2]]
            if len(same_slot_positions) >= 2:
                return min(same_slot_positions)
            return None
        return matches[0][2]

    effective_position: dict[str, tuple[int, int, int, int]] = {}
    for key in key_trace_position.keys():
        direct = _promote_primary_only_position(key, key_trace_position.get(key))
        alias = _promote_primary_only_position(key, _alias_primary_position(key))
        if alias is not None and (direct is None or alias < direct):
            effective_position[key] = alias
        elif direct is not None:
            effective_position[key] = direct

    return {
        "trace_key_order": trace_key_order,
        "effective_position": effective_position,
    }


def order_names_by_line_trace(
    names: list[str],
    trace_entries: list[dict] | None,
    *,
    row_preferred: bool = False,
    dedupe_names_in_order_fn,
    simple_name_key_fn,
    name_similarity_fn,
    common_prefix_len_fn,
) -> list[str]:
    deduped = dedupe_names_in_order_fn(names)
    if not deduped:
        return []
    if not trace_entries:
        return deduped

    context = _build_trace_order_context(
        trace_entries=trace_entries,
        row_preferred=row_preferred,
        simple_name_key_fn=simple_name_key_fn,
        name_similarity_fn=name_similarity_fn,
        common_prefix_len_fn=common_prefix_len_fn,
    )
    trace_key_order = list(context.get("trace_key_order") or [])
    effective_position = dict(context.get("effective_position") or {})
    if not effective_position:
        return deduped

    # Hashmap for quick name lookup by key and stable fallback ordering.
    key_to_name: dict[str, str] = {}
    for name in deduped:
        key = simple_name_key_fn(name)
        if not key or key in key_to_name:
            continue
        key_to_name[key] = name

    key_original_index = {
        simple_name_key_fn(name): idx
        for idx, name in enumerate(deduped)
        if simple_name_key_fn(name)
    }

    def _trace_order_sort_key(key: str) -> tuple[tuple[int, int, int, int], int]:
        pos = tuple(effective_position.get(key, (99, 9999, 9999, 9999)))
        if row_preferred:
            return (
                (int(pos[0]), int(pos[1]), int(pos[2]), int(pos[3])),
                key_original_index.get(key, 9999),
            )
        # In non-row-preferred mode, keep slot monotonicity as top priority.
        # This avoids single-line swaps when one key aliases to primary rank
        # while the paired key keeps its row rank.
        return (
            (int(pos[1]), int(pos[0]), int(pos[2]), int(pos[3])),
            key_original_index.get(key, 9999),
        )

    ordered_trace_keys = sorted(
        [key for key in trace_key_order if key in key_to_name and key in effective_position],
        key=_trace_order_sort_key,
    )

    if not ordered_trace_keys:
        return deduped

    if row_preferred:
        # Keep unknown keys at their original slots (row order), but reorder
        # known keys by trace rank.
        known_set = set(ordered_trace_keys)
        replacement_idx = 0
        ordered_names: list[str] = []
        for name in deduped:
            key = simple_name_key_fn(name)
            if key and key in known_set and replacement_idx < len(ordered_trace_keys):
                replacement_key = ordered_trace_keys[replacement_idx]
                replacement_idx += 1
                replacement_name = key_to_name.get(replacement_key)
                if replacement_name:
                    ordered_names.append(replacement_name)
                    continue
            ordered_names.append(name)
        return dedupe_names_in_order_fn(ordered_names)

    ordered_names: list[str] = []
    used_keys: set[str] = set()
    for key in ordered_trace_keys:
        name = key_to_name.get(key)
        if not name:
            continue
        used_keys.add(key)
        ordered_names.append(name)
    for name in deduped:
        key = simple_name_key_fn(name)
        if not key or key in used_keys:
            continue
        used_keys.add(key)
        ordered_names.append(name)

    return ordered_names


def collapse_slot_duplicates(
    names: list[str],
    *,
    trace_entries: list[dict] | None,
    row_preferred: bool,
    candidate_stats: dict[str, dict[str, float | int | str]],
    cfg: dict,
    dedupe_names_in_order_fn,
    simple_name_key_fn,
    name_similarity_fn,
    common_prefix_len_fn,
    candidate_bucket_score_fn,
    name_display_quality_fn,
) -> list[str]:
    deduped = dedupe_names_in_order_fn(names)
    if len(deduped) <= 1:
        return deduped
    if not trace_entries:
        return deduped

    context = _build_trace_order_context(
        trace_entries=trace_entries,
        row_preferred=row_preferred,
        simple_name_key_fn=simple_name_key_fn,
        name_similarity_fn=name_similarity_fn,
        common_prefix_len_fn=common_prefix_len_fn,
    )
    effective_position = dict(context.get("effective_position") or {})
    if not effective_position:
        return deduped

    def _slot_for_key(key: str) -> int | None:
        position = effective_position.get(str(key or ""))
        if not position:
            return None
        return int(position[1])

    def _key_score(key: str, fallback_text: str) -> tuple[float, int, int, int, int, int]:
        bucket = candidate_stats.get(str(key or ""), {}) if candidate_stats else {}
        display = str(bucket.get("display", "") or "").strip() or str(fallback_text or "").strip()
        support = int(bucket.get("support", 0))
        occurrences = int(bucket.get("occurrences", 0))
        conf = float(bucket.get("best_conf", -1.0))
        quality = name_display_quality_fn(display)
        return (
            float(candidate_bucket_score_fn(bucket, cfg)),
            int(support),
            int(occurrences),
            int(conf * 100.0),
            -int(quality[0]),
            -int(quality[2]),
        )

    def _same_slot_duplicate(existing_key: str, new_key: str) -> bool:
        left = str(existing_key or "")
        right = str(new_key or "")
        if not left or not right:
            return False
        if left == right:
            return True

        def _common_suffix_len(a: str, b: str) -> int:
            count = 0
            for ca, cb in zip(reversed(a), reversed(b)):
                if ca != cb:
                    break
                count += 1
            return count

        similarity = float(name_similarity_fn(left, right))
        if similarity >= 0.84:
            return True
        # Allow a little extra tolerance when only one OCR character drifted
        # near the beginning (e.g. Gookseller/Bookseller).
        prefix_len = int(common_prefix_len_fn(left, right))
        if prefix_len >= 3 and similarity >= 0.80:
            return True
        # Also treat strong same-length suffix matches as duplicates in the
        # same slot (e.g. yukino/vukino).
        suffix_len = _common_suffix_len(left, right)
        min_len = min(len(left), len(right))
        if min_len >= 5 and abs(len(left) - len(right)) <= 1:
            if suffix_len >= max(4, min_len - 1) and similarity >= 0.80:
                return True
        return False

    output_names: list[str] = []
    output_keys: list[str] = []
    slot_index_to_output_idx: dict[int, int] = {}

    for raw_name in deduped:
        name = str(raw_name or "").strip()
        if not name:
            continue
        key = simple_name_key_fn(name)
        if not key:
            output_keys.append("")
            output_names.append(name)
            continue
        slot_idx = _slot_for_key(key)
        if slot_idx is None:
            output_keys.append(key)
            output_names.append(name)
            continue

        existing_idx = slot_index_to_output_idx.get(int(slot_idx))
        if existing_idx is None:
            slot_index_to_output_idx[int(slot_idx)] = len(output_names)
            output_keys.append(key)
            output_names.append(name)
            continue

        existing_key = str(output_keys[existing_idx] or "")
        if (not existing_key) or (not _same_slot_duplicate(existing_key, key)):
            output_keys.append(key)
            output_names.append(name)
            continue

        existing_name = output_names[existing_idx]
        if _key_score(key, name) > _key_score(existing_key, existing_name):
            output_keys[existing_idx] = key
            output_names[existing_idx] = name

    return dedupe_names_in_order_fn(output_names)


def refill_names_to_target(
    names: list[str],
    *,
    refill_target: int,
    candidate_stats: dict[str, dict[str, float | int | str]],
    cfg: dict,
    trace_entries: list[dict] | None,
    row_preferred: bool,
    dedupe_names_in_order_fn,
    candidate_bucket_score_fn,
    name_display_quality_fn,
    simple_name_key_fn,
    order_names_by_line_trace_fn,
) -> list[str]:
    target = max(1, int(refill_target))
    output = dedupe_names_in_order_fn(names)
    if len(output) >= target:
        return output[:target]
    if not candidate_stats:
        return output

    ranked_missing = sorted(
        candidate_stats.items(),
        key=lambda kv: (
            -candidate_bucket_score_fn(kv[1], cfg),
            name_display_quality_fn(str(kv[1].get("display", ""))),
        ),
    )
    ranked_keys = [str(key) for key, _bucket in ranked_missing if str(key).strip()]

    trace_key_order: list[str] = []
    if trace_entries:
        trace_seed_names = [
            str((bucket or {}).get("display", "") or "").strip()
            for _key, bucket in ranked_missing
            if str((bucket or {}).get("display", "") or "").strip()
        ]
        ordered_seed_names = order_names_by_line_trace_fn(
            trace_seed_names,
            trace_entries,
            row_preferred=row_preferred,
        )
        seen_trace_keys: set[str] = set()
        for text in ordered_seed_names:
            key = simple_name_key_fn(text)
            if not key or key in seen_trace_keys or key not in candidate_stats:
                continue
            seen_trace_keys.add(key)
            trace_key_order.append(key)

    refill_key_order: list[str] = []
    seen_refill_keys: set[str] = set()
    for key in trace_key_order + ranked_keys:
        if not key or key in seen_refill_keys:
            continue
        seen_refill_keys.add(key)
        refill_key_order.append(key)

    seen_output_keys = {simple_name_key_fn(name) for name in output if simple_name_key_fn(name)}

    def _can_use_bucket(
        *,
        text: str,
        support: int,
        conf: float,
        allow_compact_upper_low_conf: bool,
    ) -> bool:
        if not text:
            return False
        if support <= 0:
            return False
        if len(text) <= 2 and support <= 1:
            return False
        if (
            (not allow_compact_upper_low_conf)
            and text.isupper()
            and len(text) <= 4
            and support <= 1
            and conf < 55.0
        ):
            return False
        return True

    def _refill_once(*, allow_compact_upper_low_conf: bool) -> None:
        for key in refill_key_order:
            if len(output) >= target:
                return
            if key in seen_output_keys:
                continue
            bucket = candidate_stats.get(key) or {}
            text = str(bucket.get("display", "") or "").strip()
            support = int(bucket.get("support", 0))
            conf = float(bucket.get("best_conf", -1.0))
            if not _can_use_bucket(
                text=text,
                support=support,
                conf=conf,
                allow_compact_upper_low_conf=allow_compact_upper_low_conf,
            ):
                continue
            output.append(text)
            seen_output_keys.add(key)

    _refill_once(allow_compact_upper_low_conf=False)
    if len(output) < target:
        _refill_once(allow_compact_upper_low_conf=True)
    return output
