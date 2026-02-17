from __future__ import annotations

import time

from PySide6 import QtCore, QtGui, QtWidgets

import i18n
from . import hover_tooltip_ops, runtime_tracing

_MOUSE_CLICK_EVENT_TYPES = (
    int(QtCore.QEvent.MouseButtonPress),
    int(QtCore.QEvent.MouseButtonRelease),
    int(QtCore.QEvent.MouseButtonDblClick),
)
_POST_CHOICE_GUARD_EVENT_TYPES = _MOUSE_CLICK_EVENT_TYPES + (int(QtCore.QEvent.Wheel),)
_CHOICE_POINTER_DROP_EVENT_TYPES = (
    int(QtCore.QEvent.MouseMove),
    int(QtCore.QEvent.HoverMove),
    int(QtCore.QEvent.Wheel),
)
_STARTUP_BLOCKED_INPUT_EVENT_TYPES = _POST_CHOICE_GUARD_EVENT_TYPES + (
    int(QtCore.QEvent.KeyPress),
    int(QtCore.QEvent.KeyRelease),
    int(QtCore.QEvent.HoverEnter),
    int(QtCore.QEvent.HoverLeave),
    int(QtCore.QEvent.TouchBegin),
    int(QtCore.QEvent.TouchUpdate),
    int(QtCore.QEvent.TouchEnd),
    int(QtCore.QEvent.ToolTip),
    int(QtCore.QEvent.HelpRequest),
)
_FOCUS_ACTIVATION_EVENT_TYPES = (
    int(QtCore.QEvent.WindowActivate),
    int(QtCore.QEvent.ApplicationActivate),
    int(QtCore.QEvent.ActivationChange),
)
_FOCUS_BLOCK_EVENT_TYPES = _FOCUS_ACTIVATION_EVENT_TYPES + (int(QtCore.QEvent.FocusIn),)
_MOUSE_MOVE_EVENT_TYPE = int(QtCore.QEvent.MouseMove)
_MOUSE_BUTTON_PRESS_EVENT_TYPE = int(QtCore.QEvent.MouseButtonPress)
_FAST_FILTER_EVENT_TYPES = (
    set(_STARTUP_BLOCKED_INPUT_EVENT_TYPES)
    | set(_CHOICE_POINTER_DROP_EVENT_TYPES)
    | set(_FOCUS_ACTIVATION_EVENT_TYPES)
    | {_MOUSE_BUTTON_PRESS_EVENT_TYPE}
)


