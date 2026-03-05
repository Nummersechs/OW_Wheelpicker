from __future__ import annotations

import time

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


def _event_type_name(etype: int) -> str:
    try:
        return QtCore.QEvent.Type(etype).name  # type: ignore[attr-defined]
    except Exception:
        return str(etype)


def _focus_trace_delta(mw, now: float) -> float | None:
    last = getattr(mw, "_focus_trace_last_t", None)
    mw._focus_trace_last_t = now
    if last is None:
        return None
    return round(now - last, 4)


def trace_focus_signal(mw, old, new) -> None:
    if not getattr(mw, "_focus_trace_enabled", False):
        return
    try:
        now = time.monotonic()
        dt = _focus_trace_delta(mw, now)
        if now > getattr(mw, "_focus_trace_until", 0):
            mw._focus_trace_enabled = False
            return
        if mw._focus_trace_count >= getattr(mw, "_focus_trace_max_events", 0):
            mw._focus_trace_enabled = False
            return
        old_name = type(old).__name__ if old is not None else None
        new_name = type(new).__name__ if new is not None else None
        old_obj = old.objectName() if old is not None else None
        new_obj = new.objectName() if new is not None else None
        old_win = None
        old_win_title = None
        new_win = None
        new_win_title = None
        if isinstance(old, QtWidgets.QWidget):
            try:
                win = old.window()
                old_win = type(win).__name__ if win is not None else None
                old_win_title = win.windowTitle() if win is not None else None
            except Exception:
                pass
        if isinstance(new, QtWidgets.QWidget):
            try:
                win = new.window()
                new_win = type(win).__name__ if win is not None else None
                new_win_title = win.windowTitle() if win is not None else None
            except Exception:
                pass
        app_state = None
        try:
            app_state = int(QtGui.QGuiApplication.applicationState())
        except Exception:
            pass
        line = (
            f"t={round(now, 3)} | dt={dt} | signal=focusChanged | old={old_name} | old_name={old_obj} | "
            f"old_win={old_win} | old_win_title={old_win_title} | new={new_name} | new_name={new_obj} | "
            f"new_win={new_win} | new_win_title={new_win_title} | app_state={app_state}"
        )
        with mw._focus_trace_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        mw._focus_trace_count += 1
    except Exception:
        pass


def trace_focus_window_signal(mw, win) -> None:
    if not getattr(mw, "_focus_trace_enabled", False):
        return
    try:
        now = time.monotonic()
        dt = _focus_trace_delta(mw, now)
        if now > getattr(mw, "_focus_trace_until", 0):
            mw._focus_trace_enabled = False
            return
        if mw._focus_trace_count >= getattr(mw, "_focus_trace_max_events", 0):
            mw._focus_trace_enabled = False
            return
        win_name = type(win).__name__ if win is not None else None
        win_obj = win.objectName() if win is not None else None
        try:
            win_title = win.title() if win is not None else None
        except Exception:
            win_title = None
        is_active = None
        is_visible = None
        window_state = None
        flags = None
        screen_name = None
        if isinstance(win, QtGui.QWindow):
            try:
                is_active = win.isActive()
                is_visible = win.isVisible()
                window_state = int(win.windowState())
                flags = int(win.flags())
                screen = win.screen()
                screen_name = screen.name() if screen is not None else None
            except Exception:
                pass
        app_state = None
        try:
            app_state = int(QtGui.QGuiApplication.applicationState())
        except Exception:
            pass
        line = (
            f"t={round(now, 3)} | dt={dt} | signal=focusWindowChanged | win={win_name} | win_name={win_obj} | "
            f"title={win_title} | active={is_active} | visible={is_visible} | "
            f"window_state={window_state} | flags={flags} | screen={screen_name} | app_state={app_state}"
        )
        with mw._focus_trace_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        mw._focus_trace_count += 1
    except Exception:
        pass


