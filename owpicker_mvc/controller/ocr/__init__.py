"""OCR helpers with lazy exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "capture",
    "pipeline",
    "preload",
    "runtime",
    "ocr_capture_ops",
    "ocr_import",
    "ocr_capture_entry_helpers",
    "ocr_easyocr_token_utils",
    "ocr_name_extraction",
    "ocr_postprocess_retry_utils",
    "ocr_row_pass_helpers",
    "ocr_import_ui_helpers",
]


def __getattr__(name: str) -> Any:
    if name in set(__all__):
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
