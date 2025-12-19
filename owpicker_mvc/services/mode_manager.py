"""
Kapselt Moduswechsel und Hero-Ban-Visuals, damit controller.py schlanker bleibt.
Alle Funktionen erwarten das MainWindow-Objekt als ersten Parameter.
"""
from __future__ import annotations

from typing import List
from services import hero_ban_merge
from PySide6 import QtWidgets, QtCore
import i18n


def set_hero_ban_visuals(mw, active: bool):
    """Stellt die UI entsprechend Hero-Ban an/aus."""
    mw.hero_ban_active = active
    for wheel in (mw.tank, mw.dps, mw.support):
        effect = QtWidgets.QGraphicsOpacityEffect(wheel.view) if active else None
        if active:
            is_center = wheel is mw.dps
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
                if wheel.toggle:
                    wheel.toggle.setEnabled(False)
                    wheel.toggle.setChecked(False)
                if wheel.chk_subroles:
                    wheel.chk_subroles.setEnabled(False)
                    wheel.chk_subroles.setChecked(False)
            if wheel.toggle:
                wheel.toggle.setEnabled(False)
                wheel.toggle.setChecked(False)
            if wheel.chk_subroles:
                wheel.chk_subroles.setEnabled(False)
                wheel.chk_subroles.setChecked(False)
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
            if wheel.toggle:
                wheel.toggle.setEnabled(True)
            if wheel.chk_subroles:
                wheel.chk_subroles.setEnabled(True)
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
    if mw._hero_ban_override_role:
        selected_roles.append(mw._hero_ban_override_role)
    else:
        if mw.tank.btn_include_in_all.isChecked():
            selected_roles.append("Tank")
        if mw.dps.btn_include_in_all.isChecked():
            selected_roles.append("Damage")
        if mw.support.btn_include_in_all.isChecked():
            selected_roles.append("Support")

    role_to_wheel = {"Tank": mw.tank, "Damage": mw.dps, "Support": mw.support}
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
            {"Tank": mw.tank, "Damage": mw.dps, "Support": mw.support},
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
            {"Tank": mw.tank, "Damage": mw.dps, "Support": mw.support},
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
    mw._save_state()
