from __future__ import annotations

"""
Zentrale Persistence-Helfer für saved_state.json.
Sorgt dafür, dass Controller/Manager kein eigenes JSON-Handling duplizieren.
"""

from pathlib import Path
import json
from typing import Any, Dict


def state_file(base_dir: Path) -> Path:
    """
    Liefert den Pfad zur saved_state.json relativ zum ausführenden Paket.
    """
    return base_dir / "saved_state.json"


def load_state(path: Path) -> Dict[str, Any]:
    """
    Lädt den gespeicherten Zustand oder gibt ein leeres Dict zurück.
    """
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        # bewusst still: Call-Sites können fallbacken
        pass
    return {}


def save_state(path: Path, data: Dict[str, Any]) -> None:
    """
    Schreibt den Zustand als JSON. Fehler werden intern abgefangen.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # bewusst still: Call-Sites entscheiden selbst über Logging
        pass
