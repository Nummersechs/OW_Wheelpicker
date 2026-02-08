from __future__ import annotations

from PySide6 import QtCore


class TimerRegistry:
    """Tracks QTimers to stop them reliably on shutdown."""

    def __init__(self) -> None:
        self._timers: set[QtCore.QTimer] = set()

    def register(self, timer: QtCore.QTimer | None) -> QtCore.QTimer | None:
        if timer is None:
            return None
        self._timers.add(timer)
        return timer

    def unregister(self, timer: QtCore.QTimer | None) -> None:
        if timer is None:
            return
        self._timers.discard(timer)

    def stop_all(self) -> None:
        for timer in list(self._timers):
            try:
                if timer.isActive():
                    timer.stop()
            except Exception:
                pass
        self._timers.clear()

    def snapshot(self) -> dict:
        """Return a lightweight registry snapshot for diagnostics."""
        active = 0
        for timer in list(self._timers):
            try:
                if timer.isActive():
                    active += 1
            except Exception:
                pass
        return {
            "registered": len(self._timers),
            "active": active,
        }
