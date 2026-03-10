from __future__ import annotations

from typing import Optional, Protocol

from model.mode_keys import is_role_mode
from model.role_keys import role_wheels


class OpenQueueWheel(Protocol):
    def is_selected_for_global_spin(self) -> bool: ...
    def set_included_in_global_spin(self, enabled: bool) -> None: ...
    def get_enabled_names(self) -> list[str]: ...
    def get_subrole_labels(self) -> list[str]: ...
    def is_pair_mode_enabled(self) -> bool: ...
    def set_pair_mode_enabled(self, enabled: bool) -> None: ...
    def is_subrole_filter_enabled(self) -> bool: ...
    def set_subrole_filter_enabled(self, enabled: bool) -> None: ...
    def set_override_entries(self, entries: Optional[list[dict]]) -> None: ...
    def get_override_entries(self) -> Optional[list[dict]]: ...
    def get_disabled_indices(self) -> set[int]: ...
    def restore_disabled_indices(self, indices: Optional[set[int]]) -> None: ...


class OpenQueueHost(Protocol):
    def role_wheels(self) -> list[tuple[str, OpenQueueWheel]]: ...
    def current_mode(self) -> str: ...
    def hero_ban_active(self) -> bool: ...
    def spin_mode_value(self) -> int: ...


class MainWindowOpenQueueHost:
    """Adapter that exposes the minimal Open Queue host interface."""

    def __init__(self, main_window) -> None:
        self._main_window = main_window

    def role_wheels(self) -> list[tuple[str, OpenQueueWheel]]:
        return [(role, wheel) for role, wheel in role_wheels(self._main_window)]

    def current_mode(self) -> str:
        return str(getattr(self._main_window, "current_mode", "") or "")

    def hero_ban_active(self) -> bool:
        return bool(getattr(self._main_window, "hero_ban_active", False))

    def spin_mode_value(self) -> int:
        toggle = getattr(self._main_window, "spin_mode_toggle", None)
        if toggle is None or not hasattr(toggle, "value"):
            return 0
        try:
            return int(toggle.value())
        except (AttributeError, TypeError, ValueError):
            return 0


