from dataclasses import dataclass, field
from typing import List
import itertools

@dataclass
class RoleModel:
    role_name: str
    base_names: List[str] = field(default_factory=list)
    pair_mode: bool = False

    def set_base_names_from_text(self, text: str) -> None:
        self.base_names = [line.strip() for line in text.splitlines() if line.strip()]

    def effective_names(self) -> List[str]:
        if not self.pair_mode:
            return self.base_names
        return [f"{a} + {b}" for a, b in itertools.combinations(self.base_names, 2)]
