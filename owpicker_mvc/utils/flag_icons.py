"""Create small flag icons at runtime to avoid bundling image assets."""
from __future__ import annotations

from typing import Tuple, Dict
from PySide6 import QtGui, QtCore


def _de_flag(size: Tuple[int, int]) -> QtGui.QIcon:
    w, h = size
    pm = QtGui.QPixmap(w, h)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    band_h = h / 3.0
    colors = [QtGui.QColor(0, 0, 0), QtGui.QColor(221, 0, 0), QtGui.QColor(255, 204, 0)]
    for idx, color in enumerate(colors):
        y = int(idx * band_h)
        p.fillRect(QtCore.QRect(0, y, w, int(band_h + 0.5)), color)
    p.end()
    return QtGui.QIcon(pm)


def _en_flag(size: Tuple[int, int]) -> QtGui.QIcon:
    """Simplified Union Jack: blue background, white saltire + cross, red overlays."""
    w, h = size
    pm = QtGui.QPixmap(w, h)
    pm.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    blue = QtGui.QColor(15, 45, 120)
    white = QtGui.QColor(245, 245, 245)
    red = QtGui.QColor(200, 20, 20)

    p.fillRect(QtCore.QRect(0, 0, w, h), blue)

    cx = w / 2.0
    cy = h / 2.0
    diag_w = max(2.0, w * 0.14)
    cross_w = max(2.0, w * 0.26)
    cross_r = max(2.0, w * 0.14)

    # White diagonals
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(white)
    path = QtGui.QPainterPath()
    path.moveTo(0, diag_w)
    path.lineTo(diag_w, 0)
    path.lineTo(w, h - diag_w)
    path.lineTo(w - diag_w, h)
    path.closeSubpath()
    path2 = QtGui.QPainterPath()
    path2.moveTo(0, h - diag_w)
    path2.lineTo(diag_w, h)
    path2.lineTo(w, diag_w)
    path2.lineTo(w - diag_w, 0)
    path2.closeSubpath()
    p.drawPath(path)
    p.drawPath(path2)

    # White cross
    p.fillRect(QtCore.QRectF(cx - cross_w / 2, 0, cross_w, h), white)
    p.fillRect(QtCore.QRectF(0, cy - cross_w / 2, w, cross_w), white)

    # Red diagonals (narrower)
    p.setBrush(red)
    diag_r = max(1.5, w * 0.07)
    path_r = QtGui.QPainterPath()
    path_r.moveTo(0, diag_r)
    path_r.lineTo(diag_r, 0)
    path_r.lineTo(w, h - diag_r)
    path_r.lineTo(w - diag_r, h)
    path_r.closeSubpath()
    path_r2 = QtGui.QPainterPath()
    path_r2.moveTo(0, h - diag_r)
    path_r2.lineTo(diag_r, h)
    path_r2.lineTo(w, diag_r)
    path_r2.lineTo(w - diag_r, 0)
    path_r2.closeSubpath()
    p.drawPath(path_r)
    p.drawPath(path_r2)

    # Red central cross
    p.fillRect(QtCore.QRectF(cx - cross_r / 2, 0, cross_r, h), red)
    p.fillRect(QtCore.QRectF(0, cy - cross_r / 2, w, cross_r), red)

    p.end()
    return QtGui.QIcon(pm)


_ICON_CACHE: Dict[tuple, QtGui.QIcon] = {}


def icon_for_language(lang: str, size: Tuple[int, int] = (32, 24)) -> QtGui.QIcon:
    """Return a simple drawn flag icon for a given language code (cached)."""
    key = ((lang or "").lower(), size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    try:
        code = key[0]
        if code.startswith("de"):
            icon = _de_flag(size)
        elif code.startswith("en"):
            icon = _en_flag(size)
        else:
            icon = QtGui.QIcon()
    except Exception:
        icon = QtGui.QIcon()
    _ICON_CACHE[key] = icon
    return icon


def preload(sizes: Tuple[Tuple[int, int], ...] = ((32, 24),)) -> None:
    """Render icons upfront to avoid first-click lag."""
    for size in sizes:
        for lang in ("de", "en"):
            icon_for_language(lang, size)