class OpenQueueController:
    """Handle Open Queue preview/override state outside MainWindow."""
    OPEN_MIN_PLAYERS = 1
    OPEN_MAX_PLAYERS = 6
    _OPEN_FILL_ORDER = ("Tank", "Damage", "Support", "Support", "Damage", "Tank")

    def __init__(self, host_or_main_window) -> None:
        self._host = self._as_host(host_or_main_window)
        self._preview_busy = False
        self._preview_restore: dict[OpenQueueWheel, dict] = {}
        self._spin_restore: list[dict] = []
        self._spin_active = False
        self._open_player_count = 3
        self._applying_open_combination = False

    @staticmethod
    def _as_host(host_or_main_window) -> OpenQueueHost:
        if (
            hasattr(host_or_main_window, "role_wheels")
            and callable(getattr(host_or_main_window, "role_wheels", None))
            and hasattr(host_or_main_window, "current_mode")
            and callable(getattr(host_or_main_window, "current_mode", None))
            and hasattr(host_or_main_window, "hero_ban_active")
            and callable(getattr(host_or_main_window, "hero_ban_active", None))
            and hasattr(host_or_main_window, "spin_mode_value")
            and callable(getattr(host_or_main_window, "spin_mode_value", None))
        ):
            return host_or_main_window
        return MainWindowOpenQueueHost(host_or_main_window)

    def _all_role_wheels(self) -> list[tuple[str, OpenQueueWheel]]:
        return list(self._host.role_wheels())

    def spin_mode_allowed(self) -> bool:
        return is_role_mode(self._host.current_mode()) and not self._host.hero_ban_active()

    def is_mode_active(self) -> bool:
        if not self.spin_mode_allowed():
            return False
        return self._host.spin_mode_value() == 1

    def selected_wheels(self) -> list[OpenQueueWheel]:
        return [wheel for _role, wheel in self._all_role_wheels() if wheel.is_selected_for_global_spin()]

    def all_wheels(self) -> list[OpenQueueWheel]:
        return [wheel for _role, wheel in self._all_role_wheels()]

    def is_applying_combination(self) -> bool:
        return bool(self._applying_open_combination)

    def names(self, *, include_selected_only: bool = False) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        wheels = self.selected_wheels() if include_selected_only else self.all_wheels()
        for wheel in wheels:
            for name in wheel.get_enabled_names():
                if name in seen:
                    continue
                seen.add(name)
                names.append(name)
        return names

    def slots(self) -> int:
        return sum(slots for _role, _wheel, slots in self.slot_plan())

    def _slots_from_wheel_state(self) -> dict[str, int]:
        slots_by_role: dict[str, int] = {}
        for role, wheel in self._all_role_wheels():
            include = bool(wheel.is_selected_for_global_spin())
            pair_mode = bool(wheel.is_pair_mode_enabled())
            slots_by_role[role] = 2 if include and pair_mode else (1 if include else 0)
        return slots_by_role

    def infer_player_count_from_wheels(self) -> int:
        current = self._slots_from_wheel_state()
        max_allowed = max(self.OPEN_MIN_PLAYERS, int(self.max_slots_capacity()))
        for requested in range(self.OPEN_MIN_PLAYERS, max_allowed + 1):
            plan = self.slot_plan(requested=requested)
            plan_slots = {role: slots for role, _wheel, slots in plan}
            if all(plan_slots.get(role, 0) == slots for role, slots in current.items()):
                return requested
        total_slots = sum(current.values())
        if total_slots <= 0:
            return self.OPEN_MIN_PLAYERS
        return self._clamp_player_count(total_slots, max_allowed=max_allowed)

    def sync_player_count_from_wheels(self) -> bool:
        inferred = self.infer_player_count_from_wheels()
        return self.set_player_count(inferred, max_allowed=self.max_slots_capacity())

    def max_slots_capacity(self) -> int:
        return max(0, min(self.OPEN_MAX_PLAYERS, 2 * len(self._all_role_wheels())))

    def _clamp_player_count(self, value: int, *, max_allowed: int | None = None) -> int:
        clamped = max(self.OPEN_MIN_PLAYERS, min(self.OPEN_MAX_PLAYERS, int(value)))
        if max_allowed is None:
            return clamped
        return min(clamped, max(self.OPEN_MIN_PLAYERS, int(max_allowed)))

    def _wheel_subroles(self, wheel: OpenQueueWheel) -> list[str]:
        labels = wheel.get_subrole_labels()
        if bool(wheel.is_subrole_filter_enabled()) and len(labels) >= 2:
            return list(labels[:2])
        return []

    @staticmethod
    def _wheel_mode_state(wheel: OpenQueueWheel) -> tuple[bool, bool]:
        return bool(wheel.is_pair_mode_enabled()), bool(wheel.is_subrole_filter_enabled())

    def _apply_wheel_mode_state(
        self,
        wheel: OpenQueueWheel,
        *,
        pair_mode: bool,
        use_subroles: bool,
    ) -> None:
        wheel.set_pair_mode_enabled(bool(pair_mode))
        wheel.set_subrole_filter_enabled(bool(use_subroles))

    def player_count(self, *, max_allowed: int | None = None) -> int:
        return self._clamp_player_count(self._open_player_count, max_allowed=max_allowed)

    def set_player_count(self, value: int, *, max_allowed: int | None = None) -> bool:
        next_value = self._clamp_player_count(value, max_allowed=max_allowed)
        if next_value == self._open_player_count:
            return False
        self._open_player_count = next_value
        return True

    def slot_plan(
        self,
        *,
        requested: int | None = None,
        active: list[tuple[str, OpenQueueWheel]] | None = None,
    ) -> list[tuple[str, OpenQueueWheel, int]]:
        del active  # Open uses a fixed role combination per requested count.
        role_wheels_all = self._all_role_wheels()
        if not role_wheels_all:
            return []

        capacity = 2 * len(role_wheels_all)
        desired = self.player_count(max_allowed=capacity) if requested is None else self._clamp_player_count(requested)
        if desired > capacity:
            return []

        slots_by_role = {"Tank": 0, "Damage": 0, "Support": 0}
        # Fixed Open combinations (1..6):
        # 1: T
        # 2: T+D
        # 3: T+D+S
        # 4: T+D+S(pair)
        # 5: T+D(pair)+S(pair)
        # 6: T(pair)+D(pair)+S(pair)
        for role in self._OPEN_FILL_ORDER[:desired]:
            slots_by_role[role] += 1

        return [(role, wheel, slots_by_role.get(role, 0)) for role, wheel in role_wheels_all]

    def apply_slider_combination(self) -> None:
        if self._applying_open_combination:
            return
        if not self.is_mode_active():
            return
        plan = self.slot_plan()
        if not plan:
            return

        self._applying_open_combination = True
        try:
            for _role, wheel, slots in plan:
                include = bool(slots > 0)
                pair_mode = bool(slots >= 2)
                wheel.set_included_in_global_spin(include)
                wheel.set_pair_mode_enabled(pair_mode)
        finally:
            self._applying_open_combination = False

    def _view_key(self, wheel: OpenQueueWheel, names: list[str]) -> tuple:
        use_subroles = bool(wheel.is_subrole_filter_enabled())
        subroles = tuple(self._wheel_subroles(wheel)) if use_subroles else ()
        return (tuple(names), use_subroles, subroles)

    def _entries_for_wheel(self, wheel: OpenQueueWheel, names: list[str]) -> list[dict]:
        subroles = self._wheel_subroles(wheel)
        return [{"name": n, "subroles": list(subroles), "active": True} for n in names]

    def apply_preview(self, combined_names: list[str] | None = None) -> None:
        if self._preview_busy:
            return
        if not self.spin_mode_allowed() or not self.is_mode_active():
            # On explicit mode switch back to role-mode we always restore original wheels.
            self.clear_preview(force=True)
            return
        if self._spin_active:
            return
        names = combined_names if combined_names is not None else self.names()
        for _role, wheel in self._all_role_wheels():
            entry = self._preview_restore.get(wheel)
            if entry is None:
                entry = {
                    "override_entries": wheel.get_override_entries(),
                    "disabled_indices": wheel.get_disabled_indices(),
                    "preview_entries": None,
                    "key": None,
                }
                self._preview_restore[wheel] = entry
            key = self._view_key(wheel, names)
            if entry.get("key") == key and wheel.get_override_entries() is not None:
                continue
            preview_entries = self._entries_for_wheel(wheel, names)
            wheel.set_override_entries(preview_entries)
            entry["preview_entries"] = preview_entries
            entry["key"] = key

    def clear_preview(self, *, force: bool = False) -> None:
        if self._preview_busy:
            return
        if not self._preview_restore:
            return
        if self._spin_active:
            return
        self._preview_busy = True
        try:
            for wheel, entry in list(self._preview_restore.items()):
                preview_entries = entry.get("preview_entries")
                current_override = wheel.get_override_entries()
                if (
                    not force
                    and preview_entries is not None
                    and current_override is not None
                    and current_override != preview_entries
                ):
                    continue
                wheel.set_override_entries(entry.get("override_entries"))
                wheel.restore_disabled_indices(set(entry.get("disabled_indices", set())))
            self._preview_restore = {}
        finally:
            self._preview_busy = False

    def begin_spin_override(
        self,
        entries_by_wheel: dict[OpenQueueWheel, list[dict]],
        *,
        mode_overrides: dict[OpenQueueWheel, dict[str, bool]] | None = None,
    ) -> None:
        mode_overrides = mode_overrides or {}
        self._spin_restore = []
        for wheel, entries in entries_by_wheel.items():
            current_pair_mode, current_use_subroles = self._wheel_mode_state(wheel)
            self._spin_restore.append(
                {
                    "wheel": wheel,
                    "override_entries": wheel.get_override_entries(),
                    "pair_mode_state": current_pair_mode,
                    "use_subroles_state": current_use_subroles,
                    "disabled_indices": wheel.get_disabled_indices(),
                }
            )
            override = mode_overrides.get(wheel) or {}
            next_pair_mode = bool(override.get("pair_mode", current_pair_mode))
            next_use_subroles = bool(override.get("use_subroles", current_use_subroles))
            self._apply_wheel_mode_state(
                wheel,
                pair_mode=next_pair_mode,
                use_subroles=next_use_subroles,
            )
            wheel.set_override_entries(entries)
        self._spin_active = True

    def restore_spin_overrides(self) -> None:
        if not self._spin_restore:
            self._spin_active = False
            return
        for entry in self._spin_restore:
            wheel = entry.get("wheel")
            if not wheel:
                continue
            default_pair_mode, default_use_subroles = self._wheel_mode_state(wheel)
            restored_pair_mode = bool(entry.get("pair_mode_state", default_pair_mode))
            restored_use_subroles = bool(entry.get("use_subroles_state", default_use_subroles))
            self._apply_wheel_mode_state(
                wheel,
                pair_mode=restored_pair_mode,
                use_subroles=restored_use_subroles,
            )
            wheel.set_override_entries(entry.get("override_entries"))
            wheel.restore_disabled_indices(set(entry.get("disabled_indices", set())))
        self._spin_restore = []
        self._spin_active = False
        # If Open Queue was disabled during spin, ensure we leave preview mode.
        if not self.is_mode_active():
            self.clear_preview(force=True)

    def spin_active(self) -> bool:
        return self._spin_active
