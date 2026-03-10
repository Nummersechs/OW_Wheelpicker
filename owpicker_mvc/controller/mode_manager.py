"""Mode switching + Hero-Ban visuals to keep main_window.py slimmer.
All helpers expect the MainWindow instance as the first parameter."""
from __future__ import annotations

from typing import List
from logic import hero_ban_merge
from model.mode_keys import AppMode, ROLE_MODE_VALUES, normalize_mode
from model.role_keys import role_wheel_map, role_wheels
from PySide6 import QtWidgets, QtCore
import i18n


def set_hero_ban_visuals(mw, active: bool):
    """Stellt die UI entsprechend Hero-Ban an/aus."""
    mw.hero_ban_active = active

    for role, wheel in role_wheels(mw):
        effect = QtWidgets.QGraphicsOpacityEffect(wheel.view) if active else None
        if active:
            is_center = role == "Damage"
            op = 1.0 if is_center else 0.25
            effect.setOpacity(op)
            wheel.view.setGraphicsEffect(effect)
            wheel.view.setEnabled(is_center)
            if is_center:
                wheel.set_interactive_enabled(True)
                wheel.btn_local_spin.setEnabled(True)
                wheel.set_force_spin_enabled(True)
                wheel.set_spin_button_text(i18n.t("wheel.spin_role"))
                wheel.btn_include_in_all.setEnabled(True)
                wheel.names.setEnabled(True)
            else:
                wheel.view.setEnabled(False)
                wheel.btn_local_spin.setEnabled(True)
                wheel.set_force_spin_enabled(True)
                wheel.set_show_names_visible(False)
                wheel.set_spin_button_text(None)
                wheel.btn_include_in_all.setEnabled(True)
                wheel.names.setEnabled(True)
                wheel.set_interactive_enabled(True)
            lock_pair_controls = getattr(wheel, "set_pair_controls_locked", None)
            if callable(lock_pair_controls):
                lock_pair_controls(True)
            wheel.set_header_controls_visible(False)
            wheel.set_subrole_controls_visible(False)
            if wheel is not mw.dps:
                wheel.set_wheel_render_enabled(False)
            else:
                wheel.set_wheel_render_enabled(True)
        else:
            wheel.view.setGraphicsEffect(None)
            wheel.view.setEnabled(True)
            wheel.set_interactive_enabled(True)
            wheel.btn_local_spin.setEnabled(True)
            wheel.set_force_spin_enabled(False)
            wheel.set_show_names_visible(True)
            wheel.set_spin_button_text(None)
            wheel.btn_include_in_all.setEnabled(True)
            wheel.names.setEnabled(True)
            wheel.set_wheel_render_enabled(True)
            lock_pair_controls = getattr(wheel, "set_pair_controls_locked", None)
            if callable(lock_pair_controls):
                lock_pair_controls(False)
            wheel.set_header_controls_visible(True)
            wheel.set_subrole_controls_visible(True)
            wheel.set_override_entries(None)


def update_hero_ban_wheel(mw):
    """Führt die aktivierten Rollen zu einem zentralen Rad zusammen (Einzel-Helden)."""
    if not mw.hero_ban_active:
        return
    if mw._hero_ban_rebuild:
        mw._hero_ban_pending = True
        return
    mw._hero_ban_rebuild = True
    mw._hero_ban_pending = False

    selected_roles: List[str] = []
    role_to_wheel = role_wheel_map(mw)
    if mw._hero_ban_override_role:
        selected_roles.append(mw._hero_ban_override_role)
    else:
        for role, wheel in role_to_wheel.items():
            if wheel.btn_include_in_all.isChecked():
                selected_roles.append(role)

    combined = hero_ban_merge.merge_selected_roles(selected_roles, role_to_wheel)

    try:
        mw.dps.set_override_entries(combined)
        # Keep rebuild guard active while applying visuals because those calls
        # can synchronously trigger state/tooltip updates and save_state hooks.
        set_hero_ban_visuals(mw, True)
        mw.tank.btn_local_spin.setEnabled(True)
        mw.support.btn_local_spin.setEnabled(True)
        mw.dps.btn_local_spin.setEnabled(True)
        mw._update_spin_all_enabled()
    finally:
        mw._hero_ban_rebuild = False
    if mw._hero_ban_pending:
        mw._hero_ban_pending = False
        QtCore.QTimer.singleShot(0, lambda: update_hero_ban_wheel(mw))


def on_mode_button_clicked(mw, target: str):
    came_from_hero_ban = mw.hero_ban_active
    target_mode = normalize_mode(target, default=AppMode.PLAYERS)
    if target_mode == AppMode.HERO_BAN.value:
        if mw.hero_ban_active:
            return
        mw.last_non_hero_mode = mw.current_mode
        mw._state_store.capture_mode_from_wheels(
            mw.current_mode,
            role_wheel_map(mw),
            hero_ban_active=mw.hero_ban_active,
        )
        mw.current_mode = AppMode.HEROES.value
        mw.btn_mode_players.setChecked(False)
        mw.btn_mode_heroes.setChecked(False)
        mw.btn_mode_heroban.setChecked(True)
        mw._load_mode_into_wheels(AppMode.HEROES.value, hero_ban=True)
        return

    if target_mode not in ROLE_MODE_VALUES:
        return
    if mw.hero_ban_active:
        mw._state_store.capture_mode_from_wheels(
            mw.current_mode,
            role_wheel_map(mw),
            hero_ban_active=mw.hero_ban_active,
        )
        mw.hero_ban_active = False
        mw.dps.set_override_entries(None)
    if target_mode == mw.current_mode and not came_from_hero_ban:
        return
    mw.current_mode = target_mode
    mw.last_non_hero_mode = target_mode
    mw.btn_mode_players.setChecked(target_mode == AppMode.PLAYERS.value)
    mw.btn_mode_heroes.setChecked(target_mode == AppMode.HEROES.value)
    mw.btn_mode_heroban.setChecked(False)
    mw._load_mode_into_wheels(target_mode, hero_ban=False)
    mw.state_sync.save_state()
