from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable
from logic.name_normalization import normalize_name_casefold


@dataclass
class PendingOCRImport:
    role_key: str
    candidates: list[str]
    option_labels: list[str] = field(default_factory=list)
    option_assignment_by_label_key: dict[str, str] = field(default_factory=dict)
    option_subrole_by_label_key: dict[str, tuple[str, str]] = field(default_factory=dict)
    option_subrole_code_by_label_key: dict[str, str] = field(default_factory=dict)
    hint_key: str = "ocr.pick_hint"
    hint_kwargs: dict[str, str] = field(default_factory=dict)


def normalize_name_key(value: str) -> str:
    return normalize_name_casefold(value)


def name_key_set(values: Iterable[str] | None) -> set[str]:
    keys: set[str] = set()
    for value in values or []:
        key = normalize_name_key(value)
        if key:
            keys.add(key)
    return keys


def collect_new_names(existing_names: Iterable[str] | None, raw_names: Iterable[str] | None) -> list[str]:
    existing_keys = name_key_set(existing_names)
    new_names: list[str] = []
    seen_keys: set[str] = set()
    for raw in raw_names or []:
        name = str(raw or "").strip()
        if not name:
            continue
        key = normalize_name_key(name)
        if not key or key in existing_keys or key in seen_keys:
            continue
        seen_keys.add(key)
        new_names.append(name)
    return new_names


def resolve_selected_candidates(
    pending_names: Iterable[str] | None,
    selected_names: Iterable[str] | None,
) -> list[str]:
    selected_keys = name_key_set(selected_names)
    if not selected_keys:
        return []
    names_to_add: list[str] = []
    seen_keys: set[str] = set()
    for name in pending_names or []:
        norm_name = str(name or "").strip()
        if not norm_name:
            continue
        key = normalize_name_key(norm_name)
        if not key or key not in selected_keys or key in seen_keys:
            continue
        seen_keys.add(key)
        names_to_add.append(norm_name)
    return names_to_add


def add_names(add_name: Callable[[str], bool], names: Iterable[str] | None) -> int:
    added = 0
    for name in names or []:
        norm_name = str(name or "").strip()
        if not norm_name:
            continue
        if add_name(norm_name):
            added += 1
    return added
