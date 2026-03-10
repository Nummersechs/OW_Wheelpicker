"""Compatibility alias for ``controller.ocr.capture.pipeline_helpers``."""

from __future__ import annotations

from importlib import import_module
import sys

_IMPL_MODULE = import_module(".capture.pipeline_helpers", __package__)
sys.modules[__name__] = _IMPL_MODULE

