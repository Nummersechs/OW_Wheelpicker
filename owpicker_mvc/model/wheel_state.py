from __future__ import annotations

from typing import List, Optional, Union
import itertools
import difflib


class WheelState:
    """UI-agnostic wheel state and name-computation helpers."""

    def __init__(
        self,
        pair_mode: bool = False,
        use_subrole_filter: bool = False,
        subrole_labels: Optional[List[str]] = None,
    ) -> None:
        self.pair_mode = bool(pair_mode)
        self.use_subrole_filter = bool(use_subrole_filter)
        self.subrole_labels = list(subrole_labels or [])
        self.disabled_indices: set[int] = set()
        self.disabled_labels: set[str] = set()
        self.last_wheel_names: List[str] = []
        self.override_entries: Optional[List[dict]] = None
        self._cached_effective_key: Optional[tuple] = None
        self._cached_effective_names: Optional[List[str]] = None

    def set_override_entries(self, entries: Optional[List[dict]]) -> None:
        self.override_entries = list(entries) if entries is not None else None

    def reset_disabled(self) -> None:
        self.disabled_indices.clear()
        self.disabled_labels.clear()

    def entries_for_spin(self, active_entries: List[dict]) -> List[dict]:
        if self.override_entries is not None:
            return list(self.override_entries)
        return list(active_entries)

    def effective_names_from(
        self,
        base: Union[List[dict], List[str]],
        include_disabled: bool = True,
    ) -> List[str]:
        if not base:
            return []

        # Back-compat: allow a plain list of names.
        if base and isinstance(base[0], str):
            entries = [{"name": n, "subroles": set()} for n in base if n]
        else:
            entries = base  # type: ignore

        entries = [
            {
                "name": str(e.get("name", "")).strip(),
                "subroles": e.get("subroles", set()) or set(),
            }
            for e in entries
            if str(e.get("name", "")).strip()
        ]

        labels_key: tuple = ()
        if self.use_subrole_filter:
            labels_key = tuple(self.subrole_labels[:2])
        entry_key = tuple(
            (
                e["name"],
                tuple(sorted(str(s) for s in (e.get("subroles", set()) or set()) if str(s).strip())),
            )
            for e in entries
        )
        cache_key = (bool(self.pair_mode), bool(self.use_subrole_filter), labels_key, entry_key)
        names: list[str]
        if cache_key == self._cached_effective_key and self._cached_effective_names is not None:
            names = list(self._cached_effective_names)
        else:
            base_names = [e["name"] for e in entries]
            if not self.pair_mode:
                names = base_names
            else:
                if self.use_subrole_filter and len(self.subrole_labels) >= 2:
                    role_a, role_b = self.subrole_labels[:2]
                    pairs: list[str] = []
                    for a, b in itertools.combinations(entries, 2):
                        roles_a = set(a.get("subroles", set()) or set())
                        roles_b = set(b.get("subroles", set()) or set())
                        if not roles_a or not roles_b:
                            continue
                        cond1 = role_a in roles_a and role_b in roles_b
                        cond2 = role_b in roles_a and role_a in roles_b
                        if cond1 or cond2:
                            pairs.append(f"{a['name']} + {b['name']}")
                    names = pairs
                else:
                    names = [f"{a['name']} + {b['name']}" for a, b in itertools.combinations(entries, 2)]
            self._cached_effective_key = cache_key
            self._cached_effective_names = list(names)

        if not include_disabled and self.disabled_indices:
            names = [n for i, n in enumerate(names) if i not in self.disabled_indices]
        return names

    def disable_label(self, names: List[str], label: str, include_related_pairs: bool = False) -> bool:
        if not label or not names:
            return False
        changed = False
        found_label = False
        for idx, name in enumerate(names):
            if name == label:
                found_label = True
                if idx not in self.disabled_indices:
                    self.disabled_indices.add(idx)
                    changed = True
        if not found_label:
            return False
        if include_related_pairs and self.pair_mode:
            parts = self.pair_parts_from_label(label)
            if parts:
                parts_set = set(parts)
                for idx, name in enumerate(names):
                    if idx in self.disabled_indices:
                        continue
                    other_parts = self.pair_parts_from_label(name)
                    if other_parts and parts_set.intersection(other_parts):
                        self.disabled_indices.add(idx)
                        changed = True
        return changed

    def remap_disabled_indices(self, old_names: List[str], new_names: List[str]) -> None:
        if not self.disabled_indices:
            self.disabled_indices = set()
            self.disabled_labels = set()
            return
        sm = difflib.SequenceMatcher(a=old_names, b=new_names)
        mapped: set[int] = set()
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for offset in range(i2 - i1):
                    if (i1 + offset) in self.disabled_indices:
                        mapped.add(j1 + offset)
        self.disabled_indices = mapped
        self.disabled_labels = {new_names[i] for i in self.disabled_indices if i < len(new_names)}

    def sanitize_disabled_indices(self, names: List[str]) -> None:
        if not names:
            self.reset_disabled()
            return
        self.disabled_indices = {i for i in self.disabled_indices if 0 <= i < len(names)}
        self.disabled_labels = {names[i] for i in self.disabled_indices}

    @staticmethod
    def normalize_entries(defaults: Union[List[str], List[dict]]) -> List[dict]:
        """
        Normalize input data into {"name": str, "subroles": [str], "active": bool}.
        """
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
                active = bool(item.get("active", True))
                entries.append({"name": name, "subroles": subs_list, "active": active})
        return entries

    @staticmethod
    def pair_parts_from_label(label: str) -> list[str]:
        parts = [part.strip() for part in label.split(" + ") if part.strip()]
        return parts if len(parts) == 2 else []

    def label_names(self, label: str) -> list[str]:
        """Return underlying name(s) for a label, respecting pair mode."""
        if not label:
            return []
        cleaned = label.strip()
        if not cleaned or cleaned == "–":
            return []
        if self.pair_mode:
            parts = self.pair_parts_from_label(cleaned)
            if parts:
                return parts
        return [cleaned]

    def enabled_indices(self, names: List[str]) -> List[int]:
        if not names:
            return []
        return [i for i in range(len(names)) if i not in self.disabled_indices]

    def enabled_labels(self, names: List[str]) -> set[str]:
        if not names:
            return set()
        if not self.disabled_indices:
            return set(names)
        return {n for i, n in enumerate(names) if i not in self.disabled_indices}
