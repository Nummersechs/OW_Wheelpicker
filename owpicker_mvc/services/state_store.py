"""
Verwaltet die Mode-States (players/heroes) inklusive Defaults und Capture/Restore.
Hält das Datenformat kompatibel zur bisherigen saved_state.json.
"""
from __future__ import annotations

from typing import Dict, List, Any
import config


class ModeStateStore:
    def __init__(self, mode_states: Dict[str, Dict[str, dict]] | None = None):
        self._mode_states: Dict[str, Dict[str, dict]] = mode_states or {"players": {}, "heroes": {}, "maps": {}}

    @classmethod
    def from_saved(cls, saved: dict) -> "ModeStateStore":
        mode_states = cls._build_mode_states(saved or {})
        return cls(mode_states)

    @staticmethod
    def _normalize_entries_for_state(defaults) -> List[dict]:
        entries: List[dict] = []
        for item in defaults or []:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    entries.append({"name": name, "subroles": [], "active": True})
            elif isinstance(item, dict) and "name" in item:
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                subs = item.get("subroles", [])
                if isinstance(subs, (list, set, tuple)):
                    subs_list = [str(s) for s in subs if str(s).strip()]
                else:
                    subs_list = []
                entries.append({
                    "name": name,
                    "subroles": subs_list,
                    "active": bool(item.get("active", True)),
                })
        return entries

    @classmethod
    def _default_role_state(cls, role: str, mode: str) -> dict:
        pair_defaults = {"Tank": False, "Damage": True, "Support": True}
        if mode == "heroes":
            defaults = config.DEFAULT_HEROES.get(role, [])
        elif mode == "maps":
            defaults = config.DEFAULT_MAPS.get(role, [])
        else:
            defaults = config.DEFAULT_NAMES.get(role, [])
        return {
            "entries": cls._normalize_entries_for_state(defaults),
            # Include-Status nicht mehr persistieren -> immer True
            "include_in_all": True,
            "pair_mode": pair_defaults.get(role, False),
            "use_subroles": False,
        }

    @classmethod
    def _role_state_from_saved(cls, data, role: str, mode: str) -> dict:
        base = cls._default_role_state(role, mode)
        if not isinstance(data, dict):
            return base
        if "entries" in data:
            base["entries"] = cls._normalize_entries_for_state(data["entries"])
        elif "names" in data:
            base["entries"] = cls._normalize_entries_for_state(data["names"])
        # include_in_all wird nicht mehr aus saved_state übernommen (immer Default True)
        base["pair_mode"] = bool(data.get("pair_mode", base["pair_mode"]))
        base["use_subroles"] = bool(data.get("use_subroles", base["use_subroles"]))
        return base

    @classmethod
    def _build_mode_states(cls, saved: dict) -> dict:
        roles = ("Tank", "Damage", "Support")
        players_saved = saved.get("players") if isinstance(saved, dict) else {}
        heroes_saved = saved.get("heroes") if isinstance(saved, dict) else {}
        maps_saved = saved.get("maps") if isinstance(saved, dict) else {}
        mode_states: Dict[str, Dict[str, dict]] = {"players": {}, "heroes": {}, "maps": {}}
        for role in roles:
            if isinstance(players_saved, dict) and role in players_saved:
                players_src = players_saved.get(role, {})
            else:
                players_src = saved.get(role, {})
            mode_states["players"][role] = cls._role_state_from_saved(players_src, role, "players")

            heroes_src = heroes_saved.get(role, {}) if isinstance(heroes_saved, dict) else {}
            mode_states["heroes"][role] = cls._role_state_from_saved(heroes_src, role, "heroes")

        map_roles = list(getattr(config, "MAP_CATEGORIES", [])) or list(getattr(config, "DEFAULT_MAPS", {}).keys())
        for role in map_roles:
            role_state = {}
            if isinstance(maps_saved, dict):
                role_state = maps_saved.get(role, {})
            mode_states["maps"][role] = cls._role_state_from_saved(role_state, role, "maps")
        return mode_states

    def get_mode_state(self, mode: str) -> Dict[str, dict]:
        return self._mode_states.get(mode, {})

    def set_mode_state(self, mode: str, state: Dict[str, dict]) -> None:
        self._mode_states[mode] = state

    def default_role_state(self, role: str, mode: str) -> dict:
        return self._default_role_state(role, mode)

    def capture_mode_from_wheels(self, mode: str, wheels: Dict[str, Any], hero_ban_active: bool = False) -> None:
        """
        Aktualisiert den Mode-State basierend auf den aktuellen WheelViews.
        wheels: dict role -> WheelView
        """
        base_state = self._mode_states.get(mode, {}) if hero_ban_active else {}

        def wheel_state(w, role: str) -> dict:
            base = base_state.get(role, {}) if isinstance(base_state, dict) else {}
            return {
                "entries": w.get_current_entries(),
                # include_in_all nicht persistieren
                "pair_mode": base.get("pair_mode", getattr(w, "pair_mode", False)),
                "use_subroles": base.get("use_subroles", getattr(w, "use_subrole_filter", False)),
            }

        new_state = {}
        for role, wheel in wheels.items():
            new_state[role] = wheel_state(wheel, role)
        self._mode_states[mode] = new_state

    def to_saved(self, volume: int) -> Dict[str, Any]:
        return {
            "players": self._mode_states.get("players", {}),
            "heroes": self._mode_states.get("heroes", {}),
            "maps": self._mode_states.get("maps", {}),
            "volume": volume,
        }
