from __future__ import annotations

"""Helpers for saved_state.json to avoid duplicated JSON handling."""

from pathlib import Path
import json
from typing import Any, Dict


def state_file(base_dir: Path) -> Path:
    """Return the path to saved_state.json relative to the running package."""
    return base_dir / "saved_state.json"


def load_state(path: Path) -> Dict[str, Any]:
    """Load saved state or return an empty dict on failure."""
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        # Quiet failure; callers decide on logging/fallback
        pass
    return {}


def save_state(path: Path, data: Dict[str, Any]) -> None:
    """Write state as JSON. Errors are swallowed on purpose."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # Quiet failure; callers decide on logging
        pass
