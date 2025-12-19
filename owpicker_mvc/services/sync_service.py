"""
Kapselt alle HTTP-Aufrufe (Spin-Result & Rollen-Sync).
"""
from __future__ import annotations

from typing import Any, Dict, List
import threading
import config

try:
    import requests  # type: ignore
except Exception:
    requests = None  # type: ignore


def send_spin_result(tank: str, damage: str, support: str, pair_modes: Dict[str, bool]) -> None:
    """
    Sendet das Ergebnis an den Server. Läuft im Hintergrundthread.
    """

    def split_pair(label: str, is_pair_mode: bool):
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

    def _worker():
        if requests is None:
            config.debug_print("Requests not available – spin result not sent.")
            return
        try:
            tank1, tank2 = split_pair(tank, pair_modes.get("Tank", False))
            dps1, dps2 = split_pair(damage, pair_modes.get("Damage", False))
            sup1, sup2 = split_pair(support, pair_modes.get("Support", False))

            payload = {
                "tank1": tank1,
                "tank2": tank2,
                "dps1": dps1,
                "dps2": dps2,
                "support1": sup1,
                "support2": sup2,
            }

            base = config.API_BASE_URL
            url = base.rstrip("/") + "/spin-result"

            config.debug_print("Sende Payload:", payload)

            resp = requests.post(url, json=payload, timeout=3)
            resp.raise_for_status()
            config.debug_print("Spin-Ergebnis erfolgreich an Server gesendet:", resp.json())
        except Exception as e:
            config.debug_print("Fehler beim Senden des Spin-Ergebnisses:", e)

    threading.Thread(target=_worker, daemon=True).start()


def sync_roles(roles: List[Dict[str, Any]]) -> None:
    """
    Synct die Rollenlisten an den Server. Läuft im Hintergrundthread.
    Erwartet eine Liste aus {"role": str, "names": list[str]}.
    """

    def _worker():
        if requests is None:
            config.debug_print("Requests not available – roles not synced.")
            return
        try:
            payload = {"roles": roles}
            base = config.API_BASE_URL
            url = base.rstrip("/") + "/roles-sync"

            config.debug_print("SYNC →", payload)
            resp = requests.post(url, json=payload, timeout=3)
            resp.raise_for_status()
            config.debug_print("SYNC OK:", resp.json())

        except Exception as e:
            config.debug_print("Fehler beim Rollen-Sync:", e)

    threading.Thread(target=_worker, daemon=True).start()
