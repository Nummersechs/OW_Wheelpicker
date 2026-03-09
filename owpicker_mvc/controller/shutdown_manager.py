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
    started = QtCore.QElapsedTimer()
    started.start()
    try:
        callback()
        mw._trace_event("shutdown_step:ok", step=step, duration_ms=int(started.elapsed()))
    except Exception as exc:
        mw._trace_event("shutdown_step:error", step=step, error=repr(exc))


def _schedule_app_quit_guard(mw) -> None:
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    try:
        app.setQuitOnLastWindowClosed(True)
    except Exception:
        pass
    tracer = getattr(mw, "_trace_event", None)
    if callable(tracer):
        try:
            tracer("shutdown_quit_guard:scheduled")
        except Exception:
            pass
    try:
        app.quit()
        if callable(tracer):
            tracer("shutdown_quit_guard:quit_now")
    except Exception:
        pass
    try:
        QtCore.QTimer.singleShot(0, app.quit)
    except Exception:
        try:
            app.quit()
        except Exception:
            return
    guard_ms = max(0, int(_cfg(mw, "SHUTDOWN_APP_QUIT_GUARD_MS", 1500)))
    if guard_ms <= 0:
        return

    def _guard() -> None:
        try:
            for widget in app.topLevelWidgets():
                if widget is None:
                    continue
                if widget.isVisible():
                    if callable(tracer):
                        try:
                            tracer("shutdown_quit_guard:still_visible")
                        except Exception:
                            pass
                    return
        except Exception:
            pass
        try:
            app.quit()
            if callable(tracer):
                try:
                    tracer("shutdown_quit_guard:guard_quit")
                except Exception:
                    pass
        except Exception:
            pass

    try:
        QtCore.QTimer.singleShot(int(guard_ms), _guard)
    except Exception:
        pass
    # Additional guard: force event-loop exit shortly after quit guard.
    # This helps when all windows are gone but queued callbacks still keep
    # the loop alive.
    force_exit_ms = max(0, int(_cfg(mw, "SHUTDOWN_APP_FORCE_EXIT_LOOP_MS", guard_ms + 900)))
    if force_exit_ms <= 0:
        return

    def _force_exit_loop() -> None:
        try:
            app.quit()
            if callable(tracer):
                try:
                    tracer("shutdown_quit_guard:force_quit")
                except Exception:
                    pass
        except Exception:
            pass
        try:
            app.exit(0)
            if callable(tracer):
                try:
                    tracer("shutdown_quit_guard:force_exit_loop")
                except Exception:
                    pass
        except Exception:
            pass

    try:
        QtCore.QTimer.singleShot(int(force_exit_ms), _force_exit_loop)
    except Exception:
        pass


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

    def _close_aux_windows() -> None:
        app = QtWidgets.QApplication.instance()
        if app is None:
            return
        closed = 0
        for widget in list(app.topLevelWidgets()):
            if widget is None or widget is mw:
                continue
            try:
                if not bool(widget.isVisible()):
                    continue
            except Exception:
                continue
            try:
                widget.close()
                closed += 1
            except Exception:
                continue
        mw._trace_event("shutdown_aux_windows_close", closed=int(closed))

    run_shutdown_step(mw, "stop_wheels", _stop_wheels)
    run_shutdown_step(mw, "map_ui", _shutdown_map_ui)
    run_shutdown_step(mw, "player_list_panel", _shutdown_player_panel)
    run_shutdown_step(mw, "tooltip_manager", _shutdown_tooltips)
    run_shutdown_step(mw, "timer_registry", _stop_registered_timers)
    run_shutdown_step(mw, "state_sync", _shutdown_state_sync)
    run_shutdown_step(mw, "sound", _shutdown_sound)
    run_shutdown_step(mw, "remove_event_filter", _remove_app_filter)
    run_shutdown_step(mw, "close_aux_windows", _close_aux_windows)

    if bool(_cfg(mw, "TRACE_SHUTDOWN", False)):
        mw._trace_event("shutdown_snapshot", stage="pre_super", **shutdown_resource_snapshot(mw))

    # Keep-visible behavior is handled in MainWindowShutdownMixin by deferring
    # close while background work is still running. At this point shutdown work
    # is done and we finish close by accepting the Qt close event.
    keep_window_visible = bool(_cfg(mw, "SHUTDOWN_KEEP_WINDOW_VISIBLE_UNTIL_EXIT", False))
    if keep_window_visible:
        mw._trace_event("shutdown_qt_closeevent:keep_visible_mode", active=True)

    # After MainWindow was split into mixins, `super(type(mw), mw)` resolves
    # back to MainWindowShutdownMixin.closeEvent and recurses.
    # Call the Qt base implementation directly to finish close safely.
    mw._trace_event("shutdown_qt_closeevent:before")
    QtWidgets.QMainWindow.closeEvent(mw, event)
    accepted = True
    try:
        accepted = bool(event.isAccepted())
    except Exception:
        accepted = True
    mw._trace_event("shutdown_qt_closeevent:after", accepted=bool(accepted))
    if not accepted:
        # Some Qt plugin paths can ignore close while auxiliary popups/tool windows
        # are still around. During explicit app shutdown we force acceptance.
        try:
            event.accept()
            accepted = bool(event.isAccepted())
        except Exception:
            accepted = False
        mw._trace_event("shutdown_qt_closeevent:forced_accept", accepted=bool(accepted))
    if accepted:
        _schedule_app_quit_guard(mw)
