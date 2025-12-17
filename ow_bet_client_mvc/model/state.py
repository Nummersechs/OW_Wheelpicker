from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List
import config


@dataclass
class RoleData:
    names: List[str] = field(default_factory=list)


@dataclass
class ClientState:
    username: str = ""
    roles: Dict[str, RoleData] = field(default_factory=lambda: {
        "Tank": RoleData(),
        "Damage": RoleData(),
        "Support": RoleData(),
    })

    @staticmethod
    def state_file(base_dir: Path) -> Path:
        return base_dir / "client_state.json"

    @classmethod
    def load(cls, base_dir: Path) -> "ClientState":
        path = cls.state_file(base_dir)
        try:
            if path.exists():
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                username = data.get("username", "")
                roles_raw = data.get("roles", {})
                roles: Dict[str, RoleData] = {}
                for key in ("Tank", "Damage", "Support"):
                    names = roles_raw.get(key, {}).get("names", [])
                    if not isinstance(names, list):
                        names = []
                    roles[key] = RoleData(names=list(names))
                st = cls(username=username, roles=roles)
                return st
        except Exception as e:
            config.debug_print("Konnte client_state.json nicht laden:", e)
        return cls()

    def save(self, base_dir: Path) -> None:
        path = self.state_file(base_dir)
        try:
            data = {
                "username": self.username,
                "roles": {
                    key: {"names": r.names}
                    for key, r in self.roles.items()
                },
            }
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            config.debug_print("Konnte client_state.json nicht speichern:", e)
