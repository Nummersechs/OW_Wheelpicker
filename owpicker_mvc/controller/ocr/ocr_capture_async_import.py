"""Compatibility wrapper for legacy ``ocr_capture_async_import``."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_ASYNC_FLOW_MODULE = import_module(".capture.async_flow", __package__)


def __getattr__(name: str) -> Any:
    return getattr(_ASYNC_FLOW_MODULE, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_ASYNC_FLOW_MODULE)))
