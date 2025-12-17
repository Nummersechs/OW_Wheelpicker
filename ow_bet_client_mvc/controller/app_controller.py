from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse
import threading
import requests

from PySide6 import QtCore, QtWebSockets

import config
from model.state import ClientState
from view.main_window import BetMainWindow


class AppController(QtCore.QObject):
    """
    Verbindet Model (ClientState) und View (BetMainWindow).
    Kümmert sich um WebSocket und Persistenz.
    """
    rolesLoaded = QtCore.Signal(list)

    def __init__(self, base_dir: Path, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.state = ClientState.load(base_dir)

        self.view = BetMainWindow()
        self.view.set_username(self.state.username)
        self.view.set_status("Nicht verbunden.")
        
        self.rolesLoaded.connect(self._apply_roles_msg)

        # Name-Overlay initial anzeigen
        QtCore.QTimer.singleShot(0, self._show_name_overlay_initial)

        # Events aus der View
        self.view.changeNameRequested.connect(self._on_change_name_request)
        self.view.on_name_confirmed(self._on_name_confirmed)

        self.ws: QtWebSockets.QWebSocket | None = None

    # ---------------- Name / State ----------------

    def _show_name_overlay_initial(self):
        self.view.show()
        self.view.show_name_overlay(self.state.username)

    def _on_change_name_request(self):
        self.view.show_name_overlay(self.state.username)

    def _on_name_confirmed(self, name: str):
        self.state.username = name
        self.state.save(self.base_dir)
        self.view.set_username(name)
        self._connect_websocket()

    # ---------------- WebSocket ----------------

    def _connect_websocket(self):
        # existierende Verbindung schließen
        if self.ws is not None:
            self.ws.deleteLater()
            self.ws = None

        base = config.API_BASE_URL  # z.B. "http://localhost:5326"
        u = urlparse(base)
        scheme = "ws" if u.scheme == "http" else "wss"
        ws_url = f"{scheme}://{u.hostname}"
        config.debug_print(f"[WS] Connecting to {ws_url} ...")
        if u.port:
            ws_url += f":{u.port}"
        ws_url += "/ws"

        self.view.set_status(f"Verbinde zu {ws_url} ...")

        self.ws = QtWebSockets.QWebSocket()
        self.ws.errorOccurred.connect(self._on_ws_error)
        self.ws.connected.connect(self._on_ws_connected)
        self.ws.disconnected.connect(self._on_ws_disconnected)
        self.ws.textMessageReceived.connect(self._on_ws_message)

        self.ws.open(QtCore.QUrl(ws_url))

    def _on_ws_connected(self):
        config.debug_print("[WS] Connected successfully!")
        self.view.set_status("WebSocket: Verbunden. Warte auf Rollen-Sync ...")
        self._fetch_initial_roles()

    def _on_ws_disconnected(self):
        config.debug_print("[WS] Disconnected.")
        self.view.set_status("WebSocket: Getrennt.")

    def _on_ws_error(self, err):
        config.debug_print("WebSocket-Fehler:", err)
        self.view.set_status(f"WebSocket-Fehler: {err}")

    def _on_ws_message(self, text: str):
        try:
            msg = json.loads(text)
        except Exception as e:
            config.debug_print("Ungültige WS-Nachricht:", text, e)
            return

        if "roles" in msg:
            config.debug_print("[WS] Roles update empfangen")
            self._apply_roles_msg(msg["roles"])

    def _apply_roles_msg(self, roles_list):
        """
        roles_list: [
          {"role": "Tank", "names": [...]},
          {"role": "Damage", "names": [...]},
          {"role": "Support", "names": [...]}
        ]
        """
        roles_map = {
            "Tank": [],
            "Damage": [],
            "Support": [],
        }
        for r in roles_list:
            role_name = r.get("role")
            names = r.get("names") or []
            if not isinstance(names, list):
                continue
            if role_name in roles_map:
                roles_map[role_name] = names

        # Model updaten
        for key in ("Tank", "Damage", "Support"):
            self.state.roles[key].names = list(roles_map[key])

        # optional: Rollen auch im Savefile merken
        self.state.save(self.base_dir)

        self.view.set_status(
            "Rollen-Sync empfangen: "
            f"Tank {len(roles_map['Tank'])}, "
            f"Damage {len(roles_map['Damage'])}, "
            f"Support {len(roles_map['Support'])}"
        )
        self.view.set_roles(roles_map)
    
    def _fetch_initial_roles(self):
        """
        Holt einmalig die aktuellen Rollen vom Backend (/roles-current)
        in einem eigenen Thread und wendet sie dann im GUI-Thread an.
        """
        def _worker():
            try:
                base = config.API_BASE_URL  # z.B. "http://localhost:8000"
                url = base.rstrip("/") + "/roles-current"
                config.debug_print(f"[HTTP] GET {url}")
                resp = requests.get(url, timeout=3)
                resp.raise_for_status()
                data = resp.json()
                roles = data.get("roles", [])
                config.debug_print("[HTTP] roles-current:", roles)
                # Signal → landet im GUI-Thread, ruft _apply_roles_msg(roles)
                self.rolesLoaded.emit(roles)
            except Exception as e:
                config.debug_print("Fehler beim Laden der Rollen:", e)

        threading.Thread(target=_worker, daemon=True).start()
