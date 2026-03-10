"""Compatibility alias for ``controller.ocr.capture.ops``."""

from __future__ import annotations

from importlib import import_module
import sys

_IMPL_MODULE = import_module(".capture.ops", __package__)
sys.modules[__name__] = _IMPL_MODULE

