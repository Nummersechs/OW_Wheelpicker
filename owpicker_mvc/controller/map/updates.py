from __future__ import annotations

from PySide6 import QtCore

from .combined_state import build_override_entries, collect_combined_active_names


class MapUICombinedUpdateController:
    def __init__(self, owner, *, delay_ms: int = 140) -> None:
        self._owner = owner
        self._update_delay_ms = max(0, int(delay_ms))
        self._map_combined: list[str] = []
        self._map_override_entries: list[dict] = []
        self._map_override_signature: tuple[str, ...] | None = None
        self._pending_rebuild = False
        self._pending_state_emit = False
        self._pending_wheel_refresh = False
        self._update_timer = QtCore.QTimer(owner)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self.flush_updates)

    @property
    def timer(self) -> QtCore.QTimer:
        return self._update_timer

    def set_active(self, active: bool) -> None:
        if active:
            if self._pending_rebuild or self._pending_wheel_refresh:
                emit_state = bool(self._pending_state_emit)
                self.rebuild_combined(emit_state=emit_state, force_wheel=True)
            self._pending_rebuild = False
            self._pending_state_emit = False
            return
        if self._update_timer.isActive():
            self._update_timer.stop()

    def shutdown(self) -> None:
        if self._update_timer.isActive():
            self._update_timer.stop()
        self._pending_rebuild = False
        self._pending_state_emit = False
        self._pending_wheel_refresh = False

    def resource_snapshot(self) -> dict:
        update_timer_active = False
        try:
            update_timer_active = bool(self._update_timer.isActive())
        except (AttributeError, RuntimeError, TypeError):
            pass
        return {
            "pending_rebuild": bool(self._pending_rebuild),
            "pending_state_emit": bool(self._pending_state_emit),
            "pending_wheel_refresh": bool(self._pending_wheel_refresh),
            "update_timer_active": update_timer_active,
        }

    def schedule_update(self) -> None:
        owner = self._owner
        if not bool(getattr(owner, "_active", False)):
            # Defer expensive merge work while maps mode is inactive.
            self._pending_rebuild = True
            self._pending_wheel_refresh = True
            self._pending_state_emit = True
            return
        self._pending_rebuild = True
        self._pending_state_emit = True
        if not self._update_timer.isActive():
            self._update_timer.start(self._update_delay_ms)

    def flush_updates(self) -> None:
        if not self._pending_rebuild:
            return
        emit_state = self._pending_state_emit
        self._pending_rebuild = False
        self._pending_state_emit = False
        self.apply_combined_update(emit_state=emit_state, force_wheel=False)

    def apply_combined_update(self, emit_state: bool, force_wheel: bool) -> None:
        owner = self._owner
        combined = collect_combined_active_names(owner.map_lists)
        changed = combined != self._map_combined
        if changed:
            self._map_combined = combined
            self._map_override_entries = build_override_entries(combined)
        combined_sig = tuple(self._map_combined)
        if changed or force_wheel or self._pending_wheel_refresh:
            if hasattr(owner, "map_main") and (bool(getattr(owner, "_active", False)) or force_wheel):
                needs_push = (
                    force_wheel
                    or changed
                    or self._pending_wheel_refresh
                    or self._map_override_signature != combined_sig
                )
                if needs_push:
                    owner.map_main.set_override_entries(self._map_override_entries)
                    self._map_override_signature = combined_sig
                self._pending_wheel_refresh = False
            else:
                self._pending_wheel_refresh = True
        if emit_state:
            owner.stateChanged.emit()

    def rebuild_combined(self, emit_state: bool = True, force_wheel: bool = False) -> None:
        if self._update_timer.isActive():
            self._update_timer.stop()
        self._pending_rebuild = False
        self._pending_state_emit = False
        self.apply_combined_update(emit_state=emit_state, force_wheel=force_wheel)

    def combined_names(self) -> list[str]:
        return list(self._map_combined)

    def names_for_category(self, category: str) -> list[str]:
        wheel = self._owner.map_lists.get(category)
        if not wheel:
            return []
        return [e.get("name", "").strip() for e in wheel.get_active_entries() if e.get("name", "").strip()]

