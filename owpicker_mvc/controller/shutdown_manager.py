from __future__ import annotations

from typing import Callable
import time

from model.main_window_runtime_state import ShutdownPhase

from . import shutdown_snapshot

_SHUTDOWN_MANAGER_GUARD_ERRORS = (
    AttributeError,
    RuntimeError,
    TypeError,
    ValueError,
    LookupError,
    OSError,
    ImportError,
    ModuleNotFoundError,
)


def _cfg(mw, key: str, default=None):
    getter = getattr(mw, "_cfg", None)
    if callable(getter):
        try:
            return getter(key, default)
        except _SHUTDOWN_MANAGER_GUARD_ERRORS:
            pass
    return default


def merge_shutdown_snapshot(prefix: str, payload: dict | None, target: dict) -> None:
    shutdown_snapshot.merge_shutdown_snapshot(prefix, payload, target)


def _trace_shutdown_snapshot_error(mw, *, component: str, exc: Exception) -> None:
    shutdown_snapshot.trace_shutdown_snapshot_error(mw, component=component, exc=exc)


def _append_component_snapshot(
    mw,
    *,
    target: dict,
    component: str,
    prefix: str,
    source: object | None,
) -> None:
    shutdown_snapshot.append_component_snapshot(
        mw,
        target=target,
        component=component,
        prefix=prefix,
        source=source,
    )


def _resolve_qt_core():
    try:
        from PySide6 import QtCore  # type: ignore
    except _SHUTDOWN_MANAGER_GUARD_ERRORS:
        return None
    return QtCore


def _resolve_qt_widgets():
    try:
        from PySide6 import QtWidgets  # type: ignore
    except _SHUTDOWN_MANAGER_GUARD_ERRORS:
        return None
    return QtWidgets


def _safe_duration_ms(started_monotonic: float, elapsed_timer) -> int:
    if elapsed_timer is not None:
        try:
            return int(elapsed_timer.elapsed())
        except _SHUTDOWN_MANAGER_GUARD_ERRORS:
            pass
    return int((time.monotonic() - started_monotonic) * 1000.0)


def _event_is_accepted(event: object, default: bool = True) -> bool:
    is_accepted_fn = getattr(event, "isAccepted", None)
    if callable(is_accepted_fn):
        try:
            return bool(is_accepted_fn())
        except _SHUTDOWN_MANAGER_GUARD_ERRORS:
            pass
    return bool(default)


def shutdown_resource_snapshot(mw) -> dict:
    snap: dict[str, object] = shutdown_snapshot.build_component_snapshot(mw)
    QtCore = _resolve_qt_core()
    timer_cls = getattr(QtCore, "QTimer", object) if QtCore is not None else object
    timers: list[object] = []
    try:
        finder = getattr(mw, "findChildren", None)
        if callable(finder):
            timers = list(finder(timer_cls))
    except _SHUTDOWN_MANAGER_GUARD_ERRORS as exc:
        _trace_shutdown_snapshot_error(mw, component="qt_timers_total", exc=exc)
        timers = []
    active = 0
    for timer in timers:
        try:
            if bool(getattr(timer, "isActive")()):
                active += 1
        except _SHUTDOWN_MANAGER_GUARD_ERRORS as exc:
            _trace_shutdown_snapshot_error(mw, component="qt_timer", exc=exc)
    snap["qt_timers_total"] = len(timers)
    snap["qt_timers_active"] = active
    return snap


def run_shutdown_step(mw, step: str, callback: Callable[[], None]) -> None:
    mw._trace_event("shutdown_step:start", step=step)
    started_monotonic = time.monotonic()
    elapsed_timer = None
    QtCore = _resolve_qt_core()
    if QtCore is not None:
        try:
            elapsed_timer = QtCore.QElapsedTimer()
            elapsed_timer.start()
        except _SHUTDOWN_MANAGER_GUARD_ERRORS:
            elapsed_timer = None
    try:
        callback()
        mw._trace_event(
            "shutdown_step:ok",
            step=step,
            duration_ms=_safe_duration_ms(started_monotonic, elapsed_timer),
        )
    except _SHUTDOWN_MANAGER_GUARD_ERRORS as exc:
        mw._trace_event("shutdown_step:error", step=step, error=repr(exc))


