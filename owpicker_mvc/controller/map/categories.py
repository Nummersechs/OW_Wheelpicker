from __future__ import annotations

from typing import Callable


def normalize_map_categories(raw_value) -> list[str]:
    if isinstance(raw_value, str):
        tokens = [tok.strip() for tok in raw_value.split(",")]
    elif isinstance(raw_value, (list, tuple, set)):
        tokens = [str(tok).strip() for tok in raw_value]
    else:
        tokens = []
    categories: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        categories.append(token)
    return categories


def unique_non_empty_labels(values) -> list[str]:
    unique: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in unique:
            unique.append(text)
    return unique


def build_map_type_rebuild_payload(
    *,
    new_types: list[str],
    current_states: dict,
    include_map: dict,
    saved_state: dict,
    old_categories: list[str],
    default_role_state_factory: Callable[[], dict],
) -> tuple[dict, dict]:
    new_state: dict = {}
    new_include_map: dict = {}
    for idx, category in enumerate(new_types):
        if category in current_states:
            new_state[category] = current_states[category]
            new_include_map[category] = include_map.get(category, True)
            continue
        if category in saved_state:
            new_state[category] = saved_state[category]
            new_include_map[category] = True
            continue
        if idx < len(old_categories):
            old_category = old_categories[idx]
            inherited = current_states.get(old_category) or saved_state.get(old_category)
            if inherited:
                new_state[category] = inherited
                new_include_map[category] = include_map.get(old_category, True)
                continue
        new_state[category] = default_role_state_factory()
        new_include_map[category] = True
    return new_state, new_include_map
