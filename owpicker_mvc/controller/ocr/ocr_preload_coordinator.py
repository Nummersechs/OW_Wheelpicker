"""Compatibility alias for ``controller.ocr.preload.coordinator``."""

from __future__ import annotations

import sys

from .preload import coordinator as _IMPL_MODULE

sys.modules[__name__] = _IMPL_MODULE
