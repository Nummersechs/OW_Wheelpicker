from __future__ import annotations

from PySide6 import QtWidgets
from utils import theme as theme_util


def style_primary_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    if not btn:
        return
    btn.setStyleSheet(
        "QPushButton {"
        f" color:{theme.button_text}; background:{theme.primary};"
        " border-radius:12px; font-weight:600; padding:8px 18px;"
        "}"
        f"QPushButton:hover {{ background:{theme.primary_hover}; }}"
        f"QPushButton:pressed {{ background:{theme.primary_pressed}; }}"
        f"QPushButton:disabled {{ background:{theme.disabled_bg}; color:{theme.disabled_text}; border:1px solid {theme.border}; }}"
    )


def style_include_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    if not btn:
        return
    btn.setStyleSheet(
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


def style_danger_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    if not btn:
        return
    btn.setStyleSheet(
        "QPushButton {"
        " color:white; background:#c62828;"
        " border-radius:12px; font-weight:600; padding:8px 18px;"
        "}"
        "QPushButton:hover { background:#d32f2f; }"
        "QPushButton:pressed { background:#b71c1c; }"
        f"QPushButton:disabled {{ background:{theme.disabled_bg}; color:{theme.disabled_text}; border:1px solid {theme.border}; }}"
    )


def style_success_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    if not btn:
        return
    btn.setStyleSheet(
        "QPushButton {"
        " color:white; background:#2e7d32;"
        " border-radius:12px; font-weight:600; padding:8px 18px;"
        "}"
        "QPushButton:hover { background:#388e3c; }"
        "QPushButton:pressed { background:#1b5e20; }"
        f"QPushButton:disabled {{ background:{theme.disabled_bg}; color:{theme.disabled_text}; border:1px solid {theme.border}; }}"
    )


def style_warning_button(btn: QtWidgets.QPushButton, theme: theme_util.Theme) -> None:
    if not btn:
        return
    btn.setStyleSheet(
        "QPushButton {"
        " color:white; background:#ef6c00;"
        " border-radius:12px; font-weight:600; padding:8px 18px;"
        "}"
        "QPushButton:hover { background:#f57c00; }"
        "QPushButton:pressed { background:#e65100; }"
        f"QPushButton:disabled {{ background:{theme.disabled_bg}; color:{theme.disabled_text}; border:1px solid {theme.border}; }}"
    )


def style_names_list(list_widget: QtWidgets.QListWidget, theme: theme_util.Theme) -> None:
    if not list_widget:
        return
    list_widget.setStyleSheet(
        "QListWidget {"
        f" background:{theme.base}; color:{theme.text};"
        f" border:1px solid {theme.border}; border-radius:6px; "
        "}"
        f"QListWidget::item {{ color:{theme.text}; }}"
        f"QListWidget::item:selected {{ background:{theme.alt_base}; color:{theme.text}; }}"
    )
