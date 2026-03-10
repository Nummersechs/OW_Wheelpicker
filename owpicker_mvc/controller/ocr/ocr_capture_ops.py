"""Compatibility alias for ``controller.ocr.capture.ops``."""

from __future__ import annotations

import sys

from .capture import ops as _IMPL_MODULE

sys.modules[__name__] = _IMPL_MODULE
