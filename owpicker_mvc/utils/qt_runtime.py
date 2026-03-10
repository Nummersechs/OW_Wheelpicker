from __future__ import annotations

import logging

from PySide6 import QtGui, QtWidgets


_HEADLESS_QPA_PLATFORMS = {
    "offscreen",
    "minimal",
    "minimalegl",
    "linuxfb",
    "vnc",
    "webgl",
}
_QT_RUNTIME_GUARD_ERRORS = (AttributeError, RuntimeError, TypeError, ValueError, LookupError, OSError)
_LOG = logging.getLogger(__name__)


def qpa_platform_name() -> str:
    try:
        name = QtGui.QGuiApplication.platformName()
    except _QT_RUNTIME_GUARD_ERRORS as exc:
        _LOG.debug("QPA platform detection failed", exc_info=exc)
        return ""
    return str(name or "").strip().lower()


def is_headless_qpa() -> bool:
    return qpa_platform_name() in _HEADLESS_QPA_PLATFORMS


def can_raise_windows() -> bool:
    return not is_headless_qpa()


def safe_raise(widget) -> None:
    if widget is None or not can_raise_windows():
        return
    try:
        widget.raise_()
    except _QT_RUNTIME_GUARD_ERRORS as exc:
        _LOG.debug("safe_raise failed for %r", widget, exc_info=exc)


def safe_activate_window(widget) -> None:
    if widget is None or not can_raise_windows():
        return
    try:
        widget.activateWindow()
    except _QT_RUNTIME_GUARD_ERRORS as exc:
        _LOG.debug("safe_activate_window failed for %r", widget, exc_info=exc)


def apply_preferred_app_font(app: QtWidgets.QApplication | None = None) -> None:
    app_obj = app or QtWidgets.QApplication.instance()
    if app_obj is None:
        return

    current = app_obj.font()
    current_family = str(current.family() or "").strip().lower()
    if current_family and current_family not in {"sans serif", "sans-serif"}:
        return

    try:
        available_families = QtGui.QFontDatabase.families()
    except _QT_RUNTIME_GUARD_ERRORS:
        try:
            db = QtGui.QFontDatabase()
            available_families = db.families()
        except _QT_RUNTIME_GUARD_ERRORS as exc:
            _LOG.debug("QFontDatabase family lookup failed", exc_info=exc)
            return
    families = {str(f).lower(): str(f) for f in available_families}
    preferred = (
        "Arial",
        "Helvetica Neue",
        "Helvetica",
        "Noto Sans",
        "DejaVu Sans",
        "Segoe UI",
        "Liberation Sans",
        "Cantarell",
        "Ubuntu",
    )
    chosen = None
    for candidate in preferred:
        key = candidate.lower()
        if key in families:
            chosen = families[key]
            break
    if not chosen:
        return

    updated_font = QtGui.QFont(current)
    updated_font.setFamily(chosen)
    app_obj.setFont(updated_font)
