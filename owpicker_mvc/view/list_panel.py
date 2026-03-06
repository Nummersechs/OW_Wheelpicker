from __future__ import annotations

from typing import List

from PySide6 import QtCore, QtWidgets

import i18n
from utils import theme as theme_util
from view.base_panel import BasePanel


class ListPanel(BasePanel):
    """
    List-only Variante eines Wheel-Panels (für Map-Listen).
    Bietet Spin-/Include-Buttons und eine Namensliste, aber kein Rad.
    """

    def __init__(self, title: str, entries: List[dict] | List[str], parent: QtWidgets.QWidget | None = None):
        super().__init__(
            title=title,
            spin_label=i18n.t("wheel.spin_single_map"),
            names_hint_key="wheel.names_hint_single",
            parent=parent,
        )
        self.pair_mode = False
        self.use_subrole_filter = False

        self.load_entries(entries)
        self.names.itemChanged.connect(self._on_names_changed)
        self.names.model().rowsInserted.connect(self._on_names_changed)
        self.names.model().rowsRemoved.connect(self._on_names_changed)
        self.names.metaChanged.connect(self._on_names_changed)

        self._apply_fixed_widths()
        self.apply_theme(theme_util.app_theme("light"))

    # --- API kompatibel zu WheelView für Map-Mode ---
    def set_language(self, lang: str):
        super().set_language(lang)
        self.set_spin_button_text(i18n.t("wheel.spin_single_map"))

    def get_current_entries(self) -> List[dict]:
        entries: list[dict] = []
        for i in range(self.names.count()):
            item = self.names.item(i)
            text = self.names.itemWidget(item).edit.text().strip() if item else ""
            if not text:
                continue
            active = self.names.item_state(item) == QtCore.Qt.Checked
            entries.append({"name": text, "subroles": [], "active": active})
        return entries

    def get_active_entries(self) -> List[dict]:
        return [e for e in self.get_current_entries() if e.get("active")]

    def load_entries(self, entries: List[dict] | List[str]):
        normalized = []
        for item in entries or []:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    normalized.append({"name": name, "active": True, "subroles": []})
            elif isinstance(item, dict) and "name" in item:
                name = str(item.get("name", "")).strip()
                if name:
                    normalized.append(
                        {"name": name, "active": bool(item.get("active", True)), "subroles": []}
                    )
        blockers = [QtCore.QSignalBlocker(self.names), QtCore.QSignalBlocker(self.names.model())]
        try:
            self.names.clear()
            if not normalized:
                self.names.add_name("")
            for entry in normalized:
                self.names.add_name(entry["name"], active=entry["active"])
        finally:
            del blockers
        if hasattr(self, "names_panel"):
            self.names_panel.refresh_action_state()
        self._apply_fixed_widths()

    def _on_names_changed(self, *args):
        self.stateChanged.emit()
