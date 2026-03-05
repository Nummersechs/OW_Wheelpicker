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
    selected_counts: dict[str, int] = {}
    for value in selected_names or []:
        text = str(value or "").strip()
        if not text:
            continue
        key = normalize_name_key(text) or text.casefold()
        if not key:
            continue
        selected_counts[key] = int(selected_counts.get(key, 0)) + 1
    if not selected_counts:
        return []
    names_to_add: list[str] = []
    for name in pending_names or []:
        norm_name = str(name or "").strip()
        if not norm_name:
            continue
        key = normalize_name_key(norm_name) or norm_name.casefold()
        if not key:
            continue
        remaining = int(selected_counts.get(key, 0))
        if remaining <= 0:
            continue
        selected_counts[key] = remaining - 1
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
