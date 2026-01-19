from __future__ import annotations

from view.wheel_view import WheelView


class OpenQueueController:
    """Handle Open Queue preview/override state outside MainWindow."""

    def __init__(self, main_window) -> None:
        self._mw = main_window
        self._preview_busy = False
        self._preview_restore: dict[WheelView, dict] = {}
        self._spin_restore: list[dict] = []
        self._spin_active = False

    def spin_mode_allowed(self) -> bool:
        return self._mw.current_mode in ("players", "heroes") and not getattr(self._mw, "hero_ban_active", False)

    def is_mode_active(self) -> bool:
        if not self.spin_mode_allowed():
            return False
        toggle = getattr(self._mw, "spin_mode_toggle", None)
        return bool(toggle and toggle.value() == 1)

    def selected_wheels(self) -> list[WheelView]:
        return [w for w in (self._mw.tank, self._mw.dps, self._mw.support) if w.is_selected_for_global_spin()]

    def names(self) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for wheel in self.selected_wheels():
            disabled_labels = set(getattr(wheel, "_disabled_labels", set()) or set())
            for entry in wheel._active_entries():
                name = entry.get("name", "").strip()
                if not name or name in disabled_labels:
                    continue
                if name not in seen:
                    seen.add(name)
                    names.append(name)
        return names

    def slots(self) -> int:
        return sum(2 if w.pair_mode else 1 for w in self.selected_wheels())

    def _view_key(self, wheel: WheelView, names: list[str]) -> tuple:
        use_subroles = bool(getattr(wheel, "use_subrole_filter", False))
        subroles: tuple[str, str] | tuple = ()
        if use_subroles and len(getattr(wheel, "subrole_labels", [])) >= 2:
            subroles = tuple(wheel.subrole_labels[:2])
        return (tuple(names), use_subroles, subroles)

    def _entries_for_wheel(self, wheel: WheelView, names: list[str]) -> list[dict]:
        subroles: list[str] = []
        if getattr(wheel, "use_subrole_filter", False) and len(getattr(wheel, "subrole_labels", [])) >= 2:
            subroles = list(wheel.subrole_labels[:2])
        return [{"name": n, "subroles": list(subroles), "active": True} for n in names]

    def apply_preview(self, combined_names: list[str] | None = None) -> None:
        if self._preview_busy:
            return
        if not self.spin_mode_allowed() or not self.is_mode_active():
            self.clear_preview()
            return
        if self._spin_active:
            return
        names = combined_names if combined_names is not None else self.names()
        for wheel in (self._mw.tank, self._mw.dps, self._mw.support):
            entry = self._preview_restore.get(wheel)
            if entry is None:
                entry = {
                    "override_entries": getattr(wheel, "_override_entries", None),
                    "disabled_indices": set(getattr(wheel, "_disabled_indices", set())),
                    "preview_entries": None,
                    "key": None,
                }
                self._preview_restore[wheel] = entry
            key = self._view_key(wheel, names)
            if entry.get("key") == key and getattr(wheel, "_override_entries", None) is not None:
                continue
            preview_entries = self._entries_for_wheel(wheel, names)
            wheel.set_override_entries(preview_entries)
            entry["preview_entries"] = preview_entries
            entry["key"] = key

    def clear_preview(self) -> None:
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
                current_override = getattr(wheel, "_override_entries", None)
                if preview_entries is not None and current_override is not None and current_override != preview_entries:
                    continue
                wheel.set_override_entries(entry.get("override_entries"))
                wheel._disabled_indices = set(entry.get("disabled_indices", set()))
                wheel._refresh_disabled_indices()
            self._preview_restore = {}
        finally:
            self._preview_busy = False

    def begin_spin_override(self, entries_by_wheel: dict[WheelView, list[dict]]) -> None:
        self._spin_restore = []
        for wheel, entries in entries_by_wheel.items():
            self._spin_restore.append(
                {
                    "wheel": wheel,
                    "override_entries": getattr(wheel, "_override_entries", None),
                    "disabled_indices": set(getattr(wheel, "_disabled_indices", set())),
                }
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
            wheel.set_override_entries(entry.get("override_entries"))
            wheel._disabled_indices = set(entry.get("disabled_indices", set()))
            wheel._refresh_disabled_indices()
        self._spin_restore = []
        self._spin_active = False

    def spin_active(self) -> bool:
        return self._spin_active
