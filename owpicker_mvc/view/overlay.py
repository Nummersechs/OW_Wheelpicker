from PySide6 import QtCore, QtGui, QtWidgets
from html import escape
import i18n
from utils import flag_icons, qt_runtime, theme as theme_util
from . import style_helpers
from .name_list import NameRowWidget, NamesListPanel

_OVERLAY_CARD_STYLE_CACHE: dict[str, str] = {}
_OVERLAY_TITLE_STYLE_CACHE: dict[str, str] = {}
_OVERLAY_LABEL_STYLE_CACHE: dict[str, str] = {}


def _overlay_card_style(theme: theme_util.Theme) -> str:
    cached = _OVERLAY_CARD_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = (
        "#resultCard { "
        f"background: {theme.card_bg}; "
        "border-radius: 16px; "
        f"border: 1px solid {theme.card_border}; "
        "}"
    )
    _OVERLAY_CARD_STYLE_CACHE[theme.key] = cached
    return cached


def _overlay_title_style(theme: theme_util.Theme) -> str:
    cached = _OVERLAY_TITLE_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = f"font-size:22px; font-weight:800; margin:0; color:{theme.text};"
    _OVERLAY_TITLE_STYLE_CACHE[theme.key] = cached
    return cached


def _overlay_label_style(theme: theme_util.Theme) -> str:
    cached = _OVERLAY_LABEL_STYLE_CACHE.get(theme.key)
    if cached is not None:
        return cached
    cached = f"font-size:17px; margin:4px 0; color:{theme.text};"
    _OVERLAY_LABEL_STYLE_CACHE[theme.key] = cached
    return cached


