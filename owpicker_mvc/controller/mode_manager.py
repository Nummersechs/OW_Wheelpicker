"""Mode switching + Hero-Ban visuals to keep main_window.py slimmer.
All helpers expect the MainWindow instance as the first parameter."""
from __future__ import annotations

from typing import List
from logic import hero_ban_merge
from model.role_keys import role_wheel_map, role_wheels
from PySide6 import QtWidgets, QtCore
import i18n


def set_hero_ban_visuals(mw, active: bool):
    """Stellt die UI entsprechend Hero-Ban an/aus."""
    mw.hero_ban_active = active

    def _disable_pair_controls(wheel) -> None:
        set_pair_mode = getattr(wheel, "_set_pair_mode_internal", None)
        if callable(set_pair_mode):
            set_pair_mode(False)
        elif getattr(wheel, "toggle", None):
            blocker = QtCore.QSignalBlocker(wheel.toggle)
            wheel.toggle.setChecked(False)
            del blocker
            wheel.pair_mode = False
            wheel_state = getattr(wheel, "_wheel_state", None)
            if wheel_state is not None:
                wheel_state.pair_mode = False
        if getattr(wheel, "toggle", None):
            wheel.toggle.setEnabled(False)
        if getattr(wheel, "chk_subroles", None):
            blocker = QtCore.QSignalBlocker(wheel.chk_subroles)
            wheel.chk_subroles.setChecked(False)
            del blocker
            wheel.chk_subroles.setEnabled(False)
        if hasattr(wheel, "use_subrole_filter"):
            wheel.use_subrole_filter = False
            wheel_state = getattr(wheel, "_wheel_state", None)
            if wheel_state is not None:
                wheel_state.use_subrole_filter = False

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
            _disable_pair_controls(wheel)
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
    finally:
        mw._hero_ban_rebuild = False
    set_hero_ban_visuals(mw, True)
    mw.tank.btn_local_spin.setEnabled(True)
    mw.support.btn_local_spin.setEnabled(True)
    mw.dps.btn_local_spin.setEnabled(True)
    mw._update_spin_all_enabled()
    if mw._hero_ban_pending:
        mw._hero_ban_pending = False
        QtCore.QTimer.singleShot(0, lambda: update_hero_ban_wheel(mw))


def on_mode_button_clicked(mw, target: str):
    came_from_hero_ban = mw.hero_ban_active
    if target == "hero_ban":
        if mw.hero_ban_active:
            return
        mw.last_non_hero_mode = mw.current_mode
        mw._state_store.capture_mode_from_wheels(
            mw.current_mode,
            role_wheel_map(mw),
            hero_ban_active=mw.hero_ban_active,
        )
        mw.current_mode = "heroes"
        mw.btn_mode_players.setChecked(False)
        mw.btn_mode_heroes.setChecked(False)
        mw.btn_mode_heroban.setChecked(True)
        mw._load_mode_into_wheels("heroes", hero_ban=True)
        return

    if target not in ("players", "heroes"):
        return
    if mw.hero_ban_active:
        mw._state_store.capture_mode_from_wheels(
            mw.current_mode,
            role_wheel_map(mw),
            hero_ban_active=mw.hero_ban_active,
        )
        mw.hero_ban_active = False
        mw.dps.set_override_entries(None)
    if target == mw.current_mode and not came_from_hero_ban:
        return
    mw.current_mode = target
    mw.last_non_hero_mode = target
    mw.btn_mode_players.setChecked(target == "players")
    mw.btn_mode_heroes.setChecked(target == "heroes")
    mw.btn_mode_heroban.setChecked(False)
    mw._load_mode_into_wheels(target, hero_ban=False)
    mw.state_sync.save_state()
