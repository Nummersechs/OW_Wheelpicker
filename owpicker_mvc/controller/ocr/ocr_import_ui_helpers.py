from __future__ import annotations

from collections import deque

import i18n

from .ocr_role_import import PendingOCRImport


def show_ocr_import_none_selected(mw) -> None:
    mw_message_box = getattr(getattr(mw, "QtWidgets", None), "QMessageBox", None)
    if mw_message_box is not None:
        mw_message_box.information(mw, i18n.t("ocr.result_title"), i18n.t("ocr.result_none_selected"))
        return
    from PySide6 import QtWidgets  # local import keeps helper lightweight

    QtWidgets.QMessageBox.information(mw, i18n.t("ocr.result_title"), i18n.t("ocr.result_none_selected"))


def show_ocr_import_result_for_role(mw, role_key: str, *, added: int, total: int) -> None:
    role_name = mw._ocr_role_display_name(role_key)
    if added > 0:
        message = i18n.t(
            "ocr.result_added_role",
            added=added,
            total=total,
            role=role_name,
        )
    else:
        message = i18n.t("ocr.result_duplicates_only_role", total=total, role=role_name)
    from PySide6 import QtWidgets  # local import keeps helper lightweight

    QtWidgets.QMessageBox.information(mw, i18n.t("ocr.result_title"), message)


def show_ocr_import_result_distributed(mw, *, added: int, total: int, counts: dict[str, int]) -> None:
    if added > 0:
        message = i18n.t(
            "ocr.result_added_distributed",
            added=added,
            total=total,
            tank=int(counts.get("tank", 0)),
            dps=int(counts.get("dps", 0)),
            support=int(counts.get("support", 0)),
        )
    else:
        message = i18n.t("ocr.result_duplicates_only_distributed", total=total)
    from PySide6 import QtWidgets  # local import keeps helper lightweight

    QtWidgets.QMessageBox.information(mw, i18n.t("ocr.result_title"), message)


def show_ocr_import_replaced_distributed(mw, *, total: int, counts: dict[str, int]) -> None:
    from PySide6 import QtWidgets  # local import keeps helper lightweight

    QtWidgets.QMessageBox.information(
        mw,
        i18n.t("ocr.result_title"),
        i18n.t(
            "ocr.result_replaced_distributed",
            total=total,
            tank=int(counts.get("tank", 0)),
            dps=int(counts.get("dps", 0)),
            support=int(counts.get("support", 0)),
        ),
    )


def show_ocr_import_replaced_role(mw, role_key: str, *, total: int) -> None:
    from PySide6 import QtWidgets  # local import keeps helper lightweight

    QtWidgets.QMessageBox.information(
        mw,
        i18n.t("ocr.result_title"),
        i18n.t(
            "ocr.result_replaced_role",
            role=mw._ocr_role_display_name(role_key),
            total=total,
        ),
    )


def on_overlay_ocr_import_confirmed(mw, selected_names) -> None:
    pending = getattr(mw, "_pending_ocr_import", None)
    mw._pending_ocr_import = None
    if pending is None:
        return
    entries_to_add = mw._selected_ocr_entries_for_pending(pending, selected_names)
    if not entries_to_add:
        show_ocr_import_none_selected(mw)
        return

    target_key = str(getattr(pending, "role_key", "") or "").strip().casefold()
    if target_key == "all":
        added, added_counts = mw._add_ocr_entries_distributed(entries_to_add)
        show_ocr_import_result_distributed(
            mw,
            added=added,
            total=len(entries_to_add),
            counts=added_counts,
        )
        return

    added = mw._add_ocr_entries_for_role(target_key, entries_to_add)
    show_ocr_import_result_for_role(
        mw,
        target_key,
        added=added,
        total=len(entries_to_add),
    )


def on_overlay_ocr_import_replace_requested(mw, selected_names) -> None:
    pending = getattr(mw, "_pending_ocr_import", None)
    mw._pending_ocr_import = None
    if pending is None:
        return
    entries_to_replace = mw._selected_ocr_entries_for_pending(pending, selected_names)
    if not entries_to_replace:
        show_ocr_import_none_selected(mw)
        return

    target_key = str(getattr(pending, "role_key", "") or "").strip().casefold()
    if target_key == "all":
        total, assigned_counts = mw._replace_ocr_entries_distributed(entries_to_replace)
        show_ocr_import_replaced_distributed(
            mw,
            total=total,
            counts=assigned_counts,
        )
        return

    total = mw._replace_ocr_entries_for_role(target_key, entries_to_replace)
    show_ocr_import_replaced_role(
        mw,
        target_key,
        total=total,
    )


