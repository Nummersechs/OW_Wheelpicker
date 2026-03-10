"""Compatibility alias for ``controller.ocr.pipeline.postprocess_retry_utils``."""

from __future__ import annotations

import sys

from .pipeline import postprocess_retry_utils as _IMPL_MODULE

sys.modules[__name__] = _IMPL_MODULE
