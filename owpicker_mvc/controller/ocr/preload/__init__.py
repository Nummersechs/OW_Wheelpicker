"""OCR preload package with compatibility wrappers."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "coordinator",
    "worker",
]


def __getattr__(name: str) -> Any:
    if name in set(__all__):
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

