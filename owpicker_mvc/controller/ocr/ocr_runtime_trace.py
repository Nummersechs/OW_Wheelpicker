"""Compatibility alias for ``controller.ocr.runtime.trace``."""

from __future__ import annotations

from importlib import import_module
import sys

_IMPL_MODULE = import_module(".runtime.trace", __package__)
sys.modules[__name__] = _IMPL_MODULE
