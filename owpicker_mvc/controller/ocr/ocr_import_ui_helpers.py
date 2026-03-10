"""Compatibility alias for ``controller.ocr.pipeline.import_ui_helpers``."""

from __future__ import annotations

import sys

from .pipeline import import_ui_helpers as _IMPL_MODULE

sys.modules[__name__] = _IMPL_MODULE
