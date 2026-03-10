"""Spin logic (global and single) extracted from MainWindow.
All functions expect `mw` to be the MainWindow instance."""
from __future__ import annotations

import random
import time
from logic import spin_planner
from model.role_keys import role_for_wheel, role_wheels
import i18n


def _trace(mw, event: str, **payload) -> None:
    trace_event = getattr(mw, "_trace_event", None)
    if not callable(trace_event):
        return
    try:
        trace_event(event, **payload)
    except Exception:
        pass


def _active_role_wheels(mw) -> list[tuple[str, object]]:
    if hasattr(mw, "role_mode"):
        return mw.role_mode.active_wheels()
    return [
        (role, wheel) for role, wheel in role_wheels(mw) if wheel.is_selected_for_global_spin()
    ]


def _set_controls_enabled(mw, enabled: bool, *, spin_mode: bool = False) -> None:
    setter = getattr(mw, "_set_controls_enabled", None)
    if not callable(setter):
        return
    if spin_mode:
        try:
            setter(bool(enabled), spin_mode=True)
            return
        except TypeError:
            pass
    setter(bool(enabled))


def _set_heavy_ui_updates_enabled(mw, enabled: bool) -> None:
    setter = getattr(mw, "_set_heavy_ui_updates_enabled", None)
    if not callable(setter):
        return
    try:
        setter(bool(enabled))
    except Exception:
        pass


def _arm_spin_watchdog(mw, duration_ms: int) -> None:
    arm_watchdog = getattr(mw, "_arm_spin_watchdog", None)
    if callable(arm_watchdog):
        arm_watchdog(int(duration_ms))


def _mark_spin_started(mw) -> None:
    mark_started = getattr(mw, "_mark_spin_started", None)
    if callable(mark_started):
        mark_started()
        return
    mw._spin_started_at_monotonic = time.monotonic()


def _clear_spin_started(mw) -> None:
    clear_started = getattr(mw, "_clear_spin_started", None)
    if callable(clear_started):
        clear_started()
        return
    mw._spin_started_at_monotonic = None


def _pending(mw) -> int:
    try:
        return int(getattr(mw, "pending", 0) or 0)
    except Exception:
        return 0


def _set_pending(mw, value: int) -> None:
    try:
        setattr(mw, "pending", int(value))
    except Exception:
        setattr(mw, "pending", 0)


def _inc_pending(mw, delta: int = 1) -> None:
    _set_pending(mw, _pending(mw) + int(delta))


def _sound_stop_spin(mw) -> None:
    sound = getattr(mw, "sound", None)
    stop = getattr(sound, "stop_spin", None)
    if callable(stop):
        stop()


def _sound_stop_ding(mw) -> None:
    sound = getattr(mw, "sound", None)
    stop = getattr(sound, "stop_ding", None)
    if callable(stop):
        stop()


def _sound_play_spin(mw) -> None:
    sound = getattr(mw, "sound", None)
    play = getattr(sound, "play_spin", None)
    if callable(play):
        play()


def _stop_all_wheels(mw) -> None:
    stop_all = getattr(mw, "_stop_all_wheels", None)
    if callable(stop_all):
        stop_all()


def _snapshot_results(mw) -> None:
    snapshot = getattr(mw, "_snapshot_results", None)
    if callable(snapshot):
        snapshot()


def _set_summary_text(mw, text: str) -> None:
    summary = getattr(mw, "summary", None)
    setter = getattr(summary, "setText", None)
    if callable(setter):
        setter(str(text))


def _overlay_hide(mw) -> None:
    overlay = getattr(mw, "overlay", None)
    hide = getattr(overlay, "hide", None)
    if callable(hide):
        hide()


def _overlay_show_message(mw, title: str, lines: list[str]) -> None:
    overlay = getattr(mw, "overlay", None)
    show_message = getattr(overlay, "show_message", None)
    if callable(show_message):
        show_message(str(title), list(lines))


