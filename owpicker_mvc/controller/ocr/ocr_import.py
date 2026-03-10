"""Compatibility alias for ``controller.ocr.pipeline.importer``."""

from __future__ import annotations

from importlib import import_module
import sys

_IMPL_MODULE = import_module(".pipeline.importer", __package__)
sys.modules[__name__] = _IMPL_MODULE

