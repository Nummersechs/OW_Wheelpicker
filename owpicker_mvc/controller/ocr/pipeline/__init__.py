"""OCR pipeline package with compatibility wrappers."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "debug_utils",
    "easyocr_token_utils",
    "engine_utils",
    "import_ui_helpers",
    "importer",
    "name_extraction",
    "ordering_utils",
    "postprocess_retry_utils",
    "postprocess_utils",
    "role_import",
    "row_pass_helpers",
    "row_pass_utils",
]


def __getattr__(name: str) -> Any:
    if name in set(__all__):
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

