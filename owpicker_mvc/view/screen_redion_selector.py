from __future__ import annotations

import warnings

# Compatibility alias for an older typo-based import path.
warnings.warn(
    "view.screen_redion_selector is deprecated; use view.screen_region_selector",
    DeprecationWarning,
    stacklevel=2,
)

from .screen_region_selector import (
    ScreenRegionSelectorDialog,
    select_region_from_primary_screen,
    select_region_with_macos_screencapture,
)

__all__ = [
    "ScreenRegionSelectorDialog",
    "select_region_from_primary_screen",
    "select_region_with_macos_screencapture",
]