def on_overlay_ocr_import_cancelled(mw) -> None:
    mw._pending_ocr_import = None


def ocr_distribution_role_keys() -> tuple[str, ...]:
    return ("tank", "dps", "support")


def ocr_subrole_labels_for_role(mw, role_key: str) -> list[str]:
    wheel = mw._target_wheel_for_ocr_role(role_key)
    if wheel is None:
        return []
    values: list[str] = []
    for raw in getattr(wheel, "subrole_labels", []) or []:
        text = str(raw or "").strip()
        if text:
            values.append(text)
    return values


def ocr_assignment_options(
    mw,
    role_key: str,
    *,
    normalize_ocr_name_key_fn,
) -> tuple[list[str], dict[str, str], dict[str, str], str]:
    key = str(role_key or "").strip().casefold()
    if key == "all":
        labels = [
            i18n.t("ocr.assign_tank"),
            i18n.t("ocr.assign_dps"),
            i18n.t("ocr.assign_support"),
            i18n.t("ocr.assign_main"),
            i18n.t("ocr.assign_flex"),
        ]
        assignment_mapping: dict[str, str] = {}
        subrole_code_mapping: dict[str, str] = {}
        role_codes = ocr_distribution_role_keys()
        for idx, role in enumerate(role_codes):
            if idx >= 3:
                break
            label = labels[idx]
            norm_label = normalize_ocr_name_key_fn(label)
            if not norm_label:
                continue
            assignment_mapping[norm_label] = role
        main_label_key = normalize_ocr_name_key_fn(labels[3])
        flex_label_key = normalize_ocr_name_key_fn(labels[4])
        if main_label_key:
            subrole_code_mapping[main_label_key] = "main"
        if flex_label_key:
            subrole_code_mapping[flex_label_key] = "flex"
        return labels, assignment_mapping, subrole_code_mapping, "ocr.pick_hint_all_roles"

    labels: list[str] = []
    assignment_mapping = {}
    subrole_code_mapping: dict[str, str] = {}
    for subrole in ocr_subrole_labels_for_role(mw, key):
        labels.append(subrole)
        norm_label = normalize_ocr_name_key_fn(subrole)
        if not norm_label:
            continue
        assignment_mapping[norm_label] = key
    return labels, assignment_mapping, subrole_code_mapping, "ocr.pick_hint"


