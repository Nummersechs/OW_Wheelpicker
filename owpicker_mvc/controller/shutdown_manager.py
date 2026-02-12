from __future__ import annotations

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


def merge_shutdown_snapshot(prefix: str, payload: dict | None, target: dict) -> None:
    if not isinstance(payload, dict):
        return
    for key, value in payload.items():
        target[f"{prefix}_{key}"] = value


def shutdown_resource_snapshot(mw) -> dict:
    snap: dict[str, object] = {}
    try:
        timers = mw.findChildren(QtCore.QTimer)
        active = 0
        for timer in timers:
            try:
                if timer.isActive():
                    active += 1
            except Exception:
                pass
        snap["qt_timers_total"] = len(timers)
        snap["qt_timers_active"] = active
    except Exception:
        snap["qt_timers_total"] = None
        snap["qt_timers_active"] = None

    registry = getattr(mw, "_timers", None)
    if registry is not None and hasattr(registry, "snapshot"):
        try:
            merge_shutdown_snapshot("registry", registry.snapshot(), snap)
        except Exception:
            pass

    state_sync = getattr(mw, "state_sync", None)
    if state_sync is not None and hasattr(state_sync, "resource_snapshot"):
        try:
            merge_shutdown_snapshot("state_sync", state_sync.resource_snapshot(), snap)
        except Exception:
            pass

    tooltip = getattr(mw, "_tooltip_manager", None)
    if tooltip is not None and hasattr(tooltip, "resource_snapshot"):
        try:
            merge_shutdown_snapshot("tooltip", tooltip.resource_snapshot(), snap)
        except Exception:
            pass

    sound = getattr(mw, "sound", None)
    if sound is not None and hasattr(sound, "resource_snapshot"):
        try:
            merge_shutdown_snapshot("sound", sound.resource_snapshot(), snap)
        except Exception:
            pass

    panel = getattr(mw, "player_list_panel", None)
    if panel is not None and hasattr(panel, "resource_snapshot"):
        try:
            merge_shutdown_snapshot("player_panel", panel.resource_snapshot(), snap)
        except Exception:
            pass

    map_ui = getattr(mw, "map_ui", None)
    if map_ui is not None and hasattr(map_ui, "resource_snapshot"):
        try:
            merge_shutdown_snapshot("map_ui", map_ui.resource_snapshot(), snap)
        except Exception:
            pass

    return snap


def run_shutdown_step(mw, step: str, callback: Callable[[], None]) -> None:
    mw._trace_event("shutdown_step:start", step=step)
    try:
        callback()
        mw._trace_event("shutdown_step:ok", step=step)
    except Exception as exc:
        mw._trace_event("shutdown_step:error", step=step, error=repr(exc))


def handle_close_event(mw, event: QtGui.QCloseEvent) -> None:
    mw._closing = True
    mw._trace_event("close_event")

    if bool(_cfg(mw, "TRACE_SHUTDOWN", False)):
        mw._trace_event("shutdown_snapshot", stage="begin", **shutdown_resource_snapshot(mw))

    def _stop_wheels() -> None:
        mw._stop_all_wheels()
        if getattr(mw, "map_main", None):
            mw.map_main.hard_stop()

    def _shutdown_map_ui() -> None:
        if hasattr(mw, "map_ui"):
            mw.map_ui.shutdown()

    def _shutdown_player_panel() -> None:
        if hasattr(mw, "player_list_panel"):
            mw.player_list_panel.shutdown()

    def _shutdown_tooltips() -> None:
        if hasattr(mw, "_tooltip_manager"):
            mw._tooltip_manager.shutdown()

    def _stop_registered_timers() -> None:
        if hasattr(mw, "_timers"):
            mw._timers.stop_all()

    def _shutdown_state_sync() -> None:
        mw.state_sync.save_state(sync=False, immediate=True)
        mw.state_sync.shutdown(flush=False)

    def _shutdown_sound() -> None:
        mw.sound.shutdown()

    def _remove_app_filter() -> None:
        app = QtWidgets.QApplication.instance()
        if app:
            app.removeEventFilter(mw)

    run_shutdown_step(mw, "stop_wheels", _stop_wheels)
    run_shutdown_step(mw, "map_ui", _shutdown_map_ui)
    run_shutdown_step(mw, "player_list_panel", _shutdown_player_panel)
    run_shutdown_step(mw, "tooltip_manager", _shutdown_tooltips)
    run_shutdown_step(mw, "timer_registry", _stop_registered_timers)
    run_shutdown_step(mw, "state_sync", _shutdown_state_sync)
    run_shutdown_step(mw, "sound", _shutdown_sound)
    run_shutdown_step(mw, "remove_event_filter", _remove_app_filter)

    if bool(_cfg(mw, "TRACE_SHUTDOWN", False)):
        mw._trace_event("shutdown_snapshot", stage="pre_super", **shutdown_resource_snapshot(mw))

    super(type(mw), mw).closeEvent(event)