def _update_cancel_enabled(mw) -> None:
    updater = getattr(mw, "_update_cancel_enabled", None)
    if callable(updater):
        updater()


def _set_result_sent_this_spin(mw, value: bool) -> None:
    setattr(mw, "_result_sent_this_spin", bool(value))


def _set_hero_ban_override_role(mw, role_value) -> None:
    setattr(mw, "_hero_ban_override_role", role_value)


def _update_hero_ban_wheel(mw) -> None:
    updater = getattr(mw, "_update_hero_ban_wheel", None)
    if callable(updater):
        updater()


def _duration_value(mw) -> int:
    duration = getattr(mw, "duration", None)
    value_fn = getattr(duration, "value", None)
    if callable(value_fn):
        try:
            return int(value_fn())
        except Exception:
            return 2500
    return 2500


def _open_queue_spin_active(mw) -> bool:
    open_queue = getattr(mw, "open_queue", None)
    spin_active = getattr(open_queue, "spin_active", None)
    if callable(spin_active):
        try:
            return bool(spin_active())
        except Exception:
            return False
    return False


def _open_queue_restore_spin_overrides(mw) -> None:
    open_queue = getattr(mw, "open_queue", None)
    restore = getattr(open_queue, "restore_spin_overrides", None)
    if callable(restore):
        restore()


def _open_queue_apply_slider_combination(mw) -> None:
    open_queue = getattr(mw, "open_queue", None)
    apply = getattr(open_queue, "apply_slider_combination", None)
    if callable(apply):
        apply()


def _open_queue_slot_plan(mw):
    open_queue = getattr(mw, "open_queue", None)
    plan = getattr(open_queue, "slot_plan", None)
    if callable(plan):
        return list(plan())
    return []


def _open_queue_names(mw) -> list[str]:
    open_queue = getattr(mw, "open_queue", None)
    names_fn = getattr(open_queue, "names", None)
    if callable(names_fn):
        return list(names_fn())
    return []


def _open_queue_begin_spin_override(mw, entries_by_wheel: dict, *, mode_overrides: dict) -> None:
    open_queue = getattr(mw, "open_queue", None)
    begin = getattr(open_queue, "begin_spin_override", None)
    if callable(begin):
        begin(entries_by_wheel, mode_overrides=mode_overrides)


def _prepare_spin_ui(mw) -> None:
    _sound_stop_spin(mw)
    _sound_stop_ding(mw)
    _stop_all_wheels(mw)
    _set_heavy_ui_updates_enabled(mw, True)
    _set_summary_text(mw, "")
    _set_pending(mw, 0)
    _set_controls_enabled(mw, False, spin_mode=True)
    _overlay_hide(mw)
    _sound_play_spin(mw)
    _mark_spin_started(mw)


def _mark_wheels_too_few(wheels: list[object]) -> None:
    for wheel in wheels:
        set_too_few = getattr(wheel, "set_result_too_few", None)
        if callable(set_too_few):
            set_too_few()


def _finish_spin_launch(
    mw,
    *,
    max_started_duration: int,
    trace_event: str,
    trace_payload: dict | None = None,
    restore_open_queue_when_idle: bool = False,
) -> None:
    if _pending(mw) == 0:
        _sound_stop_spin(mw)
        _set_controls_enabled(mw, True)
        _show_roles_prompt(mw)
        if restore_open_queue_when_idle and _open_queue_spin_active(mw):
            _open_queue_restore_spin_overrides(mw)
    else:
        _arm_spin_watchdog(mw, max_started_duration)
    payload = {"pending": _pending(mw), "started_duration_ms": max_started_duration}
    if trace_payload:
        payload.update(trace_payload)
    _trace(mw, trace_event, **payload)
    _update_cancel_enabled(mw)


