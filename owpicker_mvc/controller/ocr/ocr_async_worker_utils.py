"""Compatibility alias for ``controller.ocr.capture.async_worker_utils``."""

from __future__ import annotations

from importlib import import_module
import sys

_IMPL_MODULE = import_module(".capture.async_worker_utils", __package__)
sys.modules[__name__] = _IMPL_MODULE
