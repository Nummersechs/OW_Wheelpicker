"""Compatibility alias for ``controller.ocr.capture.async_worker_utils``."""

from __future__ import annotations

import sys

from .capture import async_worker_utils as _IMPL_MODULE

sys.modules[__name__] = _IMPL_MODULE