def _subroles_for_wheel(wheel) -> list[str]:
    if bool(getattr(wheel, "use_subrole_filter", False)) and len(getattr(wheel, "subrole_labels", [])) >= 2:
        return list(wheel.subrole_labels[:2])
    return []


def _entries_for_names(wheel, names: list[str]) -> list[dict]:
    subroles = _subroles_for_wheel(wheel)
    return [{"name": name, "subroles": list(subroles), "active": True} for name in names]


def _begin_spin_run(mw, active: list[tuple[str, object]]) -> None:
    _trace(mw, "spin_run_begin", roles=[role for role, _wheel in active], pending=_pending(mw))
    disarm_watchdog = getattr(mw, "_disarm_spin_watchdog", None)
    if callable(disarm_watchdog):
        disarm_watchdog()
    _snapshot_results(mw)
    for _role, wheel in active:
        wheel.clear_result()
    _prepare_spin_ui(mw)


def _run_assigned_spin(
    mw,
    active: list[tuple[str, object]],
    assigned_for_role: list[str | None],
) -> int:
    duration = _duration_value(mw)
    multipliers = [0.85, 1.00, 1.35]
    random.shuffle(multipliers)
    max_started_duration = 0

    for (idx, (_role, wheel)), mult in zip(enumerate(active), multipliers):
        target_label = assigned_for_role[idx]
        if target_label is None:
            _trace(mw, "spin_launch_skipped", role=_role, reason="no_target")
            continue
        spin_duration = int(duration * mult)
        started = False
        if hasattr(wheel, "spin_to_name"):
            started = bool(wheel.spin_to_name(target_label, duration_ms=spin_duration))
        else:
            started = bool(wheel.spin(duration_ms=spin_duration))
        if started:
            _inc_pending(mw, 1)
            if spin_duration > max_started_duration:
                max_started_duration = spin_duration
        _trace(
            mw,
            "spin_launch_attempt",
            role=_role,
            target=target_label,
            duration_ms=spin_duration,
            started=started,
        )
    return max_started_duration


def _show_roles_prompt(mw) -> None:
    _set_summary_text(mw, i18n.t("summary.roles_prompt"))


def _show_not_enough(mw) -> None:
    _show_roles_prompt(mw)
    _overlay_show_message(
        mw,
        i18n.t("overlay.not_enough_title"),
        [i18n.t("overlay.not_enough_line1"), i18n.t("overlay.not_enough_line2"), ""],
    )


def _show_team_impossible(mw) -> None:
    _sound_stop_spin(mw)
    _sound_stop_ding(mw)
    _set_controls_enabled(mw, True)
    _set_pending(mw, 0)
    _set_summary_text(mw, i18n.t("summary.team_impossible"))
    _overlay_show_message(
        mw,
        i18n.t("overlay.team_impossible_title"),
        [
            i18n.t("overlay.team_impossible_line1"),
            i18n.t("overlay.team_impossible_line2"),
            "",
        ],
    )


def _labels_to_candidates(labels: list[str]) -> list[tuple[str, list[str]]]:
    role_candidates: list[tuple[str, list[str]]] = []
    for lbl in labels:
        parts = [p.strip() for p in lbl.split("+")]
        parts = [p for p in parts if p]
        if not parts:
            continue
        role_candidates.append((lbl, parts))
    return role_candidates


def _labels_for_entries(
    wheel,
    entries: list[dict],
    *,
    include_disabled: bool,
    drop_disabled_labels: bool,
) -> list[str]:
    labels = wheel._effective_names_from(entries, include_disabled=include_disabled)
    labels = [lbl.strip() for lbl in labels if lbl and lbl.strip()]
    if not drop_disabled_labels:
        return labels
    disabled_labels = set(getattr(wheel, "_disabled_labels", set()) or set())
    if disabled_labels:
        labels = [lbl for lbl in labels if lbl not in disabled_labels]
    return labels