def _schedule_app_quit_guard(mw) -> None:
    QtWidgets = _resolve_qt_widgets()
    if QtWidgets is None:
        return
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    try:
        app.setQuitOnLastWindowClosed(True)
    except _SHUTDOWN_MANAGER_GUARD_ERRORS:
        pass
    tracer = getattr(mw, "_trace_event", None)
    if callable(tracer):
        try:
            tracer("shutdown_quit_guard:scheduled")
        except _SHUTDOWN_MANAGER_GUARD_ERRORS:
            pass
    try:
        app.quit()
        if callable(tracer):
            tracer("shutdown_quit_guard:quit_now")
    except _SHUTDOWN_MANAGER_GUARD_ERRORS:
        pass
    QtCore = _resolve_qt_core()
    if QtCore is None:
        return
    try:
        QtCore.QTimer.singleShot(0, app.quit)
    except _SHUTDOWN_MANAGER_GUARD_ERRORS:
        try:
            app.quit()
        except _SHUTDOWN_MANAGER_GUARD_ERRORS:
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
                        except _SHUTDOWN_MANAGER_GUARD_ERRORS:
                            pass
                    return
        except _SHUTDOWN_MANAGER_GUARD_ERRORS:
            pass
        try:
            app.quit()
            if callable(tracer):
                try:
                    tracer("shutdown_quit_guard:guard_quit")
                except _SHUTDOWN_MANAGER_GUARD_ERRORS:
                    pass
        except _SHUTDOWN_MANAGER_GUARD_ERRORS:
            pass

    try:
        QtCore.QTimer.singleShot(int(guard_ms), _guard)
    except _SHUTDOWN_MANAGER_GUARD_ERRORS:
        pass

    force_exit_ms = max(0, int(_cfg(mw, "SHUTDOWN_APP_FORCE_EXIT_LOOP_MS", guard_ms + 900)))
    if force_exit_ms <= 0:
        return

    def _force_exit_loop() -> None:
        try:
            app.quit()
            if callable(tracer):
                try:
                    tracer("shutdown_quit_guard:force_quit")
                except _SHUTDOWN_MANAGER_GUARD_ERRORS:
                    pass
        except _SHUTDOWN_MANAGER_GUARD_ERRORS:
            pass
        try:
            app.exit(0)
            if callable(tracer):
                try:
                    tracer("shutdown_quit_guard:force_exit_loop")
                except _SHUTDOWN_MANAGER_GUARD_ERRORS:
                    pass
        except _SHUTDOWN_MANAGER_GUARD_ERRORS:
            pass

    try:
        QtCore.QTimer.singleShot(int(force_exit_ms), _force_exit_loop)
    except _SHUTDOWN_MANAGER_GUARD_ERRORS:
        pass


def handle_close_event(mw, event: object) -> None:
    set_state = getattr(mw, "_set_shutdown_runtime_state", None)
    if callable(set_state):
        set_state(
            closing=True,
            shutdown_phase=ShutdownPhase.FINALIZING_CLOSE.value,
        )
    else:
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
        QtWidgets = _resolve_qt_widgets()
        if QtWidgets is None:
            return
        app = QtWidgets.QApplication.instance()
        if app:
            app.removeEventFilter(mw)

    def _close_aux_windows() -> None:
        QtWidgets = _resolve_qt_widgets()
        if QtWidgets is None:
            return
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
            except _SHUTDOWN_MANAGER_GUARD_ERRORS:
                continue
            try:
                widget.close()
                closed += 1
            except _SHUTDOWN_MANAGER_GUARD_ERRORS:
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

    keep_window_visible = bool(_cfg(mw, "SHUTDOWN_KEEP_WINDOW_VISIBLE_UNTIL_EXIT", False))
    if keep_window_visible:
        mw._trace_event("shutdown_qt_closeevent:keep_visible_mode", active=True)

    QtWidgets = _resolve_qt_widgets()
    mw._trace_event("shutdown_qt_closeevent:before")
    if QtWidgets is not None:
        try:
            QtWidgets.QMainWindow.closeEvent(mw, event)
        except _SHUTDOWN_MANAGER_GUARD_ERRORS as exc:
            mw._trace_event("shutdown_qt_closeevent:error", error=repr(exc))
    else:
        mw._trace_event("shutdown_qt_closeevent:qt_unavailable")
        accept_fn = getattr(event, "accept", None)
        if callable(accept_fn):
            try:
                accept_fn()
            except _SHUTDOWN_MANAGER_GUARD_ERRORS:
                pass

    accepted = _event_is_accepted(event, default=True)
    mw._trace_event("shutdown_qt_closeevent:after", accepted=bool(accepted))
    if not accepted:
        try:
            accept_fn = getattr(event, "accept", None)
            if callable(accept_fn):
                accept_fn()
            accepted = _event_is_accepted(event, default=False)
        except _SHUTDOWN_MANAGER_GUARD_ERRORS:
            accepted = False
        mw._trace_event("shutdown_qt_closeevent:forced_accept", accepted=bool(accepted))
    if accepted:
        if callable(set_state):
            set_state(shutdown_phase=ShutdownPhase.CLOSED.value)
        _schedule_app_quit_guard(mw)

