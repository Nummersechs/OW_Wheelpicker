"""Compatibility wrapper for legacy ``ocr_row_pass_utils``."""

from __future__ import annotations

from typing import Any

from .. import ocr_row_pass_utils as _LEGACY_MODULE


def __getattr__(name: str) -> Any:
    return getattr(_LEGACY_MODULE, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_LEGACY_MODULE)))
