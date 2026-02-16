from __future__ import annotations

import time
from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets

import config


def _cfg(mw, key: str, default=None):
    getter = getattr(mw, "_cfg", None)
    if callable(getter):
        try:
            return getter(key, default)
        except Exception:
            pass
    return getattr(config, key, default)


def _background_services_paused(mw) -> bool:
    return bool(getattr(mw, "_background_services_paused", False))


def mark_hover_activity(mw) -> None:
    mw._hover_activity_last = time.monotonic()


def mark_hover_user_move(mw) -> None:
    now = time.monotonic()
    mw._hover_user_move_last = now
    mw._hover_activity_last = now
    if not getattr(mw, "_hover_watchdog_started", False):
        ensure_hover_watchdog_started(mw)


def ensure_hover_watchdog_started(mw) -> None:
    if _background_services_paused(mw):
        return
    if _cfg(mw, "DISABLE_TOOLTIPS", False):
        return
    if not _cfg(mw, "HOVER_WATCHDOG_ON", False):
        return
    if not hasattr(mw, "_hover_watchdog_timer") or not mw._hover_watchdog_timer:
        return
    if mw._hover_watchdog_started:
        if not mw._hover_watchdog_timer.isActive():
            mw._hover_watchdog_timer.start()
        return
    # Start only after first real user input to avoid early re-entrant events.
    mw._hover_watchdog_started = True
    if not mw._hover_watchdog_timer.isActive():
        mw._hover_watchdog_timer.start()


def mark_hover_seen(mw, source: str | None = None) -> None:
    mark_hover_activity(mw)
    mw._hover_seen = True
    if hasattr(mw, "_hover_pump_timer") and mw._hover_pump_timer and mw._hover_pump_timer.isActive():
        try:
            mw._hover_pump_timer.stop()
        except Exception:
            pass
    if source:
        mw._trace_hover_event("hover_seen", source=source)


def record_hover_prime_deferred(mw, reason: str | None = None) -> None:
    mw._hover_prime_pending = True
    if reason:
        mw._hover_prime_reason = reason
    count = int(getattr(mw, "_hover_prime_deferred_count", 0)) + 1
    mw._hover_prime_deferred_count = count
    if count == 1:
        mw._hover_prime_first_reason = reason
        mw._hover_prime_last_reason = reason
        if reason:
            mw._trace_hover_event("hover_pump_deferred", reason=reason)
        else:
            mw._trace_hover_event("hover_pump_deferred")
    elif reason:
        mw._hover_prime_last_reason = reason


def flush_hover_prime_deferred_trace(mw) -> None:
    count = int(getattr(mw, "_hover_prime_deferred_count", 0))
    if count > 1:
        first_reason = getattr(mw, "_hover_prime_first_reason", None)
        last_reason = getattr(mw, "_hover_prime_last_reason", None)
        extra = {"count": count}
        if first_reason:
            extra["first_reason"] = first_reason
        if last_reason and last_reason != first_reason:
            extra["last_reason"] = last_reason
        mw._trace_hover_event("hover_pump_deferred_coalesced", **extra)
    mw._hover_prime_deferred_count = 0
    mw._hover_prime_first_reason = None
    mw._hover_prime_last_reason = None


def start_hover_pump(
    mw,
    reason: str | None = None,
    duration_ms: int | None = None,
    force: bool = False,
) -> None:
    if _background_services_paused(mw):
        return
    if getattr(mw, "_closing", False):
        return
    if getattr(mw, "_startup_block_input", False) or getattr(mw, "_startup_drain_active", False):
        record_hover_prime_deferred(mw, reason=reason)
        return
    if not force and not _cfg(mw, "HOVER_PUMP_ON_START", False):
        return
    flush_hover_prime_deferred_trace(mw)
    if mw._overlay_choice_active():
        return
    if mw._hover_seen:
        return
    duration_ms = int(duration_ms or _cfg(mw, "HOVER_PUMP_DURATION_MS", 1200))
    if duration_ms <= 0:
        mw._hover_pump_until = None
    else:
        now = time.monotonic()
        until = now + (duration_ms / 1000.0)
        if mw._hover_pump_until is None or until > mw._hover_pump_until:
            mw._hover_pump_until = until
    if mw._hover_pump_timer and not mw._hover_pump_timer.isActive():
        mw._hover_pump_timer.start()
    if reason:
        mw._trace_hover_event("hover_pump_start", reason=reason, duration_ms=duration_ms)


