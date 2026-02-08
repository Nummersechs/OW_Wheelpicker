from __future__ import annotations

from pathlib import Path
import json
import threading
from typing import Any, Dict, List

from PySide6 import QtCore

import config

try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore


class StateSyncController(QtCore.QObject):
    """Handle saved_state persistence + online sync outside MainWindow."""

    def __init__(self, main_window, state_file: Path) -> None:
        super().__init__(main_window)
        self._mw = main_window
        self._state_file = state_file
        self._closed = False
        self._network_threads_active = 0
        self._network_threads_lock = threading.Lock()
        self._pending_state: Dict[str, Any] | None = None
        self._pending_save_sync = False
        self._save_debounce_ms = max(0, int(getattr(config, "STATE_SAVE_DEBOUNCE_MS", 160)))
        self._last_saved_signature: str | None = None
        existing = self._load_state(state_file)
        if existing:
            self._last_saved_signature = self._state_signature(existing)
        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_pending_save)
        self._pending_sync_payload: list[dict] | None = None
        self._sync_timer = QtCore.QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._flush_role_sync)

    @staticmethod
    def state_file(base_dir: Path) -> Path:
        """Return the path to saved_state.json relative to the running package."""
        return base_dir / "saved_state.json"

    @staticmethod
    def _load_state(path: Path) -> Dict[str, Any]:
        """Load saved state or return an empty dict on failure."""
        try:
            if path.exists():
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            # Quiet failure; callers decide on logging/fallback
            pass
        return {}

    @staticmethod
    def _save_state(path: Path, data: Dict[str, Any]) -> bool:
        """Write state as JSON. Returns True on success."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            # Quiet failure; callers decide on logging
            return False

    @staticmethod
    def _state_signature(data: Dict[str, Any]) -> str | None:
        try:
            return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except Exception:
            return None

    @staticmethod
    def load_saved_state(state_file: Path) -> dict:
        data = StateSyncController._load_state(state_file)
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

    def save_state(self, sync: bool = True, immediate: bool = False) -> None:
        if self._closed:
            return
        if getattr(self._mw, "_restoring_state", False):
            return
        if getattr(self._mw, "_closing", False):
            sync = False
            immediate = True
        state = self.gather_state()
        if immediate:
            if self._save_timer.isActive():
                self._save_timer.stop()
            self._pending_state = None
            self._pending_save_sync = False
            self._persist_state(state)
            if sync:
                self.sync_all_roles()
        else:
            self._pending_state = state
            self._pending_save_sync = bool(self._pending_save_sync or sync)
            self._save_timer.start(self._save_debounce_ms)
        if self._mw.hero_ban_active and not getattr(self._mw, "_closing", False):
            self._mw._update_hero_ban_wheel()

    def _persist_state(self, state: Dict[str, Any]) -> None:
        signature = self._state_signature(state)
        if signature is not None and signature == self._last_saved_signature:
            return
        if self._save_state(self._state_file, state) and signature is not None:
            self._last_saved_signature = signature

    def _flush_pending_save(self) -> None:
        state = self._pending_state
        sync = self._pending_save_sync
        self._pending_state = None
        self._pending_save_sync = False
        if state is None:
            return
        self._persist_state(state)
        if sync:
            self.sync_all_roles()

    def shutdown(self, flush: bool = True) -> None:
        """Stop pending timers and clear queued sync payloads."""
        self._closed = True
        if flush:
            self._flush_pending_save()
        if self._save_timer.isActive():
            self._save_timer.stop()
        if self._sync_timer.isActive():
            self._sync_timer.stop()
        self._pending_state = None
        self._pending_save_sync = False
        self._pending_sync_payload = None

    def resource_snapshot(self) -> dict:
        save_timer_active = False
        sync_timer_active = False
        try:
            save_timer_active = bool(self._save_timer.isActive())
        except Exception:
            pass
        try:
            sync_timer_active = bool(self._sync_timer.isActive())
        except Exception:
            pass
        with self._network_threads_lock:
            active_threads = int(self._network_threads_active)
        return {
            "closed": bool(self._closed),
            "save_timer_active": save_timer_active,
            "sync_timer_active": sync_timer_active,
            "has_pending_state": bool(self._pending_state is not None),
            "pending_save_sync": bool(self._pending_save_sync),
            "has_pending_sync_payload": bool(self._pending_sync_payload is not None),
            "network_threads_active": active_threads,
        }

    def send_spin_result(self, tank: str, damage: str, support: str) -> None:
        if self._closed:
            return
        if not getattr(self._mw, "online_mode", False):
            config.debug_print("Spin-Result: Offline-Modus - kein Senden.")
            return
        pair_modes = {
            "Tank": getattr(self._mw.tank, "pair_mode", False),
            "Damage": getattr(self._mw.dps, "pair_mode", False),
            "Support": getattr(self._mw.support, "pair_mode", False),
        }
        self._send_spin_result(tank, damage, support, pair_modes)

    def sync_all_roles(self) -> None:
        if self._closed:
            return
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
            self._sync_roles(payload)

    @staticmethod
    def _split_pair_label(label: str, is_pair_mode: bool) -> tuple[str, str]:
        label = (label or "").strip()
        if not label:
            return "", ""
        if not is_pair_mode:
            return label, ""
        parts = [p.strip() for p in label.split("+") if p.strip()]
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], " + ".join(parts[1:])

    def _post_json_async(
        self,
        *,
        endpoint: str,
        payload: Dict[str, Any],
        payload_log: str,
        success_log: str,
        error_log: str,
        missing_requests_log: str,
    ) -> None:
        """Post JSON payload in a daemon thread."""

        def _worker() -> None:
            with self._network_threads_lock:
                self._network_threads_active += 1
            if requests is None:
                try:
                    config.debug_print(missing_requests_log)
                finally:
                    with self._network_threads_lock:
                        self._network_threads_active = max(0, self._network_threads_active - 1)
                return
            try:
                base = config.API_BASE_URL
                url = base.rstrip("/") + endpoint
                config.debug_print(payload_log, payload)
                resp = requests.post(url, json=payload, timeout=3)
                resp.raise_for_status()
                config.debug_print(success_log, resp.json())
            except Exception as e:
                config.debug_print(error_log, e)
            finally:
                with self._network_threads_lock:
                    self._network_threads_active = max(0, self._network_threads_active - 1)

        if self._closed:
            return
        threading.Thread(target=_worker, daemon=True).start()

    def _send_spin_result(self, tank: str, damage: str, support: str, pair_modes: Dict[str, bool]) -> None:
        """Send spin result to the server in a background thread."""
        tank1, tank2 = self._split_pair_label(tank, pair_modes.get("Tank", False))
        dps1, dps2 = self._split_pair_label(damage, pair_modes.get("Damage", False))
        sup1, sup2 = self._split_pair_label(support, pair_modes.get("Support", False))
        payload = {
            "tank1": tank1,
            "tank2": tank2,
            "dps1": dps1,
            "dps2": dps2,
            "support1": sup1,
            "support2": sup2,
        }
        self._post_json_async(
            endpoint="/spin-result",
            payload=payload,
            payload_log="Sende Payload:",
            success_log="Spin-Ergebnis erfolgreich an Server gesendet:",
            error_log="Fehler beim Senden des Spin-Ergebnisses:",
            missing_requests_log="Requests not available – spin result not sent.",
        )

    def _sync_roles(self, roles: List[Dict[str, Any]]) -> None:
        """Sync role lists to the server in a background thread."""
        self._post_json_async(
            endpoint="/roles-sync",
            payload={"roles": roles},
            payload_log="SYNC →",
            success_log="SYNC OK:",
            error_log="Fehler beim Rollen-Sync:",
            missing_requests_log="Requests not available – roles not synced.",
        )
