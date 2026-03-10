from __future__ import annotations

from typing import Mapping


def collect_combined_active_names(map_lists: Mapping[str, object]) -> list[str]:
    combined: list[str] = []
    for wheel in map_lists.values():
        include_btn = getattr(wheel, "btn_include_in_all", None)
        is_checked_fn = getattr(include_btn, "isChecked", None)
        if callable(is_checked_fn):
            try:
                if not bool(is_checked_fn()):
                    continue
            except (AttributeError, RuntimeError, TypeError, ValueError):
                continue
        get_active_entries = getattr(wheel, "get_active_entries", None)
        if not callable(get_active_entries):
            continue
        try:
            entries = list(get_active_entries())
        except (AttributeError, RuntimeError, TypeError, ValueError):
            continue
        for entry in entries:
            name = str((entry or {}).get("name", "")).strip()
            if name:
                combined.append(name)
    return combined


def build_override_entries(names: list[str]) -> list[dict]:
    return [{"name": str(name), "subroles": [], "active": True} for name in list(names or [])]

