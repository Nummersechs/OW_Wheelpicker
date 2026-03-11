from __future__ import annotations

from typing import Iterable, Sequence

from PySide6 import QtGui, QtWidgets

import i18n

_TEXTS_BY_KEYS_CACHE: dict[tuple[str, ...], tuple[str, ...]] = {}
_WIDTH_CACHE: dict[tuple[tuple, tuple[str, ...], tuple[str, ...], int], int] = {}
_TEXT_WIDTH_CACHE: dict[tuple[tuple, str], int] = {}


def _font_cache_key(font: QtGui.QFont) -> tuple:
    return (
        str(font.family() or ""),
        int(font.pixelSize()),
        float(font.pointSizeF()),
        int(font.weight()),
        bool(font.bold()),
        bool(font.italic()),
        int(font.stretch()),
        float(font.letterSpacing()),
    )


def _all_texts_for_keys(keys: Sequence[str]) -> tuple[str, ...]:
    key_tuple = tuple(str(k) for k in keys)
    cached = _TEXTS_BY_KEYS_CACHE.get(key_tuple)
    if cached is not None:
        return cached
    all_texts: list[str] = []
    for key in key_tuple:
        entry = i18n.TRANSLATIONS.get(key, {})
        if isinstance(entry, dict):
            all_texts.extend([str(v) for v in entry.values()])
        elif entry:
            all_texts.append(str(entry))
    unique_texts = tuple(dict.fromkeys(all_texts))
    _TEXTS_BY_KEYS_CACHE[key_tuple] = unique_texts
    return unique_texts


def _translated_width(
    font: QtGui.QFont,
    keys: Sequence[str],
    prefixes: Sequence[str] | None = None,
    padding: int = 20,
) -> int:
    prefix_tuple = tuple(str(p) for p in (prefixes or [""]))
    keys_tuple = tuple(str(k) for k in keys)
    all_texts = _all_texts_for_keys(keys_tuple)
    if not all_texts:
        return 0
    font_key = _font_cache_key(font)
    cache_key = (font_key, keys_tuple, prefix_tuple, int(padding))
    width = _WIDTH_CACHE.get(cache_key)
    if width is not None:
        return int(width)
    fm = QtGui.QFontMetrics(font)
    max_w = 0
    for txt in all_texts:
        for pre in prefix_tuple:
            text = f"{pre}{txt}"
            text_key = (font_key, text)
            measured = _TEXT_WIDTH_CACHE.get(text_key)
            if measured is None:
                measured = int(fm.horizontalAdvance(text))
                _TEXT_WIDTH_CACHE[text_key] = measured
            if measured > max_w:
                max_w = measured
    width = max_w + int(padding)
    _WIDTH_CACHE[cache_key] = width
    return int(width)


def set_fixed_width_from_translations(
    widgets: QtWidgets.QWidget | Iterable[QtWidgets.QWidget],
    keys: Sequence[str],
    padding: int = 20,
    prefixes: Sequence[str] | None = None,
) -> None:
    """Set min/max width so translated labels don't jump between languages."""
    if not isinstance(widgets, (list, tuple)):
        widgets = [widgets]
    for widget in widgets:
        if widget is None:
            continue
        width = _translated_width(
            widget.font(),
            keys,
            prefixes=prefixes,
            padding=padding,
        )
        if width <= 0:
            continue
        widget.setMinimumWidth(width)
        widget.setMaximumWidth(width)


def set_minimum_width_from_translations(
    widgets: QtWidgets.QWidget | Iterable[QtWidgets.QWidget],
    keys: Sequence[str],
    padding: int = 20,
    prefixes: Sequence[str] | None = None,
) -> None:
    """Set only minimum width based on all translations for the given keys."""
    if not isinstance(widgets, (list, tuple)):
        widgets = [widgets]
    for widget in widgets:
        if widget is None:
            continue
        width = _translated_width(
            widget.font(),
            keys,
            prefixes=prefixes,
            padding=padding,
        )
        if width <= 0:
            continue
        widget.setMinimumWidth(width)
