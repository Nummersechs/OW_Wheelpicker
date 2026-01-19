from __future__ import annotations

from typing import Iterable, Sequence

from PySide6 import QtGui, QtWidgets

import i18n


def set_fixed_width_from_translations(
    widgets: QtWidgets.QWidget | Iterable[QtWidgets.QWidget],
    keys: Sequence[str],
    padding: int = 20,
    prefixes: Sequence[str] | None = None,
) -> None:
    """Set min/max width so translated labels don't jump between languages."""
    if not isinstance(widgets, (list, tuple)):
        widgets = [widgets]
    prefixes = prefixes or [""]
    all_texts: list[str] = []
    for key in keys:
        entry = i18n.TRANSLATIONS.get(key, {})
        if isinstance(entry, dict):
            all_texts.extend([str(v) for v in entry.values()])
        elif entry:
            all_texts.append(str(entry))
    if not all_texts:
        return
    for widget in widgets:
        if widget is None:
            continue
        font = widget.font()
        fm = QtGui.QFontMetrics(font)
        max_w = 0
        for txt in all_texts:
            for pre in prefixes:
                max_w = max(max_w, fm.horizontalAdvance(f"{pre}{txt}"))
        width = max_w + padding
        widget.setMinimumWidth(width)
        widget.setMaximumWidth(width)
