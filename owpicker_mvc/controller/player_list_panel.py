from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

import i18n
from utils import qt_runtime, theme as theme_util
from view.name_list import NameRowWidget, NamesListPanel
from view import style_helpers

_PLAYER_PANEL_STYLE_CACHE: dict[str, str] = {}


def _player_panel_style(theme: theme_util.Theme) -> str:
    cached = _PLAYER_PANEL_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "QFrame#playerListPanel { "
        f"background: {theme.card_bg}; border: 2px solid {theme.card_border}; border-radius: 10px; "
        "}"
    )
    _PLAYER_PANEL_STYLE_CACHE[theme.key] = cached
    return cached


class PlayerListPanelController(QtCore.QObject):
    """Popup panel to edit the combined player list across roles."""
    _ROLE_MEMBERSHIP_ROLE = QtCore.Qt.UserRole + 30
    _ORIGINAL_NAME_ROLE = QtCore.Qt.UserRole + 31

    def __init__(self, main_window, button: QtWidgets.QPushButton) -> None:
        super().__init__(main_window)
        self._mw = main_window
        self._button = button
        self._panel: QtWidgets.QFrame | None = None
        self._title: QtWidgets.QLabel | None = None
        self._close: QtWidgets.QToolButton | None = None
        self._names_panel: NamesListPanel | None = None
        self._names: QtWidgets.QListWidget | None = None
        self._syncing = False
        self._sync_timer: QtCore.QTimer | None = None
        self._snapshot: dict[str, dict[str, set]] = {}
        self._applied_theme_key: str | None = None

    def allowed(self) -> bool:
        return self._mw.current_mode == "players" and not getattr(self._mw, "hero_ban_active", False)

    def update_button(self) -> None:
        if not self._button:
            return
        allowed = self.allowed()
        self._button.setVisible(allowed)
        if not allowed:
            self._button.setEnabled(False)
            self.hide_panel()
            return
        # Keep this entry point always available in player mode so users can
        # add new names even when role lists are currently empty.
        self._button.setEnabled(True)

    def toggle_panel(self) -> None:
        if not self.allowed():
            return
        self._ensure_panel()
        if self._panel and self._panel.isVisible():
            self._panel.hide()
            if hasattr(self._mw, "_refresh_app_event_filter_state"):
                self._mw._refresh_app_event_filter_state()
            return
        self.refresh_panel()
        self.position_panel()
        if self._panel:
            self._panel.show()
            qt_runtime.safe_raise(self._panel)
        if hasattr(self._mw, "_refresh_app_event_filter_state"):
            self._mw._refresh_app_event_filter_state()

    def hide_panel(self) -> None:
        if self._panel:
            self._panel.hide()
        if hasattr(self._mw, "_refresh_app_event_filter_state"):
            self._mw._refresh_app_event_filter_state()

    def is_visible(self) -> bool:
        panel = self._panel
        return bool(panel is not None and panel.isVisible())

    def shutdown(self) -> None:
        """Stop timers and hide the panel to release resources."""
        if self._sync_timer and self._sync_timer.isActive():
            self._sync_timer.stop()
        self._sync_timer = None
        self._syncing = False
        self.hide_panel()

    def resource_snapshot(self) -> dict:
        sync_timer_active = False
        if self._sync_timer is not None:
            try:
                sync_timer_active = bool(self._sync_timer.isActive())
            except Exception:
                pass
        panel_visible = False
        if self._panel is not None:
            try:
                panel_visible = bool(self._panel.isVisible())
            except Exception:
                pass
        return {
            "panel_exists": bool(self._panel is not None),
            "panel_visible": panel_visible,
            "sync_timer_active": sync_timer_active,
            "syncing": bool(self._syncing),
            "snapshot_entries": len(self._snapshot),
        }

    def on_resize(self) -> None:
        if self._panel and self._panel.isVisible():
            self.position_panel()

    def maybe_close_on_click(self, obj, event) -> None:
        panel = self._panel
        if not panel or not panel.isVisible():
            return
        if hasattr(event, "button") and event.button() != QtCore.Qt.LeftButton:
            return
        if isinstance(obj, QtWidgets.QWidget):
            if obj is panel or panel.isAncestorOf(obj):
                return
            if self._button and (obj is self._button or self._button.isAncestorOf(obj)):
                return
        if hasattr(event, "globalPosition"):
            pos = event.globalPosition().toPoint()
        elif hasattr(event, "globalPos"):
            pos = event.globalPos()
        else:
            return
        panel_rect = QtCore.QRect(panel.mapToGlobal(QtCore.QPoint(0, 0)), panel.size())
        if panel_rect.contains(pos):
            return
        if self._button:
            btn_rect = QtCore.QRect(self._button.mapToGlobal(QtCore.QPoint(0, 0)), self._button.size())
            if btn_rect.contains(pos):
                return
        self.hide_panel()

    def apply_theme(self) -> None:
        panel = self._panel
        if not panel:
            return
        theme = theme_util.get_theme(getattr(self._mw, "theme", "light"))
        if self._applied_theme_key == theme.key:
            return
        style_helpers.set_stylesheet_if_needed(
            panel,
            f"player_list_panel:{theme.key}",
            _player_panel_style(theme),
        )
        style_helpers.apply_theme_roles(theme, ((self._title, "label.editor_title"),))
        if self._names_panel:
            self._names_panel.apply_theme(theme)
        if self._close:
            style_helpers.style_tool_button(self._close, theme)
        self._applied_theme_key = theme.key

    def set_language(self, lang: str) -> None:
        i18n.set_language(lang)
        if self._title:
            self._title.setText(i18n.t("players.list_title"))
        if self._close:
            self._close.setToolTip(i18n.t("players.list_close_tooltip"))
        if self._names_panel:
            self._names_panel.set_language(lang)

    def _role_targets(self) -> tuple[tuple[str, object], ...]:
        return (
            ("Tank", getattr(self._mw, "tank", None)),
            ("DPS", getattr(self._mw, "dps", None)),
            ("Support", getattr(self._mw, "support", None)),
        )

    def _role_labels(self) -> list[str]:
        return [label for label, wheel in self._role_targets() if wheel is not None]

    def _roles_from_labels(self, labels) -> set:
        label_keys = {
            str(value).strip().casefold()
            for value in list(labels or [])
            if str(value).strip()
        }
        roles: set = set()
        if not label_keys:
            return roles
        for label, wheel in self._role_targets():
            if wheel is None:
                continue
            if label.casefold() in label_keys:
                roles.add(wheel)
        return roles

    def _labels_from_roles(self, roles) -> list[str]:
        role_set = set(roles or set())
        labels: list[str] = []
        for label, wheel in self._role_targets():
            if wheel is None:
                continue
            if wheel in role_set:
                labels.append(label)
        return labels

    def _active_for_state(self, state) -> bool:
        return state != QtCore.Qt.Unchecked

    def refresh_panel(self) -> None:
        names = self._names
        if not names:
            return
        stats = self._name_roles()
        blockers = [
            QtCore.QSignalBlocker(names),
            QtCore.QSignalBlocker(names.model()),
        ]
        try:
            names.clear()
            if not stats:
                names.add_name("", subroles=self._role_labels())
                self._snapshot = {}
                return
            for name in sorted(stats.keys(), key=str.casefold):
                info = stats[name]
                roles = info.get("roles", set())
                active_roles = info.get("active_roles", set())
                role_labels = self._labels_from_roles(roles)
                total = len(roles)
                active = len(active_roles)
                if active <= 0:
                    state = QtCore.Qt.Unchecked
                elif active >= total:
                    state = QtCore.Qt.Checked
                else:
                    state = QtCore.Qt.PartiallyChecked
                names.add_name(name, subroles=role_labels, active=(state == QtCore.Qt.Checked))
                item = names.item(names.count() - 1)
                if item is None:
                    continue
                if state == QtCore.Qt.PartiallyChecked:
                    item.setFlags(item.flags() | QtCore.Qt.ItemIsTristate)
                    item.setCheckState(state)
                    widget = names.itemWidget(item)
                    if widget and hasattr(widget, "chk_active"):
                        widget.chk_active.setTristate(True)
                        widget.chk_active.setCheckState(state)
                item.setData(self._ROLE_MEMBERSHIP_ROLE, set(self._roles_from_labels(role_labels)))
                item.setData(self._ORIGINAL_NAME_ROLE, name)
        finally:
            del blockers
        self._snapshot = {name: {"roles": set(info["roles"])} for name, info in stats.items()}
        if self._names_panel:
            self._names_panel.refresh_action_state()

    def position_panel(self) -> None:
        panel = self._panel
        if not panel or not panel.parentWidget():
            return
        parent = panel.parentWidget()
        # Keep room for role checkboxes, but avoid an oversized panel.
        available_w = max(300, int(parent.width()) - 16)
        target_w = max(460, int(parent.width() * 0.48))
        panel_w = max(340, min(680, target_w, available_w))
        available_h = max(260, int(parent.height()) - 16)
        target_h = max(420, int(parent.height() * 0.70))
        panel_h = max(330, min(540, target_h, available_h))
        panel.setFixedSize(panel_w, panel_h)
        self._apply_names_row_profile(panel_width=panel_w)
        tank_geo = self._mw.tank.geometry()
        x = tank_geo.x()
        y = tank_geo.y() + tank_geo.height() + 8
        x = max(8, min(x, parent.width() - panel.width() - 8))
        y = max(8, min(y, parent.height() - panel.height() - 8))
        panel.move(x, y)

    def _apply_names_row_profile(self, panel_width: int | None = None) -> None:
        names = self._names
        if names is None:
            return
        width = int(panel_width or 540)
        # Approximate usable list row width inside the popup panel after frame/layout paddings.
        row_budget = max(220, width - 86)

        # Estimate subrole block width from the current font + checkbox overhead.
        fm = QtGui.QFontMetrics(names.font())
        labels = self._role_labels()
        subrole_block_w = 6  # left margin inside subrole layout
        for idx, label in enumerate(labels):
            # text + checkbox indicator/padding overhead
            subrole_block_w += int(fm.horizontalAdvance(label)) + 27
            if idx > 0:
                subrole_block_w += 8

        fixed_w = 18 + 3 + 3 + 18  # active checkbox + spacings + delete marker column
        name_with_subroles = max(96, min(220, row_budget - fixed_w - subrole_block_w))
        name_without_subroles = max(140, min(220, row_budget - fixed_w))
        name_max_width = max(name_with_subroles, min(236, name_with_subroles + 18))

        indicator_h = max(
            0,
            int(names.style().pixelMetric(QtWidgets.QStyle.PM_IndicatorHeight, None, names)),
        )
        row_height = max(22, indicator_h + 6)
        edit_height = max(20, row_height - 2)
        names.set_row_visual_profile(
            row_height=row_height,
            name_edit_height=edit_height,
            name_min_width_with_subroles=name_with_subroles,
            name_min_width_without_subroles=name_without_subroles,
            name_max_width=name_max_width,
        )

    def _ensure_panel(self) -> None:
        if self._panel:
            return
        parent = getattr(self._mw, "role_container", None) or self._mw
        panel = QtWidgets.QFrame(parent)
        panel.setObjectName("playerListPanel")
        panel.setVisible(False)
        panel.setFixedSize(540, 470)

        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(i18n.t("players.list_title"))
        header.addWidget(title)
        header.addStretch(1)
        btn_close = QtWidgets.QToolButton()
        btn_close.setText("X")
        btn_close.setToolTip(i18n.t("players.list_close_tooltip"))
        btn_close.setCursor(QtCore.Qt.PointingHandCursor)
        btn_close.setAutoRaise(True)
        btn_close.clicked.connect(self.hide_panel)
        header.addWidget(btn_close)
        layout.addLayout(header)

        names_panel = NamesListPanel(
            subrole_labels=self._role_labels(),
            enable_mark_for_delete=True,
        )
        names = names_panel.names
        layout.addWidget(names_panel, 1)

        names.itemChanged.connect(self._schedule_sync)
        names.model().rowsInserted.connect(self._schedule_sync)
        names.model().rowsInserted.connect(self._on_rows_inserted)
        names.model().rowsRemoved.connect(self._schedule_sync)
        names.metaChanged.connect(self._schedule_sync)

        self._panel = panel
        self._title = title
        self._close = btn_close
        self._names_panel = names_panel
        self._names = names
        self._apply_names_row_profile(panel_width=int(panel.width()))
        self.apply_theme()

    def _on_rows_inserted(self, _parent, start: int, end: int) -> None:
        names = self._names
        if not names:
            return
        default_labels = self._role_labels()
        if not default_labels:
            return
        blockers = [
            QtCore.QSignalBlocker(names),
            QtCore.QSignalBlocker(names.model()),
        ]
        try:
            for row in range(max(0, int(start)), max(-1, int(end)) + 1):
                item = names.item(row)
                if item is None:
                    continue
                selected = [
                    str(value).strip()
                    for value in list(item.data(names.SUBROLE_ROLE) or [])
                    if str(value).strip()
                ]
                if selected:
                    continue
                item.setData(names.SUBROLE_ROLE, list(default_labels))
                item.setData(self._ROLE_MEMBERSHIP_ROLE, set(self._roles_from_labels(default_labels)))
                widget = names.itemWidget(item)
                if isinstance(widget, NameRowWidget):
                    for cb in widget.subrole_checks:
                        should_check = cb.text() in default_labels
                        if cb.isChecked() == should_check:
                            continue
                        prev = cb.blockSignals(True)
                        cb.setChecked(should_check)
                        cb.blockSignals(prev)
        finally:
            del blockers
        if self._names_panel:
            self._names_panel.refresh_action_state()

    def _schedule_sync(self, *_args) -> None:
        if self._syncing:
            return
        panel = self._panel
        if panel is None or not panel.isVisible():
            return
        if self._sync_timer is None:
            self._sync_timer = QtCore.QTimer(self)
            self._sync_timer.setSingleShot(True)
            self._sync_timer.timeout.connect(self._sync_panel)
        self._sync_timer.start(120)

    def _sync_panel(self) -> None:
        if self._syncing:
            return
        panel = self._panel
        if panel is None or not panel.isVisible():
            return
        names = self._names
        if not names:
            return
        self._syncing = True
        try:
            prev_snapshot = dict(self._snapshot or {})
            current: dict[str, dict[str, set]] = {}
            keep_names: set[str] = set()
            for i in range(names.count()):
                item = names.item(i)
                if item is None:
                    continue
                row_widget = names.itemWidget(item)
                if isinstance(row_widget, NameRowWidget):
                    name = row_widget.edit.text().strip()
                    selected_labels = [
                        str(value).strip()
                        for value in list(row_widget.selected_subroles())
                        if str(value).strip()
                    ]
                else:
                    name = item.text().strip()
                    selected_labels = [
                        str(value).strip()
                        for value in list(item.data(names.SUBROLE_ROLE) or [])
                        if str(value).strip()
                    ]
                if not name:
                    orig = item.data(self._ORIGINAL_NAME_ROLE)
                    if orig:
                        keep_names.add(orig)
                    continue
                roles = self._roles_from_labels(selected_labels)
                item.setData(names.SUBROLE_ROLE, list(selected_labels))
                item.setData(self._ROLE_MEMBERSHIP_ROLE, set(roles))
                item.setData(self._ORIGINAL_NAME_ROLE, name)
                current[name] = {"roles": set(roles), "state": item.checkState()}

            prev_names = set(prev_snapshot.keys())
            current_names = set(current.keys())
            current_names |= keep_names

            removed = prev_names - current_names
            for name in removed:
                roles = prev_snapshot.get(name, {}).get("roles", set())
                for wheel in roles:
                    wheel.remove_names({name})

            added = current_names - prev_names
            for name in added:
                if name not in current:
                    continue
                roles = current[name]["roles"]
                state = current[name]["state"]
                active = self._active_for_state(state)
                for wheel in roles:
                    wheel.add_name(name, active=active)

            for name in current_names & prev_names:
                if name not in current:
                    continue
                entry = current[name]
                prev_roles = set(prev_snapshot.get(name, {}).get("roles", set()))
                curr_roles = set(entry.get("roles", set()))
                state = entry.get("state")

                for wheel in prev_roles - curr_roles:
                    wheel.remove_names({name})
                for wheel in curr_roles - prev_roles:
                    wheel.add_name(name, active=self._active_for_state(state))

                if state == QtCore.Qt.PartiallyChecked:
                    continue
                active = state == QtCore.Qt.Checked
                for wheel in curr_roles & prev_roles:
                    wheel.set_names_active({name}, active)

            self._snapshot = {
                name: {"roles": set(info["roles"])} for name, info in current.items()
            }
            self._mw._update_spin_all_enabled()
        finally:
            self._syncing = False

    def _name_roles(self) -> dict[str, dict[str, set]]:
        stats: dict[str, dict[str, set]] = {}
        for wheel in (self._mw.tank, self._mw.dps, self._mw.support):
            for entry in wheel.get_current_entries():
                name = str(entry.get("name", "")).strip()
                if not name:
                    continue
                bucket = stats.setdefault(name, {"roles": set(), "active_roles": set()})
                bucket["roles"].add(wheel)
                if entry.get("active", True):
                    bucket["active_roles"].add(wheel)
        return stats
