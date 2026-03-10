"""Compatibility alias for ``controller.ocr.preload.worker``."""

from __future__ import annotations

import sys

from .preload import worker as _IMPL_MODULE

sys.modules[__name__] = _IMPL_MODULE
