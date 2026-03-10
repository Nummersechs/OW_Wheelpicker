"""Compatibility alias for ``controller.ocr.pipeline.import_ui_helpers``."""

from __future__ import annotations

from importlib import import_module
import sys

_IMPL_MODULE = import_module(".pipeline.import_ui_helpers", __package__)
sys.modules[__name__] = _IMPL_MODULE
