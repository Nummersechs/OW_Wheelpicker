"""Compatibility wrapper for legacy ``ocr_debug_utils``."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LEGACY_MODULE = import_module("..ocr_debug_utils", __package__)


def __getattr__(name: str) -> Any:
    return getattr(_LEGACY_MODULE, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_LEGACY_MODULE)))