def normalize_ocr_candidate_names(names: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw in names or []:
        name = str(raw or "").strip()
        if not name:
            continue
        normalized.append(name)
    return normalized


def request_ocr_import_selection(
    mw,
    role_key: str,
    names: list[str],
    *,
    normalize_ocr_name_key_fn,
) -> bool:
    overlay = getattr(mw, "overlay", None)
    if overlay is None:
        return False
    display_names = [str(name).strip() for name in names if str(name).strip()]
    if not display_names:
        return False
    normalized_role_key = str(role_key or "").strip().casefold()
    (
        option_labels,
        option_assignment_by_label_key,
        option_subrole_code_by_label_key,
        hint_key,
    ) = ocr_assignment_options(
        mw,
        normalized_role_key,
        normalize_ocr_name_key_fn=normalize_ocr_name_key_fn,
    )
    hint_kwargs: dict[str, str] = {}
    if normalized_role_key != "all":
        hint_kwargs["role"] = mw._ocr_role_display_name(normalized_role_key)
    mw._pending_ocr_import = PendingOCRImport(
        role_key=normalized_role_key,
        candidates=list(display_names),
        option_labels=list(option_labels),
        option_assignment_by_label_key=dict(option_assignment_by_label_key),
        option_subrole_code_by_label_key=dict(option_subrole_code_by_label_key),
        hint_key=hint_key,
        hint_kwargs=hint_kwargs,
    )
    try:
        overlay.show_ocr_name_picker(
            display_names,
            subrole_labels=option_labels,
            hint_key=hint_key,
            hint_kwargs=hint_kwargs,
        )
    except (RuntimeError, AttributeError, TypeError):
        mw._pending_ocr_import = None
        return False
    return True


def selected_ocr_entries_for_pending(
    mw,
    pending,
    selected_payload,
    *,
    normalize_ocr_name_key_fn,
    resolve_selected_ocr_candidates_fn,
) -> list[dict]:
    pending_role_key = str(pending.role_key or "").strip().casefold()
    allowed_assignments = {
        str(k).strip().casefold(): str(v).strip().casefold()
        for k, v in (pending.option_assignment_by_label_key or {}).items()
        if str(k).strip() and str(v).strip()
    }
    allowed_subrole_options: dict[str, tuple[str, str]] = {}
    if pending_role_key != "all":
        for label in pending.option_labels or []:
            subrole = str(label or "").strip()
            if not subrole:
                continue
            label_key = normalize_ocr_name_key_fn(subrole)
            if not label_key:
                continue
            allowed_subrole_options[label_key] = (pending_role_key, subrole)
    allowed_subrole_codes = {
        str(k).strip().casefold(): str(v).strip().casefold()
        for k, v in (pending.option_subrole_code_by_label_key or {}).items()
        if str(k).strip() and str(v).strip()
    }
    role_codes = ocr_distribution_role_keys()

    raw_selected: list[dict] = []
    for item in selected_payload or []:
        if isinstance(item, dict):
            name = str(item.get("name", "")).strip()
            payload_subroles = item.get("subroles", [])
        else:
            name = str(item or "").strip()
            payload_subroles = []
        if not name:
            continue
        codes: list[str] = []
        subrole_codes: list[str] = []
        subroles_by_role: dict[str, list[str]] = {}
        if isinstance(payload_subroles, (list, tuple, set)):
            for value in payload_subroles:
                label_key = normalize_ocr_name_key_fn(value)
                code = allowed_assignments.get(label_key)
                if code and code in role_codes and code not in codes:
                    codes.append(code)
                subrole_code = allowed_subrole_codes.get(label_key)
                if subrole_code in {"main", "flex"} and subrole_code not in subrole_codes:
                    subrole_codes.append(subrole_code)
                subrole_info = allowed_subrole_options.get(label_key)
                if subrole_info:
                    subrole_role, subrole_value = subrole_info
                    if subrole_role in role_codes and subrole_role not in codes:
                        codes.append(subrole_role)
                    if subrole_role in role_codes and subrole_value:
                        bucket = subroles_by_role.setdefault(subrole_role, [])
                        if subrole_value not in bucket:
                            bucket.append(subrole_value)
        if subrole_codes and codes:
            for role in codes:
                bucket = subroles_by_role.setdefault(role, [])
                for value in role_subroles_from_main_flex_codes(
                    mw,
                    role,
                    subrole_codes,
                ):
                    if value not in bucket:
                        bucket.append(value)
        raw_selected.append(
            {
                "name": name,
                "assignments": codes,
                "subrole_codes": list(subrole_codes),
                "subroles_by_role": subroles_by_role,
            }
        )

    selected_names = [entry.get("name", "") for entry in raw_selected]
    names_in_order = resolve_selected_ocr_candidates_fn(pending.candidates, selected_names)

    entries_by_name_key: dict[str, deque[dict]] = {}
    entries_in_order: list[dict] = []
    for entry in raw_selected:
        key = normalize_ocr_name_key_fn(entry.get("name", ""))
        if not key:
            continue
        payload = {
            "name": str(entry.get("name", "")).strip(),
            "assignments": list(entry.get("assignments", [])),
            "subrole_codes": [
                str(code).strip().casefold()
                for code in list(entry.get("subrole_codes", []) or [])
                if str(code).strip()
            ],
            "subroles_by_role": {
                str(role).strip().casefold(): [
                    str(subrole).strip()
                    for subrole in list(values or [])
                    if str(subrole).strip()
                ]
                for role, values in (entry.get("subroles_by_role", {}) or {}).items()
                if str(role).strip()
            },
        }
        entries_in_order.append(payload)
        queue = entries_by_name_key.setdefault(key, deque())
        queue.append(payload)

    resolved_entries: list[dict] = []
    consumed_payload_ids: set[int] = set()
    for name in names_in_order:
        key = normalize_ocr_name_key_fn(name)
        payload = None
        if key:
            queue = entries_by_name_key.get(key)
            if queue:
                payload = queue.popleft()
                consumed_payload_ids.add(id(payload))
        assignments = list((payload or {}).get("assignments", []))
        subrole_codes = list((payload or {}).get("subrole_codes", []))
        subroles_by_role = dict((payload or {}).get("subroles_by_role", {}))
        resolved_entries.append(
            {
                "name": name,
                "assignments": assignments,
                "subrole_codes": subrole_codes,
                "subroles_by_role": subroles_by_role,
                "active": True,
            }
        )

    for entry in entries_in_order:
        if id(entry) in consumed_payload_ids:
            continue
        resolved_entries.append(
            {
                "name": str(entry.get("name", "")).strip(),
                "assignments": list(entry.get("assignments", [])),
                "subrole_codes": list(entry.get("subrole_codes", [])),
                "subroles_by_role": dict(entry.get("subroles_by_role", {})),
                "active": True,
            }
        )

    if not resolved_entries:
        return []
    return resolved_entries


def role_subroles_from_main_flex_codes(mw, role_key: str, codes: list[str] | None) -> list[str]:
    labels = ocr_subrole_labels_for_role(mw, role_key)
    if not labels:
        return []
    code_set = {
        str(code).strip().casefold()
        for code in list(codes or [])
        if str(code).strip()
    }
    mapped: list[str] = []
    if "main" in code_set and len(labels) >= 1:
        mapped.append(labels[0])
    if "flex" in code_set and len(labels) >= 2:
        mapped.append(labels[1])
    return mapped


def plan_distributed_ocr_entries_for_add(
    mw,
    entries: list[dict],
    *,
    normalize_ocr_name_key_fn,
) -> dict[str, list[dict]]:
    role_keys = ocr_distribution_role_keys()
    plan: dict[str, list[dict]] = {role_key: [] for role_key in role_keys}

    existing_by_role: dict[str, set[str]] = {}
    for role_key in role_keys:
        wheel = mw._target_wheel_for_ocr_role(role_key)
        role_existing: set[str] = set()
        if wheel is not None and hasattr(wheel, "get_current_names"):
            try:
                for current_name in wheel.get_current_names():
                    key = normalize_ocr_name_key_fn(current_name)
                    if key:
                        role_existing.add(key)
            except (RuntimeError, AttributeError, TypeError, ValueError):
                role_existing = set()
        existing_by_role[role_key] = role_existing

    next_start_idx = 0
    role_count = len(role_keys)
    if role_count <= 0:
        return plan

    for entry in entries or []:
        name = str((entry or {}).get("name", "")).strip()
        if not name:
            continue
        key = normalize_ocr_name_key_fn(name)
        if not key:
            continue
        subroles_by_role = dict((entry or {}).get("subroles_by_role", {}) or {})
        subrole_codes = [
            str(code).strip().casefold()
            for code in list((entry or {}).get("subrole_codes", []) or [])
            if str(code).strip()
        ]
        explicit_targets_raw = list((entry or {}).get("assignments", []) or [])
        explicit_targets: list[str] = []
        for value in explicit_targets_raw:
            role_key = str(value or "").strip().casefold()
            if role_key in role_keys and role_key not in explicit_targets:
                explicit_targets.append(role_key)

        if explicit_targets:
            for target_role in explicit_targets:
                if key in existing_by_role.get(target_role, set()):
                    continue
                role_subroles = [
                    str(subrole).strip()
                    for subrole in list(subroles_by_role.get(target_role, []) or [])
                    if str(subrole).strip()
                ]
                if not role_subroles:
                    role_subroles = role_subroles_from_main_flex_codes(mw, target_role, subrole_codes)
                plan[target_role].append({"name": name, "subroles": role_subroles, "active": True})
                existing_by_role[target_role].add(key)
            continue

        if all(key in existing_by_role.get(role_key, set()) for role_key in role_keys):
            continue

        chosen_idx: int | None = None
        for offset in range(role_count):
            idx = (next_start_idx + offset) % role_count
            role_key = role_keys[idx]
            if key in existing_by_role.get(role_key, set()):
                continue
            chosen_idx = idx
            break
        if chosen_idx is None:
            continue

        chosen_role = role_keys[chosen_idx]
        role_subroles = [
            str(subrole).strip()
            for subrole in list(subroles_by_role.get(chosen_role, []) or [])
            if str(subrole).strip()
        ]
        if not role_subroles:
            role_subroles = role_subroles_from_main_flex_codes(mw, chosen_role, subrole_codes)
        plan[chosen_role].append({"name": name, "subroles": role_subroles, "active": True})
        existing_by_role[chosen_role].add(key)
        next_start_idx = (chosen_idx + 1) % role_count

    return plan


def add_ocr_entries_distributed(
    mw,
    entries: list[dict],
    *,
    normalize_ocr_name_key_fn,
) -> tuple[int, dict[str, int]]:
    role_keys = ocr_distribution_role_keys()
    added_counts: dict[str, int] = {role_key: 0 for role_key in role_keys}
    planned = plan_distributed_ocr_entries_for_add(
        mw,
        entries,
        normalize_ocr_name_key_fn=normalize_ocr_name_key_fn,
    )

    for role_key in role_keys:
        wheel = mw._target_wheel_for_ocr_role(role_key)
        if wheel is None or not hasattr(wheel, "add_name"):
            continue
        for entry in planned.get(role_key, []):
            name = str((entry or {}).get("name", "")).strip()
            if not name:
                continue
            role_subroles = [
                str(subrole).strip()
                for subrole in list((entry or {}).get("subroles", []) or [])
                if str(subrole).strip()
            ]
            if wheel.add_name(name, active=True, subroles=role_subroles):
                added_counts[role_key] = int(added_counts.get(role_key, 0)) + 1

    total_added = int(sum(added_counts.values()))
    if total_added > 0:
        mw.state_sync.save_state()
        mw._update_spin_all_enabled()
    return total_added, added_counts


def replace_ocr_entries_distributed(
    mw,
    entries: list[dict],
    *,
    normalize_ocr_name_key_fn,
) -> tuple[int, dict[str, int]]:
    role_keys = ocr_distribution_role_keys()
    distributed: dict[str, list[dict]] = {role_key: [] for role_key in role_keys}
    if not role_keys:
        return 0, {role_key: 0 for role_key in role_keys}

    unique_names: list[str] = []
    seen_keys: set[str] = set()
    for entry in entries or []:
        name = str((entry or {}).get("name", "")).strip()
        if not name:
            continue
        key = normalize_ocr_name_key_fn(name)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        unique_names.append(name)

    explicit_targets_by_name_key: dict[str, set[str]] = {}
    subrole_codes_by_name_key: dict[str, list[str]] = {}
    subroles_by_name_key: dict[str, dict[str, list[str]]] = {}
    for entry in entries or []:
        name = str((entry or {}).get("name", "")).strip()
        if not name:
            continue
        key = normalize_ocr_name_key_fn(name)
        if not key:
            continue
        explicit_targets = explicit_targets_by_name_key.setdefault(key, set())
        for raw_role in list((entry or {}).get("assignments", []) or []):
            role_key = str(raw_role or "").strip().casefold()
            if role_key in role_keys:
                explicit_targets.add(role_key)
        subrole_codes_by_name_key[key] = [
            str(code).strip().casefold()
            for code in list((entry or {}).get("subrole_codes", []) or [])
            if str(code).strip()
        ]
        raw_subroles = dict((entry or {}).get("subroles_by_role", {}) or {})
        normalized_subroles: dict[str, list[str]] = {}
        for raw_role, raw_values in raw_subroles.items():
            role = str(raw_role or "").strip().casefold()
            if role not in role_keys:
                continue
            normalized = [
                str(value).strip()
                for value in list(raw_values or [])
                if str(value).strip()
            ]
            if normalized:
                normalized_subroles[role] = normalized
        subroles_by_name_key[key] = normalized_subroles

    non_explicit_index = 0
    role_count = len(role_keys)
    if role_count <= 0:
        return 0, {role_key: 0 for role_key in role_keys}
    for name in unique_names:
        key = normalize_ocr_name_key_fn(name)
        if not key:
            continue
        explicit_targets = sorted(explicit_targets_by_name_key.get(key, set()))
        subrole_codes = list(subrole_codes_by_name_key.get(key, []))
        subroles_for_roles = dict(subroles_by_name_key.get(key, {}))
        if explicit_targets:
            for target_role in explicit_targets:
                subroles = list(subroles_for_roles.get(target_role, []))
                if not subroles:
                    subroles = role_subroles_from_main_flex_codes(mw, target_role, subrole_codes)
                distributed[target_role].append({"name": name, "subroles": subroles, "active": True})
            continue

        target_role = role_keys[non_explicit_index % role_count]
        non_explicit_index += 1
        subroles = list(subroles_for_roles.get(target_role, []))
        if not subroles:
            subroles = role_subroles_from_main_flex_codes(mw, target_role, subrole_codes)
        distributed[target_role].append({"name": name, "subroles": subroles, "active": True})

    assigned_counts: dict[str, int] = {role_key: 0 for role_key in role_keys}
    for role_key in role_keys:
        wheel = mw._target_wheel_for_ocr_role(role_key)
        if wheel is None or not hasattr(wheel, "load_entries"):
            continue
        role_entries = list(distributed.get(role_key, []))
        entries_for_role: list[dict] = []
        for entry in role_entries:
            name = str((entry or {}).get("name", "")).strip()
            if not name:
                continue
            entries_for_role.append(
                {
                    "name": name,
                    "subroles": [
                        str(subrole).strip()
                        for subrole in list((entry or {}).get("subroles", []) or [])
                        if str(subrole).strip()
                    ],
                    "active": True,
                }
            )
        wheel.load_entries(entries_for_role)
        assigned_counts[role_key] = len(entries_for_role)

    total_assigned = int(sum(assigned_counts.values()))
    mw.state_sync.save_state()
    mw._update_spin_all_enabled()
    return total_assigned, assigned_counts


def add_ocr_entries_for_role(
    mw,
    role_key: str,
    entries: list[dict],
    *,
    normalize_ocr_name_key_fn,
) -> int:
    wheel = mw._target_wheel_for_ocr_role(role_key)
    if wheel is None or not hasattr(wheel, "add_name"):
        return 0
    normalized_role_key = str(role_key or "").strip().casefold()
    added = 0
    for entry in entries or []:
        name = str((entry or {}).get("name", "")).strip()
        if not name:
            continue
        subroles_by_role = dict((entry or {}).get("subroles_by_role", {}) or {})
        role_subroles = [
            str(subrole).strip()
            for subrole in list(subroles_by_role.get(normalized_role_key, []) or [])
            if str(subrole).strip()
        ]
        if not role_subroles:
            role_subroles = role_subroles_from_main_flex_codes(
                mw,
                normalized_role_key,
                list((entry or {}).get("subrole_codes", []) or []),
            )
        if wheel.add_name(name, active=True, subroles=role_subroles):
            added += 1
    if added > 0:
        mw.state_sync.save_state()
        mw._update_spin_all_enabled()
    return added


def replace_ocr_entries_for_role(
    mw,
    role_key: str,
    entries: list[dict],
    *,
    normalize_ocr_name_key_fn,
) -> int:
    wheel = mw._target_wheel_for_ocr_role(role_key)
    if wheel is None or not hasattr(wheel, "load_entries"):
        return 0
    normalized_role_key = str(role_key or "").strip().casefold()
    unique_names: list[str] = []
    seen_keys: set[str] = set()
    subroles_by_name_key: dict[str, list[str]] = {}
    for entry in entries or []:
        name = str((entry or {}).get("name", "")).strip()
        if not name:
            continue
        key = normalize_ocr_name_key_fn(name)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        unique_names.append(name)
        subrole_codes = [
            str(code).strip().casefold()
            for code in list((entry or {}).get("subrole_codes", []) or [])
            if str(code).strip()
        ]
        raw_subroles = dict((entry or {}).get("subroles_by_role", {}) or {})
        role_subroles = [
            str(subrole).strip()
            for subrole in list(raw_subroles.get(normalized_role_key, []) or [])
            if str(subrole).strip()
        ]
        if not role_subroles:
            role_subroles = role_subroles_from_main_flex_codes(
                mw,
                normalized_role_key,
                subrole_codes,
            )
        subroles_by_name_key[key] = role_subroles
    wheel.load_entries(
        [
            {
                "name": name,
                "subroles": list(subroles_by_name_key.get(normalize_ocr_name_key_fn(name), [])),
                "active": True,
            }
            for name in unique_names
        ]
    )
    mw.state_sync.save_state()
    mw._update_spin_all_enabled()
    return len(unique_names)
