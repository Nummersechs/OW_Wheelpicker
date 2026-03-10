from __future__ import annotations

from typing import Dict
from PySide6 import QtCore, QtWidgets
import i18n
from .categories import (
    build_map_type_rebuild_payload,
    normalize_map_categories,
)
from .editor import MapTypeEditorController
from .editor_flow import MapUIEditorFlowController
from .list_flow import MapUIListFlowController
from .presentation import MapUIPresentationController
from .sizing import MapUIDynamicSizingController
from .styling import MapUIStylingController
from .updates import MapUICombinedUpdateController
from utils import theme as theme_util
from view import style_helpers, ui_tokens
from view.wheel_view import WheelView
from view.list_panel import ListPanel

QWIDGETSIZE_MAX = getattr(QtWidgets, "QWIDGETSIZE_MAX", getattr(QtCore, "QWIDGETSIZE_MAX", 16777215))


def _default_map_role_state() -> dict:
    return {"entries": [], "pair_mode": False, "use_subroles": False}


class MapUI(QtCore.QObject):
    """
    Kapselt die komplette Map-UI (Listen + zentrales Rad) aus MainWindow heraus.
    Stellt kombinierte Namen, State-Load/Save und Theme/Language-Hooks bereit.
    """

    stateChanged = QtCore.Signal()
    requestSpinCategory = QtCore.Signal(str)
    listsBuilt = QtCore.Signal()

    def __init__(
        self,
        state_store,
        language: str,
        theme_key: str,
        role_widgets: tuple,
        defer_lists: bool = False,
        *,
        settings=None,
    ):
        super().__init__()
        self.state_store = state_store
        self.language = language
        self.theme_key = theme_key
        self._role_widgets = role_widgets  # (tank, dps, support)
        self._defer_list_build = bool(defer_lists)
        self._settings = settings
        self.map_categories = self._resolve_map_categories()
        self.map_lists: Dict[str, ListPanel] = {}
        self._map_result_text = "–"
        self._active = True
        self._pending_list_categories: list[str] = []
        self._pending_list_state: dict = {}
        self._list_build_timer: QtCore.QTimer | None = None
        self._styling = MapUIStylingController(self)
        self._sizing = MapUIDynamicSizingController(self)
        self._updates = MapUICombinedUpdateController(self, delay_ms=140)
        self._lists = MapUIListFlowController(
            self,
            default_role_state_factory=_default_map_role_state,
            rebuild_payload_builder=build_map_type_rebuild_payload,
        )
        # Compatibility alias (e.g. background timer pausing logic).
        self._update_timer = self._updates.timer
        self._map_type_editor_ctrl = MapTypeEditorController(
            on_confirm_types=self._apply_map_types,
            apply_editor_widths=self._styling.apply_map_editor_widths,
        )
        self._editor = MapUIEditorFlowController(self, self._map_type_editor_ctrl)
        self._presentation = MapUIPresentationController(self)
        self.container = self._build_ui()

    def _cfg(self, key: str, default=None):
        settings = self._settings
        if settings is not None and hasattr(settings, "resolve"):
            try:
                return settings.resolve(key, default)
            except (AttributeError, TypeError, ValueError):
                pass
        if settings is not None and hasattr(settings, "get"):
            try:
                return settings.get(key, default)
            except (AttributeError, TypeError, ValueError):
                pass
        return default

    def _map_settings(self):
        settings = self._settings
        return getattr(settings, "map", None)

    def _map_int(self, attr: str, key: str, default: int, *, minimum: int = 0) -> int:
        section = self._map_settings()
        if section is not None and hasattr(section, attr):
            try:
                return max(int(minimum), int(getattr(section, attr)))
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
        try:
            return max(int(minimum), int(self._cfg(key, default)))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return max(int(minimum), int(default))

    def _resolve_map_categories(self) -> list[str]:
        map_section = self._map_settings()
        if map_section is not None and hasattr(map_section, "categories"):
            configured = normalize_map_categories(getattr(map_section, "categories", []))
            if configured:
                return configured
        configured = normalize_map_categories(self._cfg("MAP_CATEGORIES", []))
        if configured:
            return configured
        state = self.state_store.get_mode_state("maps") or {}
        fallback = normalize_map_categories(list(state.keys()))
        if fallback:
            return fallback
        return ["Control", "Escort", "Hybrid", "Push", "Flashpoint", "Assault", "Clash"]

    @staticmethod
    def _names_canvas(wheel: ListPanel | None) -> QtWidgets.QListWidget | None:
        return MapUIDynamicSizingController.names_canvas(wheel)

    @staticmethod
    def _row_height_hint(names_canvas: QtWidgets.QListWidget) -> int:
        return MapUIDynamicSizingController.row_height_hint(names_canvas)

    # ----- Build UI -----
    def _build_ui(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # --- Sidebar ---
        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("mapSidebar")
        sb_layout = QtWidgets.QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(
            ui_tokens.PANEL_CONTENT_MARGIN_H,
            ui_tokens.PANEL_CONTENT_MARGIN_V,
            ui_tokens.PANEL_CONTENT_MARGIN_H,
            ui_tokens.PANEL_CONTENT_MARGIN_V,
        )
        sb_layout.setSpacing(ui_tokens.PANEL_LAYOUT_SPACING)
        self.lbl_map_types = QtWidgets.QLabel(i18n.t("map.types"))
        style_helpers.apply_theme_roles(
            theme_util.get_theme(self.theme_key),
            ((self.lbl_map_types, "label.map_types"),),
        )
        sb_layout.addWidget(self.lbl_map_types)
        self.map_type_checks: dict[str, QtWidgets.QCheckBox] = {}
        self._map_type_list_layout = QtWidgets.QVBoxLayout()
        self._map_type_list_layout.setContentsMargins(0, 2, 0, 0)
        self._map_type_list_layout.setSpacing(ui_tokens.SECTION_SPACING)
        sb_layout.addLayout(self._map_type_list_layout)
        sb_layout.addSpacing(ui_tokens.SECTION_SPACING)
        self.btn_edit_map_types = QtWidgets.QPushButton(i18n.t("map.edit_types"))
        self.btn_edit_map_types.setToolTip(i18n.t("map.edit_types_tooltip"))
        self.btn_edit_map_types.clicked.connect(lambda: self._show_map_type_editor(container))
        self.btn_edit_map_types.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.map_sidebar = sidebar
        self._styling.apply_map_control_widths()
        sb_layout.addWidget(self.btn_edit_map_types, 0, QtCore.Qt.AlignLeft)
        sb_layout.addStretch(1)
        sidebar.setSizePolicy(QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Expanding)

        # --- Listen-Gitter rechts ---
        self.map_grid_container = QtWidgets.QWidget()
        self.map_grid_container.setObjectName("mapGridContainer")
        self.map_grid = QtWidgets.QVBoxLayout(self.map_grid_container)
        self.map_grid.setContentsMargins(0, 0, 0, 0)
        self.map_grid.setSpacing(ui_tokens.SECTION_SPACING)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.map_grid_container)
        scroll.setObjectName("mapListScroll")
        scroll.setFocusPolicy(QtCore.Qt.ClickFocus)
        self.map_lists_frame = scroll
        right_wrap = QtWidgets.QFrame()
        right_wrap.setObjectName("mapListsWrapper")
        right_wrap_layout = QtWidgets.QVBoxLayout(right_wrap)
        right_wrap_layout.setContentsMargins(
            ui_tokens.PANEL_CONTENT_MARGIN_H,
            ui_tokens.PANEL_CONTENT_MARGIN_V,
            ui_tokens.PANEL_CONTENT_MARGIN_H,
            ui_tokens.PANEL_CONTENT_MARGIN_V,
        )
        right_wrap_layout.setSpacing(ui_tokens.PANEL_LAYOUT_SPACING)
        right_wrap_layout.addWidget(scroll)
        right_wrap.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.map_lists_wrapper = right_wrap

        # Listen initial erstellen
        map_state = self.state_store.get_mode_state("maps") or {}
        if self._defer_list_build:
            self._pending_list_state = map_state
            QtCore.QTimer.singleShot(0, self._start_list_build)
        else:
            self._build_map_lists(map_state)

        # zentrales Map-Rad
        self.map_main = WheelView("Map-Rad", [], pair_mode=False, allow_pair_toggle=False, title_key="map.wheel_title")
        self.map_main.set_header_controls_visible(False)
        self.map_main.set_subrole_controls_visible(False)
        self.map_main.set_show_names_visible(True)
        self.map_main.btn_include_in_all.setVisible(False)
        self.map_main.btn_local_spin.setText(i18n.t("wheel.spin_map"))
        self.map_main.names_hint.setVisible(False)
        if hasattr(self.map_main, "names_panel"):
            self.map_main.names_panel.setVisible(False)
        else:
            self.map_main.names.setVisible(False)
        self.map_main.result_widget.setVisible(False)
        self.map_main.btn_local_spin.setVisible(False)

        self.map_main.view.setMinimumSize(0, 0)
        self.map_main.view.setMaximumSize(QtCore.QSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX))
        self.map_main.view.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.map_main.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.map_main.btn_local_spin.setFocusPolicy(QtCore.Qt.ClickFocus)

        # Gesamt-Layout
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(ui_tokens.GRID_SPACING)
        row.addWidget(sidebar, 0)
        row.addWidget(self.map_main, 1)
        row.addWidget(right_wrap, 1)
        row.setStretch(0, 1)
        row.setStretch(1, 9)
        row.setStretch(2, 9)
        layout.addLayout(row, 1)
        layout.setStretchFactor(row, 1)
        self._sizing.install_resize_watch(
            container,
            self.map_main,
            right_wrap,
            sidebar,
        )
        QtCore.QTimer.singleShot(0, self._sizing.schedule_cap_heights)
        if not self._defer_list_build:
            QtCore.QTimer.singleShot(0, lambda: self.rebuild_combined(emit_state=False, force_wheel=True))
        return container

    # ----- Map lists -----
    def _clear_map_lists(self) -> None:
        self._lists.clear_map_lists()

    def _map_list_target_names_height(self, wheel: ListPanel) -> int | None:
        return self._sizing.map_list_target_names_height(wheel)

    def _apply_dynamic_map_list_height(self, wheel: ListPanel) -> None:
        self._sizing.apply_dynamic_map_list_height(wheel)

    def _bind_dynamic_map_list_height(self, wheel: ListPanel) -> None:
        self._sizing.bind_dynamic_map_list_height(wheel)

    def _add_map_list(self, cat: str, role_state: dict) -> None:
        self._lists.add_map_list(cat, role_state)

    def _build_map_lists(self, map_state: dict):
        self._lists.build_map_lists(map_state)

    def _start_list_build(self):
        self._lists.start_list_build()

    def _build_list_step(self):
        self._lists.build_list_step()

    def _on_map_type_toggled(self, category: str, checked: bool):
        self._lists.on_map_type_toggled(category, checked)

    def _on_list_include_toggled(self, category: str, checked: bool):
        self._lists.on_list_include_toggled(category, checked)

    # ----- Map-Type-Editor -----
    def _show_map_type_editor(self, parent_widget: QtWidgets.QWidget):
        self._editor.show_editor(parent_widget)

    def _add_map_type_row(self):
        self._editor.add_row()

    def _del_map_type_row(self):
        self._editor.delete_row()

    def _confirm_map_types(self):
        self._editor.confirm()

    def _start_map_type_edit(self, item: QtWidgets.QListWidgetItem):
        self._editor.start_edit(item)

    def _focus_editor_end(self):
        self._editor.focus_editor_end()

    def _apply_map_types(self, new_types: list[str]):
        self._lists.apply_map_types(new_types)

    # ----- State / Language / Theme -----
    def set_language(self, lang: str):
        self._presentation.set_language(lang)

    def apply_theme(self, theme: theme_util.Theme):
        self._presentation.apply_theme(theme)

    def load_state(self):
        self._lists.load_state()

    def capture_state(self):
        self._lists.capture_state()

    # ----- Data helpers -----
    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self._updates.set_active(self._active)

    def shutdown(self) -> None:
        """Stop internal timers and prevent further wheel updates."""
        self.set_active(False)
        self._updates.shutdown()
        self._sizing.shutdown()
        if self._list_build_timer is not None and self._list_build_timer.isActive():
            self._list_build_timer.stop()
        self._pending_list_categories = []

    def resource_snapshot(self) -> dict:
        updates = self._updates.resource_snapshot()
        list_build_timer_active = False
        if self._list_build_timer is not None:
            try:
                list_build_timer_active = bool(self._list_build_timer.isActive())
            except (AttributeError, RuntimeError, TypeError):
                pass
        return {
            "active": bool(self._active),
            "map_lists": len(self.map_lists),
            "pending_rebuild": bool(updates.get("pending_rebuild", False)),
            "pending_state_emit": bool(updates.get("pending_state_emit", False)),
            "pending_wheel_refresh": bool(updates.get("pending_wheel_refresh", False)),
            "pending_list_categories": len(self._pending_list_categories),
            "update_timer_active": bool(updates.get("update_timer_active", False)),
            "list_build_timer_active": list_build_timer_active,
        }

    def _schedule_update(self):
        self._updates.schedule_update()

    def _flush_updates(self):
        self._updates.flush_updates()

    def _apply_combined_update(self, emit_state: bool, force_wheel: bool):
        self._updates.apply_combined_update(emit_state=emit_state, force_wheel=force_wheel)

    def rebuild_combined(self, emit_state: bool = True, force_wheel: bool = False):
        self._updates.rebuild_combined(emit_state=emit_state, force_wheel=force_wheel)

    def combined_names(self) -> list[str]:
        return self._updates.combined_names()

    def names_for_category(self, category: str) -> list[str]:
        return self._updates.names_for_category(category)

    # ----- Sizing -----
    def _cap_heights(self):
        self._sizing.cap_heights()

    def _schedule_cap_heights(self) -> None:
        self._sizing.schedule_cap_heights()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        self._sizing.handle_event(obj, event)
        return super().eventFilter(obj, event)

    def set_interactive_enabled(self, en: bool):
        for wheel in self.map_lists.values():
            wheel.set_interactive_enabled(en)
        if hasattr(self, "map_main"):
            self.map_main.set_interactive_enabled(en)
