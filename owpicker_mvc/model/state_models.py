from __future__ import annotations

"""
Basis-Models für Rollen- und Modus-Zustände.
Diese Dataclasses kapseln das JSON-Format, das saved_state.json nutzt.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class EntryState:
    name: str
    subroles: List[str] = field(default_factory=list)
    active: bool = True

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "EntryState":
        return cls(
            name=str(raw.get("name", "")).strip(),
            subroles=[str(s).strip() for s in raw.get("subroles", []) if str(s).strip()],
            active=bool(raw.get("active", True)),
        )

    def to_raw(self) -> Dict[str, Any]:
        return {"name": self.name, "subroles": list(self.subroles), "active": bool(self.active)}


@dataclass
class RoleState:
    entries: List[EntryState] = field(default_factory=list)
    include_in_all: bool = True
    pair_mode: bool = False
    use_subroles: bool = False

    def to_raw(self) -> Dict[str, Any]:
        return {
            "entries": [e.to_raw() for e in self.entries],
            "include_in_all": self.include_in_all,
            "pair_mode": self.pair_mode,
            "use_subroles": self.use_subroles,
        }

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], defaults: Dict[str, Any] | None = None) -> "RoleState":
        defaults = defaults or {}
        entries_raw = raw.get("entries") if isinstance(raw, dict) else None
        entries = []
        if isinstance(entries_raw, list):
            for item in entries_raw:
                if isinstance(item, dict):
                    name = str(item.get("name", "")).strip()
                    if name:
                        entries.append(EntryState.from_raw(item))
                elif isinstance(item, str) and item.strip():
                    entries.append(EntryState(name=item.strip()))
        elif isinstance(raw, dict) and "names" in raw and isinstance(raw.get("names"), list):
            for item in raw.get("names", []):
                if isinstance(item, str) and item.strip():
                    entries.append(EntryState(name=item.strip()))

        return cls(
            entries=entries or defaults.get("entries", []),
            include_in_all=bool(raw.get("include_in_all", defaults.get("include_in_all", True))) if isinstance(raw, dict) else defaults.get("include_in_all", True),
            pair_mode=bool(raw.get("pair_mode", defaults.get("pair_mode", False))) if isinstance(raw, dict) else defaults.get("pair_mode", False),
            use_subroles=bool(raw.get("use_subroles", defaults.get("use_subroles", False))) if isinstance(raw, dict) else defaults.get("use_subroles", False),
        )


@dataclass
class ModeSnapshot:
    """Hält die drei Rollen eines Modus (players/heroes)."""
    tank: RoleState
    damage: RoleState
    support: RoleState

    def to_raw(self) -> Dict[str, Any]:
        return {
            "Tank": self.tank.to_raw(),
            "Damage": self.damage.to_raw(),
            "Support": self.support.to_raw(),
        }
