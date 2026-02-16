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
        self._last_signature: tuple | None = None
        self._pending_signature: tuple | None = None
        self._paused = False
        self._generation = 0

    def pause(self) -> None:
        if self._paused:
            return
        self._paused = True
        # Invalidate already scheduled singleShot callbacks.
        self._generation += 1
        if self._timer.isActive():
            self._timer.stop()

    def resume(self) -> None:
        if not self._paused:
            return
        self._paused = False
        # Continue pending refresh work after spin/overlay phases.
        if self._pending_signature is not None:
            self._timer.start(0)

    def shutdown(self) -> None:
        if self._timer.isActive():
            self._timer.stop()

    def resource_snapshot(self) -> dict:
        timer_active = False
        try:
            timer_active = bool(self._timer.isActive())
        except Exception:
            timer_active = False
        return {
            "timer_active": timer_active,
            "paused": bool(self._paused),
            "done_callbacks": len(self._done_callbacks),
            "has_last_signature": bool(self._last_signature is not None),
            "has_pending_signature": bool(self._pending_signature is not None),
        }

    def _wheels(self):
        current_mode = getattr(self._mw, "current_mode", "")
        if current_mode == "maps":
            map_main = getattr(self._mw, "map_main", None)
            return [map_main] if map_main else []
        wheels = [self._mw.tank, self._mw.dps, self._mw.support]
        map_main = getattr(self._mw, "map_main", None)
        if map_main and getattr(config, "TOOLTIP_CACHE_ON_START", True):
            wheels.append(map_main)
        return wheels

    def refresh_caches_async(
        self,
        delay_step_ms: int = 80,
        on_done: Callable[[], None] | None = None,
        reason: str | None = None,
        force: bool = False,
    ) -> None:
        """Rebuild tooltip caches in small slices to keep UI responsive."""
        if getattr(self._mw, "_closing", False):
            return
        if self._mw._overlay_choice_active():
            return
        wheels = self._wheels()
        if not wheels:
            return
        signature = self._build_signature(wheels)
        if not force and (signature == self._last_signature or signature == self._pending_signature):
            try:
                self._mw._trace_event("refresh_tooltip_caches:skip", reason=reason or "async")
            except Exception:
                pass
            return
        self._pending_signature = signature
        self._mw._trace_event("refresh_tooltip_caches:async", step_ms=delay_step_ms)
        self._step_ms = max(0, int(delay_step_ms))
        if on_done is not None:
            self._done_callbacks.append(on_done)
        if self._paused:
            return
        # debounce
        self._timer.start(60)

    def _run_cache_refresh(self) -> None:
        if self._paused:
            return
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
        generation = int(self._generation)

        def _rebuild_single_guarded(w, generation_key: int) -> None:
            if self._paused:
                return
            if int(generation_key) != int(self._generation):
                return
            rebuild_single(w)

        for idx, w in enumerate(wheels):
            QtCore.QTimer.singleShot(
                idx * step_ms,
                lambda _w=w, _g=generation: _rebuild_single_guarded(_w, _g),
            )
        total_delay = len(wheels) * step_ms + 40
        QtCore.QTimer.singleShot(
            total_delay,
            lambda _g=generation: self._finish_cache_refresh(_g),
        )

    def _finish_cache_refresh(self, generation_key: int | None = None) -> None:
        if generation_key is not None and int(generation_key) != int(self._generation):
            return
        if self._paused:
            return
        self.ensure_hover_cache(ready=True)
        if self._pending_signature is not None:
            self._last_signature = self._pending_signature
            self._pending_signature = None
        callbacks = self._done_callbacks
        self._done_callbacks = []
        for cb in callbacks:
            try:
                cb()
            except Exception:
                pass

    def _build_signature(self, wheels) -> tuple:
        mode = getattr(self._mw, "current_mode", "")
        theme = getattr(self._mw, "theme", None)
        lang = getattr(self._mw, "language", None)
        revs = []
        for w in wheels:
            if not w:
                continue
            rev = None
            try:
                rev_attr = getattr(w, "tooltip_revision", None)
                rev = rev_attr() if callable(rev_attr) else rev_attr
            except Exception:
                rev = None
            revs.append((id(w), rev))
        return (mode, theme, lang, tuple(revs))

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
