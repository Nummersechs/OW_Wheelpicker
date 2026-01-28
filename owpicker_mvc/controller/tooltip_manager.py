from __future__ import annotations

from PySide6 import QtCore
from typing import Callable
import config


class TooltipManager:
    """Handles tooltip cache rebuilds + readiness without blocking the UI thread."""

    def __init__(self, main_window) -> None:
        self._mw = main_window
        self._step_ms = 80
        self._timer = QtCore.QTimer(main_window)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._run_cache_refresh)
        self._done_callbacks: list[Callable[[], None]] = []

    def shutdown(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def _wheels(self):
        wheels = [self._mw.tank, self._mw.dps, self._mw.support]
        map_main = getattr(self._mw, "map_main", None)
        if map_main:
            include_map = (
                getattr(self._mw, "current_mode", "") == "maps"
                or getattr(config, "TOOLTIP_CACHE_ON_START", True)
            )
            if include_map:
                wheels.append(map_main)
        return wheels

    def refresh_caches_sync(self) -> None:
        """Rebuild tooltip caches immediately (sync)."""
        if getattr(self._mw, "_closing", False):
            return
        if self._mw._overlay_choice_active():
            return
        self._mw._trace_event("refresh_tooltip_caches:sync")
        for w in self._wheels():
            wheel = getattr(getattr(w, "view", None), "wheel", None)
            if wheel and hasattr(wheel, "_ensure_cache"):
                try:
                    wheel._cached = None
                    wheel._ensure_cache(force=True)
                except Exception:
                    pass
            if wheel and hasattr(wheel, "set_tooltips_ready"):
                try:
                    wheel.set_tooltips_ready(True)
                except Exception:
                    pass

    def refresh_caches_async(self, delay_step_ms: int = 80, on_done: Callable[[], None] | None = None) -> None:
        """Rebuild tooltip caches in small slices to keep UI responsive."""
        if getattr(self._mw, "_closing", False):
            return
        if self._mw._overlay_choice_active():
            return
        self._mw._trace_event("refresh_tooltip_caches:async", step_ms=delay_step_ms)
        self._step_ms = max(0, int(delay_step_ms))
        if on_done is not None:
            self._done_callbacks.append(on_done)
        # debounce
        self._timer.start(60)

    def _run_cache_refresh(self) -> None:
        if getattr(self._mw, "_closing", False):
            return
        if self._mw._overlay_choice_active():
            return
        if getattr(self._mw, "_stack_switching", False):
            self._mw._trace_event("run_tooltip_cache_refresh:defer", reason="stack_switching")
            self._timer.start(80)
            return
        self._mw._trace_event("run_tooltip_cache_refresh")

        def rebuild_single(w):
            wheel = getattr(getattr(w, "view", None), "wheel", None)
            if wheel and hasattr(wheel, "_ensure_cache"):
                try:
                    wheel._cached = None
                    wheel._ensure_cache(force=True)
                except Exception:
                    pass

        step_ms = max(0, int(self._step_ms))
        wheels = self._wheels()
        for idx, w in enumerate(wheels):
            QtCore.QTimer.singleShot(idx * step_ms, lambda _w=w: rebuild_single(_w))
        total_delay = len(wheels) * step_ms + 40
        QtCore.QTimer.singleShot(total_delay, self._finish_cache_refresh)

    def _finish_cache_refresh(self) -> None:
        self.ensure_hover_cache(ready=True)
        callbacks = self._done_callbacks
        self._done_callbacks = []
        for cb in callbacks:
            try:
                cb()
            except Exception:
                pass

    def reset_hover_cache_under_cursor(self) -> None:
        for w in self._wheels():
            wheel = getattr(getattr(w, "view", None), "wheel", None)
            if wheel and hasattr(wheel, "_ensure_cache") and hasattr(wheel, "_needs_tooltip_runtime"):
                try:
                    wheel._ensure_cache(force=False)
                except Exception:
                    pass

    def set_tooltips_ready(self, ready: bool = True) -> None:
        if getattr(self._mw, "_closing", False):
            return
        if self._mw._overlay_choice_active():
            return
        for w in self._wheels():
            wheel = getattr(getattr(w, "view", None), "wheel", None)
            if wheel and hasattr(wheel, "set_tooltips_ready"):
                try:
                    wheel.set_tooltips_ready(bool(ready))
                except Exception:
                    pass

    def ensure_hover_cache(self, ready: bool | None = None, refresh_hover: bool = False) -> None:
        if ready is not None:
            self.set_tooltips_ready(ready)
        self.reset_hover_cache_under_cursor()
        if refresh_hover:
            QtCore.QTimer.singleShot(0, self._mw._refresh_hover_under_cursor)
