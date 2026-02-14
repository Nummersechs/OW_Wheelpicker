"""Spin logic (global and single) extracted from MainWindow.
All functions expect `mw` to be the MainWindow instance."""
from __future__ import annotations

import random
import time
from logic import spin_planner
from model.role_keys import role_for_wheel, role_wheels
import i18n


def _active_role_wheels(mw) -> list[tuple[str, object]]:
    if hasattr(mw, "role_mode"):
        return mw.role_mode.active_wheels()
    return [
        (role, wheel) for role, wheel in role_wheels(mw) if wheel.is_selected_for_global_spin()
    ]


def _begin_spin_run(mw, active: list[tuple[str, object]]) -> None:
    if hasattr(mw, "_trace_event"):
        try:
            mw._trace_event("spin_run_begin", roles=[role for role, _wheel in active], pending=mw.pending)
        except Exception:
            pass
    if hasattr(mw, "_disarm_spin_watchdog"):
        mw._disarm_spin_watchdog()
    mw._snapshot_results()
    for _role, wheel in active:
        wheel.clear_result()
    mw.sound.stop_spin()
    mw.sound.stop_ding()
    mw._stop_all_wheels()
    mw.summary.setText("")
    mw.pending = 0
    mw._set_controls_enabled(False)
    mw.overlay.hide()
    mw.sound.play_spin()
    if hasattr(mw, "_mark_spin_started"):
        mw._mark_spin_started()
    else:
        mw._spin_started_at_monotonic = time.monotonic()


def _run_assigned_spin(
    mw,
    active: list[tuple[str, object]],
    assigned_for_role: list[str | None],
) -> int:
    duration = mw.duration.value()
    multipliers = [0.85, 1.00, 1.35]
    random.shuffle(multipliers)
    max_started_duration = 0

    for (idx, (_role, wheel)), mult in zip(enumerate(active), multipliers):
        target_label = assigned_for_role[idx]
        if target_label is None:
            if hasattr(mw, "_trace_event"):
                try:
                    mw._trace_event("spin_launch_skipped", role=_role, reason="no_target")
                except Exception:
                    pass
            continue
        spin_duration = int(duration * mult)
        started = False
        if hasattr(wheel, "spin_to_name"):
            started = bool(wheel.spin_to_name(target_label, duration_ms=spin_duration))
        else:
            started = bool(wheel.spin(duration_ms=spin_duration))
        if started:
            mw.pending += 1
            if spin_duration > max_started_duration:
                max_started_duration = spin_duration
        if hasattr(mw, "_trace_event"):
            try:
                mw._trace_event(
                    "spin_launch_attempt",
                    role=_role,
                    target=target_label,
                    duration_ms=spin_duration,
                    started=started,
                )
            except Exception:
                pass
    return max_started_duration


def _show_roles_prompt(mw) -> None:
    mw.summary.setText(i18n.t("summary.roles_prompt"))


def _show_not_enough(mw) -> None:
    _show_roles_prompt(mw)
    mw.overlay.show_message(
        i18n.t("overlay.not_enough_title"),
        [i18n.t("overlay.not_enough_line1"), i18n.t("overlay.not_enough_line2"), ""],
    )