def hover_pump_tick(mw) -> None:
    if _background_services_paused(mw):
        try:
            if mw._hover_pump_timer:
                mw._hover_pump_timer.stop()
        except Exception:
            pass
        return
    if getattr(mw, "_closing", False):
        return
    if mw._overlay_choice_active():
        try:
            if mw._hover_pump_timer:
                mw._hover_pump_timer.stop()
        except Exception:
            pass
        return
    if not mw.isActiveWindow():
        try:
            if mw._hover_pump_timer:
                mw._hover_pump_timer.stop()
        except Exception:
            pass
        return
    if mw._hover_seen:
        try:
            if mw._hover_pump_timer:
                mw._hover_pump_timer.stop()
        except Exception:
            pass
        return
    now = time.monotonic()
    if mw._hover_pump_until is not None and now > mw._hover_pump_until:
        try:
            if mw._hover_pump_timer:
                mw._hover_pump_timer.stop()
        except Exception:
            pass
        return
    try:
        pos = QtGui.QCursor.pos()
    except Exception:
        return
    hit = hover_poke_at_global(mw, pos, reason="hover_pump")
    if hit:
        # Stop the pump once a hover event lands on a view to avoid extra spam/lag.
        mark_hover_seen(mw, source="hover_pump")


def hover_poke_under_cursor(mw, reason: str | None = None) -> None:
    if _background_services_paused(mw):
        return
    if not _cfg(mw, "HOVER_POKE_ON_REARM", False):
        return
    if getattr(mw, "_closing", False):
        return
    if mw._overlay_choice_active():
        return
    try:
        pos = QtGui.QCursor.pos()
    except Exception:
        return
    hover_poke_at_global(mw, pos, reason=reason)


def hover_cursor_hits_view(mw, pos: QtCore.QPoint) -> bool:
    for view in iter_hover_views(mw):
        try:
            if hasattr(view, "isVisible") and not view.isVisible():
                continue
            vp = view.viewport()
            if hasattr(vp, "isVisible") and not vp.isVisible():
                continue
            local = vp.mapFromGlobal(pos)
            if vp.rect().contains(local):
                return True
        except Exception:
            continue
    return False


def iter_hover_views(mw, include_maps: bool | None = None) -> list:
    views: list = []
    for _role, w in mw._role_wheels():
        if not w:
            continue
        view = getattr(w, "view", None)
        if view is not None:
            views.append(view)
    if include_maps is None:
        include_maps = getattr(mw, "current_mode", "") == "maps"
    if include_maps:
        map_main = getattr(mw, "map_main", None)
        if map_main:
            view = getattr(map_main, "view", None)
            if view is not None:
                views.append(view)
        if hasattr(mw, "map_lists"):
            for w in mw.map_lists.values():
                view = getattr(w, "view", None)
                if view is not None:
                    views.append(view)
    return views


def hover_watchdog_tick(mw) -> None:
    if _background_services_paused(mw):
        return
    if _cfg(mw, "DISABLE_TOOLTIPS", False):
        return
    if not _cfg(mw, "HOVER_WATCHDOG_ON", False):
        return
    if getattr(mw, "_closing", False):
        return
    if mw._overlay_choice_active():
        return
    if getattr(mw, "_stack_switching", False):
        return
    if getattr(mw, "_map_prebuild_in_progress", False):
        return
    if not mw.isActiveWindow():
        return
    if not mw.isVisible():
        return
    req_move_ms = int(_cfg(mw, "HOVER_WATCHDOG_REQUIRE_MOVE_MS", 0))
    if req_move_ms > 0:
        last_move = getattr(mw, "_hover_user_move_last", None)
        if last_move is None:
            return
        if (time.monotonic() - last_move) > (req_move_ms / 1000.0):
            return
    last = getattr(mw, "_hover_activity_last", None)
    if last is None:
        return
    now = time.monotonic()
    stale_ms = int(_cfg(mw, "HOVER_WATCHDOG_STALE_MS", 650))
    if (now - last) < (stale_ms / 1000.0):
        return
    cooldown_ms = int(_cfg(mw, "HOVER_WATCHDOG_COOLDOWN_MS", 700))
    last_watch = getattr(mw, "_hover_watchdog_last", None)
    if last_watch is not None and (now - last_watch) < (cooldown_ms / 1000.0):
        return
    try:
        pos = QtGui.QCursor.pos()
    except Exception:
        return
    if not hover_cursor_hits_view(mw, pos):
        return
    mw._hover_watchdog_last = now
    mw._hover_seen = False
    mw._hover_forward_last = None
    mw._trace_hover_event("hover_watchdog", age_ms=int((now - last) * 1000))
    rearm_hover_tracking(mw, reason="hover_watchdog")
    start_hover_pump(mw, reason="hover_watchdog", duration_ms=800, force=True)


