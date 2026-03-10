"""Compatibility wrapper for OCR async import flow."""

from __future__ import annotations

from typing import Any

from . import async_flow as _FLOW_MODULE


def __getattr__(name: str) -> Any:
    return getattr(_FLOW_MODULE, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_FLOW_MODULE)))
