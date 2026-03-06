from __future__ import annotations

from typing import Iterable

from PySide6 import QtWidgets
from utils import theme as theme_util

_STYLE_KEY_PROP = "_ow_style_cache_key"
_PRIMARY_BUTTON_STYLE_CACHE: dict[str, str] = {}
_INCLUDE_BUTTON_STYLE_CACHE: dict[str, str] = {}
_DANGER_BUTTON_STYLE_CACHE: dict[str, str] = {}
_SUCCESS_BUTTON_STYLE_CACHE: dict[str, str] = {}
_WARNING_BUTTON_STYLE_CACHE: dict[str, str] = {}
_NAMES_LIST_STYLE_CACHE: dict[str, str] = {}
_MODE_BUTTON_STYLE_CACHE: dict[str, str] = {}
_HORIZONTAL_SLIDER_STYLE_CACHE: dict[str, str] = {}
_LABEL_STYLE_CACHE: dict[str, str] = {}
_FRAME_STYLE_CACHE: dict[str, str] = {}


def set_stylesheet_if_needed(widget: QtWidgets.QWidget, style_key: str, style: str) -> None:
    if widget is None:
        return
    if widget.property(_STYLE_KEY_PROP) == style_key:
        return
    widget.setStyleSheet(style)
    widget.setProperty(_STYLE_KEY_PROP, style_key)


def _primary_button_style(theme: theme_util.Theme) -> str:
    cached = _PRIMARY_BUTTON_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QPushButton {"
        f" color:{theme.button_text}; background:{theme.primary};"
        " border-radius:12px; font-weight:600; padding:8px 18px;"
        "}"
        f"QPushButton:hover {{ background:{theme.primary_hover}; color:{theme.button_text}; }}"
        f"QPushButton:pressed {{ background:{theme.primary_pressed}; color:{theme.button_text}; }}"
        f"QPushButton:disabled {{ background:{theme.disabled_bg}; color:{theme.disabled_text}; border:1px solid {theme.border}; }}"
    )
    _PRIMARY_BUTTON_STYLE_CACHE[theme.key] = cached
    return cached


def _include_button_style(theme: theme_util.Theme) -> str:
    cached = _INCLUDE_BUTTON_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QPushButton {"
        f" color:{theme.button_text}; background:{theme.primary};"
        " border-radius:12px; font-weight:600; padding:8px 18px;"
        "}"
        f"QPushButton:checked {{ background:{theme.checked}; color:{theme.button_text}; border:2px solid {theme.checked_border}; }}"
        f"QPushButton:checked:hover {{ background:{theme.checked_hover}; color:{theme.button_text}; }}"
        f"QPushButton:checked:pressed {{ background:{theme.checked_pressed}; color:{theme.button_text}; }}"
        f"QPushButton:hover {{ background:{theme.primary_hover}; color:{theme.button_text}; }}"
        f"QPushButton:pressed {{ background:{theme.primary_pressed}; color:{theme.button_text}; }}"
        f"QPushButton:disabled {{ background:{theme.disabled_bg}; color:{theme.disabled_text}; border:1px solid {theme.border}; }}"
    )
    _INCLUDE_BUTTON_STYLE_CACHE[theme.key] = cached
    return cached


def _danger_button_style(theme: theme_util.Theme) -> str:
    cached = _DANGER_BUTTON_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QPushButton {"
        " color:white; background:#c62828;"
        " border-radius:12px; font-weight:600; padding:8px 18px;"
        "}"
        "QPushButton:hover { background:#d32f2f; color:white; }"
        "QPushButton:pressed { background:#b71c1c; color:white; }"
        f"QPushButton:disabled {{ background:{theme.disabled_bg}; color:{theme.disabled_text}; border:1px solid {theme.border}; }}"
    )
    _DANGER_BUTTON_STYLE_CACHE[theme.key] = cached
    return cached


def _success_button_style(theme: theme_util.Theme) -> str:
    cached = _SUCCESS_BUTTON_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QPushButton {"
        " color:white; background:#2e7d32;"
        " border-radius:12px; font-weight:600; padding:8px 18px;"
        "}"
        "QPushButton:hover { background:#388e3c; color:white; }"
        "QPushButton:pressed { background:#1b5e20; color:white; }"
        f"QPushButton:disabled {{ background:{theme.disabled_bg}; color:{theme.disabled_text}; border:1px solid {theme.border}; }}"
    )
    _SUCCESS_BUTTON_STYLE_CACHE[theme.key] = cached
    return cached


