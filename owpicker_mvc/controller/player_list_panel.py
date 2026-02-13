from __future__ import annotations

from PySide6 import QtCore, QtWidgets

import i18n
from utils import qt_runtime, theme as theme_util
from view.name_list import NamesListPanel


class PlayerListPanelController(QtCore.QObject):
    """Popup panel to edit the combined player list across roles."""

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
        has_names = bool(self._name_stats())
        self._button.setEnabled(has_names and self._mw.pending == 0)

    def toggle_panel(self) -> None:
        if not self.allowed() or not self._name_stats():
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
        panel.setStyleSheet(
            f"QFrame#playerListPanel {{ background: {theme.card_bg}; border: 2px solid {theme.card_border}; border-radius: 10px; }}"
        )
        if self._title:
            self._title.setStyleSheet(f"font-weight:700; font-size:14px; color:{theme.text};")
        if self._names_panel:
            self._names_panel.apply_theme(theme)
        if self._close:
            self._close.setStyleSheet(theme_util.tool_button_stylesheet(theme))
        self._applied_theme_key = theme.key

    def set_language(self, lang: str) -> None:
        i18n.set_language(lang)
        if self._title:
            self._title.setText(i18n.t("players.list_title"))
        if self._names_panel:
            self._names_panel.set_language(lang)

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
                names.add_name("")
                self._snapshot = {}
                return
            for name in sorted(stats.keys(), key=str.casefold):
                info = stats[name]
                roles = info.get("roles", set())
                active_roles = info.get("active_roles", set())
                total = len(roles)
                active = len(active_roles)
                if active <= 0:
                    state = QtCore.Qt.Unchecked
                elif active >= total:
                    state = QtCore.Qt.Checked
                else:
                    state = QtCore.Qt.PartiallyChecked
                names.add_name(name, active=(state == QtCore.Qt.Checked))
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
                item.setData(QtCore.Qt.UserRole + 2, set(roles))
                item.setData(QtCore.Qt.UserRole + 3, name)
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
        tank_geo = self._mw.tank.geometry()
        max_w = max(300, min(420, tank_geo.width() or 360))
        panel.setFixedWidth(max_w)
        panel.setFixedHeight(420)
        x = tank_geo.x()
        y = tank_geo.y() + tank_geo.height() + 8
        x = max(8, min(x, parent.width() - panel.width() - 8))
        y = max(8, min(y, parent.height() - panel.height() - 8))
        panel.move(x, y)

    def _ensure_panel(self) -> None:
        if self._panel:
            return
        parent = getattr(self._mw, "role_container", None) or self._mw
        panel = QtWidgets.QFrame(parent)
        panel.setObjectName("playerListPanel")
        panel.setVisible(False)
        panel.setFixedSize(360, 420)

        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel(i18n.t("players.list_title"))
        title.setStyleSheet("font-weight:700; font-size:14px;")
        header.addWidget(title)
        header.addStretch(1)
        btn_close = QtWidgets.QToolButton()
        btn_close.setText("X")
        btn_close.setCursor(QtCore.Qt.PointingHandCursor)
        btn_close.setAutoRaise(True)
        btn_close.clicked.connect(self.hide_panel)
        header.addWidget(btn_close)
        layout.addLayout(header)

        names_panel = NamesListPanel()
        names = names_panel.names
        layout.addWidget(names_panel, 1)

        names.itemChanged.connect(self._schedule_sync)
        names.model().rowsInserted.connect(self._schedule_sync)
        names.model().rowsRemoved.connect(self._schedule_sync)
        names.metaChanged.connect(self._schedule_sync)

        self._panel = panel
        self._title = title
        self._close = btn_close
        self._names_panel = names_panel
        self._names = names
        self.apply_theme()

    def _schedule_sync(self, *_args) -> None:
        if self._syncing:
            return
        if self._sync_timer is None:
            self._sync_timer = QtCore.QTimer(self)
            self._sync_timer.setSingleShot(True)
            self._sync_timer.timeout.connect(self._sync_panel)
        self._sync_timer.start(120)

    def _sync_panel(self) -> None:
        if self._syncing:
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
                name = item.text().strip()
                if not name:
                    orig = item.data(QtCore.Qt.UserRole + 3)
                    if orig:
                        keep_names.add(orig)
                    continue
                roles = item.data(QtCore.Qt.UserRole + 2)
                if not roles:
                    roles = {self._mw.tank, self._mw.dps, self._mw.support}
                    item.setData(QtCore.Qt.UserRole + 2, set(roles))
                if not item.data(QtCore.Qt.UserRole + 3):
                    item.setData(QtCore.Qt.UserRole + 3, name)
                current[name] = {"roles": set(roles), "state": item.checkState()}

            for i in range(names.count()):
                item = names.item(i)
                if item is None:
                    continue
                name = item.text().strip()
                if not name:
                    continue
                orig = item.data(QtCore.Qt.UserRole + 3)
                if orig and orig != name:
                    roles = item.data(QtCore.Qt.UserRole + 2) or set()
                    for wheel in roles:
                        wheel.rename_name(orig, name)
                    prev_snapshot.pop(orig, None)
                    prev_snapshot[name] = {"roles": set(roles)}
                    item.setData(QtCore.Qt.UserRole + 3, name)

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
                roles = current[name]["roles"]
                state = current[name]["state"]
                active = state == QtCore.Qt.Checked
                for wheel in roles:
                    wheel.add_name(name, active=active)

            for name in current_names & prev_names:
                entry = current[name]
                state = entry.get("state")
                if state == QtCore.Qt.PartiallyChecked:
                    continue
                active = state == QtCore.Qt.Checked
                for wheel in entry.get("roles", set()):
                    wheel.set_names_active({name}, active)

            self._snapshot = {
                name: {"roles": set(info["roles"])} for name, info in current.items()
            }
            self._mw._update_spin_all_enabled()
        finally:
            self._syncing = False

    def _name_stats(self) -> dict[str, dict[str, int]]:
        stats: dict[str, dict[str, int]] = {}
        for wheel in (self._mw.tank, self._mw.dps, self._mw.support):
            for entry in wheel.get_current_entries():
                name = str(entry.get("name", "")).strip()
                if not name:
                    continue
                bucket = stats.setdefault(name, {"total": 0, "active": 0})
                bucket["total"] += 1
                if entry.get("active", True):
                    bucket["active"] += 1
        return stats

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
