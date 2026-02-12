"""Spin logic (global and single) extracted from MainWindow.
All functions expect `mw` to be the MainWindow instance."""
from __future__ import annotations

import random
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
    mw._snapshot_results()
    for _role, wheel in active:
        wheel.clear_result()
    mw.sound.stop_ding()
    mw._stop_all_wheels()
    mw.summary.setText("")
    mw.pending = 0
    mw._set_controls_enabled(False)
    mw.overlay.hide()
    mw.sound.play_spin()


def _run_assigned_spin(mw, active: list[tuple[str, object]], assigned_for_role: list[str | None]) -> None:
    duration = mw.duration.value()
    multipliers = [0.85, 1.00, 1.35]
    random.shuffle(multipliers)

    for (idx, (_role, wheel)), mult in zip(enumerate(active), multipliers):
        target_label = assigned_for_role[idx]
        if target_label is None:
            continue
        if hasattr(wheel, "spin_to_name"):
            if wheel.spin_to_name(target_label, duration_ms=int(duration * mult)):
                mw.pending += 1
        else:
            if wheel.spin(duration_ms=int(duration * mult)):
                mw.pending += 1


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

    all_candidates_per_role = []
    missing_roles = False
    for _role, wheel in active:
        base_entries = wheel._active_entries()
        candidates = _build_candidates_for_wheel(
            wheel,
            base_entries,
            include_disabled=False,
            drop_disabled_labels=False,
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

    _begin_spin_run(mw, active)
    _run_assigned_spin(mw, active, assigned_for_role)

    if mw.pending == 0:
        mw.sound.stop_spin()
        mw._set_controls_enabled(True)
        _show_roles_prompt(mw)
    mw._update_cancel_enabled()


def spin_open_queue(mw):
    if mw.hero_ban_active or mw.current_mode == "maps":
        return
    if mw.pending > 0:
        return
    mw._result_sent_this_spin = False

    active = _active_role_wheels(mw)
    if not active:
        return

    combined_names: list[str] = []
    seen: set[str] = set()
    for _role, wheel in active:
        for entry in wheel._active_entries():
            name = entry.get("name", "").strip()
            if name and name not in seen:
                seen.add(name)
                combined_names.append(name)

    total_slots = sum(2 if wheel.pair_mode else 1 for _role, wheel in active)
    if not combined_names or total_slots <= 0 or len(combined_names) < total_slots:
        _show_not_enough(mw)
        return

    all_candidates_per_role = []
    entries_by_wheel: dict = {}
    missing_roles = False
    for _role, wheel in active:
        subroles: list[str] = []
        if getattr(wheel, "use_subrole_filter", False) and len(getattr(wheel, "subrole_labels", [])) >= 2:
            subroles = list(wheel.subrole_labels[:2])
        entries = [{"name": n, "subroles": list(subroles), "active": True} for n in combined_names]
        entries_by_wheel[wheel] = entries

        candidates = _build_candidates_for_wheel(
            wheel,
            entries,
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

    _begin_spin_run(mw, active)
    mw.open_queue.begin_spin_override(entries_by_wheel)
    _run_assigned_spin(mw, active, assigned_for_role)

    if mw.pending == 0:
        mw.sound.stop_spin()
        mw._set_controls_enabled(True)
        _show_roles_prompt(mw)
        if mw.open_queue.spin_active():
            mw.open_queue.restore_spin_overrides()
    mw._update_cancel_enabled()


def spin_single(mw, wheel, mult: float = 1.0, hero_ban_override: bool = True):
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
    mw.sound.stop_ding()
    mw._stop_all_wheels()
    mw._set_controls_enabled(False)
    mw.summary.setText("")
    mw.pending = 0
    mw.overlay.hide()
    mw.sound.play_spin()
    duration = int(mw.duration.value() * mult)
    if target_wheel.spin(duration_ms=duration):
        mw.pending = 1
    else:
        mw.sound.stop_spin()
        mw._set_controls_enabled(True)
        mw.summary.setText(i18n.t("summary.wheel_prompt"))
        mw.overlay.show_message(
            i18n.t("overlay.not_enough_title"),
            [i18n.t("overlay.not_enough_line1"), i18n.t("overlay.not_enough_line2"), ""],
        )
    mw._update_cancel_enabled()