def _warning_button_style(theme: theme_util.Theme) -> str:
    cached = _WARNING_BUTTON_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QPushButton {"
        " color:white; background:#ef6c00;"
        " border-radius:12px; font-weight:600; padding:8px 18px;"
        "}"
        "QPushButton:hover { background:#f57c00; color:white; }"
        "QPushButton:pressed { background:#e65100; color:white; }"
        f"QPushButton:disabled {{ background:{theme.disabled_bg}; color:{theme.disabled_text}; border:1px solid {theme.border}; }}"
    )
    _WARNING_BUTTON_STYLE_CACHE[theme.key] = cached
    return cached


def _names_list_style(theme: theme_util.Theme) -> str:
    cached = _NAMES_LIST_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    name_edit_border = theme.frame_border if theme.key == "dark" else theme.border
    name_edit_focus_border = theme.border if theme.key == "dark" else theme.primary_hover
    cached = (
        "QListWidget {"
        f" background:{theme.base}; color:{theme.text};"
        f" border:1px solid {theme.border}; border-radius:6px; padding:0px; "
        "}"
        f"QListWidget::item {{ color:{theme.text}; margin:0px; padding:0px; border:0px; }}"
        f"QListWidget::item:selected {{ background:{theme.alt_base}; color:{theme.text}; }}"
        "QListWidget QLineEdit {"
        f" background:{theme.base}; color:{theme.text};"
        f" border:1px solid {name_edit_border}; border-radius:4px; padding:0 4px;"
        f" selection-background-color:{theme.primary}; selection-color:{theme.button_text};"
        "}"
        "QListWidget QLineEdit:focus {"
        f" border:1px solid {name_edit_focus_border};"
        "}"
    )
    _NAMES_LIST_STYLE_CACHE[theme.key] = cached
    return cached


def _mode_button_style(theme: theme_util.Theme) -> str:
    cached = _MODE_BUTTON_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QPushButton {"
        f" color:{theme.text}; background:{theme.alt_base}; border:1px solid {theme.border};"
        " border-radius:12px; font-weight:600; padding:6px 14px; font-size:13px; min-width:120px;"
        "}"
        f"QPushButton:hover {{ background:{theme.frame_bg}; color:{theme.text}; }}"
        f"QPushButton:pressed {{ background:{theme.slider_groove}; color:{theme.text}; }}"
        f"QPushButton:checked {{ background:{theme.primary}; color:{theme.button_text}; border:2px solid {theme.primary_hover}; padding:8px 18px; font-size:14px; }}"
        f"QPushButton:checked:hover {{ background:{theme.primary_hover}; color:{theme.button_text}; }}"
        f"QPushButton:checked:pressed {{ background:{theme.primary_pressed}; color:{theme.button_text}; }}"
        f"QPushButton:disabled {{ background:{theme.disabled_bg}; color:{theme.disabled_text}; border:1px solid {theme.border}; }}"
    )
    _MODE_BUTTON_STYLE_CACHE[theme.key] = cached
    return cached


def _horizontal_slider_style(theme: theme_util.Theme) -> str:
    cached = _HORIZONTAL_SLIDER_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    if theme.key == "light":
        # Only darken the rail (groove) for better visibility in light mode.
        groove_bg = "#c4cad5"
        groove_border = "#9ea6b4"
    else:
        groove_bg = theme.slider_groove
        groove_border = theme.border
    cached = (
        "QSlider::groove:horizontal {"
        f" height:8px; border:1px solid {groove_border}; border-radius:4px; background:{groove_bg};"
        "}"
        "QSlider::handle:horizontal {"
        f" width:14px; margin:-5px 0; border:1px solid {theme.primary_hover}; border-radius:7px; background:{theme.slider_handle};"
        "}"
        "QSlider::handle:horizontal:hover {"
        f" background:{theme.primary_hover};"
        "}"
        "QSlider::handle:horizontal:pressed {"
        f" background:{theme.primary_pressed};"
        "}"
    )
    _HORIZONTAL_SLIDER_STYLE_CACHE[theme.key] = cached
    return cached


