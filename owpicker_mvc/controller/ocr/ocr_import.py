"""Compatibility alias for ``controller.ocr.pipeline.importer``."""

from __future__ import annotations

import sys

from .pipeline import importer as _IMPL_MODULE

sys.modules[__name__] = _IMPL_MODULE
