from __future__ import annotations

from dataclasses import dataclass
from PySide6 import QtGui, QtWidgets


@dataclass(frozen=True)
class Theme:
    key: str
    window: str
    base: str
    alt_base: str
    text: str
    muted_text: str
    primary: str
    primary_hover: str
    primary_pressed: str
    checked: str
    checked_hover: str
    checked_pressed: str
    checked_border: str
    button_text: str
    disabled_bg: str
    disabled_text: str
    border: str
    card_bg: str
    card_border: str
    frame_bg: str
    frame_border: str
    tooltip_bg: str
    tooltip_text: str
    slider_groove: str
    slider_handle: str
    tool_hover: str
    tool_pressed: str


THEMES: dict[str, Theme] = {
    "light": Theme(
        key="light",
        window="#f5f6f8",
        base="#ffffff",
        alt_base="#f0f0f0",
        text="#202124",
        muted_text="#555555",
        primary="#0b57d0",
        primary_hover="#0a4fc0",
        primary_pressed="#0946ab",
        checked="#188038",
        checked_hover="#176b34",
        checked_pressed="#14592b",
        checked_border="#0f5f26",
        button_text="#ffffff",
        disabled_bg="#c7c7c7",
        disabled_text="#777777",
        border="#e6e6e6",
        card_bg="rgba(255,255,255,0.80)",
        card_border="#e6e6e6",
        frame_bg="rgba(245,245,245,0.90)",
        frame_border="#dddddd",
        tooltip_bg="#ffffff",
        tooltip_text="#202124",
        slider_groove="#e0e0e0",
        slider_handle="#0078d4",
        tool_hover="rgba(0,0,0,0.06)",
        tool_pressed="rgba(0,0,0,0.12)",
    ),
    "dark": Theme(
        key="dark",
        window="#111317",
        base="#1a1d22",
        alt_base="#22262d",
        text="#e7e9ee",
        muted_text="#c0c5d0",
        primary="#4d7cff",
        primary_hover="#3f6de0",
        primary_pressed="#365fbe",
        checked="#2fa36f",
        checked_hover="#298c60",
        checked_pressed="#237654",
        checked_border="#1c5b40",
        button_text="#ffffff",
        disabled_bg="#3a3f49",
        disabled_text="#7f8696",
        border="#2f343d",
        card_bg="rgba(30,33,40,0.92)",
        card_border="#2f343d",
        frame_bg="rgba(28,31,38,0.92)",
        frame_border="#2a2f37",
        tooltip_bg="#2b3038",
        tooltip_text="#e7e9ee",
        slider_groove="#2d323c",
        slider_handle="#6ea1ff",
        tool_hover="rgba(255,255,255,0.06)",
        tool_pressed="rgba(255,255,255,0.10)",
    ),
}


def get_theme(key: str) -> Theme:
    """Return a valid theme (defaults to light if unknown)."""
    return THEMES.get(key, THEMES["light"])


def build_palette(theme: Theme) -> QtGui.QPalette:
    pal = QtGui.QPalette()
    pal.setColor(QtGui.QPalette.Window, QtGui.QColor(theme.window))
    pal.setColor(QtGui.QPalette.Base, QtGui.QColor(theme.base))
    pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(theme.alt_base))
    pal.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(theme.tooltip_bg))
    pal.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(theme.tooltip_text))
    pal.setColor(QtGui.QPalette.Text, QtGui.QColor(theme.text))
    pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(theme.text))
    pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(theme.button_text))
    pal.setColor(QtGui.QPalette.Button, QtGui.QColor(theme.base))
    pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(theme.primary))
    pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(theme.button_text))
    return pal


