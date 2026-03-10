from __future__ import annotations

from threading import RLock

from .app_settings import AppSettings

_SETTINGS_LOCK = RLock()
_CURRENT_SETTINGS: AppSettings | None = None


def set_settings(settings: AppSettings | None) -> AppSettings:
    resolved = settings if isinstance(settings, AppSettings) else AppSettings(values={})
    global _CURRENT_SETTINGS
    with _SETTINGS_LOCK:
        _CURRENT_SETTINGS = resolved
    return resolved


def get_settings() -> AppSettings:
    global _CURRENT_SETTINGS
    with _SETTINGS_LOCK:
        if _CURRENT_SETTINGS is None:
            _CURRENT_SETTINGS = AppSettings(values={})
        return _CURRENT_SETTINGS


def resolve(key: str, default=None):
    return get_settings().resolve(key, default)

