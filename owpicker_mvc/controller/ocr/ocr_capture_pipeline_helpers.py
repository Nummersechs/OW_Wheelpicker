"""Compatibility alias for ``controller.ocr.capture.pipeline_helpers``."""

from __future__ import annotations

import sys

from .capture import pipeline_helpers as _IMPL_MODULE

sys.modules[__name__] = _IMPL_MODULE
