from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore

import config
from services import persistence, sync_service


class StateSyncController(QtCore.QObject):
    """Handle saved_state persistence + online sync outside MainWindow."""

    def __init__(self, main_window, state_file: Path) -> None:
        super().__init__(main_window)
        self._mw = main_window
        self._state_file = state_file
        self._pending_sync_payload: list[dict] | None = None
        self._sync_timer = QtCore.QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._flush_role_sync)

    @staticmethod
    def load_saved_state(state_file: Path) -> dict:
        data = persistence.load_state(state_file)
        if isinstance(data, dict):
            return data
        return {}

    def gather_state(self) -> dict:
        mode_to_capture = self._mw.current_mode
        if mode_to_capture == "maps":
            mode_to_capture = getattr(self._mw, "last_non_hero_mode", "players") or "players"
            if mode_to_capture not in ("players", "heroes"):
                mode_to_capture = "players"
        self._mw._state_store.capture_mode_from_wheels(
            mode_to_capture,
            {"Tank": self._mw.tank, "Damage": self._mw.dps, "Support": self._mw.support},
            hero_ban_active=self._mw.hero_ban_active if mode_to_capture == "heroes" else False,
        )
        if getattr(self._mw, "map_lists", None):
            self._mw.map_mode.capture_state()
        state = self._mw._state_store.to_saved(self._mw.volume_slider.value())
        state["language"] = self._mw.language
        state["theme"] = self._mw.theme
        return state

    def save_state(self) -> None:
        if getattr(self._mw, "_restoring_state", False):
            return
        state = self.gather_state()
        persistence.save_state(self._state_file, state)
        self.sync_all_roles()
        if self._mw.hero_ban_active:
            self._mw._update_hero_ban_wheel()

    def send_spin_result(self, tank: str, damage: str, support: str) -> None:
        if not getattr(self._mw, "online_mode", False):
            config.debug_print("Spin-Result: Offline-Modus - kein Senden.")
            return
        pair_modes = {
            "Tank": getattr(self._mw.tank, "pair_mode", False),
            "Damage": getattr(self._mw.dps, "pair_mode", False),
            "Support": getattr(self._mw.support, "pair_mode", False),
        }
        sync_service.send_spin_result(tank, damage, support, pair_modes)

    def sync_all_roles(self) -> None:
        if not getattr(self._mw, "online_mode", False):
            config.debug_print("Sync uebersprungen: Offline-Modus.")
            self._pending_sync_payload = None
            if self._sync_timer.isActive():
                self._sync_timer.stop()
            return
        payload = [
            {"role": "Tank", "names": self._mw.tank.get_current_names()},
            {"role": "Damage", "names": self._mw.dps.get_current_names()},
            {"role": "Support", "names": self._mw.support.get_current_names()},
        ]
        self._pending_sync_payload = payload
        # kurze Verzoegerung, um schnelle State-Aenderungen zu buendeln
        self._sync_timer.start(200)

    def _flush_role_sync(self) -> None:
        """Sendet den letzten vorbereiteten Sync-Payload (debounced)."""
        if not getattr(self._mw, "online_mode", False):
            self._pending_sync_payload = None
            return
        payload = self._pending_sync_payload
        self._pending_sync_payload = None
        if payload:
            sync_service.sync_roles(payload)
