"""Compatibility wrapper for legacy ``ocr_capture_async_import``."""

from __future__ import annotations

from typing import Any

from .capture import async_flow as _ASYNC_FLOW_MODULE


def __getattr__(name: str) -> Any:
    return getattr(_ASYNC_FLOW_MODULE, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_ASYNC_FLOW_MODULE)))