def global_stylesheet(theme: Theme) -> str:
    """Shared stylesheet for the application based on the active theme."""
    return f"""
        QLabel {{ color:{theme.text}; }}
        QPlainTextEdit {{
            background:{theme.base}; color:{theme.text};
            border:1px solid {theme.border}; border-radius:10px; padding:6px;
            font-size:13px;
        }}
        QSlider::groove:horizontal {{
            height:6px; background:{theme.slider_groove}; border-radius:3px;
        }}
        QSlider::handle:horizontal {{
            width:14px; background:{theme.slider_handle}; border-radius:7px; margin:-5px 0;
        }}
        QGraphicsView {{
            background:transparent;
        }}
        /* Scrollbars besser sichtbar in beiden Themes */
        QScrollBar:vertical {{
            background:{theme.alt_base};
            width:12px;
            margin:2px;
            border-radius:6px;
        }}
        QScrollBar::handle:vertical {{
            background:{theme.slider_handle};
            min-height:24px;
            border-radius:6px;
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {{
            height:0px;
            background:transparent;
        }}
        QScrollBar::sub-page:vertical,
        QScrollBar::add-page:vertical {{
            background:{theme.slider_groove};
            border-radius:6px;
        }}
        QScrollBar:horizontal {{
            background:{theme.alt_base};
            height:12px;
            margin:2px;
            border-radius:6px;
        }}
        QScrollBar::handle:horizontal {{
            background:{theme.slider_handle};
            min-width:24px;
            border-radius:6px;
        }}
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {{
            width:0px;
            background:transparent;
        }}
        QScrollBar::sub-page:horizontal,
        QScrollBar::add-page:horizontal {{
            background:{theme.slider_groove};
            border-radius:6px;
        }}
        QPushButton {{
            color:{theme.button_text};
            background:{theme.primary};
            border-radius:12px;
            font-weight:600;
            padding:8px 18px;
        }}
        QPushButton[modeButton="true"] {{
            padding:6px 14px;
            font-size:13px;
            min-width:120px;
        }}
        QPushButton[modeButton="true"]:checked {{
            padding:10px 18px;
            font-size:14px;
        }}
        QPushButton:hover {{ background:{theme.primary_hover}; }}
        QPushButton:pressed {{ background:{theme.primary_pressed}; }}

        QPushButton:checked {{
            background:{theme.checked};
            border:2px solid {theme.checked_border};
        }}
        QPushButton:checked:hover {{
            background:{theme.checked_hover};
        }}
        QPushButton:checked:pressed {{
            background:{theme.checked_pressed};
        }}

        QPushButton:disabled {{
            background:{theme.disabled_bg};
            color:{theme.disabled_text};
            border-radius:12px;
            border:1px solid {theme.border};
        }}
        /* Map-spezifische Container, damit sie immer korrekt einfärben */
        QFrame#mapSidebar {{
            background: {theme.frame_bg};
            border:1px solid {theme.frame_border};
            border-radius:8px;
            color:{theme.text};
        }}
        QWidget#mapGridContainer {{
            background: {theme.base};
            border: none;
            color:{theme.text};
        }}
        QWidget#mapListsWrapper {{
            background: {theme.base};
            border: none;
            color:{theme.text};
        }}
        QScrollArea#mapListScroll QWidget {{
            background: {theme.base};
            color:{theme.text};
        }}

        QCheckBox {{
            color:{theme.text};
            font-size:13px;
        }}

        QCheckBox::indicator {{
            width: 8px;
            height: 8px;
            border: 2px solid {theme.text};
            border-radius: 3px;
            background: {theme.base};
        }}

        QCheckBox::indicator:checked {{
            background: {theme.primary};
        }}
    """


def tool_button_stylesheet(theme: Theme) -> str:
    """Hover/press styling for tool buttons that keep a transparent base."""
    return (
        "QToolButton { font-size:18px; padding:2px; background:transparent; border:none; border-radius:6px; }"
        f"QToolButton:hover {{ background:{theme.tool_hover}; }}"
        f"QToolButton:pressed {{ background:{theme.tool_pressed}; }}"
    )


def apply_app_theme(theme: Theme) -> None:
    """Apply palette and global stylesheet to the QApplication."""
    app = QtWidgets.QApplication.instance()
    if not app:
        return
    app.setStyle("Fusion")
    app.setPalette(build_palette(theme))
    app.setStyleSheet(global_stylesheet(theme))
