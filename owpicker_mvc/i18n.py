"""
Lightweight translation helper for the UI.
Sources per language live in i18n_de.py / i18n_en.py to keep strings organized.
"""
from __future__ import annotations

from typing import Dict

import i18n_de
import i18n_en

# Map language code -> flat key/value dictionary
LANG_SOURCES: Dict[str, Dict[str, str]] = {
    "de": i18n_de.TRANSLATIONS_DE,
    "en": i18n_en.TRANSLATIONS_EN,
}

SUPPORTED_LANGS = tuple(LANG_SOURCES.keys())
_current_language = "de"


def _build_translations() -> Dict[str, Dict[str, str]]:
    combined: Dict[str, Dict[str, str]] = {}
    for lang, entries in LANG_SOURCES.items():
        for key, text in (entries or {}).items():
            combined.setdefault(key, {})[lang] = text
    return combined


TRANSLATIONS = _build_translations()


def set_language(lang: str) -> None:
    """Set active language (falls back to German)."""
    global _current_language
    _current_language = lang if lang in SUPPORTED_LANGS else "de"


def get_language() -> str:
    return _current_language


def t(key: str, **kwargs) -> str:
    """Translate a key and apply optional format kwargs."""
    entry = TRANSLATIONS.get(key)
    if isinstance(entry, dict):
        text = entry.get(_current_language) or entry.get("de")
    else:
        text = str(entry) if entry is not None else None
    if text is None:
        text = key
    try:
        return text.format(**kwargs)
    except Exception:
        return text
