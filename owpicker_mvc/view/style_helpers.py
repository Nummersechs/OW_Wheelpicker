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


def style_profile_combo(combo: QtWidgets.QComboBox, theme: theme_util.Theme) -> None:
    if not combo:
        return
    combo.setStyleSheet(
        "QComboBox {"
        f" background:{theme.base}; color:{theme.text};"
        f" border:1px solid {theme.border}; border-radius:10px;"
        " font-size:13px; font-weight:600;"
        " padding:6px 38px 6px 10px;"
        "}"
        f"QComboBox:hover {{ border:1px solid {theme.primary}; }}"
        f"QComboBox:focus {{ border:1px solid {theme.primary_hover}; }}"
        "QComboBox::drop-down {"
        " subcontrol-origin: padding;"
        " subcontrol-position: top right;"
        f" width:30px; border-left:1px solid {theme.primary}; background:{theme.frame_bg};"
        " border-top-right-radius:10px; border-bottom-right-radius:10px;"
        "}"
        f"QComboBox::drop-down:hover {{ background:{theme.tool_hover}; }}"
        f"QComboBox::drop-down:pressed {{ background:{theme.tool_pressed}; }}"
        "QComboBox::down-arrow {"
        " image:none;"
        " width:0px; height:0px;"
        "}"
        f"QComboBox:disabled {{ background:{theme.disabled_bg}; color:{theme.disabled_text}; }}"
        "QComboBox QLineEdit {"
        " border:0; background:transparent; padding:0;"
        f" color:{theme.text}; font-size:13px; font-weight:600;"
        " selection-background-color: rgba(64,128,255,0.35);"
        "}"
        "QComboBox QAbstractItemView {"
        f" background:{theme.base}; color:{theme.text};"
        f" border:1px solid {theme.border};"
        " selection-background-color: rgba(64,128,255,0.28);"
        f" selection-color:{theme.text};"
        " outline:0; padding:2px;"
        "}"
    )
