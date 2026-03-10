from __future__ import annotations

from typing import Callable

import i18n
from PySide6 import QtCore, QtWidgets

from utils import theme as theme_util
from view.list_panel import ListPanel


class MapUIListFlowController:
    def __init__(
        self,
        owner,
        *,
        default_role_state_factory: Callable[[], dict],
        rebuild_payload_builder: Callable[..., tuple[dict, dict]],
    ) -> None:
        self._owner = owner
        self._default_role_state_factory = default_role_state_factory
        self._rebuild_payload_builder = rebuild_payload_builder

    def clear_map_lists(self) -> None:
        owner = self._owner
        while owner.map_grid.count():
            item = owner.map_grid.takeAt(0)
            widget = item.widget()
            if widget:
                owner._sizing.unbind_widget(widget)
                try:
                    widget.hide()
                except (AttributeError, RuntimeError, TypeError):
                    pass
                widget.deleteLater()
            del item
        owner.map_lists.clear()
        while owner._map_type_list_layout.count():
            item = owner._map_type_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                try:
                    widget.hide()
                except (AttributeError, RuntimeError, TypeError):
                    pass
                widget.deleteLater()
            del item
        owner.map_type_checks.clear()

    def add_map_list(self, cat: str, role_state: dict) -> None:
        owner = self._owner
        include_checked = role_state.get("include_in_all", True)
        wheel = ListPanel(cat, role_state.get("entries", []), parent=owner.map_grid_container)
        wheel.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        owner._bind_dynamic_map_list_height(wheel)
        wheel.set_spin_button_text(i18n.t("wheel.spin_single_map"))
        wheel.set_language(owner.language)
        wheel.set_interactive_enabled(include_checked)
        wheel.setVisible(include_checked)
        wheel.btn_include_in_all.setChecked(include_checked)
        wheel.btn_include_in_all.setVisible(False)
        if hasattr(wheel, "names_panel"):
            wheel.names_panel.set_auto_focus_enabled(False)
            if hasattr(wheel.names_panel, "set_compact_vertical"):
                try:
                    wheel.names_panel.set_compact_vertical(True)
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    pass
        wheel.btn_local_spin.setFocusPolicy(QtCore.Qt.ClickFocus)
        wheel.btn_include_in_all.setFocusPolicy(QtCore.Qt.ClickFocus)
        if hasattr(wheel, "names"):
            wheel.names.setFocusPolicy(QtCore.Qt.ClickFocus)
        if hasattr(wheel, "btn_sort_names"):
            wheel.btn_sort_names.setFocusPolicy(QtCore.Qt.ClickFocus)
        if hasattr(wheel, "btn_toggle_all_names"):
            wheel.btn_toggle_all_names.setFocusPolicy(QtCore.Qt.ClickFocus)
        wheel.btn_include_in_all.toggled.connect(
            lambda checked, c=cat: self.on_list_include_toggled(c, checked)
        )
        wheel.stateChanged.connect(owner._schedule_update)
        wheel.request_spin.connect(lambda _=None, c=cat: owner.requestSpinCategory.emit(c))
        owner.map_lists[cat] = wheel
        owner.map_grid.addWidget(wheel, 0, QtCore.Qt.AlignTop)

        checkbox = QtWidgets.QCheckBox(cat)
        checkbox.setChecked(include_checked)
        checkbox.setFocusPolicy(QtCore.Qt.ClickFocus)
        checkbox.toggled.connect(lambda checked, c=cat: self.on_map_type_toggled(c, checked))
        owner.map_type_checks[cat] = checkbox
        owner._map_type_list_layout.addWidget(checkbox)

    def build_map_lists(self, map_state: dict) -> None:
        owner = self._owner
        self.clear_map_lists()
        for cat in owner.map_categories:
            role_state = map_state.get(cat) or self._default_role_state_factory()
            self.add_map_list(cat, role_state)
        owner.map_grid.addStretch(1)
        owner._map_type_list_layout.addStretch(1)
        owner._styling.apply_map_control_widths()
        owner._styling.reset_theme_signature()
        owner.apply_theme(theme_util.get_theme(owner.theme_key))
        owner.listsBuilt.emit()

    def start_list_build(self) -> None:
        owner = self._owner
        self.clear_map_lists()
        owner._pending_list_categories = list(owner.map_categories)
        if owner._list_build_timer is None:
            owner._list_build_timer = QtCore.QTimer(owner)
            owner._list_build_timer.setSingleShot(True)
            owner._list_build_timer.timeout.connect(self.build_list_step)
        owner._list_build_timer.start(0)

    def build_list_step(self) -> None:
        owner = self._owner
        if not owner._pending_list_categories:
            owner.map_grid.addStretch(1)
            owner._map_type_list_layout.addStretch(1)
            owner.rebuild_combined(emit_state=False, force_wheel=True)
            owner._styling.reset_theme_signature()
            owner.apply_theme(theme_util.get_theme(owner.theme_key))
            owner.listsBuilt.emit()
            return
        cat = owner._pending_list_categories.pop(0)
        role_state = owner._pending_list_state.get(cat) or self._default_role_state_factory()
        self.add_map_list(cat, role_state)
        if owner._list_build_timer is not None:
            owner._list_build_timer.start(0)

    def on_map_type_toggled(self, category: str, checked: bool) -> None:
        owner = self._owner
        wheel = owner.map_lists.get(category)
        if wheel:
            wheel.btn_include_in_all.setChecked(checked)
            wheel.setVisible(checked)
            wheel.set_interactive_enabled(checked)

    def on_list_include_toggled(self, category: str, checked: bool) -> None:
        owner = self._owner
        if checkbox := owner.map_type_checks.get(category):
            if checkbox.isChecked() != checked:
                blocker = QtCore.QSignalBlocker(checkbox)
                checkbox.setChecked(checked)
                del blocker
        wheel = owner.map_lists.get(category)
        if wheel:
            wheel.setVisible(checked)
            wheel.set_interactive_enabled(checked)

    def apply_map_types(self, new_types: list[str]) -> None:
        owner = self._owner
        current_states: dict[str, dict] = {}
        include_map: dict[str, bool] = {}
        for cat, wheel in owner.map_lists.items():
            current_states[cat] = {
                "entries": wheel.get_current_entries(),
                "pair_mode": False,
                "use_subroles": False,
            }
            include_map[cat] = wheel.btn_include_in_all.isChecked()

        saved_state = owner.state_store.get_mode_state("maps") or {}
        old_categories = list(owner.map_categories)
        new_state, new_include_map = self._rebuild_payload_builder(
            new_types=list(new_types),
            current_states=current_states,
            include_map=include_map,
            saved_state=saved_state,
            old_categories=old_categories,
            default_role_state_factory=self._default_role_state_factory,
        )

        owner.map_categories = list(new_types)
        self.build_map_lists(new_state)
        for cat, wheel in owner.map_lists.items():
            checked = bool(new_include_map.get(cat, True))
            wheel.btn_include_in_all.setChecked(checked)
            wheel.set_interactive_enabled(checked)
            wheel.setVisible(checked)
            if checkbox := owner.map_type_checks.get(cat):
                checkbox.setChecked(checked)
        owner.rebuild_combined(emit_state=True, force_wheel=True)

    def load_state(self) -> None:
        owner = self._owner
        state = owner.state_store.get_mode_state("maps") or {}
        for cat, wheel in owner.map_lists.items():
            role_state = state.get(cat) or owner.state_store.default_role_state(cat, "maps")
            wheel.load_entries(role_state.get("entries", []))
            checked = bool(role_state.get("include_in_all", True))
            wheel.btn_include_in_all.setChecked(checked)
            wheel.set_interactive_enabled(checked)
            wheel.setVisible(checked)
            if checkbox := owner.map_type_checks.get(cat):
                checkbox.setChecked(checked)
        owner.rebuild_combined(emit_state=False, force_wheel=True)

    def capture_state(self) -> None:
        owner = self._owner
        payload: dict[str, dict] = {}
        for cat, wheel in owner.map_lists.items():
            payload[cat] = {
                "entries": wheel.get_current_entries(),
                "pair_mode": False,
                "use_subroles": False,
                "include_in_all": wheel.btn_include_in_all.isChecked(),
            }
        owner.state_store.set_mode_state("maps", payload)

