from __future__ import annotations

from PySide6 import QtWidgets

from utils import theme as theme_util, ui_helpers
from view import style_helpers, ui_tokens

_MAP_TYPE_LIST_STYLE_CACHE: dict[str, str] = {}
_MAP_NAMES_HINT_STYLE_CACHE: dict[str, str] = {}
_MAP_SIDEBAR_STYLE_CACHE: dict[str, str] = {}
_MAP_RIGHT_CANVAS_STYLE_CACHE: dict[str, str] = {}
_MAP_LIST_SCROLL_STYLE_CACHE: dict[str, str] = {}
_MAP_GRID_CONTAINER_STYLE_CACHE: dict[str, str] = {}


def _map_type_list_style(theme: theme_util.Theme) -> str:
    cached = _MAP_TYPE_LIST_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QListWidget {"
        f" background:{theme.base}; color:{theme.text};"
        f" border:1px solid {theme.border}; border-radius:8px; padding:2px;"
        "}"
        f"QListWidget::item {{ color:{theme.text}; padding:4px 6px; border-radius:6px; }}"
        f"QListWidget::item:selected {{ background:{theme.primary}; color:{theme.button_text}; }}"
        f"QListWidget::item:hover {{ background:{theme.alt_base}; color:{theme.text}; }}"
        "QListWidget QLineEdit {"
        f" background:{theme.base}; color:{theme.text};"
        f" border:1px solid {theme.border}; border-radius:4px; padding:1px 4px;"
        "}"
    )
    _MAP_TYPE_LIST_STYLE_CACHE[theme.key] = cached
    return cached


def _map_names_hint_style(theme: theme_util.Theme) -> str:
    cached = _MAP_NAMES_HINT_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        f"color:{theme.muted_text};"
        " font-size:12px; padding:2px;"
        f" background:{theme.card_bg}; border:none;"
    )
    _MAP_NAMES_HINT_STYLE_CACHE[theme.key] = cached
    return cached


def _map_sidebar_style(theme: theme_util.Theme) -> str:
    cached = _MAP_SIDEBAR_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QFrame#mapSidebar {"
        f" background:{theme.card_bg}; color:{theme.text};"
        f" border:1px solid {theme.card_border}; border-radius:16px;"
        "}"
    )
    _MAP_SIDEBAR_STYLE_CACHE[theme.key] = cached
    return cached


def _map_right_canvas_style(theme: theme_util.Theme) -> str:
    cached = _MAP_RIGHT_CANVAS_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QFrame#mapListsWrapper {"
        f" background:{theme.card_bg}; color:{theme.text};"
        f" border:1px solid {theme.card_border}; border-radius:16px;"
        "}"
    )
    _MAP_RIGHT_CANVAS_STYLE_CACHE[theme.key] = cached
    return cached


def _map_list_scroll_style(theme: theme_util.Theme) -> str:
    cached = _MAP_LIST_SCROLL_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QScrollArea#mapListScroll {"
        " background:transparent; border:none;"
        "}"
        "QScrollArea#mapListScroll > QWidget#qt_scrollarea_viewport {"
        " background:transparent; border:none;"
        "}"
    )
    _MAP_LIST_SCROLL_STYLE_CACHE[theme.key] = cached
    return cached


def _map_grid_container_style(theme: theme_util.Theme) -> str:
    cached = _MAP_GRID_CONTAINER_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QWidget#mapGridContainer {"
        " background:transparent; border:none;"
        "}"
    )
    _MAP_GRID_CONTAINER_STYLE_CACHE[theme.key] = cached
    return cached


