"""Map package entrypoint with lazy UI import.

Importing :mod:`controller.map` should stay Qt-free for headless unit tests.
`MapUI` is resolved only when explicitly requested.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

# Keep star-imports headless-safe by not exposing Qt-bound symbols via __all__.
__all__: list[str] = []


def __getattr__(name: str) -> Any:
    if name == "MapUI":
        module = import_module(".ui", __name__)
        return getattr(module, "MapUI")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