def _build_candidates_for_wheel(
    wheel,
    entries: list[dict],
    *,
    include_disabled: bool,
    drop_disabled_labels: bool,
) -> list[tuple[str, list[str]]]:
    labels = _labels_for_entries(
        wheel,
        entries,
        include_disabled=include_disabled,
        drop_disabled_labels=drop_disabled_labels,
    )
    return _labels_to_candidates(labels)


def _build_candidates_for_wheel_with_mode(
    wheel,
    entries: list[dict],
    *,
    pair_mode: bool,
    use_subroles: bool,
    include_disabled: bool,
    drop_disabled_labels: bool,
) -> list[tuple[str, list[str]]]:
    state = getattr(wheel, "_wheel_state", None)
    if state is None:
        return _build_candidates_for_wheel(
            wheel,
            entries,
            include_disabled=include_disabled,
            drop_disabled_labels=drop_disabled_labels,
        )
    prev_pair_mode = bool(getattr(state, "pair_mode", False))
    prev_use_subroles = bool(getattr(state, "use_subrole_filter", False))
    try:
        state.pair_mode = bool(pair_mode)
        state.use_subrole_filter = bool(use_subroles)
        return _build_candidates_for_wheel(
            wheel,
            entries,
            include_disabled=include_disabled,
            drop_disabled_labels=drop_disabled_labels,
        )
    finally:
        state.pair_mode = prev_pair_mode
        state.use_subrole_filter = prev_use_subroles


def _plan_assignments(mw, all_candidates_per_role: list[list[tuple[str, list[str]]]]) -> list[str | None] | None:
    if all(not cands for cands in all_candidates_per_role):
        _show_roles_prompt(mw)
        return None
    assigned_for_role = spin_planner.plan_assignments(all_candidates_per_role)
    if not assigned_for_role:
        _show_team_impossible(mw)
        return None
    return assigned_for_role


def spin_all(mw):
    _trace(mw, "spin_all_dispatch", pending=_pending(mw))
    if mw.hero_ban_active:
        if _pending(mw) > 0:
            return
        _set_hero_ban_override_role(mw, None)
        _update_hero_ban_wheel(mw)
        mw._spin_single(mw.dps, 1.0, hero_ban_override=False)
        return
    if _pending(mw) > 0:
        return
    _set_result_sent_this_spin(mw, False)

    active = _active_role_wheels(mw)
    if not active:
        return

    valid_active: list[tuple[str, object]] = []
    all_candidates_per_role = []
    missing_wheels: list[object] = []
    for _role, wheel in active:
        base_entries = wheel._active_entries()
        candidates = _build_candidates_for_wheel(
            wheel,
            base_entries,
            include_disabled=False,
            drop_disabled_labels=False,
        )
        if not candidates:
            missing_wheels.append(wheel)
            continue
        valid_active.append((_role, wheel))
        all_candidates_per_role.append(candidates)

    if not valid_active:
        _mark_wheels_too_few(missing_wheels)
        _show_not_enough(mw)
        return

    assigned_for_role = _plan_assignments(mw, all_candidates_per_role)
    if assigned_for_role is None:
        return

    _begin_spin_run(mw, active)
    _mark_wheels_too_few(missing_wheels)
    max_started_duration = _run_assigned_spin(mw, valid_active, assigned_for_role)
    _finish_spin_launch(
        mw,
        max_started_duration=max_started_duration,
        trace_event="spin_all_started",
        trace_payload={
            "active_roles": [role for role, _wheel in valid_active],
            "missing_roles": len(missing_wheels),
        },
    )


