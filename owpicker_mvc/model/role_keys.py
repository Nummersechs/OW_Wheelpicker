from __future__ import annotations

from enum import Enum
from typing import Any, Iterable


class RoleKey(str, Enum):
    TANK = "Tank"
    DAMAGE = "Damage"
    SUPPORT = "Support"


# Canonical role order used across UI, state persistence and spin logic.
ROLE_KEYS: tuple[str, str, str] = tuple(role.value for role in RoleKey)  # type: ignore[assignment]
ROLE_KEY_SET: frozenset[str] = frozenset(ROLE_KEYS)

# Default pair-mode behavior per role.
PAIR_MODE_DEFAULTS: dict[str, bool] = {
    RoleKey.TANK.value: False,
    RoleKey.DAMAGE.value: True,
    RoleKey.SUPPORT.value: True,
}

# Mapping role -> MainWindow attribute that stores the wheel widget.
ROLE_WIDGET_ATTRS: tuple[tuple[str, str], ...] = (
    (RoleKey.TANK.value, "tank"),
    (RoleKey.DAMAGE.value, "dps"),
    (RoleKey.SUPPORT.value, "support"),
)


_ROLE_ALIASES: dict[str, str] = {
    "tank": RoleKey.TANK.value,
    "damage": RoleKey.DAMAGE.value,
    "dmg": RoleKey.DAMAGE.value,
    "dps": RoleKey.DAMAGE.value,
    "support": RoleKey.SUPPORT.value,
    "sup": RoleKey.SUPPORT.value,
}


def normalize_role_key(value: str | RoleKey | None, default: str | None = None) -> str | None:
    if isinstance(value, RoleKey):
        return value.value
    token = str(value or "").strip()
    if not token:
        return default
    if token in ROLE_KEY_SET:
        return token
    return _ROLE_ALIASES.get(token.casefold(), default)


def iter_role_wheels(owner: Any) -> Iterable[tuple[str, Any]]:
    for role, attr in ROLE_WIDGET_ATTRS:
        wheel = getattr(owner, attr, None)
        if wheel is not None:
            yield role, wheel


def role_wheels(owner: Any) -> list[tuple[str, Any]]:
    return list(iter_role_wheels(owner))


def role_wheel_map(owner: Any) -> dict[str, Any]:
    return dict(iter_role_wheels(owner))


def role_for_wheel(owner: Any, target_wheel: Any) -> str | None:
    for role, wheel in iter_role_wheels(owner):
        if wheel is target_wheel:
            return role
    return None
