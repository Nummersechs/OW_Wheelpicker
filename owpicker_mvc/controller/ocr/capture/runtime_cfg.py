"""Compatibility wrapper for legacy ``ocr_capture_runtime_cfg``."""

from __future__ import annotations

from typing import Any

from .. import ocr_capture_runtime_cfg as _LEGACY_MODULE


def __getattr__(name: str) -> Any:
    return getattr(_LEGACY_MODULE, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_LEGACY_MODULE)))
