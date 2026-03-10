from __future__ import annotations

_SHUTDOWN_SNAPSHOT_GUARD_ERRORS = (
    AttributeError,
    RuntimeError,
    TypeError,
    ValueError,
    LookupError,
    OSError,
)


def _cfg(mw, key: str, default=None):
    getter = getattr(mw, "_cfg", None)
    if callable(getter):
        try:
            return getter(key, default)
        except _SHUTDOWN_SNAPSHOT_GUARD_ERRORS:
            pass
    return default


def merge_shutdown_snapshot(prefix: str, payload: dict | None, target: dict) -> None:
    if not isinstance(payload, dict):
        return
    for key, value in payload.items():
        target[f"{prefix}_{key}"] = value


def trace_shutdown_snapshot_error(mw, *, component: str, exc: Exception) -> None:
    if not bool(_cfg(mw, "TRACE_SHUTDOWN", False)):
        return
    tracer = getattr(mw, "_trace_event", None)
    if not callable(tracer):
        return
    tracer("shutdown_snapshot:error", component=component, error=repr(exc))


def append_component_snapshot(
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
    except _SHUTDOWN_SNAPSHOT_GUARD_ERRORS as exc:
        trace_shutdown_snapshot_error(mw, component=component, exc=exc)
        return
    merge_shutdown_snapshot(prefix, payload, target)


def build_component_snapshot(mw) -> dict[str, object]:
    snap: dict[str, object] = {}
    append_component_snapshot(
        mw,
        target=snap,
        component="timer_registry",
        prefix="registry",
        source=getattr(mw, "_timers", None),
    )
    append_component_snapshot(
        mw,
        target=snap,
        component="state_sync",
        prefix="state_sync",
        source=getattr(mw, "state_sync", None),
    )
    append_component_snapshot(
        mw,
        target=snap,
        component="tooltip_manager",
        prefix="tooltip",
        source=getattr(mw, "_tooltip_manager", None),
    )
    append_component_snapshot(
        mw,
        target=snap,
        component="sound",
        prefix="sound",
        source=getattr(mw, "sound", None),
    )
    append_component_snapshot(
        mw,
        target=snap,
        component="player_list_panel",
        prefix="player_panel",
        source=getattr(mw, "player_list_panel", None),
    )
    append_component_snapshot(
        mw,
        target=snap,
        component="map_ui",
        prefix="map_ui",
        source=getattr(mw, "map_ui", None),
    )
    return snap

