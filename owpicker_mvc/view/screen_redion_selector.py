from __future__ import annotations

# Compatibility alias for an older typo-based import path.
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