def spin_open_queue(mw):
    _trace(mw, "spin_open_dispatch", pending=_pending(mw))
    if mw.hero_ban_active or mw.current_mode == "maps":
        return
    if _pending(mw) > 0:
        return
    _set_result_sent_this_spin(mw, False)

    all_role_wheels = role_wheels(mw)
    if not all_role_wheels:
        return

    _open_queue_apply_slider_combination(mw)
    slot_plan = _open_queue_slot_plan(mw)
    if not slot_plan:
        _show_not_enough(mw)
        return
    used_plan = [(role, wheel, slots) for role, wheel, slots in slot_plan if slots > 0]
    total_slots = sum(slots for _role, _wheel, slots in used_plan)
    if not used_plan or total_slots <= 0:
        _show_not_enough(mw)
        return

    combined_names = _open_queue_names(mw)

    if not combined_names or total_slots <= 0 or len(combined_names) < total_slots:
        _show_not_enough(mw)
        return

    all_candidates_per_role = []
    entries_by_wheel: dict = {}
    mode_overrides_by_wheel: dict = {}
    missing_roles = False
    for _role, wheel, slots in used_plan:
        entries = _entries_for_names(wheel, combined_names)
        entries_by_wheel[wheel] = entries
        pair_mode = slots >= 2
        use_subroles = bool(pair_mode and getattr(wheel, "use_subrole_filter", False))
        mode_overrides_by_wheel[wheel] = {
            "pair_mode": pair_mode,
            "use_subroles": use_subroles,
        }

        candidates = _build_candidates_for_wheel_with_mode(
            wheel,
            entries,
            pair_mode=pair_mode,
            use_subroles=use_subroles,
            include_disabled=True,
            drop_disabled_labels=True,
        )
        if not candidates:
            _mark_wheels_too_few([wheel])
            missing_roles = True
            all_candidates_per_role.append([])
            continue
        all_candidates_per_role.append(candidates)

    if missing_roles:
        _show_not_enough(mw)
        return

    assigned_for_role = _plan_assignments(mw, all_candidates_per_role)
    if assigned_for_role is None:
        return

    _begin_spin_run(mw, all_role_wheels)
    _open_queue_begin_spin_override(
        mw,
        entries_by_wheel,
        mode_overrides=mode_overrides_by_wheel,
    )
    max_started_duration = _run_assigned_spin(
        mw,
        [(role, wheel) for role, wheel, _slots in used_plan],
        assigned_for_role,
    )
    _finish_spin_launch(
        mw,
        max_started_duration=max_started_duration,
        trace_event="spin_open_started",
        trace_payload={"total_slots": total_slots},
        restore_open_queue_when_idle=True,
    )


def spin_single(mw, wheel, mult: float = 1.0, hero_ban_override: bool = True):
    role = None
    try:
        role = role_for_wheel(mw, wheel)
    except Exception:
        pass
    _trace(mw, "spin_single_dispatch", role=role, pending=_pending(mw))
    if _pending(mw) > 0:
        return
    if mw.hero_ban_active:
        resolved_role = role_for_wheel(mw, wheel)
        _set_hero_ban_override_role(mw, resolved_role if hero_ban_override else None)
        _update_hero_ban_wheel(mw)
        target_wheel = mw.dps
    else:
        target_wheel = wheel
    _set_result_sent_this_spin(mw, False)
    _snapshot_results(mw)
    _prepare_spin_ui(mw)
    duration = int(_duration_value(mw) * mult)
    if target_wheel.spin(duration_ms=duration):
        _set_pending(mw, 1)
        _arm_spin_watchdog(mw, duration)
        _trace(mw, "spin_single_started", pending=_pending(mw), duration_ms=duration)
    else:
        _sound_stop_spin(mw)
        _set_controls_enabled(mw, True)
        _clear_spin_started(mw)
        _set_summary_text(mw, i18n.t("summary.wheel_prompt"))
        _overlay_show_message(
            mw,
            i18n.t("overlay.not_enough_title"),
            [i18n.t("overlay.not_enough_line1"), i18n.t("overlay.not_enough_line2"), ""],
        )
        _trace(mw, "spin_single_failed", pending=_pending(mw), duration_ms=duration)
    _update_cancel_enabled(mw)