def _label_style(theme: theme_util.Theme, variant: str) -> str:
    cache_key = f"{variant}:{theme.key}"
    cached = _LABEL_STYLE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if variant == "window_title":
        cached = f"font-size:22px; font-weight:700; color:{theme.text}; margin:8px 0 2px 0;"
    elif variant == "section":
        cached = f"color:{theme.text}; font-size:13px; font-weight:600;"
    elif variant == "section_muted":
        cached = f"color:{theme.muted_text}; font-size:13px; font-weight:600;"
    elif variant == "summary":
        cached = f"font-size:15px; color:{theme.muted_text}; margin:10px 0 6px 0;"
    elif variant == "panel_title":
        cached = f"font-size:18px; font-weight:800; letter-spacing:0.3px; color:{theme.text};"
    elif variant == "hint":
        cached = f"color:{theme.muted_text}; font-size:12px; padding:2px;"
    elif variant == "map_types":
        cached = f"font-weight:600; color:{theme.text};"
    elif variant == "editor_title":
        cached = f"font-weight:700; font-size:14px; color:{theme.text};"
    else:
        raise ValueError(f"unknown label style variant: {variant}")
    _LABEL_STYLE_CACHE[cache_key] = cached
    return cached


def _frame_style(theme: theme_util.Theme, variant: str) -> str:
    cache_key = f"{variant}:{theme.key}"
    cached = _FRAME_STYLE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if variant == "card":
        cached = (
            "#card { "
            f"background: {theme.card_bg}; "
            f"border:1px solid {theme.card_border}; border-radius:16px; }}"
        )
    elif variant == "editor_dialog":
        cached = (
            "QFrame { "
            f"background:{theme.card_bg}; "
            f"border:2px solid {theme.card_border}; border-radius:10px; }}"
        )
    else:
        raise ValueError(f"unknown frame style variant: {variant}")
    _FRAME_STYLE_CACHE[cache_key] = cached
    return cached


def style_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme, variant: str = "primary") -> None:
    if not btn:
        return
    if variant == "primary":
        style = _primary_button_style(theme)
    elif variant == "include":
        style = _include_button_style(theme)
    elif variant == "danger":
        style = _danger_button_style(theme)
    elif variant == "success":
        style = _success_button_style(theme)
    elif variant == "warning":
        style = _warning_button_style(theme)
    elif variant == "mode":
        style = _mode_button_style(theme)
    else:
        raise ValueError(f"unknown button style variant: {variant}")
    set_stylesheet_if_needed(btn, f"button:{variant}:{theme.key}", style)


def style_primary_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    style_button(btn, theme, "primary")


def style_danger_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    style_button(btn, theme, "danger")


def style_success_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    style_button(btn, theme, "success")


def style_warning_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    style_button(btn, theme, "warning")


def style_names_list(list_widget: QtWidgets.QListWidget, theme: theme_util.Theme) -> None:
    if not list_widget:
        return
    set_stylesheet_if_needed(list_widget, f"names_list:{theme.key}", _names_list_style(theme))


def style_horizontal_slider(slider: QtWidgets.QSlider, theme: theme_util.Theme) -> None:
    if not slider:
        return
    set_stylesheet_if_needed(slider, f"slider_h:{theme.key}", _horizontal_slider_style(theme))


def style_tool_button(btn: QtWidgets.QToolButton, theme: theme_util.Theme) -> None:
    if not btn:
        return
    set_stylesheet_if_needed(btn, f"tool:{theme.key}", theme_util.tool_button_stylesheet(theme))


def style_label(label: QtWidgets.QWidget, theme: theme_util.Theme, variant: str) -> None:
    if not label:
        return
    set_stylesheet_if_needed(label, f"label:{variant}:{theme.key}", _label_style(theme, variant))


def style_frame(frame: QtWidgets.QWidget, theme: theme_util.Theme, variant: str) -> None:
    if not frame:
        return
    set_stylesheet_if_needed(frame, f"frame:{variant}:{theme.key}", _frame_style(theme, variant))


def apply_theme_role(widget: QtWidgets.QWidget, theme: theme_util.Theme, role: str) -> None:
    if not widget:
        return
    if role.startswith("button."):
        style_button(widget, theme, role.split(".", 1)[1])
        return
    if role == "slider.horizontal":
        style_horizontal_slider(widget, theme)
        return
    if role == "list.names":
        style_names_list(widget, theme)
        return
    if role == "tool.button":
        style_tool_button(widget, theme)
        return
    if role.startswith("label."):
        style_label(widget, theme, role.split(".", 1)[1])
        return
    if role.startswith("frame."):
        style_frame(widget, theme, role.split(".", 1)[1])
        return
    raise ValueError(f"unknown theme role: {role}")


def apply_theme_roles(theme: theme_util.Theme, bindings: Iterable[tuple[QtWidgets.QWidget, str]]) -> None:
    for widget, role in bindings:
        apply_theme_role(widget, theme, role)
