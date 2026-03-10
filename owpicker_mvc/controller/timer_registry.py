from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class TimerLike(Protocol):
    def isActive(self) -> bool:
        ...

    def stop(self) -> None:
        ...


class TimerRegistry:
    """Tracks timer-like objects and stops them reliably on shutdown."""

    def __init__(self) -> None:
        self._timers: set[TimerLike] = set()

    def register(self, timer: Optional[TimerLike]) -> Optional[TimerLike]:
        if timer is None:
            return None
        if not isinstance(timer, TimerLike):
            return None
        self._timers.add(timer)
        return timer

    def unregister(self, timer: Optional[TimerLike]) -> None:
        if timer is None:
            return
        self._timers.discard(timer)

    def stop_all(self) -> None:
        for timer in list(self._timers):
            try:
                if timer.isActive():
                    timer.stop()
            except (AttributeError, RuntimeError):
                pass
        self._timers.clear()

    def snapshot(self) -> dict:
        """Return a lightweight registry snapshot for diagnostics."""
        active = 0
        for timer in list(self._timers):
            try:
                if timer.isActive():
                    active += 1
            except (AttributeError, RuntimeError):
                pass
        return {
            "registered": len(self._timers),
            "active": active,
        }