def hover_poke_at_global(mw, pos: QtCore.QPoint, reason: str | None = None) -> bool:
    if _background_services_paused(mw):
        return False
    if _cfg(mw, "DISABLE_TOOLTIPS", False):
        return False
    if getattr(mw, "_closing", False):
        return False
    if getattr(mw, "_startup_block_input", False) or getattr(mw, "_startup_drain_active", False):
        return False
    if mw._overlay_choice_active():
        return False
    views = iter_hover_views(mw)
    prev_forwarding = getattr(mw, "_hover_forwarding", False)
    mw._hover_forwarding = True
    hit = False
    for view in views:
        try:
            if hasattr(view, "isVisible") and not view.isVisible():
                continue
            vp = view.viewport()
            if hasattr(vp, "isVisible") and not vp.isVisible():
                continue
            local = vp.mapFromGlobal(pos)
            if not vp.rect().contains(local):
                continue
            hit = True
            if not bool(getattr(vp, "_hover_entered", False)):
                try:
                    QtWidgets.QApplication.sendEvent(vp, QtCore.QEvent(QtCore.QEvent.Enter))
                except Exception:
                    pass
                try:
                    hover_enter = QtGui.QHoverEvent(
                        QtCore.QEvent.HoverEnter,
                        QtCore.QPointF(local),
                        QtCore.QPointF(local),
                    )
                    QtWidgets.QApplication.sendEvent(vp, hover_enter)
                except Exception:
                    pass
                try:
                    setattr(vp, "_hover_entered", True)
                except Exception:
                    pass
            if reason:
                mw._trace_hover_event(
                    "hover_poke",
                    reason=reason,
                    view=type(view).__name__,
                    local=f"{local.x()},{local.y()}",
                )
            try:
                hover = QtGui.QHoverEvent(
                    QtCore.QEvent.HoverMove,
                    QtCore.QPointF(local),
                    QtCore.QPointF(local),
                )
                QtWidgets.QApplication.sendEvent(vp, hover)
            except Exception:
                pass
            try:
                mouse = QtGui.QMouseEvent(
                    QtCore.QEvent.MouseMove,
                    QtCore.QPointF(local),
                    QtCore.QPointF(local),
                    QtCore.QPointF(pos),
                    QtCore.Qt.NoButton,
                    QtCore.Qt.NoButton,
                    QtCore.Qt.NoModifier,
                )
                QtWidgets.QApplication.sendEvent(vp, mouse)
            except Exception:
                pass
            # A single hit under cursor is enough to revive hover handling.
            # Poking additional views can create avoidable UI stalls.
            break
        except Exception:
            continue
    mw._hover_forwarding = prev_forwarding
    return hit