def trace_app_state(mw, state) -> None:
    if not getattr(mw, "_focus_trace_enabled", False):
        return
    try:
        now = time.monotonic()
        dt = _focus_trace_delta(mw, now)
        if now > getattr(mw, "_focus_trace_until", 0):
            mw._focus_trace_enabled = False
            return
        if mw._focus_trace_count >= getattr(mw, "_focus_trace_max_events", 0):
            mw._focus_trace_enabled = False
            return
        focus_name = None
        focus_obj = None
        focus_win = None
        focus_win_title = None
        app = QtWidgets.QApplication.instance()
        if app:
            focus_widget = app.focusWidget()
            if focus_widget is not None:
                focus_name = type(focus_widget).__name__
                focus_obj = focus_widget.objectName()
                try:
                    win = focus_widget.window()
                    focus_win = type(win).__name__ if win is not None else None
                    focus_win_title = win.windowTitle() if win is not None else None
                except Exception:
                    pass
        line = (
            f"t={round(now, 3)} | dt={dt} | signal=appState | state={state} | "
            f"focus={focus_name} | focus_name={focus_obj} | focus_win={focus_win} | "
            f"focus_win_title={focus_win_title}"
        )
        with mw._focus_trace_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        mw._focus_trace_count += 1
    except Exception:
        pass


def trace_window_snapshot(mw) -> None:
    if not getattr(mw, "_focus_trace_enabled", False):
        return
    try:
        now = time.monotonic()
        dt = _focus_trace_delta(mw, now)
        if now > getattr(mw, "_focus_trace_until", 0):
            mw._focus_trace_enabled = False
            return
        if mw._focus_trace_count >= getattr(mw, "_focus_trace_max_events", 0):
            mw._focus_trace_enabled = False
            return
        app = QtGui.QGuiApplication.instance()
        windows = []
        if app:
            for win in app.allWindows():
                try:
                    info = {
                        "type": type(win).__name__,
                        "title": win.title(),
                        "name": win.objectName(),
                        "visible": win.isVisible(),
                        "active": win.isActive(),
                        "state": int(win.windowState()),
                        "flags": int(win.flags()),
                    }
                except Exception:
                    continue
                windows.append(info)
        app_state = None
        try:
            app_state = int(QtGui.QGuiApplication.applicationState())
        except Exception:
            pass
        line = f"t={round(now, 3)} | dt={dt} | snapshot=windows | app_state={app_state} | data={windows}"
        with mw._focus_trace_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        mw._focus_trace_count += 1
        mw._focus_trace_snapshot_remaining -= 1
        if mw._focus_trace_snapshot_remaining <= 0 and mw._focus_trace_snapshot_timer:
            mw._focus_trace_snapshot_timer.stop()
    except Exception:
        pass


