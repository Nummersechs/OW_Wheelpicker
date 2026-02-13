from __future__ import annotations

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
        f"QPushButton:hover {{ background:{theme.primary_hover}; }}"
        f"QPushButton:pressed {{ background:{theme.primary_pressed}; }}"
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
        f"QPushButton:checked {{ background:{theme.checked}; border:2px solid {theme.checked_border}; }}"
        f"QPushButton:checked:hover {{ background:{theme.checked_hover}; }}"
        f"QPushButton:checked:pressed {{ background:{theme.checked_pressed}; }}"
        f"QPushButton:hover {{ background:{theme.primary_hover}; }}"
        f"QPushButton:pressed {{ background:{theme.primary_pressed}; }}"
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
        "QPushButton:hover { background:#d32f2f; }"
        "QPushButton:pressed { background:#b71c1c; }"
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
        "QPushButton:hover { background:#388e3c; }"
        "QPushButton:pressed { background:#1b5e20; }"
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
        "QPushButton:hover { background:#f57c00; }"
        "QPushButton:pressed { background:#e65100; }"
        f"QPushButton:disabled {{ background:{theme.disabled_bg}; color:{theme.disabled_text}; border:1px solid {theme.border}; }}"
    )
    _WARNING_BUTTON_STYLE_CACHE[theme.key] = cached
    return cached


def _names_list_style(theme: theme_util.Theme) -> str:
    cached = _NAMES_LIST_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QListWidget {"
        f" background:{theme.base}; color:{theme.text};"
        f" border:1px solid {theme.border}; border-radius:6px; "
        "}"
        f"QListWidget::item {{ color:{theme.text}; }}"
        f"QListWidget::item:selected {{ background:{theme.alt_base}; color:{theme.text}; }}"
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


def style_primary_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    if not btn:
        return
    set_stylesheet_if_needed(btn, f"primary:{theme.key}", _primary_button_style(theme))


def style_include_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    if not btn:
        return
    set_stylesheet_if_needed(btn, f"include:{theme.key}", _include_button_style(theme))


def style_danger_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    if not btn:
        return
    set_stylesheet_if_needed(btn, f"danger:{theme.key}", _danger_button_style(theme))


def style_success_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    if not btn:
        return
    set_stylesheet_if_needed(btn, f"success:{theme.key}", _success_button_style(theme))


def style_warning_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    if not btn:
        return
    set_stylesheet_if_needed(btn, f"warning:{theme.key}", _warning_button_style(theme))


def style_names_list(list_widget: QtWidgets.QListWidget, theme: theme_util.Theme) -> None:
    if not list_widget:
        return
    set_stylesheet_if_needed(list_widget, f"names_list:{theme.key}", _names_list_style(theme))


def style_mode_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    if not btn:
        return
    set_stylesheet_if_needed(btn, f"mode:{theme.key}", _mode_button_style(theme))
