from __future__ import annotations

import importlib
import unittest
from typing import Any


_SKIP_REASON = "PySide6 not available; skipping Qt-dependent tests"


def require_pyside6() -> None:
    try:
        importlib.import_module("PySide6")
    except Exception as exc:
        raise unittest.SkipTest(_SKIP_REASON) from exc


def import_qt(*module_names: str) -> tuple[Any, ...]:
    require_pyside6()
    modules: list[Any] = []
    for name in module_names:
        try:
            modules.append(importlib.import_module(f"PySide6.{name}"))
        except Exception as exc:
            raise unittest.SkipTest(f"{_SKIP_REASON} (missing {name})") from exc
    return tuple(modules)
