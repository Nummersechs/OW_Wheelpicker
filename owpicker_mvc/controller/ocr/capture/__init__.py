"""OCR capture package with compatibility wrappers."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "async_worker_utils",
    "async_import",
    "async_flow",
    "click_flow",
    "error_flow",
    "entry_helpers",
    "job_flow",
    "ops",
    "pipeline_helpers",
    "preflight_flow",
    "result_flow",
    "runtime_cfg",
    "thread_flow",
    "ui_helpers",
]


def __getattr__(name: str) -> Any:
    if name in set(__all__):
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
