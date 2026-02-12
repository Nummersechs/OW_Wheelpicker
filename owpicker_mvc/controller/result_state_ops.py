from __future__ import annotations

import i18n


def mode_key(mw) -> str:
    return "hero_ban" if mw.hero_ban_active else mw.current_mode


def snapshot_mode_results(mw) -> None:
    """Merkt Summary/Resultate für den aktuellen Modus (temp, nicht persistiert)."""
    key = mode_key(mw)
    if mw.current_mode == "maps":
        mw._mode_results[key] = {
            "map": getattr(mw, "_map_result_text", "–"),
        }
    else:
        wheels_payload: dict[str, dict] = {}
        for role, wheel in mw._role_wheels():
            wheels_payload[mw._role_state_key(role)] = wheel.get_result_payload()
        mw._mode_results[key] = {
            "wheels": wheels_payload
        }


def apply_mode_results(mw, key: str) -> None:
    """Stellt Summary/Resultate für den gewünschten Modus wieder her."""
    if not hasattr(mw, "summary"):
        return
    snap = mw._mode_results.get(key)
    if not snap:
        # Reset auf neutrale Anzeige
        if mw.current_mode == "maps":
            mw._map_result_text = "–"
        else:
            for _role, wheel in mw._role_wheels():
                wheel.clear_result()
        mw.summary.setText("")
        return
    mw.summary.setText("")
    if mw.current_mode == "maps":
        mw._map_result_text = snap.get("map", "–")
        update_summary_from_results(mw)
    else:
        wheel_payloads = snap.get("wheels", {})
        for role, wheel in mw._role_wheels():
            wheel.apply_result_payload(wheel_payloads.get(mw._role_state_key(role)))
        update_summary_from_results(mw)


def update_summary_from_results(mw) -> None:
    """Erzeugt die Summary basierend auf den aktuellen Resultaten und Modus."""
    if mw.current_mode == "maps":
        choice = getattr(mw, "_map_result_text", "–")
        if choice and choice != "–":
            mw.summary.setText(i18n.t("map.summary.choice", choice=choice))
        else:
            mw.summary.setText("")
        return
    if mw.hero_ban_active:
        pick = mw.dps.get_result_value()
        mw.summary.setText(i18n.t("summary.hero_ban", pick=pick or "–") if pick else "")
        return
    t = mw.tank.get_result_value()
    d = mw.dps.get_result_value()
    s = mw.support.get_result_value()
    if t or d or s:
        mw.summary.setText(i18n.t("summary.team", tank=t or "–", dps=d or "–", sup=s or "–"))
    else:
        mw.summary.setText("")


def snapshot_results(mw) -> None:
    """Merkt aktuelle Resultate & Summary, um sie bei Abbruch wiederherzustellen."""
    if mw.current_mode == "maps":
        mw._last_results_snapshot = {
            "mode": "maps",
            "map": getattr(mw, "_map_result_text", "–"),
        }
    else:
        wheels_payload: dict[str, dict] = {}
        for role, wheel in mw._role_wheels():
            wheels_payload[mw._role_state_key(role)] = wheel.get_result_payload()
        mw._last_results_snapshot = {
            "mode": mode_key(mw),
            "wheels": wheels_payload,
        }


def restore_results_snapshot(mw) -> None:
    snap = getattr(mw, "_last_results_snapshot", None)
    if not snap:
        return
    if snap.get("mode") == "maps":
        txt = snap.get("map", None)
        if txt is not None:
            mw._map_result_text = txt
        update_summary_from_results(mw)
    else:
        wheel_payloads = snap.get("wheels", {})
        for role, wheel in mw._role_wheels():
            wheel.apply_result_payload(wheel_payloads.get(mw._role_state_key(role)))
        update_summary_from_results(mw)
    mw._last_results_snapshot = None
