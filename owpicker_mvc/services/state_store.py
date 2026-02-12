"""
Manages mode states (players/heroes/maps) including defaults and capture/restore.
Keeps the data format compatible with saved_state.json.
"""
from __future__ import annotations

import copy
from typing import Dict, List, Any

import config
from model.role_keys import ROLE_KEYS, PAIR_MODE_DEFAULTS


class ModeStateStore:
    _ROLES = ROLE_KEYS

    def __init__(
        self,
        mode_states: Dict[str, Dict[str, dict]] | None = None,
        player_profiles: List[dict] | None = None,
        active_player_profile_index: int = 0,
    ):
        self._mode_states: Dict[str, Dict[str, dict]] = mode_states or {
            "players": {},
            "heroes": {},
            "maps": {},
        }
        if player_profiles is None:
            players_state = self._mode_states.get("players", {})
            self._player_profiles = self._build_profiles_from_players_state(players_state)
            self._active_player_profile_index = 0
        else:
            self._player_profiles = self._normalize_profiles_payload(player_profiles)
            self._active_player_profile_index = self._clamp_profile_index(active_player_profile_index)
        self._sync_players_mode_from_active_profile()

    @classmethod
    def from_saved(cls, saved: dict) -> "ModeStateStore":
        saved = saved or {}
        profiles, active_index = cls._build_player_profiles(saved)
        mode_states = cls._build_mode_states(
            saved,
            active_players_state=profiles[active_index]["players"] if profiles else None,
        )
        return cls(
            mode_states=mode_states,
            player_profiles=profiles,
            active_player_profile_index=active_index,
        )

    @staticmethod
    def _clone(value):
        try:
            return copy.deepcopy(value)
        except Exception:
            return value

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
                entries.append(
                    {
                        "name": name,
                        "subroles": subs_list,
                        "active": bool(item.get("active", True)),
                    }
                )
        return entries

    @classmethod
    def _default_role_state(cls, role: str, mode: str) -> dict:
        if mode == "heroes":
            defaults = config.DEFAULT_HEROES.get(role, [])
        elif mode == "maps":
            defaults = config.DEFAULT_MAPS.get(role, [])
        else:
            defaults = config.DEFAULT_NAMES.get(role, [])
        include_default = True
        if mode == "maps":
            cfg = getattr(config, "MAP_INCLUDE_DEFAULTS", None)
            if isinstance(cfg, dict):
                include_default = bool(cfg.get(role, False))
            elif isinstance(cfg, (list, tuple, set)):
                include_default = role in cfg
            else:
                include_default = True
        return {
            "entries": cls._normalize_entries_for_state(defaults),
            "include_in_all": include_default,
            "pair_mode": PAIR_MODE_DEFAULTS.get(role, False),
            "use_subroles": False,
        }

    @classmethod
    def _role_state_from_saved(cls, data, role: str, mode: str) -> dict:
        base = cls._default_role_state(role, mode)
        if not isinstance(data, dict):
            return base
        if "entries" in data:
            entries = cls._normalize_entries_for_state(data["entries"])
            # Guard: if hero defaults accidentally ended up in player data,
            # reset to player defaults (fix for overwritten player tab).
            if mode == "players":
                hero_defaults = set(config.DEFAULT_HEROES.get(role, []))
                if hero_defaults and set(e["name"] for e in entries) == hero_defaults:
                    entries = cls._normalize_entries_for_state(config.DEFAULT_NAMES.get(role, []))
            base["entries"] = entries
        elif "names" in data:
            base["entries"] = cls._normalize_entries_for_state(data["names"])
        base["include_in_all"] = bool(data.get("include_in_all", base.get("include_in_all", True)))
        base["pair_mode"] = bool(data.get("pair_mode", base["pair_mode"]))
        base["use_subroles"] = bool(data.get("use_subroles", base["use_subroles"]))
        return base

    @classmethod
    def _players_mode_state_from_saved(cls, saved: dict) -> Dict[str, dict]:
        state: Dict[str, dict] = {}
        players_saved = saved.get("players") if isinstance(saved, dict) else {}
        for role in cls._ROLES:
            if isinstance(players_saved, dict) and role in players_saved:
                players_src = players_saved.get(role, {})
            else:
                players_src = saved.get(role, {}) if isinstance(saved, dict) else {}
            state[role] = cls._role_state_from_saved(players_src, role, "players")
        return state

    @classmethod
    def _default_players_mode_state(cls) -> Dict[str, dict]:
        return {role: cls._default_role_state(role, "players") for role in cls._ROLES}

    @classmethod
    def _empty_players_mode_state(cls) -> Dict[str, dict]:
        state = cls._default_players_mode_state()
        for role in cls._ROLES:
            role_state = state.get(role, {})
            if isinstance(role_state, dict):
                role_state["entries"] = []
        return state

    @classmethod
    def _player_profile_capacity(cls) -> int:
        # UI/Storage intentionally fixed to 6 slots.
        return 6

    @classmethod
    def _default_player_profile_names(cls, capacity: int | None = None) -> List[str]:
        cap = capacity if capacity is not None else cls._player_profile_capacity()
        cfg_names = getattr(config, "PLAYER_PROFILE_DEFAULT_NAMES", None)
        names: List[str] = []
        if isinstance(cfg_names, (list, tuple)):
            for raw in cfg_names:
                label = str(raw).strip()
                if label:
                    names.append(label)
        while len(names) < cap:
            names.append(f"Roster {len(names) + 1}")
        return names[:cap]

    @classmethod
    def _default_profile_name_for_slot(cls, index: int) -> str:
        names = cls._default_player_profile_names()
        if 0 <= index < len(names):
            return names[index]
        return f"Roster {index + 1}"

    @classmethod
    def _build_profiles_from_players_state(cls, players_state: Dict[str, dict]) -> List[dict]:
        cap = cls._player_profile_capacity()
        defaults = cls._default_player_profile_names(cap)
        profiles: List[dict] = [
            {
                "name": defaults[0],
                "players": cls._players_mode_state_from_saved({"players": players_state}),
            }
        ]
        while len(profiles) < cap:
            idx = len(profiles)
            profiles.append(
                {
                    "name": defaults[idx],
                    "players": cls._empty_players_mode_state(),
                }
            )
        return profiles

    @classmethod
    def _normalize_profiles_payload(cls, profiles: List[dict] | None) -> List[dict]:
        cap = cls._player_profile_capacity()
        defaults = cls._default_player_profile_names(cap)
        normalized: List[dict] = []
        for idx in range(cap):
            item = profiles[idx] if isinstance(profiles, list) and idx < len(profiles) else {}
            if not isinstance(item, dict):
                item = {}
            name = str(item.get("name", "")).strip() or defaults[idx]
            players_src = item.get("players", {})
            if isinstance(players_src, dict):
                players = cls._players_mode_state_from_saved({"players": players_src})
            else:
                players = cls._empty_players_mode_state()
            normalized.append({"name": name, "players": players})
        return normalized

    @classmethod
    def _build_player_profiles(cls, saved: dict) -> tuple[List[dict], int]:
        cap = cls._player_profile_capacity()
        defaults = cls._default_player_profile_names(cap)
        legacy_players = cls._players_mode_state_from_saved(saved)
        raw_profiles_obj = saved.get("player_profiles") if isinstance(saved, dict) else None
        raw_profiles = raw_profiles_obj.get("profiles") if isinstance(raw_profiles_obj, dict) else None

        if isinstance(raw_profiles, list) and raw_profiles:
            profiles = cls._normalize_profiles_payload(raw_profiles)
        else:
            profiles = [
                {"name": defaults[0], "players": legacy_players},
            ]
            while len(profiles) < cap:
                idx = len(profiles)
                profiles.append(
                    {
                        "name": defaults[idx],
                        "players": cls._empty_players_mode_state(),
                    }
                )

        active_index = 0
        if isinstance(raw_profiles_obj, dict):
            try:
                active_index = int(raw_profiles_obj.get("active_index", 0))
            except Exception:
                active_index = 0
        active_index = max(0, min(cap - 1, active_index))
        return profiles, active_index

    @classmethod
    def _build_mode_states(cls, saved: dict, active_players_state: Dict[str, dict] | None = None) -> dict:
        roles = cls._ROLES
        heroes_saved = saved.get("heroes") if isinstance(saved, dict) else {}
        maps_saved = saved.get("maps") if isinstance(saved, dict) else {}
        mode_states: Dict[str, Dict[str, dict]] = {"players": {}, "heroes": {}, "maps": {}}

        if isinstance(active_players_state, dict) and active_players_state:
            mode_states["players"] = cls._players_mode_state_from_saved({"players": active_players_state})
        else:
            mode_states["players"] = cls._players_mode_state_from_saved(saved)

        for role in roles:
            heroes_src = heroes_saved.get(role, {}) if isinstance(heroes_saved, dict) else {}
            mode_states["heroes"][role] = cls._role_state_from_saved(heroes_src, role, "heroes")

        map_roles = list(getattr(config, "MAP_CATEGORIES", [])) or list(getattr(config, "DEFAULT_MAPS", {}).keys())
        for role in map_roles:
            role_state = {}
            if isinstance(maps_saved, dict):
                role_state = maps_saved.get(role, {})
            mode_states["maps"][role] = cls._role_state_from_saved(role_state, role, "maps")
        return mode_states

    def _clamp_profile_index(self, index: int) -> int:
        if not self._player_profiles:
            return 0
        return max(0, min(len(self._player_profiles) - 1, int(index)))

    def _sync_players_mode_from_active_profile(self) -> None:
        if not self._player_profiles:
            self._mode_states["players"] = self._default_players_mode_state()
            return
        active = self._player_profiles[self._active_player_profile_index]
        self._mode_states["players"] = self._players_mode_state_from_saved({"players": active.get("players", {})})

    def _sync_active_profile_from_players_mode(self) -> None:
        if not self._player_profiles:
            return
        players_state = self._players_mode_state_from_saved({"players": self._mode_states.get("players", {})})
        self._player_profiles[self._active_player_profile_index]["players"] = players_state

    def get_player_profile_names(self) -> List[str]:
        return [str(p.get("name", "")).strip() for p in self._player_profiles]

    def get_active_player_profile_index(self) -> int:
        return int(self._active_player_profile_index)

    def rename_player_profile(self, index: int, new_name: str) -> bool:
        if not self._player_profiles:
            return False
        idx = self._clamp_profile_index(index)
        label = str(new_name or "").strip() or self._default_profile_name_for_slot(idx)
        if self._player_profiles[idx]["name"] == label:
            return False
        self._player_profiles[idx]["name"] = label
        return True

    def set_active_player_profile(self, index: int) -> bool:
        if not self._player_profiles:
            return False
        idx = self._clamp_profile_index(index)
        if idx == self._active_player_profile_index:
            return False
        self._sync_active_profile_from_players_mode()
        self._active_player_profile_index = idx
        self._sync_players_mode_from_active_profile()
        return True

    def reorder_player_profiles(self, order: List[int]) -> bool:
        if not self._player_profiles:
            return False
        n = len(self._player_profiles)
        try:
            indices = [int(v) for v in order]
        except Exception:
            return False
        if len(indices) != n:
            return False
        if sorted(indices) != list(range(n)):
            return False
        if indices == list(range(n)):
            return False
        active_profile = self._player_profiles[self._active_player_profile_index]
        self._player_profiles = [self._player_profiles[i] for i in indices]
        for idx, profile in enumerate(self._player_profiles):
            if profile is active_profile:
                self._active_player_profile_index = idx
                break
        self._sync_players_mode_from_active_profile()
        return True

    def get_mode_state(self, mode: str) -> Dict[str, dict]:
        return self._mode_states.get(mode, {})

    def set_mode_state(self, mode: str, state: Dict[str, dict]) -> None:
        self._mode_states[mode] = state
        if mode == "players":
            self._sync_active_profile_from_players_mode()

    def default_role_state(self, role: str, mode: str) -> dict:
        return self._default_role_state(role, mode)

    def capture_mode_from_wheels(self, mode: str, wheels: Dict[str, Any], hero_ban_active: bool = False) -> None:
        """Update mode state based on current WheelViews (role -> WheelView)."""
        base_state = self._mode_states.get(mode, {}) if hero_ban_active else {}

        def wheel_state(w, role: str) -> dict:
            base = base_state.get(role, {}) if isinstance(base_state, dict) else {}
            return {
                "entries": w.get_current_entries(),
                "include_in_all": bool(getattr(getattr(w, "btn_include_in_all", None), "isChecked", lambda: True)()),
                "pair_mode": base.get("pair_mode", getattr(w, "pair_mode", False)),
                "use_subroles": base.get("use_subroles", getattr(w, "use_subrole_filter", False)),
            }

        new_state = {}
        for role, wheel in wheels.items():
            new_state[role] = wheel_state(wheel, role)
        self._mode_states[mode] = new_state
        if mode == "players":
            self._sync_active_profile_from_players_mode()

    def to_saved(self, volume: int) -> Dict[str, Any]:
        profiles_payload = []
        for idx, profile in enumerate(self._player_profiles):
            profiles_payload.append(
                {
                    "name": str(profile.get("name", "")).strip() or self._default_profile_name_for_slot(idx),
                    "players": self._clone(profile.get("players", {})),
                }
            )
        return {
            "players": self._mode_states.get("players", {}),
            "player_profiles": {
                "active_index": int(self._active_player_profile_index),
                "profiles": profiles_payload,
            },
            "heroes": self._mode_states.get("heroes", {}),
            "maps": self._mode_states.get("maps", {}),
            "volume": volume,
        }
