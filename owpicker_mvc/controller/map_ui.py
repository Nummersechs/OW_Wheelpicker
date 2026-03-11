"""Compatibility alias for ``controller.map.ui``.

Keeping this module path makes frozen/runtime import behavior more stable
across refactors and preserves backwards compatibility with older imports.
"""

from __future__ import annotations

from .map.ui import MapUI

__all__ = ["MapUI"]
