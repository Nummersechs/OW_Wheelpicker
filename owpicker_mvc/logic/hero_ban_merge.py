"""Helpers for Hero-Ban: merge selected roles into a single list."""
from __future__ import annotations

from typing import Any, Dict, List


def merge_selected_roles(selected_roles: List[str], wheel_map: Dict[str, Any]) -> List[dict]:
    """
    selected_roles: list of role names (e.g., Tank/Damage/Support) to include.
    wheel_map: role -> WheelView (must provide get_current_entries).
    Returns: [{"name": str, "subroles": [], "active": True}] unique and only active.
    """
    combined: List[dict] = []
    seen = set()
    for role in selected_roles:
        wheel = wheel_map.get(role)
        if not wheel:
            continue
        for entry in wheel.get_current_entries():
            if not entry.get("active", True):
                continue
            name = str(entry.get("name", "")).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            combined.append({"name": name, "subroles": [], "active": True})
    return combined