def trace_focus_event(mw, obj, event) -> None:
    if not getattr(mw, "_focus_trace_enabled", False):
        return
    try:
        now = time.monotonic()
        dt = _focus_trace_delta(mw, now)
        if now > getattr(mw, "_focus_trace_until", 0):
            mw._focus_trace_enabled = False
            return
        if mw._focus_trace_count >= getattr(mw, "_focus_trace_max_events", 0):
            mw._focus_trace_enabled = False
            return
        etype = int(event.type())
        focus_events = (
            QtCore.QEvent.FocusIn,
            QtCore.QEvent.FocusOut,
            QtCore.QEvent.WindowActivate,
            QtCore.QEvent.WindowDeactivate,
            QtCore.QEvent.ApplicationActivate,
            QtCore.QEvent.ApplicationDeactivate,
        )
        window_events = (
            QtCore.QEvent.Show,
            QtCore.QEvent.Hide,
            QtCore.QEvent.ShowToParent,
            QtCore.QEvent.HideToParent,
            QtCore.QEvent.WindowStateChange,
            QtCore.QEvent.ActivationChange,
            QtCore.QEvent.Move,
            QtCore.QEvent.Resize,
        )
        if etype not in focus_events:
            if not mw._focus_trace_window_events or etype not in window_events:
                return
        app = QtWidgets.QApplication.instance()
        focus_widget = app.focusWidget() if app else None
        focus_name = type(focus_widget).__name__ if focus_widget is not None else None
        focus_obj = focus_widget.objectName() if focus_widget is not None else None
        focus_win = None
        focus_win_title = None
        if isinstance(focus_widget, QtWidgets.QWidget):
            try:
                win = focus_widget.window()
                focus_win = type(win).__name__ if win is not None else None
                focus_win_title = win.windowTitle() if win is not None else None
            except Exception:
                pass
        obj_name = obj.objectName() if hasattr(obj, "objectName") else None
        obj_type = type(obj).__name__ if obj is not None else None
        is_window = False
        is_visible = None
        is_active = None
        window_state = None
        obj_geom = None
        obj_win = None
        obj_win_title = None
        if isinstance(obj, QtWidgets.QWidget):
            try:
                is_window = obj.isWindow()
                is_visible = obj.isVisible()
                is_active = obj.isActiveWindow()
                window_state = int(obj.windowState())
                g = obj.geometry()
                obj_geom = f"{g.x()},{g.y()},{g.width()},{g.height()}"
                win = obj.window()
                obj_win = type(win).__name__ if win is not None else None
                obj_win_title = win.windowTitle() if win is not None else None
            except Exception:
                pass
        elif isinstance(obj, QtGui.QWindow):
            try:
                is_window = True
                is_visible = obj.isVisible()
                is_active = obj.isActive()
                window_state = int(obj.windowState())
                g = obj.geometry()
                obj_geom = f"{g.x()},{g.y()},{g.width()},{g.height()}"
                obj_win = type(obj).__name__
                obj_win_title = obj.title()
            except Exception:
                pass
        if getattr(mw, "_focus_trace_windows_only", False) and not is_window:
            return
        text = None
        if hasattr(obj, "text"):
            try:
                text = obj.text()
            except Exception:
                text = None
        app_state = None
        try:
            app_state = int(QtGui.QGuiApplication.applicationState())
        except Exception:
            pass
        line = (
            f"t={round(now, 3)} | dt={dt} | etype={etype} | etype_name={_event_type_name(etype)} | "
            f"obj={obj_type} | obj_name={obj_name} | obj_text={text} | "
            f"obj_geom={obj_geom} | obj_win={obj_win} | obj_win_title={obj_win_title} | "
            f"is_window={is_window} | is_visible={is_visible} | is_active={is_active} | "
            f"window_state={window_state} | focus={focus_name} | focus_name={focus_obj} | "
            f"focus_win={focus_win} | focus_win_title={focus_win_title} | app_state={app_state}"
        )
        with mw._focus_trace_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        mw._focus_trace_count += 1
    except Exception:
        pass


def trace_hover_event(mw, name: str, **extra) -> None:
    if not getattr(mw, "_hover_trace_enabled", False):
        return
    try:
        if mw._hover_trace_count >= mw._hover_trace_max_events:
            return
        now = time.monotonic()
        last = getattr(mw, "_hover_trace_last_t", None)
        dt = round(now - last, 4) if last is not None else None
        mw._hover_trace_last_t = now
        line = f"t={round(now, 3)} | dt={dt} | event={name}"
        for key, val in extra.items():
            line += f" | {key}={val}"
        with mw._hover_trace_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        mw._hover_trace_count += 1
    except Exception:
        pass