def forward_hover_from_app_mousemove(mw, event: QtGui.QMouseEvent) -> None:
    if _background_services_paused(mw):
        return
    if _cfg(mw, "DISABLE_TOOLTIPS", False):
        return
    if not _cfg(mw, "HOVER_FORWARD_MOUSEMOVE", False):
        return
    if getattr(mw, "_closing", False):
        return
    if mw._overlay_choice_active():
        return
    if getattr(mw, "_hover_forwarding", False):
        return
    try:
        if event.buttons() != QtCore.Qt.NoButton:
            return
    except Exception:
        pass
    now = time.monotonic()
    last = getattr(mw, "_hover_forward_last", None)
    interval_ms = float(_cfg(mw, "HOVER_FORWARD_INTERVAL_MS", 30))
    if last is not None and (now - last) < (interval_ms / 1000.0):
        return
    mw._hover_forward_last = now
    try:
        gp = event.globalPosition()
        pos = QtCore.QPoint(int(gp.x()), int(gp.y()))
    except Exception:
        try:
            pos = event.globalPos()
        except Exception:
            try:
                pos = QtGui.QCursor.pos()
            except Exception:
                return
    try:
        mw._hover_forwarding = True
        hit = hover_poke_at_global(mw, pos, reason="app_mouse_move")
        if hit:
            mark_hover_seen(mw, source="app_mouse_move")
    finally:
        mw._hover_forwarding = False


def rearm_hover_tracking(mw, reason: str | None = None, force: bool = False) -> None:
    """Re-enable hover tracking on wheel views without forcing focus."""
    if _background_services_paused(mw):
        return
    if getattr(mw, "_closing", False):
        return
    if mw._overlay_choice_active():
        return
    now = time.monotonic()
    last = getattr(mw, "_hover_rearm_last", None)
    if not force and last is not None and (now - last) < 0.12:
        return
    mw._hover_rearm_last = now
    views = iter_hover_views(mw)
    if reason:
        mw._trace_event("hover_rearm", reason=reason, count=len(views))
    for view in views:
        if hasattr(view, "isVisible") and not view.isVisible():
            continue
        if hasattr(view, "_rearm_hover_tracking"):
            try:
                view._rearm_hover_tracking()
                continue
            except Exception:
                pass
        try:
            view.setMouseTracking(True)
            view.setInteractive(True)
            vp = view.viewport()
            vp.setMouseTracking(True)
            vp.setAttribute(QtCore.Qt.WA_Hover, True)
        except Exception:
            pass
    # When tooltips are globally disabled, skip cache/poke/pump work completely.
    # This avoids unnecessary expensive hover cache rebuilds during map interactions.
    if _cfg(mw, "DISABLE_TOOLTIPS", False):
        return
    reset_hover_cache_under_cursor(mw)
    if not reason:
        return
    reason_text = str(reason).lower()
    suppress_poke = False
    # During/after map stack switches, immediate synthetic hover events can
    # block the UI thread on some systems. Let natural mouse movement recover.
    if "stack_switching" in reason_text and getattr(mw, "current_mode", "") == "maps":
        suppress_poke = True
    if not suppress_poke:
        hover_poke_under_cursor(mw, reason=reason)
        start_hover_pump(mw, reason=reason, duration_ms=1200)


def refresh_tooltip_caches_async(
    mw,
    delay_step_ms: int = 80,
    on_done: Callable[[], None] | None = None,
    reason: str | None = None,
    force: bool = False,
) -> None:
    """
    Baut die Tooltip-Caches in kleinen Scheiben (per Timer) neu auf,
    damit der UI-Thread beim Online/Offline-Klick nicht blockiert.
    Mehrfachaufrufe werden kurz gesammelt, um die Render-Last zu drosseln.
    """
    if _cfg(mw, "DISABLE_TOOLTIPS", False):
        return
    if hasattr(mw, "_tooltip_manager"):
        mw._tooltip_manager.refresh_caches_async(
            delay_step_ms=delay_step_ms,
            on_done=on_done,
            reason=reason,
            force=force,
        )


def reset_hover_cache_under_cursor(mw) -> None:
    """Stellt sicher, dass Tooltip-Caches vorhanden sind, ohne Voll-Rebuild zu erzwingen."""
    if hasattr(mw, "_tooltip_manager"):
        mw._tooltip_manager.reset_hover_cache_under_cursor()


def set_tooltips_ready(mw, ready: bool = True) -> None:
    """Setzt das Tooltip-Ready-Flag für alle Räder."""
    if hasattr(mw, "_tooltip_manager"):
        mw._tooltip_manager.set_tooltips_ready(bool(ready))
