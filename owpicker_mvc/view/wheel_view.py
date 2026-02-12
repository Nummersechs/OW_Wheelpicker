from contextlib import contextmanager
from typing import List, Optional, Union
from PySide6 import QtCore, QtWidgets
from view.base_panel import BasePanel
from view.wheel_widget import WheelWidget
from view.name_list import NameRowWidget
from view import wheel_entries_ops, wheel_spin_ops
from model.wheel_state import WheelState
import i18n
from utils import qt_runtime, theme as theme_util, ui_helpers

class WheelView(BasePanel):
    spun = QtCore.Signal(str)
    def __init__(self, title: str, defaults: List[str], pair_mode=False, allow_pair_toggle=False, subrole_labels: Optional[List[str]] = None, title_key: Optional[str] = None):
        self.pair_mode = pair_mode
        self.allow_pair_toggle = allow_pair_toggle
        self._is_spinning = False
        self.use_subrole_filter = False
        default_spin_label = i18n.t("wheel.spin_role")
        super().__init__(
            title=title,
            spin_label=default_spin_label,
            names_hint_text="",
            subrole_labels=subrole_labels,
            title_key=title_key,
            header_mode="custom",
        )
        self._default_spin_label = default_spin_label
        self._custom_spin_label: Optional[str] = None
        self._suppress_wheel_render = False
        self._suppress_state_signal = False
        self._force_spin_enabled = False
        self._wheel_state = WheelState(
            pair_mode=self.pair_mode,
            use_subrole_filter=self.use_subrole_filter,
            subrole_labels=self.subrole_labels,
        )
        self._entries_cache: dict[str, list] | None = None
        self._subrole_controls_visible = True
        self._header_controls_visible = True
        self._show_names_visible = True
        self._names_change_timer: QtCore.QTimer | None = None
        self._subrole_visibility_applied: tuple[bool, int] | None = None
        self._tooltip_rev = 0
        self._wheel_overlay_widget: QtWidgets.QWidget | None = None
        self._wheel_overlay_margin_top = 8
        self._wheel_overlay_margin_right = 8
        self.view = WheelWidget(self._effective_names_from(defaults))
        self.view.viewport().installEventFilter(self)
        self.view.segmentToggled.connect(self._on_segment_toggled)
        self.wheel = self.view.wheel
        self._wheel_state.last_wheel_names = list(self.wheel.names)
        self._result_state: str = "empty"  # empty | value | too_few
        self._result_value: Optional[str] = None

        header = self.header_layout
        header.setContentsMargins(0, 0, 0, 0)

        self.btn_reset_segments = QtWidgets.QToolButton()
        self.btn_reset_segments.setText("↺")
        self.btn_reset_segments.setToolTip(i18n.t("wheel.reset_disabled_tooltip"))
        self.btn_reset_segments.setAutoRaise(True)
        self.btn_reset_segments.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_reset_segments.setFixedSize(30, 30)
        self.btn_reset_segments.clicked.connect(self.reset_disabled_segments)
        self._update_reset_button_state()

        header.addWidget(self.btn_reset_segments, 0, QtCore.Qt.AlignVCenter)
        header.addStretch(1)
        header.addWidget(self.label)
        header.addStretch(1)

        self.toggle = None
        if allow_pair_toggle:
            self.toggle = QtWidgets.QCheckBox(i18n.t("wheel.pairs_toggle"))
            self.toggle.setChecked(self.pair_mode)
            self.toggle.stateChanged.connect(self._on_toggle_pair_mode)
            header.setSpacing(12)
            header.addWidget(self.toggle, 0, QtCore.Qt.AlignVCenter)
        self.chk_subroles = None
        if self.subrole_labels and allow_pair_toggle:
            self.chk_subroles = QtWidgets.QCheckBox(i18n.t("wheel.subroles_toggle"))
            self.chk_subroles.setChecked(False)
            hint = i18n.t("wheel.subroles_hint_generic")
            if len(self.subrole_labels) >= 2:
                hint = i18n.t(
                    "wheel.subroles_hint_labels",
                    a=self.subrole_labels[0],
                    b=self.subrole_labels[1],
                )
            self.chk_subroles.setToolTip(hint)
            self.chk_subroles.setEnabled(self.pair_mode)
            self.chk_subroles.stateChanged.connect(self._on_toggle_subroles)
            header.addWidget(self.chk_subroles, 0, QtCore.Qt.AlignVCenter)

        # Optional: Checkbox "Namen anzeigen" im Header
        self.chk_show_names = QtWidgets.QCheckBox(i18n.t("wheel.show_names"))
        self.chk_show_names.setChecked(True)
        self.chk_show_names.stateChanged.connect(self._on_toggle_show_names)
        header.addWidget(self.chk_show_names, 0, QtCore.Qt.AlignVCenter)

        # ---------- Ergebnis-Widget: Label + Löschen-Icon ----------
        self.result = QtWidgets.QLabel("–")
        # Text links, vertikal mittig
        self.result.setAlignment(QtCore.Qt.AlignCenter)
        self.result.setStyleSheet(
            "font-size:14px; color:#666; margin-top:6px;"
        )

        self.btn_clear_result = QtWidgets.QToolButton()
        self.btn_clear_result.setText("✖")
        self.btn_clear_result.setToolTip(i18n.t("wheel.clear_result_tooltip"))
        self.btn_clear_result.setAutoRaise(True)  # kein blauer Button, nur Icon
        self.btn_clear_result.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_clear_result.setStyleSheet("""
            QToolButton {
                background: transparent;
                border: none;
                color: #b00020;
                font-size: 14px;
            }
            QToolButton:hover {
                color: #ff1744;
            }
        """)
        self.btn_clear_result.clicked.connect(self._clear_result)
        self.btn_clear_result.setVisible(False)  # nur zeigen, wenn Ergebnis da ist

        # Container-Widget für Ergebnis + Icon
        self.result_widget = QtWidgets.QWidget()
        result_layout = QtWidgets.QHBoxLayout(self.result_widget)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(4)

        # [ Stretch | Ergebnis | X | Stretch ]
        result_layout.addStretch(1)
        result_layout.addWidget(self.result, 0, QtCore.Qt.AlignVCenter)
        result_layout.addSpacing(4)
        result_layout.addWidget(self.btn_clear_result, 0, QtCore.Qt.AlignVCenter)
        result_layout.addStretch(1)

        self.add_body_widget(self.view, 1)
        self.add_body_widget(self.result_widget)

        # Start-Namen anlegen – neue Namen sind standardmäßig aktiv (Checked)
        for entry in self._normalize_entries(defaults):
            self.names.add_name(
                entry["name"],
                subroles=entry.get("subroles", []),
                active=entry.get("active", True),
            )
        
        # Falls gar keine Defaults/Saved Names vorhanden sind, eine leere Zeile hinzufügen
        if self.names.count() == 0:
            self.names.add_name("")

        # Änderungen an Text oder Häkchen überwachen
        self.names.itemChanged.connect(self._on_names_list_changed)
        self.names.model().rowsInserted.connect(self._on_names_list_changed)
        self.names.model().rowsRemoved.connect(self._on_names_list_changed)
        self.names.metaChanged.connect(self._on_names_list_changed)
        # Neue Zeilen sollen sofort die korrekte Sichtbarkeit der Subrollen übernehmen
        self.names.model().rowsInserted.connect(lambda *_: self._apply_subrole_visibility())
        self.btn_include_in_all.setToolTip(i18n.t("wheel.include_tooltip"))
        self._apply_fixed_widths()
        
        # Checkbox-Styling konsistent halten
        self.setStyleSheet("""
            QCheckBox::indicator,
            QListView::indicator {
                width: 6px;
                height: 6px;
                border: 2px solid black;
                border-radius: 3px;
                background: white;
            }

            QCheckBox::indicator:checked,
            QListView::indicator:checked {
                background: black;
            }
        """)

        # Startwert für Namensanzahl merken und UI initial justieren
        self._last_name_count = len(self._base_names())
        self._update_name_dependent_ui()
        self._apply_placeholder()
        self._apply_result_state()

        # Default theme; main window reapplies the persisted choice.
        self.apply_theme(theme_util.get_theme("light"))
        QtCore.QTimer.singleShot(0, self._refit_view)

    def set_wheel_overlay_widget(
        self,
        widget: QtWidgets.QWidget,
        *,
        margin_top: int = 8,
        margin_right: int = 8,
    ) -> None:
        if widget is None:
            return
        self._wheel_overlay_widget = widget
        self._wheel_overlay_margin_top = max(0, int(margin_top))
        self._wheel_overlay_margin_right = max(0, int(margin_right))
        widget.setParent(self.view.viewport())
        widget.show()
        qt_runtime.safe_raise(widget)
        widget.installEventFilter(self)
        QtCore.QTimer.singleShot(0, self._position_wheel_overlay_widget)

    def _position_wheel_overlay_widget(self) -> None:
        widget = self._wheel_overlay_widget
        if widget is None:
            return
        viewport = self.view.viewport()
        x = max(0, viewport.width() - widget.width() - self._wheel_overlay_margin_right)
        y = max(0, self._wheel_overlay_margin_top)
        widget.move(x, y)
        qt_runtime.safe_raise(widget)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent):
        if obj is self.view.viewport() and event.type() in (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
            QtCore.QEvent.LayoutRequest,
        ):
            QtCore.QTimer.singleShot(0, self._position_wheel_overlay_widget)
        elif obj is self._wheel_overlay_widget and event.type() in (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
        ):
            QtCore.QTimer.singleShot(0, self._position_wheel_overlay_widget)
        return super().eventFilter(obj, event)

    @contextmanager
    def _suspend_list_signals(self):
        blockers = [
            QtCore.QSignalBlocker(self.names),
            QtCore.QSignalBlocker(self.names.model()),
        ]
        prev = self._suppress_state_signal
        self._suppress_state_signal = True
        try:
            yield prev
        finally:
            del blockers
            self._suppress_state_signal = prev

    def _ensure_entries_cache(self) -> None:
        if self._entries_cache is None:
            self._rebuild_entries_cache()

    def _rebuild_entries_cache(self) -> None:
        self._entries_cache = wheel_entries_ops.rebuild_entries_cache(self.names)

    def set_language(self, lang: str):
        """Reapply translated labels for the current wheel."""
        super().set_language(lang)
        self._default_spin_label = i18n.t("wheel.spin_role")
        if self.toggle:
            self.toggle.setText(i18n.t("wheel.pairs_toggle"))
        if self.chk_subroles:
            self.chk_subroles.setText(i18n.t("wheel.subroles_toggle"))
            hint = i18n.t("wheel.subroles_hint_generic")
            if len(self.subrole_labels) >= 2:
                hint = i18n.t(
                    "wheel.subroles_hint_labels",
                    a=self.subrole_labels[0],
                    b=self.subrole_labels[1],
                )
            self.chk_subroles.setToolTip(hint)
        if self.chk_show_names:
            self.chk_show_names.setText(i18n.t("wheel.show_names"))
        if hasattr(self, "btn_reset_segments"):
            self.btn_reset_segments.setToolTip(i18n.t("wheel.reset_disabled_tooltip"))
        self.btn_clear_result.setToolTip(i18n.t("wheel.clear_result_tooltip"))
        self.btn_include_in_all.setToolTip(i18n.t("wheel.include_tooltip"))
        if self._custom_spin_label is None:
            self.set_spin_button_text(None)
        self._apply_placeholder()
        self._apply_result_state()
        self._apply_fixed_widths()

    def _refit_view(self):
        """Reicht Größenanpassung an das WheelWidget weiter."""
        if hasattr(self, "view") and hasattr(self.view, "_refit_view"):
            self.view._refit_view()

    def _apply_result_state(self):
        """Render the current result state with translated labels."""
        if self._result_state == "value" and self._result_value is not None:
            self.result.setText(i18n.t("wheel.result_prefix", result=self._result_value))
        elif self._result_state == "too_few":
            self.result.setText(i18n.t("wheel.result_too_few"))
        else:
            self.result.setText("–")
        self._update_clear_button_enabled()

    def _apply_fixed_widths(self):
        """Set fixed widths based on max translation to avoid layout jumps."""
        super()._apply_fixed_widths()
        if self.toggle:
            ui_helpers.set_fixed_width_from_translations(
                self.toggle,
                ["wheel.pairs_toggle"],
                padding=30,
            )
        if self.chk_subroles:
            ui_helpers.set_fixed_width_from_translations(
                self.chk_subroles,
                ["wheel.subroles_toggle"],
                padding=30,
            )
        if self.chk_show_names:
            ui_helpers.set_fixed_width_from_translations(
                self.chk_show_names,
                ["wheel.show_names"],
                padding=30,
            )

    def apply_theme(self, theme: theme_util.Theme) -> None:
        """Apply color palette for the active theme to this wheel."""
        super().apply_theme(theme)
        self.result.setStyleSheet(f"font-size:14px; color:{theme.muted_text}; margin-top:6px;")
        # Indicator styling stays aligned with the active theme colors.
        self.setStyleSheet(
            f"""
            QCheckBox::indicator,
            QListView::indicator {{
                width: 6px;
                height: 6px;
                border: 2px solid {theme.text};
                border-radius: 3px;
                background: {theme.base};
            }}

            QCheckBox::indicator:checked,
            QListView::indicator:checked {{
                background: {theme.primary};
            }}

            /* Scrollbar-Farben im aktiven Theme halten */
            QScrollBar:vertical {{
                background:{theme.frame_bg};
                width:12px;
                margin:2px;
                border-radius:6px;
            }}
            QScrollBar::handle:vertical {{
                background:{theme.slider_handle};
                min-height:24px;
                border-radius:6px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height:0px;
                background:transparent;
            }}
            QScrollBar::sub-page:vertical,
            QScrollBar::add-page:vertical {{
                background:{theme.slider_groove};
                border-radius:6px;
            }}
            QScrollBar:horizontal {{
                background:{theme.frame_bg};
                height:12px;
                margin:2px;
                border-radius:6px;
            }}
            QScrollBar::handle:horizontal {{
                background:{theme.slider_handle};
                min-width:24px;
                border-radius:6px;
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width:0px;
                background:transparent;
            }}
            QScrollBar::sub-page:horizontal,
            QScrollBar::add-page:horizontal {{
                background:{theme.slider_groove};
                border-radius:6px;
            }}
            """
        )
        if hasattr(self, "btn_reset_segments"):
            tool_style = theme_util.tool_button_stylesheet(theme)
            self.btn_reset_segments.setStyleSheet(
                f"{tool_style} "
                f"QToolButton {{ color:{theme.primary}; background:{theme.base}; "
                f"border:1px solid {theme.primary}; border-radius:6px; }} "
                f"QToolButton:disabled {{ color:{theme.disabled_text}; background:{theme.alt_base}; "
                f"border:1px solid {theme.border}; border-radius:6px; }}"
            )

    def set_result_value(self, value: str):
        self._result_state = "value"
        self._result_value = value
        self._apply_result_state()

    def set_result_too_few(self):
        self._result_state = "too_few"
        self._result_value = None
        self._apply_result_state()

    def clear_result(self):
        self._result_state = "empty"
        self._result_value = None
        self._apply_result_state()

    def get_result_value(self) -> Optional[str]:
        return self._result_value if self._result_state == "value" else None

    def tooltip_revision(self) -> int:
        """Monotonic revision for tooltip cache invalidation."""
        return self._tooltip_rev

    def _pair_parts_from_label(self, label: str) -> list[str]:
        return self._wheel_state.pair_parts_from_label(label)

    def result_label_names(self, label: str) -> list[str]:
        """Return the underlying name(s) for a result label."""
        return self._wheel_state.label_names(label)

    @property
    def _override_entries(self) -> Optional[List[dict]]:
        return self._wheel_state.override_entries

    @_override_entries.setter
    def _override_entries(self, entries: Optional[List[dict]]) -> None:
        self.set_override_entries(entries)

    @property
    def _disabled_indices(self) -> set[int]:
        return set(self._wheel_state.disabled_indices)

    @_disabled_indices.setter
    def _disabled_indices(self, value: Optional[set[int]]) -> None:
        self._wheel_state.disabled_indices = set(value or [])

    @property
    def _disabled_labels(self) -> set[str]:
        return set(self._wheel_state.disabled_labels)

    def deactivate_names(self, names: set[str]) -> bool:
        """Uncheck matching names in the list so they drop from active selection."""
        if not names:
            return False
        targets = {n.strip() for n in names if isinstance(n, str) and n.strip()}
        if not targets:
            return False
        changed = False
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            text = self._item_text(item)
            if not text or text not in targets:
                continue
            widget = self.names.itemWidget(item)
            if isinstance(widget, NameRowWidget):
                if widget.chk_active.isChecked():
                    widget.chk_active.setChecked(False)
                    changed = True
            else:
                if item.checkState() == QtCore.Qt.Checked:
                    item.setCheckState(QtCore.Qt.Unchecked)
                    changed = True
        return changed

    def add_name(self, name: str, active: bool = True, subroles: Optional[List[str]] = None) -> bool:
        """Add a name if missing; returns True if it changed."""
        name = str(name or "").strip()
        if not name:
            return False
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            if self._item_text(item) == name:
                if active:
                    return self.set_names_active({name}, True)
                return False
        with self._suspend_list_signals() as prev:
            self.names.add_name(name, subroles=subroles or [], active=active)
            self._apply_names_list_changes()
        if not prev:
            self.stateChanged.emit()
        return True

    def remove_names(self, names: set[str]) -> bool:
        """Remove matching names from the list."""
        targets = {n.strip() for n in names if isinstance(n, str) and n.strip()}
        if not targets:
            return False
        changed = False
        with self._suspend_list_signals() as prev:
            for i in range(self.names.count() - 1, -1, -1):
                item = self.names.item(i)
                if item is None:
                    continue
                if self._item_text(item) in targets:
                    self.names.delete_row(i)
                    changed = True
            if changed:
                self._apply_names_list_changes()
        if changed and not prev:
            self.stateChanged.emit()
        return changed

    def rename_name(self, old: str, new: str) -> bool:
        """Rename a name in the list while keeping its state/subroles."""
        old = str(old or "").strip()
        new = str(new or "").strip()
        if not old or not new or old == new:
            return False
        changed = False
        with self._suspend_list_signals() as prev:
            for i in range(self.names.count()):
                item = self.names.item(i)
                if item is None:
                    continue
                if self._item_text(item) != old:
                    continue
                widget = self.names.itemWidget(item)
                if isinstance(widget, NameRowWidget):
                    widget.edit.setText(new)
                item.setText(new)
                changed = True
            if changed:
                self._apply_names_list_changes()
        if changed and not prev:
            self.stateChanged.emit()
        return changed

    def set_names_active(self, names: set[str], active: bool) -> bool:
        """Set active state for matching names in the list."""
        if not names:
            return False
        targets = {n.strip() for n in names if isinstance(n, str) and n.strip()}
        if not targets:
            return False
        changed = False
        with self._suspend_list_signals() as prev:
            for i in range(self.names.count()):
                item = self.names.item(i)
                if item is None:
                    continue
                text = self._item_text(item)
                if not text or text not in targets:
                    continue
                widget = self.names.itemWidget(item)
                target_state = QtCore.Qt.Checked if active else QtCore.Qt.Unchecked
                if isinstance(widget, NameRowWidget):
                    if widget.chk_active.isChecked() != active:
                        widget.chk_active.setChecked(active)
                        changed = True
                else:
                    if item.checkState() != target_state:
                        item.setCheckState(target_state)
                        changed = True
            if changed:
                self._apply_names_list_changes()
        if changed and not prev:
            self.stateChanged.emit()
        return changed

    def disable_label(self, label: str) -> bool:
        """Disable a segment by its label (returns True if it was newly disabled)."""
        if not label:
            return False
        names = list(getattr(self.wheel, "names", []))
        if not names:
            return False
        changed = self._wheel_state.disable_label(names, label, include_related_pairs=False)
        if changed:
            self._refresh_disabled_indices()
            self.stateChanged.emit()
        return changed

    def disable_label_with_related_pairs(self, label: str) -> bool:
        """Disable the label and all other pair segments that share a name."""
        if not label:
            return False
        names = list(getattr(self.wheel, "names", []))
        if not names:
            return False
        changed = self._wheel_state.disable_label(names, label, include_related_pairs=True)
        if changed:
            self._refresh_disabled_indices()
            self.stateChanged.emit()
        return changed

    def disable_current_result(self, include_related: bool = False) -> bool:
        """Disable the currently selected result segment, if any."""
        label = self.get_result_value() or ""
        if include_related:
            return self.disable_label_with_related_pairs(label)
        return self.disable_label(label)

    def reset_disabled_segments(self) -> None:
        """Re-enable all segments on this wheel."""
        self._wheel_state.reset_disabled()
        self._refresh_disabled_indices()
        self.stateChanged.emit()

    def get_result_payload(self) -> dict:
        return {"state": self._result_state, "value": self._result_value}

    def apply_result_payload(self, payload: Optional[dict]):
        if not payload:
            self.clear_result()
            return
        state = payload.get("state")
        value = payload.get("value")
        if state == "value" and isinstance(value, str):
            self.set_result_value(value)
        elif state == "too_few":
            self.set_result_too_few()
        else:
            self.clear_result()

    def _apply_placeholder(self):
        tooltip_key = "wheel.tooltip_pairs" if self.pair_mode else "wheel.tooltip_single"
        self.result.setToolTip(i18n.t(tooltip_key))

        if self.pair_mode:
            if self.use_subrole_filter and len(self.subrole_labels) >= 2:
                self.names_hint.setText(
                    i18n.t(
                        "wheel.names_hint_pairs_subroles",
                        a=self.subrole_labels[0],
                        b=self.subrole_labels[1],
                    )
                )
            else:
                self.names_hint.setText(i18n.t("wheel.names_hint_pairs"))
        else:
            self.names_hint.setText(i18n.t("wheel.names_hint_single"))

    def get_current_names(self) -> list[str]:
        """Liefert alle aktuell eingetragenen Namen (ohne Leerzeilen)."""
        return self._base_names()
    def get_current_entries(self) -> list[dict]:
        """
        Liefert alle Einträge (auch inaktive) mit Subrollen.
        Struktur: {"name": str, "subroles": [str], "active": bool}
        """
        self._ensure_entries_cache()
        return list(self._entries_cache["entries"]) if self._entries_cache else []
    def set_override_entries(self, entries: Optional[List[dict]]):
        """
        Externe Einträge für das Rad setzen (z.B. im Hero-Ban).
        Die sichtbare Namensliste bleibt unverändert.
        """
        if entries is None and self._wheel_state.override_entries is None:
            return
        if entries is not None and self._wheel_state.override_entries is not None:
            if entries == self._wheel_state.override_entries:
                return
        self._wheel_state.set_override_entries(entries)
        self._apply_override()
    def get_effective_wheel_names(self, include_disabled: bool = True) -> List[str]:
        """
        Liefert die aktuell vom Rad genutzten Namen (Override falls gesetzt).
        """
        base_entries = (
            self._wheel_state.override_entries
            if self._wheel_state.override_entries is not None
            else self._active_entries()
        )
        return self._effective_names_from(base_entries, include_disabled=include_disabled)
    def _item_text(self, item: QtWidgets.QListWidgetItem) -> str:
        return wheel_entries_ops.item_text(self.names, item)

    def _item_subroles(self, item: QtWidgets.QListWidgetItem) -> set[str]:
        return wheel_entries_ops.item_subroles(self.names, item)
    def _base_names(self) -> List[str]:
        """Alle Namen aus der Liste (ohne Leerzeilen, Häkchen egal)."""
        self._ensure_entries_cache()
        return list(self._entries_cache["base_names"]) if self._entries_cache else []

    def _active_entries(self) -> List[dict]:
        """
        Nur die aktivierten Namen inklusive Subrollen-Auswahl.
        Rückgabe-Element: {"name": str, "subroles": set[str]}
        """
        self._ensure_entries_cache()
        return list(self._entries_cache["active_entries"]) if self._entries_cache else []

    def _entries_for_spin(self) -> List[dict]:
        """Nutzt Override-Einträge, falls gesetzt, sonst die aktiven Einträge."""
        return self._wheel_state.entries_for_spin(self._active_entries())

    def _active_names(self) -> List[str]:
        self._ensure_entries_cache()
        return list(self._entries_cache["active_names"]) if self._entries_cache else []

    def _on_names_list_changed(self, *args):
        """Wenn Namen geändert, hinzugefügt oder entfernt werden (debounced)."""
        if self._names_change_timer is None:
            self._names_change_timer = QtCore.QTimer(self)
            self._names_change_timer.setSingleShot(True)
            self._names_change_timer.timeout.connect(self._apply_names_list_changes)
        if not self._names_change_timer.isActive():
            # Debounce to avoid repeated heavy rebuilds while typing.
            self._names_change_timer.start(30)

    def _apply_names_list_changes(self):
        """Apply list changes immediately (heavy path)."""
        if self._names_change_timer is not None and self._names_change_timer.isActive():
            self._names_change_timer.stop()
        self._rebuild_entries_cache()
        if self._wheel_state.override_entries is not None:
            # Override bestimmt das Rad – sichtbare Liste nur Anzeige
            self._apply_override()
            if not self._suppress_state_signal:
                self.stateChanged.emit()
            return
        old_names = list(self._wheel_state.last_wheel_names)
        active_entries = list(self._entries_cache.get("active_entries", [])) if self._entries_cache else []
        new_names = self._effective_names_from(active_entries, include_disabled=True)
        # Rad mit aktiven Namen aktualisieren
        if getattr(self, "_suppress_wheel_render", False):
            if getattr(self.wheel, "names", []):
                self.wheel.set_names([])
            self._rebuild_disabled_indices([], [])
        else:
            current_wheel_names = list(getattr(self.wheel, "names", []))
            if new_names != old_names or new_names != current_wheel_names:
                self.wheel.set_names(new_names)
                self._rebuild_disabled_indices(old_names, new_names)
        self._refresh_disabled_indices()
        self._update_name_dependent_ui()
        self._wheel_state.last_wheel_names = list(new_names)
        self._apply_subrole_visibility()
        self._tooltip_rev += 1
        if not self._suppress_state_signal:
            self.stateChanged.emit()

    def _effective_names_from(self, base: Union[List[dict], List[str]], include_disabled: bool = True) -> List[str]:
        """
        Liefert die Labels, die tatsächlich auf dem Rad landen.
        Nutzt Subrollen-Filter, falls aktiviert.
        """
        return self._wheel_state.effective_names_from(base, include_disabled=include_disabled)
    def _apply_subrole_visibility(self):
        """Blendet Subrollen-Checkboxen in den Zeilen ein/aus."""
        desired = (self._subrole_controls_visible, self.names.count())
        if self._subrole_visibility_applied == desired:
            return
        self._subrole_visibility_applied = desired
        wheel_entries_ops.apply_subrole_visibility(self.names, self._subrole_controls_visible)
    def _apply_override(self):
        """Wendet die Override-Liste auf das Rad an, ohne die sichtbare Liste zu ändern."""
        if self._wheel_state.override_entries is None:
            # Zurück zum normalen Rendering basierend auf der Liste
            self._apply_names_list_changes()
            return
        names = self._effective_names_from(self._wheel_state.override_entries, include_disabled=True)
        old_names = list(getattr(self.wheel, "names", []))
        if names != old_names:
            # Bei neuem Override: deaktivierte Segmente zurücksetzen, damit Indizes passen
            self._wheel_state.reset_disabled()
            self.wheel.set_names(names)
            self._wheel_state.last_wheel_names = list(names)
        self._refresh_disabled_indices()
        self._tooltip_rev += 1

    def _on_segment_toggled(self, idx: int, disabled: bool, label: str):
        if disabled:
            self._wheel_state.disabled_indices.add(idx)
        else:
            self._wheel_state.disabled_indices.discard(idx)
        self._refresh_disabled_indices()
        self.stateChanged.emit()

    def _enabled_labels(self) -> set[str]:
        names = list(getattr(self.wheel, "names", []))
        return self._wheel_state.enabled_labels(names)

    def _rebuild_disabled_indices(self, old_names: List[str], new_names: List[str]):
        """
        Überträgt deaktivierte Segmente auf die neue Namensliste, wenn Einträge
        entfernt oder hinzugefügt wurden. Deaktivierte Einträge, die nicht mehr
        existieren, fallen dabei weg.
        """
        self._wheel_state.remap_disabled_indices(old_names, new_names)

    def _refresh_disabled_indices(self):
        names = list(getattr(self.wheel, "names", []))
        if not names:
            if self._wheel_state.disabled_indices or self._wheel_state.disabled_labels:
                self._wheel_state.reset_disabled()
            self._update_reset_button_state()
            return
        # Nur valide Indizes behalten
        self._wheel_state.sanitize_disabled_indices(names)
        desired = set(self._wheel_state.disabled_indices)
        current = set(getattr(self.wheel, "disabled_indices", set()))
        if desired != current:
            self.wheel.set_disabled_indices(desired)
        self._update_reset_button_state()

    def _update_reset_button_state(self):
        if hasattr(self, "btn_reset_segments"):
            self.btn_reset_segments.setEnabled(bool(self._wheel_state.disabled_indices))

    def _on_names_changed(self):
        # Kompatibilitäts-Methode, falls sie anderswo noch aufgerufen wird
        self._apply_names_list_changes()

    def _on_toggle_pair_mode(self, _state: int):
        self.pair_mode = bool(self.toggle.isChecked())
        self._wheel_state.pair_mode = self.pair_mode
        if not self.pair_mode and self.chk_subroles:
            self.chk_subroles.setChecked(False)
        # Wechsel des Modus → Disabled-Segmente zurücksetzen
        self._wheel_state.reset_disabled()
        self._update_subrole_toggle_state()
        self._apply_placeholder()
        self._on_names_changed()
        self._tooltip_rev += 1
        self.stateChanged.emit()
    def _on_toggle_show_names(self, _state: int):
        show = bool(self.chk_show_names.isChecked())
        self.wheel.set_show_labels(show)
        self._tooltip_rev += 1
        self.stateChanged.emit()
    def _on_toggle_subroles(self, _state: int):
        self.use_subrole_filter = bool(self.pair_mode and self.chk_subroles and self.chk_subroles.isChecked())
        self._wheel_state.use_subrole_filter = self.use_subrole_filter
        # Subrollenwechsel → Disabled-Segmente zurücksetzen
        self._wheel_state.reset_disabled()
        self._apply_placeholder()
        self._on_names_changed()
        self._tooltip_rev += 1
        self.stateChanged.emit()
    def set_interactive_enabled(self, en: bool):
        # Statt self.edit:
        self.names.setEnabled(en)
        # Optional, wenn du während des globalen Spins auch das Rad selbst sperren willst:
        # self.view.setEnabled(en)

        if en:
            # Wenn allgemein aktiv → Feinsteuerung über _update_name_dependent_ui
            self._update_name_dependent_ui()
            if hasattr(self, "view") and hasattr(self.view, "_rearm_hover_tracking"):
                try:
                    self.view._rearm_hover_tracking()
                except Exception:
                    pass
        else:
            # Alles aus, wenn global deaktiviert
            self.btn_local_spin.setEnabled(False)
            if self.toggle:
                self.toggle.setEnabled(False)
            if hasattr(self, "btn_include_in_all"):
                self.btn_include_in_all.setEnabled(False)
    def is_selected_for_global_spin(self) -> bool:
        """Ob dieses Rad beim globalen Spin ('Drehen') mitgedreht werden soll."""
        return getattr(self, "btn_include_in_all", None) is None or self.btn_include_in_all.isChecked()
    def is_anim_running(self) -> bool:
        return hasattr(self, "anim") and self.anim.state() == QtCore.QAbstractAnimation.Running
    def hard_stop(self):
        if hasattr(self, "anim"):
            try:
                if self.is_anim_running(): self.anim.stop()
            finally:
                self.anim.deleteLater(); delattr(self, "anim")
        self._is_spinning = False
    def spin(self, duration_ms: int = 2500):
        if self._is_spinning and self.is_anim_running():
            return None
        
        # Sobald ein neues Spin startet, alte Auswahl löschen
        self.clear_result()

        base_entries = self._entries_for_spin()
        names = self._effective_names_from(base_entries, include_disabled=True)
        enabled_indices = self._wheel_state.enabled_indices(names)
        if (self.pair_mode and len(base_entries) < 2) or not enabled_indices:
            self.set_result_too_few()
            return None
        duration_ms = max(1, int(duration_ms))
        return wheel_spin_ops.spin_to_label(
            self,
            names,
            enabled_indices,
            duration_ms=duration_ms,
        )
    def spin_to_name(self, target_name: str, duration_ms: int = 2500):
        """Spinnt das Rad gezielt auf einen bestimmten Namen.

        Falls der Name im aktuellen Rad nicht vorkommt, fällt die Methode auf
        das normale Zufalls-Spin zurück.
        """
        if self._is_spinning and self.is_anim_running():
            return None

        # Sobald ein neues Spin startet, alte Auswahl löschen
        self.clear_result()

        base_entries = self._entries_for_spin()
        names = self._effective_names_from(base_entries, include_disabled=True)
        enabled_indices = self._wheel_state.enabled_indices(names)
        if (self.pair_mode and len(base_entries) < 2) or not enabled_indices:
            self.set_result_too_few()
            return None
        duration_ms = max(1, int(duration_ms))
        return wheel_spin_ops.spin_to_label(
            self,
            names,
            enabled_indices,
            duration_ms=duration_ms,
            target_label=target_name,
        )


    def _emit_result(self):
        if hasattr(self, "_pending_result"):
            self.set_result_value(str(self._pending_result))
            self.spun.emit(self._pending_result)
            delattr(self, "_pending_result")

        if hasattr(self, "anim"):
            self.anim.deleteLater()
            delattr(self, "anim")
        self._is_spinning = False

    def _update_name_dependent_ui(self):
        """
        Passt UI-Elemente je nach Anzahl der Basenamen an:
        - 0 Namen  → Spin-Button aus, Include-in-all aus, Pair-Toggle aus
        - 1 Name   → Spin-Button an, Pair-Toggle aus, ggf. Include-in-all an (von 0 kommend)
        - >= 2     → Spin-Button an, Pair-Toggle an
        """
        base = self._base_names()
        count = len(base)
        prev = getattr(self, "_last_name_count", count)
        self._last_name_count = count

        # --- Single-Rad drehen ---
        # Wenn kein Name da ist, deaktivieren
        if not self._force_spin_enabled:
            self.btn_local_spin.setEnabled(count > 0)
        else:
            self.btn_local_spin.setEnabled(True)

        # --- Paare-Toggle ---
        if getattr(self, "allow_pair_toggle", False) and getattr(self, "toggle", None) is not None:
            if count < 2:
                # Wenn nur noch ein Name steht und Paare aktiviert ist, deaktiviere dann.
                if self.toggle.isChecked():
                    self.toggle.setChecked(False)
                self.toggle.setEnabled(False)
                self.pair_mode = False
                self._wheel_state.pair_mode = False
                self._apply_placeholder()
            else:
                # Ab 2 Namen wieder aktivierbar
                self.toggle.setEnabled(True)

        # --- "Bei Drehen"-Toggle ---
        if hasattr(self, "btn_include_in_all"):
            if count == 0:
                # Wenn kein Name da ist, dann deaktiviere den Toggle.
                self.btn_include_in_all.setEnabled(False)
                # Leeres Rad soll bei "Drehen" NICHT teilnehmen
                if self.btn_include_in_all.isChecked():
                    self.btn_include_in_all.setChecked(False)
            else:
                # Mindestens ein Name → Toggle aktivierbar
                self.btn_include_in_all.setEnabled(True)
                # Wenn nachdem kein Name da war, jetzt ein Name ist,
                # dann aktiviere den Toggle für "Drehen" wieder.
                if prev == 0 and not self.btn_include_in_all.isChecked():
                    self.btn_include_in_all.setChecked(True)
        # --- Subrollen-Toggle ---
        self._update_subrole_toggle_state()

    def _update_subrole_toggle_state(self):
        if not getattr(self, "chk_subroles", None):
            return
        can_use = self.pair_mode and len(self._base_names()) >= 2
        self.chk_subroles.setEnabled(can_use)
        if not can_use and self.chk_subroles.isChecked():
            # deaktivieren, wenn Paare-Modus aus ist oder zu wenige Namen vorhanden sind
            self.chk_subroles.setChecked(False)
        self.use_subrole_filter = bool(can_use and self.chk_subroles.isChecked())
        self._wheel_state.use_subrole_filter = self.use_subrole_filter
        self._apply_placeholder()
    def _update_clear_button_enabled(self):
        """
        Blendet das Löschen-Symbol nur ein, wenn ein echtes Ergebnis da ist.
        """
        self.btn_clear_result.setVisible(self._result_state == "value")
    def _clear_result(self):
        self.clear_result()
    def set_spin_button_text(self, text: Optional[str]):
        """Setzt den Text des lokalen Spin-Buttons (None → Default)."""
        if text:
            self._custom_spin_label = text
            self.btn_local_spin.setText(text)
        else:
            self._custom_spin_label = None
            self.btn_local_spin.setText(self._default_spin_label)
    def set_force_spin_enabled(self, enabled: bool):
        """Erzwingt, dass der lokale Spin-Button aktiv bleibt (Hero-Ban)."""
        self._force_spin_enabled = bool(enabled)
        self._update_name_dependent_ui()
    def set_show_names_visible(self, visible: bool):
        """Blendet die Checkbox 'Namen anzeigen' ein/aus."""
        self._show_names_visible = bool(visible)
        if self.chk_show_names:
            self.chk_show_names.setVisible(visible)
    def set_header_controls_visible(self, visible: bool):
        """Blendet Pair-/Subrollen-Toggles im Header ein/aus."""
        self._header_controls_visible = bool(visible)
        if self.toggle:
            self.toggle.setVisible(visible)
        if self.chk_subroles:
            self.chk_subroles.setVisible(visible)
    def set_subrole_controls_visible(self, visible: bool):
        """Blendet Subrollen-Kästchen in den Zeilen ein/aus."""
        new_val = bool(visible)
        if new_val == self._subrole_controls_visible:
            return
        self._subrole_controls_visible = new_val
        self._tooltip_rev += 1
        self._apply_subrole_visibility()
    def set_wheel_render_enabled(self, enabled: bool):
        """
        Schaltet das Zeichnen des Rads an/aus (z.B. im Hero-Ban für äußere Räder).
        Listen/Buttons bleiben davon unberührt.
        """
        self._suppress_wheel_render = not enabled
        prev = self._suppress_state_signal
        self._suppress_state_signal = True
        try:
            self._apply_names_list_changes()
        finally:
            self._suppress_state_signal = prev
    def _normalize_entries(self, defaults: Union[List[str], List[dict]]) -> List[dict]:
        """
        Macht aus verschiedenen Input-Formaten eine einheitliche Liste von
        {"name": str, "subroles": [str], "active": bool}.
        """
        return self._wheel_state.normalize_entries(defaults)
    def load_entries(self, entries: Union[List[str], List[dict]],
                     pair_mode: Optional[bool] = None,
                     include_in_all: Optional[bool] = None,
                     use_subroles: Optional[bool] = None):
        """
        Ersetzt die gesamte Namensliste durch neue Einträge (z.B. beim Moduswechsel).
        Optionale Flags setzen Pair-/Subrollen- und Include-Status mit.
        """
        normalized = self._normalize_entries(entries)
        # Liste ohne Signale neu aufbauen
        blockers = [
            QtCore.QSignalBlocker(self.names),
            QtCore.QSignalBlocker(self.names.model()),
        ]
        try:
            self.names.clear()
            for entry in normalized:
                self.names.add_name(
                    entry.get("name", ""),
                    subroles=entry.get("subroles", []),
                    active=entry.get("active", True),
                )
            if not normalized:
                self.names.add_name("")
        finally:
            del blockers

        # Disabled-Segmente und Hilfswerte zurücksetzen
        self._wheel_state.reset_disabled()
        self._wheel_state.last_wheel_names = []

        # Pair-/Subrollen-Status setzen (Signale blocken, UI updaten)
        if pair_mode is not None and not getattr(self, "allow_pair_toggle", False):
            pair_mode = False
        if pair_mode is not None:
            self.pair_mode = bool(pair_mode)
            self._wheel_state.pair_mode = self.pair_mode
            if getattr(self, "toggle", None):
                blocker = QtCore.QSignalBlocker(self.toggle)
                self.toggle.setChecked(self.pair_mode)
                del blocker
            if not self.pair_mode and getattr(self, "chk_subroles", None):
                blocker = QtCore.QSignalBlocker(self.chk_subroles)
                self.chk_subroles.setChecked(False)
                del blocker
        if use_subroles is not None and getattr(self, "chk_subroles", None):
            blocker = QtCore.QSignalBlocker(self.chk_subroles)
            self.chk_subroles.setChecked(bool(use_subroles))
            del blocker
            self.use_subrole_filter = bool(self.chk_subroles.isChecked())
            self._wheel_state.use_subrole_filter = self.use_subrole_filter
        self._update_subrole_toggle_state()

        if include_in_all is not None and hasattr(self, "btn_include_in_all"):
            blocker = QtCore.QSignalBlocker(self.btn_include_in_all)
            self.btn_include_in_all.setChecked(bool(include_in_all))
            del blocker
            self._on_include_in_all_toggled(self.btn_include_in_all.isChecked())

        self._apply_placeholder()
        self._apply_names_list_changes()
        if hasattr(self, "names_panel"):
            self.names_panel.refresh_action_state()
        # Sichtbarkeit der Subrollen-Kästchen nach einem vollständigen Neuaufbau anwenden
        self._apply_subrole_visibility()

    # --- Added resize behaviour ---

    # wheel resizing handled by WheelWidget
