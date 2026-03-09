from __future__ import annotations

from enum import Enum


class AppMode(str, Enum):
    PLAYERS = "players"
    HEROES = "heroes"
    MAPS = "maps"
    HERO_BAN = "hero_ban"


MODE_VALUES: frozenset[str] = frozenset(mode.value for mode in AppMode)
ROLE_MODE_VALUES: frozenset[str] = frozenset({AppMode.PLAYERS.value, AppMode.HEROES.value})


def normalize_mode(value: str | AppMode | None, default: AppMode = AppMode.PLAYERS) -> str:
    if isinstance(value, AppMode):
        return value.value
    text = str(value or "").strip().lower()
    if not text:
        return default.value
    for mode in AppMode:
        if mode.value == text:
            return mode.value
    return default.value


def is_role_mode(value: str | AppMode | None) -> bool:
    return normalize_mode(value) in ROLE_MODE_VALUES

