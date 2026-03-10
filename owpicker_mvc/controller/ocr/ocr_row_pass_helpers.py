"""Compatibility alias for ``controller.ocr.pipeline.row_pass_helpers``."""

from __future__ import annotations

import sys

from .pipeline import row_pass_helpers as _IMPL_MODULE

sys.modules[__name__] = _IMPL_MODULE
