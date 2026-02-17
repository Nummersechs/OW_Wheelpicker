from __future__ import annotations

from typing import List, Optional, Union

from PySide6 import QtCore, QtWidgets

import i18n
from view import wheel_entries_ops
from view.name_list import NameRowWidget


class WheelViewEntriesMixin:
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

    def _ensure_entries_cache(self) -> None:
        if self._entries_cache is None:
            self._rebuild_entries_cache()

    def _rebuild_entries_cache(self) -> None:
        self._entries_cache = wheel_entries_ops.rebuild_entries_cache(self.names)

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
        entries_signature = self._entries_signature()
        if entries_signature == self._last_entries_signature:
            return
        self._last_entries_signature = entries_signature
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

    def _entries_signature(self) -> tuple:
        if not self._entries_cache:
            return (
                (),
                bool(self.pair_mode),
                bool(self.use_subrole_filter),
                tuple(self.subrole_labels),
                bool(self._suppress_wheel_render),
                bool(self._wheel_state.override_entries is not None),
            )
        signature: list[tuple[str, bool, tuple[str, ...]]] = []
        for entry in self._entries_cache.get("entries", []):
            name = str(entry.get("name", "")).strip()
            active = bool(entry.get("active", True))
            subroles_raw = entry.get("subroles", []) or []
            subroles = tuple(sorted(str(role).strip() for role in subroles_raw if str(role).strip()))
            signature.append((name, active, subroles))
        return (
            tuple(signature),
            bool(self.pair_mode),
            bool(self.use_subrole_filter),
            tuple(self.subrole_labels),
            bool(self._suppress_wheel_render),
            bool(self._wheel_state.override_entries is not None),
        )

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
            # Force rebuild after override removal: load_entries() already updated
            # the signature in non-override mode, so an unchanged signature would
            # otherwise skip restoring wheel names from the base list.
            self._last_entries_signature = None
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
        # Wechsel des Modus -> Disabled-Segmente zurücksetzen
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
        # Subrollenwechsel -> Disabled-Segmente zurücksetzen
        self._wheel_state.reset_disabled()
        self._apply_placeholder()
        self._on_names_changed()
        self._tooltip_rev += 1
        self.stateChanged.emit()

    def _set_name_inputs_blocked(self, blocked: bool) -> None:
        try:
            if not hasattr(self, "_names_default_focus_policy"):
                self._names_default_focus_policy = self.names.focusPolicy()
        except Exception:
            self._names_default_focus_policy = QtCore.Qt.StrongFocus
        try:
            self.names.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, bool(blocked))
        except Exception:
            pass
        try:
            if blocked:
                self.names.clearFocus()
                self.names.setFocusPolicy(QtCore.Qt.NoFocus)
            else:
                self.names.setFocusPolicy(getattr(self, "_names_default_focus_policy", QtCore.Qt.StrongFocus))
        except Exception:
            pass

    def set_interactive_enabled(self, en: bool, *, disable_name_inputs: bool = True):
        if disable_name_inputs:
            self._set_name_inputs_blocked(False)
            self.names.setEnabled(en)
        else:
            # Keep the list visually active to avoid expensive widget-state
            # cascades on large OCR-imported lists while still blocking edits.
            self.names.setEnabled(True)
            self._set_name_inputs_blocked(not en)
        if hasattr(self, "names_panel"):
            self.names_panel.set_interactive_enabled(en)
        if en:
            # Wenn allgemein aktiv -> Feinsteuerung über _update_name_dependent_ui
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

    def _update_name_dependent_ui(self):
        """
        Passt UI-Elemente je nach Anzahl der Basenamen an:
        - 0 Namen  -> Spin-Button aus, Include-in-all aus, Pair-Toggle aus
        - 1 Name   -> Spin-Button an, Pair-Toggle aus, ggf. Include-in-all an (von 0 kommend)
        - >= 2     -> Spin-Button an, Pair-Toggle an
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
                # Mindestens ein Name -> Toggle aktivierbar
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
        """Setzt den Text des lokalen Spin-Buttons (None -> Default)."""
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
            self._subrole_visibility_applied = None
            self._apply_subrole_visibility()
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

    def load_entries(
        self,
        entries: Union[List[str], List[dict]],
        pair_mode: Optional[bool] = None,
        include_in_all: Optional[bool] = None,
        use_subroles: Optional[bool] = None,
    ):
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