def trace_event(mw, name: str, **extra) -> None:
    if not getattr(mw, "_trace_enabled", False):
        return
    try:
        now = time.monotonic()
        last = getattr(mw, "_trace_last_t", None)
        dt = round(now - last, 4) if last is not None else None
        mw._trace_last_t = now
        stack_idx = mw.mode_stack.currentIndex() if hasattr(mw, "mode_stack") else None
        stack_widget = None
        if hasattr(mw, "mode_stack"):
            try:
                stack_widget = mw.mode_stack.currentWidget()
            except Exception:
                stack_widget = None
        stack_widget_name = type(stack_widget).__name__ if stack_widget is not None else None
        overlay = getattr(mw, "overlay", None)
        overlay_visible = overlay.isVisible() if overlay else False
        overlay_type = getattr(overlay, "_last_view", {}) or {}
        overlay_type = overlay_type.get("type") if isinstance(overlay_type, dict) else None
        tank_updates = mw.tank.updatesEnabled() if hasattr(mw, "tank") else None
        map_updates = getattr(mw, "map_main", None)
        map_updates = map_updates.updatesEnabled() if map_updates else None
        role_vis = None
        map_vis = None
        if getattr(mw, "role_container", None):
            role_vis = mw.role_container.isVisible()
        if getattr(mw, "map_container", None):
            map_vis = mw.map_container.isVisible()
        app_state = None
        try:
            app_state = int(QtGui.QGuiApplication.applicationState())
        except Exception:
            pass
        focus_name = None
        focus_obj = None
        focus_win = None
        focus_win_title = None
        app = QtWidgets.QApplication.instance()
        if app:
            focus_widget = app.focusWidget()
            if focus_widget is not None:
                focus_name = type(focus_widget).__name__
                focus_obj = focus_widget.objectName()
                try:
                    win = focus_widget.window()
                    focus_win = type(win).__name__ if win is not None else None
                    focus_win_title = win.windowTitle() if win is not None else None
                except Exception:
                    pass
        if extra.pop("force_vis", False):
            pass
        base = {
            "t": round(now, 3),
            "dt": dt,
            "event": name,
            "mode": getattr(mw, "current_mode", None),
            "stack": stack_idx,
            "stack_widget": stack_widget_name,
            "overlay": overlay_type,
            "overlay_visible": overlay_visible,
            "post_init": getattr(mw, "_post_choice_init_done", None),
            "map_init": getattr(mw, "_map_initialized", None),
            "stack_switching": getattr(mw, "_stack_switching", None),
            "stack_timer": mw._stack_switch_timer.isActive() if hasattr(mw, "_stack_switch_timer") else None,
            "post_timer": mw._post_choice_timer.isActive() if hasattr(mw, "_post_choice_timer") else None,
            "pending": getattr(mw, "pending", None),
            "cancel_enabled": mw.btn_cancel_spin.isEnabled() if hasattr(mw, "btn_cancel_spin") else None,
            "hero_ban": getattr(mw, "hero_ban_active", None),
            "hero_ban_pending": getattr(mw, "_hero_ban_pending", None),
            "hero_ban_rebuild": getattr(mw, "_hero_ban_rebuild", None),
            "restoring": getattr(mw, "_restoring_state", None),
            "closing": getattr(mw, "_closing", None),
            "map_lists_ready": getattr(mw, "_map_lists_ready", None),
            "map_prebuild": getattr(mw, "_map_prebuild_in_progress", None),
            "map_temp_override": getattr(mw, "_map_temp_override", None),
            "focus": focus_name,
            "focus_name": focus_obj,
            "focus_win": focus_win,
            "focus_win_title": focus_win_title,
            "app_state": app_state,
            "tank_updates": tank_updates,
            "map_updates": map_updates,
            "role_vis": role_vis,
            "map_vis": map_vis,
        }
        base.update(extra)
        line = " | ".join(f"{k}={v}" for k, v in base.items())
        try:
            with mw._trace_file.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        try:
            if bool(getattr(mw, "_spin_perf_enabled", False)):
                event_name = str(name or "").strip().casefold()
                if event_name and ("spin" in event_name):
                    with mw._spin_perf_file.open("a", encoding="utf-8") as f:
                        f.write(line + "\n")
        except Exception:
            pass
        if _cfg(mw, "DEBUG", False):
            config.debug_print(line)
    except Exception:
        pass
