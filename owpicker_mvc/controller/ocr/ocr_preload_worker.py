"""Compatibility alias for ``controller.ocr.preload.worker``."""

from __future__ import annotations

from importlib import import_module
import sys

_IMPL_MODULE = import_module(".preload.worker", __package__)
sys.modules[__name__] = _IMPL_MODULE
