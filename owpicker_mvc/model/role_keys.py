from __future__ import annotations

from typing import Any, Iterable

# Canonical role order used across UI, state persistence and spin logic.
ROLE_KEYS: tuple[str, str, str] = ("Tank", "Damage", "Support")

# Default pair-mode behavior per role.
PAIR_MODE_DEFAULTS: dict[str, bool] = {
    "Tank": False,
    "Damage": True,
    "Support": True,
}

# Mapping role -> MainWindow attribute that stores the wheel widget.
ROLE_WIDGET_ATTRS: tuple[tuple[str, str], ...] = (
    ("Tank", "tank"),
    ("Damage", "dps"),
    ("Support", "support"),
)


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