class ResultOverlay(QtWidgets.QWidget):
    closed = QtCore.Signal()
    modeChosen = QtCore.Signal(bool)
    languageToggleRequested = QtCore.Signal()
    disableResultsRequested = QtCore.Signal()
    deleteNamesConfirmed = QtCore.Signal()
    deleteNamesCancelled = QtCore.Signal()
    ocrImportConfirmed = QtCore.Signal(object)
    ocrImportReplaceRequested = QtCore.Signal(object)
    ocrImportCancelled = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        # Keep overlay as a child widget (not a separate window) to avoid Stage Manager focus jumps.
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(QtCore.Qt.NoFocus)

        self.card = QtWidgets.QFrame(self)
        self.card.setObjectName("resultCard")

        v = QtWidgets.QVBoxLayout(self.card)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(10)

        self.title = QtWidgets.QLabel(i18n.t("overlay.title_result"))
        self.title.setAlignment(QtCore.Qt.AlignCenter)

        # Top-Bar mit zentrierter Überschrift und Sprache-Button rechts
        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        self.btn_language = QtWidgets.QToolButton()
        self.btn_language.setAutoRaise(True)
        self.btn_language.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_language.setFixedSize(40, 32)
        self.btn_language.setIconSize(QtCore.QSize(28, 20))
        self.btn_language.clicked.connect(self.languageToggleRequested.emit)

        self._title_balance = QtWidgets.QWidget(self.card)
        self._title_balance.setFixedSize(self.btn_language.size())
        self._title_balance.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        top_row.addWidget(self._title_balance, 0, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        top_row.addStretch(1)
        top_row.addWidget(self.title, 0, QtCore.Qt.AlignVCenter)
        top_row.addStretch(1)
        top_row.addWidget(self.btn_language, 0, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        v.addLayout(top_row)

        self.lab_tank = QtWidgets.QLabel("")
        self.lab_dps = QtWidgets.QLabel("")
        self.lab_sup = QtWidgets.QLabel("")
        for lab in (self.lab_tank, self.lab_dps, self.lab_sup):
            lab.setAlignment(QtCore.Qt.AlignCenter)
            lab.setWordWrap(True)
            v.addWidget(lab)

        self.ocr_names_panel = NamesListPanel(
            subrole_labels=None,
            enable_mark_for_delete=False,
        )
        self.ocr_names_panel.set_auto_focus_enabled(False)
        self.ocr_names_panel.set_aux_controls_visible(False)
        self.ocr_names_panel.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.ocr_names_panel.hide()
        v.addWidget(self.ocr_names_panel, 1)

        self.btn_close = QtWidgets.QPushButton(i18n.t("overlay.button_ok"))
        self.btn_close.setFixedHeight(40)
        self.btn_close.clicked.connect(self._close)

        self.btn_disable = QtWidgets.QPushButton(i18n.t("overlay.button_disable_results"))
        self.btn_disable.setFixedHeight(40)
        self.btn_disable.clicked.connect(self.disableResultsRequested.emit)

        self.btn_online = QtWidgets.QPushButton(i18n.t("overlay.button_online"))
        self.btn_online.setFixedHeight(40)
        self.btn_offline = QtWidgets.QPushButton(i18n.t("overlay.button_offline"))
        self.btn_offline.setFixedHeight(40)

        self.btn_delete_cancel = QtWidgets.QPushButton(i18n.t("names.delete_confirm_cancel"))
        self.btn_delete_cancel.setFixedHeight(40)
        self.btn_delete_confirm = QtWidgets.QPushButton(i18n.t("names.delete_confirm_delete"))
        self.btn_delete_confirm.setFixedHeight(40)
        self.btn_ocr_cancel = QtWidgets.QPushButton(i18n.t("ocr.pick_cancel"))
        self.btn_ocr_cancel.setFixedHeight(40)
        self.btn_ocr_replace = QtWidgets.QPushButton(i18n.t("ocr.pick_replace"))
        self.btn_ocr_replace.setFixedHeight(40)
        self.btn_ocr_confirm = QtWidgets.QPushButton(i18n.t("ocr.pick_confirm"))
        self.btn_ocr_confirm.setFixedHeight(40)
        self._apply_button_labels()
        self._set_min_widths()

        self.btn_online.clicked.connect(self._choose_online)
        self.btn_offline.clicked.connect(self._choose_offline)
        self.btn_delete_cancel.clicked.connect(self._cancel_delete_names)
        self.btn_delete_confirm.clicked.connect(self._confirm_delete_names)
        self.btn_ocr_cancel.clicked.connect(self._cancel_ocr_import)
        self.btn_ocr_replace.clicked.connect(self._replace_ocr_import)
        self.btn_ocr_confirm.clicked.connect(self._confirm_ocr_import)

        # Buttons in einer Zeile anordnen
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_offline)
        btn_row.addWidget(self.btn_online)
        btn_row.addWidget(self.btn_delete_cancel)
        btn_row.addWidget(self.btn_delete_confirm)
        btn_row.addWidget(self.btn_ocr_confirm)
        btn_row.addWidget(self.btn_ocr_replace)
        btn_row.addWidget(self.btn_ocr_cancel)
        btn_row.addWidget(self.btn_disable)
        btn_row.addWidget(self.btn_close)
        btn_row.addStretch(1)
        self._btn_row = btn_row
        v.addLayout(btn_row)

        self.hide()
        self._last_view: dict | None = None
        self._applied_theme_key: str | None = None
        # Default to light; caller reapplies with the persisted theme.
        default_theme = theme_util.get_theme("light")
        self.apply_theme(default_theme, theme_util.tool_button_stylesheet(default_theme))

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 140))
        p.end()
        super().paintEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout_card_for_current_view()

    def _layout_card_for_current_view(self) -> None:
        """Keep card size in sync with the currently active overlay view."""
        view = getattr(self, "_last_view", {}) or {}
        view_type = view.get("type")
        if view_type == "ocr_name_picker":
            # OCR picker needs more horizontal room for per-name role/subrole checkboxes.
            w = max(760, int(self.width() * 0.72))
            h = max(380, int(self.height() * 0.58))
        else:
            w = max(520, int(self.width() * 0.45))
            h = max(280, int(self.height() * 0.30))
        self.card.setGeometry((self.width() - w) // 2, (self.height() - h) // 2, w, h)

    def _show(self):
        if self.parent():
            self.setGeometry(self.parent().rect())
        self._layout_card_for_current_view()
        self.show()
        qt_runtime.safe_raise(self)
        # Keine Fokus-Erzwingung, damit kein unerwarteter Refokus entsteht.

    def _set_info_labels_visible(self, *, tank: bool, dps: bool, sup: bool) -> None:
        self.lab_tank.setVisible(bool(tank))
        self.lab_dps.setVisible(bool(dps))
        self.lab_sup.setVisible(bool(sup))

    def _set_action_buttons_visible(
        self,
        *,
        close: bool = False,
        disable: bool = False,
        online: bool = False,
        offline: bool = False,
        delete_cancel: bool = False,
        delete_confirm: bool = False,
        ocr_cancel: bool = False,
        ocr_replace: bool = False,
        ocr_confirm: bool = False,
    ) -> None:
        self.btn_close.setVisible(bool(close))
        self.btn_disable.setVisible(bool(disable))
        self.btn_online.setVisible(bool(online))
        self.btn_offline.setVisible(bool(offline))
        self.btn_delete_cancel.setVisible(bool(delete_cancel))
        self.btn_delete_confirm.setVisible(bool(delete_confirm))
        self.btn_ocr_cancel.setVisible(bool(ocr_cancel))
        self.btn_ocr_replace.setVisible(bool(ocr_replace))
        self.btn_ocr_confirm.setVisible(bool(ocr_confirm))
        if hasattr(self, "_btn_row"):
            ocr_mode_active = bool(ocr_cancel or ocr_replace or ocr_confirm)
            result_actions_active = bool(
                close and disable
                and not (online or offline or delete_cancel or delete_confirm or ocr_cancel or ocr_replace or ocr_confirm)
            )
            if ocr_mode_active:
                self._btn_row.setSpacing(80)
            elif result_actions_active:
                self._btn_row.setSpacing(14)
            else:
                self._btn_row.setSpacing(8)

    def show_result(self, tank, dps, sup):
        self._apply_button_labels()
        self.title.setText(i18n.t("overlay.title_result"))
        self._set_info_labels_visible(tank=True, dps=True, sup=True)
        self.lab_tank.setText(f"Tank: <b>{escape(tank)}</b>")
        self.lab_dps.setText(f"Damage: <b>{escape(dps)}</b>")
        self.lab_sup.setText(f"Support: <b>{escape(sup)}</b>")
        self.ocr_names_panel.setVisible(False)
        self._set_action_buttons_visible(close=True, disable=True)
        self._last_view = {"type": "result", "data": (tank, dps, sup)}
        self._show()

    def show_message(self, title, lines):
        self._apply_button_labels()
        self.title.setText(escape(title))
        self._set_info_labels_visible(tank=True, dps=True, sup=True)
        texts = list(lines) + ["", "", ""]
        self.lab_tank.setText(escape(texts[0]))
        self.lab_dps.setText(escape(texts[1]))
        self.lab_sup.setText(escape(texts[2]))
        self.ocr_names_panel.setVisible(False)
        self._set_action_buttons_visible(close=True)
        self._last_view = {"type": "message", "data": (title, list(lines))}
        self._show()

    def show_online_choice(self):
        """Overlay zur Wahl von Online/Offline anzeigen."""
        self._apply_button_labels()
        self.title.setText(i18n.t("overlay.mode_title"))
        self._set_info_labels_visible(tank=True, dps=True, sup=True)

        # Deine drei Zeilen im bekannten Stil
        self.lab_tank.setText(i18n.t("overlay.mode_line1"))
        self.lab_dps.setText(i18n.t("overlay.mode_line2"))
        self.lab_sup.setText(i18n.t("overlay.mode_line3"))
        self.ocr_names_panel.setVisible(False)
        self._set_action_buttons_visible(online=True, offline=True)

        self._last_view = {"type": "online_choice"}
        self._show()

    def show_delete_names_confirm(self, count: int):
        self._apply_button_labels()
        count_value = max(0, int(count))
        self.title.setText(i18n.t("names.delete_confirm_title"))
        self._set_info_labels_visible(tank=True, dps=False, sup=False)
        self.lab_tank.setText(i18n.t("names.delete_confirm_message", count=count_value))
        self.lab_dps.setText("")
        self.lab_sup.setText("")
        self.ocr_names_panel.setVisible(False)
        self._set_action_buttons_visible(delete_cancel=True, delete_confirm=True)
        self._last_view = {"type": "delete_names_confirm", "data": count_value}
        self._show()

    def _set_ocr_subrole_labels(self, labels: list[str] | None) -> None:
        names_list = self.ocr_names_panel.names
        normalized = [str(label).strip() for label in (labels or []) if str(label).strip()]
        names_list.subrole_labels = normalized
        names_list.has_subroles = bool(normalized)

    def _apply_ocr_picker_compact_layout(self) -> None:
        names_list = self.ocr_names_panel.names
        # Keep OCR rows compact: shorter name field + tighter per-row height.
        row_height = 18
        edit_height = 16
        name_max_width = 164 if names_list.has_subroles else 188
        names_list.set_row_visual_profile(
            row_height=row_height,
            name_edit_height=edit_height,
            name_min_width_with_subroles=min(name_max_width, 164),
            name_min_width_without_subroles=min(name_max_width, 188),
            name_max_width=name_max_width,
            read_only=False,
        )

    @staticmethod
    def _ocr_picker_hint_text(hint_key: str, hint_kwargs: dict | None, count: int) -> str:
        payload = {"count": max(0, int(count))}
        if isinstance(hint_kwargs, dict):
            payload.update(hint_kwargs)
        try:
            return i18n.t(hint_key, **payload)
        except Exception:
            return i18n.t("ocr.pick_hint", count=max(0, int(count)))

    def show_ocr_name_picker(
        self,
        names: list[str],
        subrole_labels: list[str] | None = None,
        *,
        hint_key: str = "ocr.pick_hint",
        hint_kwargs: dict | None = None,
    ):
        self._apply_button_labels()
        display_names = [str(name).strip() for name in names if str(name).strip()]
        self._set_ocr_subrole_labels(subrole_labels)
        self.title.setText(i18n.t("ocr.pick_title"))
        self._set_info_labels_visible(tank=True, dps=False, sup=False)
        self.lab_tank.setText(
            self._ocr_picker_hint_text(
                str(hint_key or "ocr.pick_hint"),
                hint_kwargs,
                len(display_names),
            )
        )
        self.lab_dps.setText("")
        self.lab_sup.setText("")
        names_list = self.ocr_names_panel.names
        blockers = [QtCore.QSignalBlocker(names_list), QtCore.QSignalBlocker(names_list.model())]
        try:
            names_list.clear()
            names_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            for name in display_names:
                names_list.add_name(name, subroles=[], active=True)
            self._apply_ocr_picker_compact_layout()
        finally:
            del blockers
        self.ocr_names_panel.refresh_action_state()
        self.ocr_names_panel.setVisible(True)
        self._set_action_buttons_visible(ocr_cancel=True, ocr_replace=True, ocr_confirm=True)
        self._last_view = {
            "type": "ocr_name_picker",
            "data": display_names,
            "hint_key": str(hint_key or "ocr.pick_hint"),
            "hint_kwargs": dict(hint_kwargs or {}),
        }
        self._show()

    def set_choice_enabled(self, enabled: bool):
        """Aktiviert/Deaktiviert die Online/Offline-Buttons (z.B. während des Ladens)."""
        self.btn_online.setEnabled(enabled)
        self.btn_offline.setEnabled(enabled)

    def _choose_online(self):
        self.hide()
        self.modeChosen.emit(True)   # True = Online

    def _choose_offline(self):
        self.hide()
        self.modeChosen.emit(False)  # False = Offline

    def _cancel_delete_names(self):
        self.hide()
        self.deleteNamesCancelled.emit()

    def _confirm_delete_names(self):
        self.hide()
        self.deleteNamesConfirmed.emit()

    def _cancel_ocr_import(self):
        self.hide()
        self.ocrImportCancelled.emit()

    def _selected_ocr_entries(self) -> list[dict]:
        selected: list[dict] = []
        names_list = self.ocr_names_panel.names
        for i in range(names_list.count()):
            item = names_list.item(i)
            if item is None or item.checkState() != QtCore.Qt.Checked:
                continue
            widget = names_list.itemWidget(item)
            edit = getattr(widget, "edit", None)
            if isinstance(edit, QtWidgets.QLineEdit):
                text = edit.text().strip()
            else:
                text = item.text().strip()
            if text:
                subroles: list[str] = []
                if isinstance(widget, NameRowWidget):
                    subroles = sorted(
                        {
                            str(role).strip()
                            for role in widget.selected_subroles()
                            if str(role).strip()
                        }
                    )
                selected.append({"name": text, "subroles": subroles})
        return selected

    def _replace_ocr_import(self):
        selected = self._selected_ocr_entries()
        self.hide()
        self.ocrImportReplaceRequested.emit(selected)

    def _confirm_ocr_import(self):
        selected = self._selected_ocr_entries()
        self.hide()
        self.ocrImportConfirmed.emit(selected)

    def _close(self):
        self.hide()
        self.closed.emit()

    def set_language(self, lang: str):
        """Refresh labels while keeping current visibility."""
        # Zustand merken, damit Online/Offline nicht erneut deaktiviert wird
        prev_choice_enabled = self.btn_online.isEnabled() and self.btn_offline.isEnabled()
        i18n.set_language(lang)
        self._apply_button_labels()
        self._set_min_widths()
        self._apply_flag()
        # Re-render current view if something is shown
        if not self.isVisible() or not self._last_view:
            return
        kind = self._last_view.get("type")
        data = self._last_view.get("data") or ()
        if kind == "result" and len(data) == 3:
            self.show_result(*data)
        elif kind == "message" and len(data) == 2:
            title, lines = data
            self.show_message(title, lines)
        elif kind == "online_choice":
            self.show_online_choice()
            if prev_choice_enabled:
                self.set_choice_enabled(True)
        elif kind == "delete_names_confirm":
            try:
                count_value = int(data)
            except Exception:
                count_value = 0
            self.show_delete_names_confirm(count_value)
        elif kind == "ocr_name_picker":
            count_value = self.ocr_names_panel.names.count()
            hint_key = str(self._last_view.get("hint_key") or "ocr.pick_hint")
            hint_kwargs = self._last_view.get("hint_kwargs")
            self.title.setText(i18n.t("ocr.pick_title"))
            self.lab_tank.setText(self._ocr_picker_hint_text(hint_key, hint_kwargs, count_value))

    def apply_theme(self, theme: theme_util.Theme, tool_style: str | None = None) -> None:
        """Update overlay colors to match the active theme."""
        if self._applied_theme_key == theme.key:
            return
        self.card.setStyleSheet(_overlay_card_style(theme))
        self.title.setStyleSheet(_overlay_title_style(theme))
        label_style = _overlay_label_style(theme)
        for lab in (self.lab_tank, self.lab_dps, self.lab_sup):
            lab.setStyleSheet(label_style)
        if tool_style:
            self.btn_language.setStyleSheet(tool_style)
        self.ocr_names_panel.apply_theme(theme)
        style_helpers.style_primary_button(self.btn_online, theme)
        style_helpers.style_primary_button(self.btn_offline, theme)
        style_helpers.style_primary_button(self.btn_delete_cancel, theme)
        style_helpers.style_danger_button(self.btn_delete_confirm, theme)
        style_helpers.style_danger_button(self.btn_ocr_cancel, theme)
        style_helpers.style_warning_button(self.btn_ocr_replace, theme)
        style_helpers.style_success_button(self.btn_ocr_confirm, theme)
        self._applied_theme_key = theme.key

    def _apply_button_labels(self):
        self.btn_close.setText(i18n.t("overlay.button_ok"))
        self.btn_close.setToolTip(i18n.t("overlay.button_ok_tooltip"))
        self.btn_disable.setText(i18n.t("overlay.button_disable_results"))
        self.btn_disable.setToolTip(i18n.t("overlay.button_disable_results_tooltip"))
        self.btn_online.setText(i18n.t("overlay.button_online"))
        self.btn_online.setToolTip(i18n.t("overlay.button_online_tooltip"))
        self.btn_offline.setText(i18n.t("overlay.button_offline"))
        self.btn_offline.setToolTip(i18n.t("overlay.button_offline_tooltip"))
        self.btn_delete_cancel.setText(i18n.t("names.delete_confirm_cancel"))
        self.btn_delete_cancel.setToolTip(i18n.t("names.delete_confirm_cancel_tooltip"))
        self.btn_delete_confirm.setText(i18n.t("names.delete_confirm_delete"))
        self.btn_delete_confirm.setToolTip(i18n.t("names.delete_confirm_delete_tooltip"))
        self.btn_ocr_cancel.setText(i18n.t("ocr.pick_cancel"))
        self.btn_ocr_cancel.setToolTip(i18n.t("ocr.pick_cancel_tooltip"))
        self.btn_ocr_replace.setText(i18n.t("ocr.pick_replace"))
        self.btn_ocr_replace.setToolTip(i18n.t("ocr.pick_replace_tooltip"))
        self.btn_ocr_confirm.setText(i18n.t("ocr.pick_confirm"))
        self.btn_ocr_confirm.setToolTip(i18n.t("ocr.pick_confirm_tooltip"))

    def _set_min_widths(self):
        """Fix widths so language switch doesn't move layout."""
        font = self.btn_close.font()
        fm = QtGui.QFontMetrics(font)
        def max_width(keys):
            max_w = 0
            for key in keys:
                entry = i18n.TRANSLATIONS.get(key, {})
                texts = entry.values() if isinstance(entry, dict) else [entry]
                for txt in texts:
                    if txt is None:
                        continue
                    max_w = max(max_w, fm.horizontalAdvance(str(txt)))
            return max_w + 48

        # Keep result actions compact: "OK" should not inherit the long disable-button width.
        ok_width = max_width(("overlay.button_ok",))
        ok_width = max(96, min(int(ok_width), 140))
        self.btn_close.setMinimumWidth(ok_width)
        self.btn_close.setMaximumWidth(ok_width)

        disable_width = max_width(("overlay.button_disable_results",))
        disable_width = max(200, min(int(disable_width), 320))
        self.btn_disable.setMinimumWidth(disable_width)
        self.btn_disable.setMaximumWidth(disable_width)

        choice_width = max_width(("overlay.button_online", "overlay.button_offline"))
        for btn in (
            self.btn_online,
            self.btn_offline,
        ):
            btn.setMinimumWidth(choice_width)
            btn.setMaximumWidth(choice_width)

        delete_width = max_width(("names.delete_confirm_cancel", "names.delete_confirm_delete"))
        for btn in (self.btn_delete_cancel, self.btn_delete_confirm):
            btn.setMinimumWidth(delete_width)
            btn.setMaximumWidth(delete_width)

        # Keep OCR action buttons compact enough to avoid overlap on smaller windows.
        ocr_width = max_width(("ocr.pick_cancel", "ocr.pick_replace", "ocr.pick_confirm")) - 20
        ocr_width = max(120, int(ocr_width))
        for btn in (self.btn_ocr_cancel, self.btn_ocr_replace, self.btn_ocr_confirm):
            btn.setMinimumWidth(ocr_width)
            btn.setMaximumWidth(ocr_width)

    def _apply_flag(self):
        """Aktualisiert Text/Tooltip des Sprache-Buttons."""
        if not hasattr(self, "btn_language"):
            return
        flag = flag_icons.icon_for_language(i18n.get_language())
        tooltip = i18n.t("language.tooltip.de") if i18n.get_language() == "de" else i18n.t("language.tooltip.en")
        self.btn_language.setIcon(flag)
        self.btn_language.setText("")
        self.btn_language.setToolTip(tooltip)
