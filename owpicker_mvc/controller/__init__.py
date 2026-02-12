"""Controller package with lazy exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["MainWindow", "mode_manager", "spin_service"]


def __getattr__(name: str) -> Any:
    if name == "MainWindow":
        return import_module(".main_window", __name__).MainWindow
    if name in {"mode_manager", "spin_service"}:
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
