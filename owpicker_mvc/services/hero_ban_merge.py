"""
Hilfsfunktionen für Hero-Ban: Rollen auswählen und zu einer zentralen Liste zusammenführen.
"""
from __future__ import annotations

from typing import Dict, List


def merge_selected_roles(selected_roles: List[str], wheel_map: Dict[str, any]) -> List[dict]:
    """
    selected_roles: Liste der Rollen-Namen (z.B. Tank/Damage/Support), die einfließen sollen.
    wheel_map: role -> WheelView (muss get_current_entries bereitstellen).
    Rückgabe: Liste von {"name": str, "subroles": [], "active": True} ohne Duplikate, nur aktive Einträge.
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
