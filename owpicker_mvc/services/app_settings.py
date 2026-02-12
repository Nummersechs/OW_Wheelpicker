from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AppSettings:
    values: dict[str, Any]

    @classmethod
    def from_module(cls, module: Any) -> "AppSettings":
        data: dict[str, Any] = {}
        for key in dir(module):
            if not key.isupper():
                continue
            try:
                data[key] = getattr(module, key)
            except Exception:
                pass
        return cls(values=data)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def bool(self, key: str, default: bool = False) -> bool:
        return bool(self.values.get(key, default))

    def int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.values.get(key, default))
        except Exception:
            return int(default)

    def float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self.values.get(key, default))
        except Exception:
            return float(default)