class MainWindowInputMixin:
    def eventFilter(self, obj, event):
        etype_int = int(event.type())
        hover_forward_enabled = getattr(self, "_hover_forward_mousemove_enabled", None)
        if hover_forward_enabled is None:
            hover_forward_enabled = bool(self._cfg("HOVER_FORWARD_MOUSEMOVE", False))
            self._hover_forward_mousemove_enabled = hover_forward_enabled
        # Fast-path: ignore the vast majority of unrelated app-level events.
        if (
            not getattr(self, "_focus_trace_enabled", False)
            and etype_int not in _FAST_FILTER_EVENT_TYPES
            and not (hover_forward_enabled and etype_int == _MOUSE_MOVE_EVENT_TYPE)
            and etype_int not in _MOUSE_CLICK_EVENT_TYPES
        ):
            return super().eventFilter(obj, event)

        if self._should_block_startup_focus_event(etype_int):
            return True
        if self._should_drop_post_choice_clickthrough_event(etype_int, obj):
            return True
        if self._should_drop_disabled_choice_pointer_event(etype_int):
            return True
        if self._should_drop_disabled_choice_mouse_event(etype_int):
            return True
        if getattr(self, "_startup_block_input", False):
            if etype_int in _STARTUP_BLOCKED_INPUT_EVENT_TYPES:
                self._record_blocked_input_event(etype_int)
                return True
        if getattr(self, "_startup_drain_active", False):
            if etype_int in _STARTUP_BLOCKED_INPUT_EVENT_TYPES:
                self._record_drained_input_event(etype_int)
                self._restart_startup_drain_timer()
                return True
        if getattr(self, "_focus_trace_enabled", False):
            self._trace_focus_event(obj, event)
        if etype_int in _FOCUS_ACTIVATION_EVENT_TYPES:
            if self.isActiveWindow():
                reason = self._event_type_name(etype_int)
                if getattr(self, "_startup_block_input", False) or getattr(self, "_startup_drain_active", False):
                    self._record_hover_prime_deferred(reason=reason)
                else:
                    self._rearm_hover_tracking(reason=reason)
                    # After focus/activation changes, re-prime hover even if a prior pump marked "seen".
                    self._hover_seen = False
                    self._hover_forward_last = None
                    self._start_hover_pump(reason=reason, duration_ms=900, force=True)
        if hover_forward_enabled and etype_int == _MOUSE_MOVE_EVENT_TYPE:
            try:
                if isinstance(event, QtGui.QMouseEvent):
                    self._forward_hover_from_app_mousemove(event)
            except Exception:
                pass
        if etype_int in _MOUSE_CLICK_EVENT_TYPES:
            if not getattr(self, "_closing", False) and not self._overlay_choice_active():
                try:
                    if isinstance(event, QtGui.QMouseEvent):
                        if not hasattr(event, "spontaneous") or event.spontaneous():
                            # Click spam should not trigger expensive hover rearm/pump cycles.
                            # We only mark activity; watchdog/activation paths recover hover.
                            self._mark_hover_activity()
                except Exception:
                    pass
        if getattr(self, "_closing", False):
            return super().eventFilter(obj, event)
        if self._overlay_choice_active():
            return super().eventFilter(obj, event)
        if etype_int == _MOUSE_BUTTON_PRESS_EVENT_TYPE:
            if hasattr(self, "player_list_panel"):
                self.player_list_panel.maybe_close_on_click(obj, event)
        return super().eventFilter(obj, event)

    def _should_drop_disabled_choice_mouse_event(self, etype: int) -> bool:
        if etype not in _MOUSE_CLICK_EVENT_TYPES:
            return False
        return self._choice_overlay_buttons_locked()

    def _should_block_startup_focus_event(self, etype: int) -> bool:
        if etype not in _FOCUS_BLOCK_EVENT_TYPES:
            return False
        if not getattr(self, "_startup_block_input", False):
            return False
        if not bool(self._cfg("STARTUP_CLEAR_FOCUS_WHILE_BLOCKED", True)):
            return False
        try:
            self._clear_focus_now()
        except Exception:
            pass
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event("startup_focus_blocked", event=self._event_type_name(etype))
            except Exception:
                pass
        return True

    def _post_choice_input_guard_active(self) -> bool:
        until = getattr(self, "_post_choice_input_guard_until", None)
        if until is None:
            return False
        if time.monotonic() >= until:
            self._post_choice_input_guard_until = None
            if hasattr(self, "_refresh_app_event_filter_state"):
                self._refresh_app_event_filter_state()
            return False
        return True

    def _arm_post_choice_input_guard(self, reason: str | None = None, duration_ms: int | None = None) -> None:
        ms = int(
            duration_ms
            if duration_ms is not None
            else self._cfg("MODE_CHOICE_INPUT_GUARD_MS", 220)
        )
        if ms <= 0:
            self._post_choice_input_guard_until = None
            if hasattr(self, "_refresh_app_event_filter_state"):
                self._refresh_app_event_filter_state()
            return
        self._post_choice_input_guard_until = time.monotonic() + (ms / 1000.0)
        self._trace_event("mode_choice_input_guard", active=True, duration_ms=ms, reason=reason)
        if hasattr(self, "_refresh_app_event_filter_state"):
            self._refresh_app_event_filter_state()

    def _is_wheel_view_event_target(self, obj) -> bool:
        if obj is None:
            return False
        try:
            views = self._iter_hover_views(include_maps=True)
        except Exception:
            views = []
        for view in views:
            if view is None:
                continue
            if obj is view:
                return True
            try:
                vp = view.viewport()
            except Exception:
                continue
            if obj is vp:
                return True
            if isinstance(obj, QtWidgets.QWidget):
                try:
                    if vp.isAncestorOf(obj):
                        return True
                except Exception:
                    pass
        return False

    def _should_drop_post_choice_clickthrough_event(self, etype: int, obj=None) -> bool:
        if etype not in _POST_CHOICE_GUARD_EVENT_TYPES:
            return False
        if self._overlay_choice_active():
            return False
        # Segment toggles on wheel views should remain responsive even directly
        # after mode choice; spin/mode actions are guarded separately.
        if self._is_wheel_view_event_target(obj):
            return False
        return self._post_choice_input_guard_active()

    def _should_drop_disabled_choice_pointer_event(self, etype: int) -> bool:
        drop_pointer_events = getattr(self, "_startup_drop_choice_pointer_events", None)
        if drop_pointer_events is None:
            drop_pointer_events = bool(self._cfg("STARTUP_DROP_CHOICE_POINTER_EVENTS", True))
            self._startup_drop_choice_pointer_events = drop_pointer_events
        if not drop_pointer_events:
            return False
        if etype not in _CHOICE_POINTER_DROP_EVENT_TYPES:
            return False
        return self._choice_overlay_buttons_locked()

    def _choice_overlay_buttons_locked(self) -> bool:
        if not (getattr(self, "_startup_block_input", False) or getattr(self, "_startup_drain_active", False)):
            return False
        if not self._overlay_choice_active():
            return False
        overlay = getattr(self, "overlay", None)
        if overlay is None:
            return False
        btn_offline = getattr(overlay, "btn_offline", None)
        btn_online = getattr(overlay, "btn_online", None)
        if btn_offline is None or btn_online is None:
            return False
        try:
            locked = (not btn_offline.isEnabled()) and (not btn_online.isEnabled())
        except Exception:
            return False
        # During startup warmup/drain the mode-choice buttons are intentionally locked.
        # Drop click and pointer move events globally so spam doesn't keep re-queueing input.
        return bool(locked)

    def _event_type_name(self, etype: int) -> str:
        try:
            return QtCore.QEvent.Type(etype).name  # type: ignore[attr-defined]
        except Exception:
            return str(etype)

    def _set_map_button_loading(self, loading: bool, reason: str | None = None) -> None:
        if getattr(self, "_map_button_loading", False) == bool(loading):
            return
        self._map_button_loading = bool(loading)
        if hasattr(self, "btn_mode_maps"):
            label_key = "mode.maps_loading" if self._map_button_loading else "mode.maps"
            try:
                self.btn_mode_maps.setText(i18n.t(label_key))
            except Exception:
                pass
        self._trace_event("map_button_loading", active=self._map_button_loading, reason=reason)

    def _trace_focus_signal(self, old, new) -> None:
        runtime_tracing.trace_focus_signal(self, old, new)

    def _trace_focus_window_signal(self, win) -> None:
        runtime_tracing.trace_focus_window_signal(self, win)

    def _trace_app_state(self, state) -> None:
        runtime_tracing.trace_app_state(self, state)

    def _trace_window_snapshot(self) -> None:
        runtime_tracing.trace_window_snapshot(self)

    def _trace_focus_event(self, obj, event) -> None:
        runtime_tracing.trace_focus_event(self, obj, event)

    def _apply_focus_policy_defaults(self) -> None:
        """Avoid automatic focus on startup by forcing ClickFocus for focusable widgets."""
        if hasattr(self, "_focus_policy"):
            self._focus_policy.apply_defaults()

    def _schedule_clear_focus(self) -> None:
        """Clear any automatic focus after startup to avoid refocus flicker."""
        if hasattr(self, "_focus_policy"):
            self._focus_policy.schedule_clear_focus()

    def _clear_focus_now(self) -> None:
        if hasattr(self, "_focus_policy"):
            self._focus_policy.clear_focus_now()

    def _refresh_hover_under_cursor(self):
        """Trigger a hover refresh for widgets that just became enabled."""
        if getattr(self, "_closing", False):
            return
        if self._overlay_choice_active():
            return
        # Hover-Refocus deaktiviert
        return

    def _refresh_hover_state(self):
        """Normalize hover/tooltips after enable/disable transitions."""
        return

    def _trace_hover_event(self, name: str, **extra) -> None:
        runtime_tracing.trace_hover_event(self, name, **extra)

    def _mark_hover_activity(self) -> None:
        hover_tooltip_ops.mark_hover_activity(self)

    def _mark_hover_user_move(self) -> None:
        hover_tooltip_ops.mark_hover_user_move(self)

    def _ensure_hover_watchdog_started(self) -> None:
        hover_tooltip_ops.ensure_hover_watchdog_started(self)

    def _mark_hover_seen(self, source: str | None = None) -> None:
        hover_tooltip_ops.mark_hover_seen(self, source=source)

    def _record_hover_prime_deferred(self, reason: str | None = None) -> None:
        hover_tooltip_ops.record_hover_prime_deferred(self, reason=reason)

    def _flush_hover_prime_deferred_trace(self) -> None:
        hover_tooltip_ops.flush_hover_prime_deferred_trace(self)

    def _start_hover_pump(
        self,
        reason: str | None = None,
        duration_ms: int | None = None,
        force: bool = False,
    ) -> None:
        hover_tooltip_ops.start_hover_pump(
            self,
            reason=reason,
            duration_ms=duration_ms,
            force=force,
        )

    def _hover_pump_tick(self) -> None:
        hover_tooltip_ops.hover_pump_tick(self)

    def _hover_poke_under_cursor(self, reason: str | None = None) -> None:
        hover_tooltip_ops.hover_poke_under_cursor(self, reason=reason)

    def _hover_cursor_hits_view(self, pos: QtCore.QPoint) -> bool:
        return hover_tooltip_ops.hover_cursor_hits_view(self, pos)

    def _iter_hover_views(self, include_maps: bool | None = None) -> list:
        return hover_tooltip_ops.iter_hover_views(self, include_maps=include_maps)

    def _hover_watchdog_tick(self) -> None:
        hover_tooltip_ops.hover_watchdog_tick(self)

    def _hover_poke_at_global(self, pos: QtCore.QPoint, reason: str | None = None) -> bool:
        return hover_tooltip_ops.hover_poke_at_global(self, pos, reason=reason)

    def _forward_hover_from_app_mousemove(self, event: QtGui.QMouseEvent) -> None:
        hover_tooltip_ops.forward_hover_from_app_mousemove(self, event)

    def _rearm_hover_tracking(self, reason: str | None = None, force: bool = False) -> None:
        hover_tooltip_ops.rearm_hover_tracking(self, reason=reason, force=force)
