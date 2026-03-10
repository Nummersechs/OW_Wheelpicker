"""Compatibility alias for ``controller.ocr.pipeline.row_pass_helpers``."""

from __future__ import annotations

from importlib import import_module
import sys

_IMPL_MODULE = import_module(".pipeline.row_pass_helpers", __package__)
sys.modules[__name__] = _IMPL_MODULE
