from __future__ import annotations

from typing import List, Optional
from PySide6 import QtCore, QtWidgets, QtGui

import i18n
from utils import theme as theme_util
from view import style_helpers
from view.name_list import NamesListPanel


class ListPanel(QtWidgets.QWidget):
    """
    List-only Variante eines Wheel-Panels (für Map-Listen).
    Bietet Spin-/Include-Buttons und eine Namensliste, aber kein Rad.
    """

    stateChanged = QtCore.Signal()
    request_spin = QtCore.Signal()

    def __init__(self, title: str, entries: List[dict] | List[str]):
        super().__init__()
        self.pair_mode = False
        self.use_subrole_filter = False
        self._title = title

        self.card = QtWidgets.QFrame()
        self.card.setObjectName("card")

        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.card)

        inner = QtWidgets.QVBoxLayout(self.card)
        inner.setContentsMargins(16, 12, 16, 12)
        inner.setSpacing(10)

        self.label = QtWidgets.QLabel(title)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet("font-size:18px; font-weight:800; letter-spacing:0.3px;")
        inner.addWidget(self.label)

        # Buttons: Spin + Include
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_local_spin = QtWidgets.QPushButton(i18n.t("wheel.spin_single_map"))
        self.btn_local_spin.setFixedHeight(36)
        self.btn_local_spin.clicked.connect(self.request_spin.emit)

        self.btn_include_in_all = QtWidgets.QPushButton()
        self.btn_include_in_all.setCheckable(True)
        self.btn_include_in_all.setChecked(True)
        self.btn_include_in_all.setFixedHeight(36)
        self.btn_include_in_all.toggled.connect(self._on_include_toggled)
        btn_row.addWidget(self.btn_local_spin, 1)
        btn_row.addWidget(self.btn_include_in_all, 0)
        inner.addLayout(btn_row)

        # Hint + Liste
        self.names_hint = QtWidgets.QLabel(i18n.t("wheel.names_hint_single"))
        self.names_hint.setStyleSheet("color:#444; font-size:12px; padding:2px;")
        inner.addWidget(self.names_hint)

        self.names_panel = NamesListPanel()
        self.names = self.names_panel.names
        self.btn_sort_names = self.names_panel.btn_sort_names
        self.btn_toggle_all_names = self.names_panel.btn_toggle_all_names
        inner.addWidget(self.names_panel)

        # Populate list
        self.load_entries(entries)
        self.names.itemChanged.connect(self._on_names_changed)
        self.names.model().rowsInserted.connect(self._on_names_changed)
        self.names.model().rowsRemoved.connect(self._on_names_changed)
        self.names.metaChanged.connect(self._on_names_changed)

        self._apply_fixed_widths()
        self.apply_theme(theme_util.get_theme("light"))

    # --- API kompatibel zu WheelView für Map-Mode ---
    def set_language(self, lang: str):
        i18n.set_language(lang)
        self.btn_local_spin.setText(i18n.t("wheel.spin_single_map"))
        if hasattr(self, "names_panel"):
            self.names_panel.set_language(lang)
        self.btn_include_in_all.setText(self._include_label())
        self.names_hint.setText(i18n.t("wheel.names_hint_single"))
        self._apply_fixed_widths()

    def set_spin_button_text(self, text: str):
        self.btn_local_spin.setText(text)
        self._apply_fixed_widths()

    def set_interactive_enabled(self, en: bool):
        self.names.setEnabled(en)
        self.btn_local_spin.setEnabled(en)
        self.btn_include_in_all.setEnabled(en)
        if hasattr(self, "btn_sort_names"):
            self.btn_sort_names.setEnabled(en)
        if hasattr(self, "btn_toggle_all_names"):
            self.btn_toggle_all_names.setEnabled(en)

    def get_current_entries(self) -> List[dict]:
        entries: list[dict] = []
        for i in range(self.names.count()):
            item = self.names.item(i)
            text = self.names.itemWidget(item).edit.text().strip() if item else ""
            if not text:
                continue
            active = item.checkState() == QtCore.Qt.Checked
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

    def apply_theme(self, theme: theme_util.Theme):
        self.card.setStyleSheet(
            "#card { "
            f"background: {theme.card_bg}; "
            f"border:1px solid {theme.card_border}; border-radius:16px; }}"
        )
        self.label.setStyleSheet(
            "font-size:18px; font-weight:800; letter-spacing:0.3px; "
            f"color:{theme.text};"
        )
        self.names_hint.setStyleSheet(f"color:{theme.muted_text}; font-size:12px; padding:2px;")
        style_helpers.style_primary_button(self.btn_local_spin, theme)
        style_helpers.style_include_button(self.btn_include_in_all, theme)
        if hasattr(self, "names_panel"):
            self.names_panel.apply_theme(theme)

    def _on_names_changed(self, *args):
        self.stateChanged.emit()

    def _on_include_toggled(self, checked: bool):
        self.btn_include_in_all.setText(self._include_label())
        self.stateChanged.emit()

    def _include_label(self) -> str:
        prefix = "☑" if self.btn_include_in_all.isChecked() else "☐"
        return f"{prefix} {i18n.t('wheel.include_prefix')}"

    def _apply_fixed_widths(self):
        """Fixe Breiten für Buttons analog WheelView, damit Sprache nicht springt."""
        def set_min(widget, keys, padding=20, prefixes=None):
            if widget is None:
                return
            prefixes_local = prefixes or [""]
            font = widget.font()
            fm = QtGui.QFontMetrics(font)
            max_w = 0
            for key in keys:
                entry = i18n.TRANSLATIONS.get(key, {})
                texts = entry.values() if isinstance(entry, dict) else [entry]
                for txt in texts:
                    if txt is None:
                        continue
                    for pre in prefixes_local:
                        max_w = max(max_w, fm.horizontalAdvance(f"{pre}{txt}"))
            width = max_w + padding
            widget.setMinimumWidth(width)
            widget.setMaximumWidth(width)

        set_min(self.btn_local_spin, ["wheel.spin_role", "wheel.spin_map", "wheel.spin_single_map"], padding=44)
        set_min(self.btn_include_in_all, ["wheel.include_prefix"], padding=42, prefixes=["☑ ", "☐ "])
        if hasattr(self, "names_panel"):
            self.names_panel.apply_fixed_widths()
        self.btn_include_in_all.setText(self._include_label())
