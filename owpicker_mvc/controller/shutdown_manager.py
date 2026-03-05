from __future__ import annotations

from typing import Callable

from PySide6 import QtCore, QtGui, QtWidgets

import config


def _cfg(mw, key: str, default=None):
    getter = getattr(mw, "_cfg", None)
    if callable(getter):
        try:
            return getter(key, default)
        except Exception as exc:
            try:
                config.debug_print(f"shutdown _cfg fallback for {key}: {exc}")
            except Exception:
                pass
    return getattr(config, key, default)


def merge_shutdown_snapshot(prefix: str, payload: dict | None, target: dict) -> None:
    if not isinstance(payload, dict):
        return
    for key, value in payload.items():
        target[f"{prefix}_{key}"] = value


def _trace_shutdown_snapshot_error(mw, *, component: str, exc: Exception) -> None:
    if not bool(_cfg(mw, "TRACE_SHUTDOWN", False)):
        return
    tracer = getattr(mw, "_trace_event", None)
    if not callable(tracer):
        return
    tracer("shutdown_snapshot:error", component=component, error=repr(exc))


def _append_component_snapshot(
    mw,
    *,
    target: dict,
    component: str,
    prefix: str,
    source: object | None,
) -> None:
    if source is None:
        return
    snapshot_fn = getattr(source, "resource_snapshot", None)
    if not callable(snapshot_fn):
        return
    try:
        payload = snapshot_fn()
    except Exception as exc:
        _trace_shutdown_snapshot_error(mw, component=component, exc=exc)
        return
    merge_shutdown_snapshot(prefix, payload, target)


def shutdown_resource_snapshot(mw) -> dict:
    snap: dict[str, object] = {}
    try:
        timers = mw.findChildren(QtCore.QTimer)
        active = 0
        for timer in timers:
            try:
                if timer.isActive():
                    active += 1
            except RuntimeError as exc:
                _trace_shutdown_snapshot_error(mw, component="qt_timer", exc=exc)
        snap["qt_timers_total"] = len(timers)
        snap["qt_timers_active"] = active
    except Exception as exc:
        _trace_shutdown_snapshot_error(mw, component="qt_timers_total", exc=exc)
        snap["qt_timers_total"] = None
        snap["qt_timers_active"] = None

    _append_component_snapshot(
        mw,
        target=snap,
        component="timer_registry",
        prefix="registry",
        source=getattr(mw, "_timers", None),
    )
    _append_component_snapshot(
        mw,
        target=snap,
        component="state_sync",
        prefix="state_sync",
        source=getattr(mw, "state_sync", None),
    )
    _append_component_snapshot(
        mw,
        target=snap,
        component="tooltip_manager",
        prefix="tooltip",
        source=getattr(mw, "_tooltip_manager", None),
    )
    _append_component_snapshot(
        mw,
        target=snap,
        component="sound",
        prefix="sound",
        source=getattr(mw, "sound", None),
    )
    _append_component_snapshot(
        mw,
        target=snap,
        component="player_list_panel",
        prefix="player_panel",
        source=getattr(mw, "player_list_panel", None),
    )
    _append_component_snapshot(
        mw,
        target=snap,
        component="map_ui",
        prefix="map_ui",
        source=getattr(mw, "map_ui", None),
    )

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

    # After MainWindow was split into mixins, `super(type(mw), mw)` resolves
    # back to MainWindowShutdownMixin.closeEvent and recurses.
    # Call the Qt base implementation directly to finish close safely.
    QtWidgets.QMainWindow.closeEvent(mw, event)