class MapUIStylingController:
    """Applies width constraints and themed styles for MapUI."""

    def __init__(self, owner) -> None:
        self._owner = owner
        self._theme_apply_signature: tuple[str, int, bool] | None = None

    def reset_theme_signature(self) -> None:
        self._theme_apply_signature = None

    def _editor_widgets(
        self,
    ) -> tuple[
        QtWidgets.QFrame | None,
        QtWidgets.QLabel | None,
        QtWidgets.QListWidget | None,
        QtWidgets.QPushButton | None,
        QtWidgets.QPushButton | None,
        QtWidgets.QPushButton | None,
        QtWidgets.QPushButton | None,
    ]:
        editor_ctrl = self._owner._map_type_editor_ctrl
        if editor_ctrl is None:
            return (None, None, None, None, None, None, None)
        return editor_ctrl.widgets()

    def apply_map_control_widths(self) -> None:
        owner = self._owner
        label = getattr(owner, "lbl_map_types", None)
        if label is not None:
            ui_helpers.set_fixed_width_from_translations([label], ["map.types"], padding=30)
        btn_edit = getattr(owner, "btn_edit_map_types", None)
        if btn_edit is not None:
            ui_helpers.set_fixed_width_from_translations([btn_edit], ["map.edit_types"], padding=48)
        self.apply_sidebar_width_constraints()

    def apply_sidebar_width_constraints(self) -> None:
        owner = self._owner
        sidebar = getattr(owner, "map_sidebar", None)
        if sidebar is None:
            return
        content_width = 0
        widgets = [
            getattr(owner, "lbl_map_types", None),
            getattr(owner, "btn_edit_map_types", None),
        ]
        for widget in widgets:
            if widget is None:
                continue
            content_width = max(
                content_width,
                int(widget.minimumSizeHint().width()),
                int(widget.sizeHint().width()),
                int(widget.width()),
            )
        checks = list(owner.map_type_checks.values())
        if checks:
            for cb in checks:
                if not isinstance(cb, QtWidgets.QCheckBox):
                    continue
                content_width = max(
                    content_width,
                    int(cb.minimumSizeHint().width()),
                    int(cb.sizeHint().width()),
                    int(cb.width()),
                )
        else:
            fm = sidebar.fontMetrics()
            for cat in list(owner.map_categories or []):
                label_w = int(fm.horizontalAdvance(str(cat)))
                content_width = max(content_width, label_w + 34)
        margins = int(ui_tokens.PANEL_CONTENT_MARGIN_H) * 2
        frame = max(0, int(sidebar.frameWidth())) * 2
        target = max(236, min(360, int(content_width + margins + frame + 8)))
        if int(sidebar.minimumWidth()) != target:
            sidebar.setMinimumWidth(target)
        if int(sidebar.maximumWidth()) != target:
            sidebar.setMaximumWidth(target)

    def apply_map_editor_widths(self) -> None:
        _frame, title, _list_widget, btn_add, btn_del, btn_ok, btn_cancel = self._editor_widgets()
        if title is not None:
            ui_helpers.set_fixed_width_from_translations([title], ["map.editor.title"], padding=28)
        if btn_add is not None and btn_del is not None:
            ui_helpers.set_fixed_width_from_translations(
                [btn_add, btn_del],
                ["map.editor.add", "map.editor.delete"],
                padding=40,
            )
        if btn_ok is not None and btn_cancel is not None:
            ui_helpers.set_fixed_width_from_translations(
                [btn_ok, btn_cancel],
                ["map.editor.apply", "map.editor.cancel"],
                padding=44,
            )

    def apply_theme_to_controls(self, theme: theme_util.Theme) -> None:
        owner = self._owner
        map_sidebar = getattr(owner, "map_sidebar", None)
        map_lists_wrapper = getattr(owner, "map_lists_wrapper", None)
        map_lists_frame = getattr(owner, "map_lists_frame", None)
        map_grid_container = getattr(owner, "map_grid_container", None)
        style_helpers.apply_theme_roles(
            theme,
            (
                (owner.lbl_map_types, "label.map_types"),
                (owner.btn_edit_map_types, "button.primary"),
            ),
        )
        if map_sidebar is not None:
            style_helpers.set_stylesheet_if_needed(
                map_sidebar,
                f"map_sidebar:{theme.key}",
                _map_sidebar_style(theme),
            )
        if map_lists_wrapper is not None:
            style_helpers.set_stylesheet_if_needed(
                map_lists_wrapper,
                f"map_lists_wrapper:{theme.key}",
                _map_right_canvas_style(theme),
            )
        if map_lists_frame is not None:
            style_helpers.set_stylesheet_if_needed(
                map_lists_frame,
                f"map_list_scroll:{theme.key}",
                _map_list_scroll_style(theme),
            )
        if map_grid_container is not None:
            style_helpers.set_stylesheet_if_needed(
                map_grid_container,
                f"map_grid_container:{theme.key}",
                _map_grid_container_style(theme),
            )
        editor_frame, editor_title, editor_list, btn_add, btn_del, btn_ok, btn_cancel = self._editor_widgets()
        if editor_frame is not None:
            style_helpers.apply_theme_roles(
                theme,
                (
                    (editor_frame, "frame.editor_dialog"),
                    (editor_title, "label.editor_title"),
                ),
            )
            style_helpers.set_stylesheet_if_needed(
                editor_list,
                f"map_editor_list:{theme.key}",
                _map_type_list_style(theme),
            )
            style_helpers.apply_theme_roles(
                theme,
                (
                    (btn_add, "button.primary"),
                    (btn_del, "button.danger"),
                    (btn_ok, "button.success"),
                    (btn_cancel, "button.primary"),
                ),
            )

    def apply_theme(self, theme: theme_util.Theme) -> None:
        owner = self._owner
        editor_frame, _editor_title, _editor_list, _btn_add, _btn_del, _btn_ok, _btn_cancel = self._editor_widgets()
        signature = (theme.key, len(owner.map_lists), bool(editor_frame is not None))
        if self._theme_apply_signature == signature:
            return
        owner.theme_key = theme.key
        owner.map_main.apply_theme(theme)
        for wheel in owner.map_lists.values():
            wheel.apply_theme(theme)
            style_helpers.set_stylesheet_if_needed(
                wheel.names_hint,
                f"map_names_hint:{theme.key}",
                _map_names_hint_style(theme),
            )
        self.apply_theme_to_controls(theme)
        self._theme_apply_signature = signature
