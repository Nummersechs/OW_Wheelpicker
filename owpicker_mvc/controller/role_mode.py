from __future__ import annotations

from model.mode_keys import is_role_mode
from model.role_keys import role_wheels as build_role_wheels


class RoleModeController:
    """Role-mode helpers to keep MainWindow and spin_service consistent."""

    def __init__(self, main_window) -> None:
        self._mw = main_window

    def role_wheels(self) -> list[tuple[str, object]]:
        return build_role_wheels(self._mw)

    def active_wheels(self) -> list[tuple[str, object]]:
        return [
            (role, wheel)
            for role, wheel in self.role_wheels()
            if wheel.is_selected_for_global_spin()
        ]

    def any_selected(self) -> bool:
        return any(wheel.is_selected_for_global_spin() for _role, wheel in self.role_wheels())

    def can_spin_all(self) -> bool:
        return self.any_selected() and getattr(self._mw, "pending", 0) == 0

    def is_active_mode(self) -> bool:
        if not is_role_mode(getattr(self._mw, "current_mode", None)):
            return False
        if getattr(self._mw, "hero_ban_active", False):
            return False
        open_queue = getattr(self._mw, "open_queue", None)
        if open_queue and open_queue.is_mode_active():
            return False
        return True