def _show_team_impossible(mw) -> None:
    mw.sound.stop_spin()
    mw.sound.stop_ding()
    mw._set_controls_enabled(True)
    mw.pending = 0
    mw.summary.setText(i18n.t("summary.team_impossible"))
    mw.overlay.show_message(
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
    if hasattr(mw, "_trace_event"):
        try:
            mw._trace_event("spin_all_dispatch", pending=mw.pending)
        except Exception:
            pass
    if mw.hero_ban_active:
        if mw.pending > 0:
            return
        mw._hero_ban_override_role = None
        mw._update_hero_ban_wheel()
        mw._spin_single(mw.dps, 1.0, hero_ban_override=False)
        return
    if mw.pending > 0:
        return
    mw._result_sent_this_spin = False

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
        for wheel in missing_wheels:
            if hasattr(wheel, "set_result_too_few"):
                wheel.set_result_too_few()
        _show_not_enough(mw)
        return

    assigned_for_role = _plan_assignments(mw, all_candidates_per_role)
    if assigned_for_role is None:
        return

    _begin_spin_run(mw, active)
    for wheel in missing_wheels:
        if hasattr(wheel, "set_result_too_few"):
            wheel.set_result_too_few()
    max_started_duration = _run_assigned_spin(mw, valid_active, assigned_for_role)

    if mw.pending == 0:
        mw.sound.stop_spin()
        mw._set_controls_enabled(True)
        _show_roles_prompt(mw)
    elif hasattr(mw, "_arm_spin_watchdog"):
        mw._arm_spin_watchdog(max_started_duration)
    if hasattr(mw, "_trace_event"):
        try:
            mw._trace_event(
                "spin_all_started",
                pending=mw.pending,
                started_duration_ms=max_started_duration,
                active_roles=[role for role, _wheel in valid_active],
                missing_roles=len(missing_wheels),
            )
        except Exception:
            pass
    mw._update_cancel_enabled()


def spin_open_queue(mw):
    if hasattr(mw, "_trace_event"):
        try:
            mw._trace_event("spin_open_dispatch", pending=mw.pending)
        except Exception:
            pass
    if mw.hero_ban_active or mw.current_mode == "maps":
        return
    if mw.pending > 0:
        return
    mw._result_sent_this_spin = False

    all_role_wheels = role_wheels(mw)
    if not all_role_wheels:
        return

    mw.open_queue.apply_slider_combination()
    slot_plan = mw.open_queue.slot_plan()
    if not slot_plan:
        _show_not_enough(mw)
        return
    used_plan = [(role, wheel, slots) for role, wheel, slots in slot_plan if slots > 0]
    total_slots = sum(slots for _role, _wheel, slots in used_plan)
    if not used_plan or total_slots <= 0:
        _show_not_enough(mw)
        return

    combined_names: list[str] = []
    seen: set[str] = set()
    for _role, wheel, _slots in used_plan:
        for entry in wheel._active_entries():
            name = entry.get("name", "").strip()
            if name and name not in seen:
                seen.add(name)
                combined_names.append(name)

    if not combined_names or total_slots <= 0 or len(combined_names) < total_slots:
        _show_not_enough(mw)
        return

    all_candidates_per_role = []
    entries_by_wheel: dict = {}
    mode_overrides_by_wheel: dict = {}
    missing_roles = False
    for _role, wheel, slots in used_plan:
        subroles: list[str] = []
        if getattr(wheel, "use_subrole_filter", False) and len(getattr(wheel, "subrole_labels", [])) >= 2:
            subroles = list(wheel.subrole_labels[:2])
        entries = [{"name": n, "subroles": list(subroles), "active": True} for n in combined_names]
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
            if hasattr(wheel, "set_result_too_few"):
                wheel.set_result_too_few()
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
    mw.open_queue.begin_spin_override(
        entries_by_wheel,
        mode_overrides=mode_overrides_by_wheel,
    )
    max_started_duration = _run_assigned_spin(
        mw,
        [(role, wheel) for role, wheel, _slots in used_plan],
        assigned_for_role,
    )

    if mw.pending == 0:
        mw.sound.stop_spin()
        mw._set_controls_enabled(True)
        _show_roles_prompt(mw)
        if mw.open_queue.spin_active():
            mw.open_queue.restore_spin_overrides()
    elif hasattr(mw, "_arm_spin_watchdog"):
        mw._arm_spin_watchdog(max_started_duration)
    if hasattr(mw, "_trace_event"):
        try:
            mw._trace_event(
                "spin_open_started",
                pending=mw.pending,
                started_duration_ms=max_started_duration,
                total_slots=total_slots,
            )
        except Exception:
            pass
    mw._update_cancel_enabled()


def spin_single(mw, wheel, mult: float = 1.0, hero_ban_override: bool = True):
    if hasattr(mw, "_trace_event"):
        try:
            role = role_for_wheel(mw, wheel)
            mw._trace_event("spin_single_dispatch", role=role, pending=mw.pending)
        except Exception:
            pass
    if mw.pending > 0:
        return
    if mw.hero_ban_active:
        resolved_role = role_for_wheel(mw, wheel)
        mw._hero_ban_override_role = resolved_role if hero_ban_override else None
        mw._update_hero_ban_wheel()
        target_wheel = mw.dps
    else:
        target_wheel = wheel
    mw._result_sent_this_spin = False
    mw._snapshot_results()
    mw.sound.stop_spin()
    mw.sound.stop_ding()
    mw._stop_all_wheels()
    mw._set_controls_enabled(False)
    mw.summary.setText("")
    mw.pending = 0
    mw.overlay.hide()
    mw.sound.play_spin()
    if hasattr(mw, "_mark_spin_started"):
        mw._mark_spin_started()
    else:
        mw._spin_started_at_monotonic = time.monotonic()
    duration = int(mw.duration.value() * mult)
    if target_wheel.spin(duration_ms=duration):
        mw.pending = 1
        if hasattr(mw, "_arm_spin_watchdog"):
            mw._arm_spin_watchdog(duration)
        if hasattr(mw, "_trace_event"):
            try:
                mw._trace_event("spin_single_started", pending=mw.pending, duration_ms=duration)
            except Exception:
                pass
    else:
        mw.sound.stop_spin()
        mw._set_controls_enabled(True)
        if hasattr(mw, "_clear_spin_started"):
            mw._clear_spin_started()
        else:
            mw._spin_started_at_monotonic = None
        mw.summary.setText(i18n.t("summary.wheel_prompt"))
        mw.overlay.show_message(
            i18n.t("overlay.not_enough_title"),
            [i18n.t("overlay.not_enough_line1"), i18n.t("overlay.not_enough_line2"), ""],
        )
        if hasattr(mw, "_trace_event"):
            try:
                mw._trace_event("spin_single_failed", pending=mw.pending, duration_ms=duration)
            except Exception:
                pass
    mw._update_cancel_enabled()
