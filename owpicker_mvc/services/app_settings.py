from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AppSettings:
    values: dict[str, Any]

    @classmethod
    def from_module(cls, module: Any) -> "AppSettings":
        if module is None:
            return cls(values={})
        try:
            source = vars(module)
        except TypeError:
            source = {}
        data = {
            key: value
            for key, value in source.items()
            if isinstance(key, str) and key.isupper()
        }
        return cls(values=dict(data))

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def bool(self, key: str, default: bool = False) -> bool:
        return bool(self.values.get(key, default))

    def int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.values.get(key, default))
        except (TypeError, ValueError):
            return int(default)

    def float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.values.get(key, default))
        except (TypeError, ValueError):
            return float(default)
