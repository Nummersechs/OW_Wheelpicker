"""Compatibility alias for ``controller.ocr.runtime.trace``."""

from __future__ import annotations

import sys

from .runtime import trace as _IMPL_MODULE

sys.modules[__name__] = _IMPL_MODULE
