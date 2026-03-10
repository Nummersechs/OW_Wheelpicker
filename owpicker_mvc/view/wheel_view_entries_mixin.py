from __future__ import annotations

from contextlib import nullcontext
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
                state_getter = getattr(self.names, "item_state", None)
                state_setter = getattr(self.names, "set_item_state", None)
                current_state = (
                    state_getter(item) if callable(state_getter) else item.checkState()
                )
                if current_state == QtCore.Qt.Checked:
                    if callable(state_setter):
                        state_setter(item, QtCore.Qt.Unchecked)
                    else:
                        item.setCheckState(QtCore.Qt.Unchecked)
                    changed = True
        return changed

    def add_name(self, name: str, active: bool = True, subroles: Optional[List[str]] = None) -> bool:
        """Add a name if missing; returns True if it changed."""
        name = str(name or "").strip()
        if not name:
            return False
        has_non_empty = False
        first_empty_item: QtWidgets.QListWidgetItem | None = None
        for i in range(self.names.count()):
            item = self.names.item(i)
            if item is None:
                continue
            item_text = self._item_text(item)
            if item_text:
                has_non_empty = True
            elif first_empty_item is None:
                first_empty_item = item
            if item_text == name:
                if active:
                    return self.set_names_active({name}, True)
                return False
        # If the list is effectively empty (only placeholder rows), reuse the
        # first empty row instead of appending another row.
        if (not has_non_empty) and first_empty_item is not None:
            normalized_subroles: list[str] = []
            seen_subroles: set[str] = set()
            for raw_subrole in list(subroles or []):
                value = str(raw_subrole or "").strip()
                if not value:
                    continue
                key = value.casefold()
                if key in seen_subroles:
                    continue
                seen_subroles.add(key)
                normalized_subroles.append(value)
            with self._suspend_list_signals() as prev:
                row_widget = self.names.itemWidget(first_empty_item)
                if isinstance(row_widget, NameRowWidget):
                    row_widget.edit.setText(name)
                    first_empty_item.setData(self.names.SUBROLE_ROLE, list(normalized_subroles))
                    if row_widget.subrole_checks:
                        selected_subroles = set(normalized_subroles)
                        for checkbox in row_widget.subrole_checks:
                            blocker = QtCore.QSignalBlocker(checkbox)
                            checkbox.setChecked(checkbox.text() in selected_subroles)
                            del blocker
                    target_checked = bool(active)
                    self.names.set_item_state(
                        first_empty_item,
                        QtCore.Qt.Checked if target_checked else QtCore.Qt.Unchecked,
                    )
                    active_blocker = QtCore.QSignalBlocker(row_widget.chk_active)
                    row_widget.chk_active.setChecked(target_checked)
                    del active_blocker
                else:
                    first_empty_item.setText(name)
                    first_empty_item.setData(self.names.SUBROLE_ROLE, list(normalized_subroles))
                    self.names.set_item_state(
                        first_empty_item,
                        QtCore.Qt.Checked if active else QtCore.Qt.Unchecked,
                    )
                self._apply_names_list_changes()
            if not prev:
                self.stateChanged.emit()
            return True
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
                    state_getter = getattr(self.names, "item_state", None)
                    state_setter = getattr(self.names, "set_item_state", None)
                    current_state = (
                        state_getter(item) if callable(state_getter) else item.checkState()
                    )
                    if current_state != target_state:
                        if callable(state_setter):
                            state_setter(item, target_state)
                        else:
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
        tooltip_text = i18n.t(tooltip_key)
        if str(self.result.toolTip() or "") != str(tooltip_text or ""):
            self.result.setToolTip(tooltip_text)

        if self.pair_mode:
            if self.use_subrole_filter and len(self.subrole_labels) >= 2:
                hint_text = i18n.t(
                    "wheel.names_hint_pairs_subroles",
                    a=self.subrole_labels[0],
                    b=self.subrole_labels[1],
                )
                if str(self.names_hint.text() or "") != str(hint_text or ""):
                    self.names_hint.setText(hint_text)
            else:
                hint_text = i18n.t("wheel.names_hint_pairs")
                if str(self.names_hint.text() or "") != str(hint_text or ""):
                    self.names_hint.setText(hint_text)
        else:
            hint_text = i18n.t("wheel.names_hint_single")
            if str(self.names_hint.text() or "") != str(hint_text or ""):
                self.names_hint.setText(hint_text)

    def get_current_names(self) -> list[str]:
        """Liefert alle aktuell eingetragenen Namen (ohne Leerzeilen)."""
        return self._base_names()

    def get_enabled_names(self) -> list[str]:
        """
        Return currently enabled raw names for controller logic (e.g. Open Queue).

        This keeps controller code off private wheel internals.
        """
        disabled_labels = set(self._disabled_labels)
        enabled: list[str] = []
        seen: set[str] = set()
        for entry in self._active_entries():
            name = str(entry.get("name", "")).strip()
            if not name or name in disabled_labels:
                continue
            if name in seen:
                continue
            seen.add(name)
            enabled.append(name)
        return enabled

    def get_subrole_labels(self) -> list[str]:
        """Public copy of configured subrole labels for controller logic."""
        return [str(label) for label in list(getattr(self, "subrole_labels", []))]

    def get_active_entries(self) -> List[dict]:
        """Public copy of active entries used by spin/controllers."""
        return [dict(entry) for entry in self._active_entries()]

    def get_disabled_labels(self) -> set[str]:
        """Public view of disabled labels for controller logic."""
        return set(self._wheel_state.disabled_labels)

    def get_effective_labels_from_entries(
        self,
        entries: List[dict],
        *,
        include_disabled: bool = True,
        pair_mode: Optional[bool] = None,
        use_subroles: Optional[bool] = None,
    ) -> List[str]:
        """
        Return effective wheel labels from entries with optional temporary mode overrides.

        This keeps candidate generation off internal wheel state mutation in controllers.
        """
        state = self._wheel_state
        prev_state_pair_mode = bool(state.pair_mode)
        prev_state_use_subroles = bool(state.use_subrole_filter)
        prev_attr_pair_mode = bool(getattr(self, "pair_mode", False))
        prev_attr_use_subroles = bool(getattr(self, "use_subrole_filter", False))
        override_pair_mode = prev_state_pair_mode if pair_mode is None else bool(pair_mode)
        override_use_subroles = prev_state_use_subroles if use_subroles is None else bool(use_subroles)
        override_use_subroles = bool(override_use_subroles and override_pair_mode)
        try:
            state.pair_mode = override_pair_mode
            state.use_subrole_filter = override_use_subroles
            self.pair_mode = override_pair_mode
            self.use_subrole_filter = override_use_subroles
            labels = state.effective_names_from(entries, include_disabled=bool(include_disabled))
            return [str(label) for label in list(labels) if str(label).strip()]
        finally:
            state.pair_mode = prev_state_pair_mode
            state.use_subrole_filter = prev_state_use_subroles
            self.pair_mode = prev_attr_pair_mode
            self.use_subrole_filter = prev_attr_use_subroles

    def is_pair_mode_enabled(self) -> bool:
        toggle = getattr(self, "toggle", None)
        if toggle is not None:
            return bool(toggle.isChecked())
        return bool(getattr(self, "pair_mode", False))

    def is_subrole_filter_enabled(self) -> bool:
        chk = getattr(self, "chk_subroles", None)
        if chk is not None:
            return bool(chk.isChecked())
        return bool(getattr(self, "use_subrole_filter", False))

    def set_pair_mode_enabled(self, enabled: bool) -> None:
        target = bool(enabled)
        toggle = getattr(self, "toggle", None)
        if toggle is not None:
            if bool(toggle.isChecked()) != target:
                toggle.setChecked(target)
            return
        if self._set_pair_mode_internal(target):
            self._ensure_pair_mode_has_candidates()
            self._update_subrole_toggle_state()
            self._apply_names_list_changes()
            if not getattr(self, "_suppress_state_signal", False):
                self.stateChanged.emit()

    def set_subrole_filter_enabled(self, enabled: bool) -> None:
        target = bool(enabled)
        chk = getattr(self, "chk_subroles", None)
        if chk is not None and chk.isEnabled():
            if bool(chk.isChecked()) != target:
                chk.setChecked(target)
            return
        resolved = bool(target and self.is_pair_mode_enabled())
        self.use_subrole_filter = resolved
        self._wheel_state.use_subrole_filter = resolved
        self._apply_names_list_changes()
        if not getattr(self, "_suppress_state_signal", False):
            self.stateChanged.emit()

    def set_pair_controls_locked(self, locked: bool) -> None:
        """
        Lock/unlock pair+subrole controls without direct controller access to internals.
        """
        lock = bool(locked)
        if lock:
            self.set_pair_mode_enabled(False)
            self.set_subrole_filter_enabled(False)
        toggle = getattr(self, "toggle", None)
        if toggle is not None:
            toggle.setEnabled(not lock)
        chk = getattr(self, "chk_subroles", None)
        if chk is not None:
            if lock and chk.isChecked():
                blocker = QtCore.QSignalBlocker(chk)
                chk.setChecked(False)
                del blocker
            if lock:
                chk.setEnabled(False)
            else:
                update_subrole_toggle_state = getattr(self, "_update_subrole_toggle_state", None)
                if callable(update_subrole_toggle_state):
                    update_subrole_toggle_state()
                else:
                    chk.setEnabled(bool(self.is_pair_mode_enabled()))

    def set_included_in_global_spin(self, enabled: bool) -> None:
        button = getattr(self, "btn_include_in_all", None)
        if button is None:
            return
        target = bool(enabled)
        if bool(button.isChecked()) != target:
            button.setChecked(target)

    def get_override_entries(self) -> Optional[List[dict]]:
        override = self._wheel_state.override_entries
        if override is None:
            return None
        return [dict(entry) for entry in list(override)]

    def get_disabled_indices(self) -> set[int]:
        return set(self._wheel_state.disabled_indices)

    def restore_disabled_indices(self, indices: Optional[set[int]]) -> None:
        self._wheel_state.disabled_indices = set(indices or set())
        self._refresh_disabled_indices()

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
        self._ensure_pair_mode_has_candidates(active_entries)
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

    def _set_pair_mode_internal(self, enabled: bool) -> bool:
        """Set pair mode atomically without re-entering toggle signal handlers."""
        target = bool(enabled)
        changed = bool(self.pair_mode != target)
        self.pair_mode = target
        self._wheel_state.pair_mode = target

        toggle = getattr(self, "toggle", None)
        if toggle is not None and bool(toggle.isChecked()) != target:
            blocker = QtCore.QSignalBlocker(toggle)
            toggle.setChecked(target)
            del blocker

        if not target:
            chk_subroles = getattr(self, "chk_subroles", None)
            if chk_subroles is not None and chk_subroles.isChecked():
                blocker = QtCore.QSignalBlocker(chk_subroles)
                chk_subroles.setChecked(False)
                del blocker
            self.use_subrole_filter = False
            self._wheel_state.use_subrole_filter = False

        return changed

    def _ensure_pair_mode_has_candidates(self, entries: Optional[List[dict]] = None) -> bool:
        """
        Keep pair-mode consistent: never stay in pair/sub-filter mode when it would
        produce no wheel entries.
        Returns True when state was auto-adjusted.
        """
        if not self.pair_mode:
            return False

        source_entries = list(entries) if entries is not None else list(self._entries_for_spin())
        pair_names = self._effective_names_from(source_entries, include_disabled=True)
        if pair_names:
            return False

        changed = False

        # First fallback: keep pair-mode, but disable subrole filtering.
        if self.use_subrole_filter:
            changed = True
            chk_subroles = getattr(self, "chk_subroles", None)
            if chk_subroles is not None and chk_subroles.isChecked():
                blocker = QtCore.QSignalBlocker(chk_subroles)
                chk_subroles.setChecked(False)
                del blocker
            self.use_subrole_filter = False
            self._wheel_state.use_subrole_filter = False
            pair_names = self._effective_names_from(source_entries, include_disabled=True)

        if pair_names:
            return changed

        # Final fallback: disable pair-mode so the wheel can render singles.
        if self._set_pair_mode_internal(False):
            changed = True
        return changed

    def _on_names_changed(self):
        # Kompatibilitäts-Methode, falls sie anderswo noch aufgerufen wird
        self._apply_names_list_changes()

    def _on_toggle_pair_mode(self, _state: int):
        requested = bool(self.toggle.isChecked())
        self._set_pair_mode_internal(requested)
        self._ensure_pair_mode_has_candidates()
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
        spin_enabled = bool(self._force_spin_enabled or count > 0)
        self.btn_local_spin.setEnabled(spin_enabled)
        if spin_enabled:
            self.btn_local_spin.setToolTip(i18n.t("wheel.spin_button_tooltip"))
        else:
            self.btn_local_spin.setToolTip(i18n.t("wheel.spin_button_disabled_no_names_tooltip"))

        # --- Paare-Toggle ---
        if getattr(self, "allow_pair_toggle", False) and getattr(self, "toggle", None) is not None:
            if count < 2:
                # Mit <2 Basenamen darf Pair-Mode nicht aktiv bleiben.
                self._set_pair_mode_internal(False)
                self.toggle.setEnabled(False)
                self._apply_placeholder()
            else:
                # Ab 2 Namen wieder aktivierbar
                self.toggle.setEnabled(True)
                self._ensure_pair_mode_has_candidates()

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
        target = bool(enabled)
        if bool(getattr(self, "_force_spin_enabled", False)) == target:
            return
        self._force_spin_enabled = target
        self._update_name_dependent_ui()

    def set_show_names_visible(self, visible: bool):
        """Blendet die Checkbox 'Namen anzeigen' ein/aus."""
        self._show_names_visible = bool(visible)
        if self.chk_show_names:
            self.chk_show_names.setVisible(visible)
        if hasattr(self, "_apply_adaptive_header_labels"):
            QtCore.QTimer.singleShot(0, self._apply_adaptive_header_labels)

    def set_header_controls_visible(self, visible: bool):
        """Blendet Pair-/Subrollen-Toggles im Header ein/aus."""
        self._header_controls_visible = bool(visible)
        if self.toggle:
            self.toggle.setVisible(visible)
        if self.chk_subroles:
            self.chk_subroles.setVisible(visible)
        if hasattr(self, "_apply_adaptive_header_labels"):
            QtCore.QTimer.singleShot(0, self._apply_adaptive_header_labels)

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
            batch_update = getattr(self.names, "batch_update", None)
            batch_ctx = batch_update() if callable(batch_update) else nullcontext()
            with batch_ctx:
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
