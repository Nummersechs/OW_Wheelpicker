"""View package with lazy exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["WheelView", "WheelDisc", "ResultOverlay"]


def __getattr__(name: str) -> Any:
    if name == "WheelView":
        return import_module(".wheel_view", __name__).WheelView
    if name == "WheelDisc":
        return import_module(".wheel_disc", __name__).WheelDisc
    if name == "ResultOverlay":
        return import_module(".overlay", __name__).ResultOverlay
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
