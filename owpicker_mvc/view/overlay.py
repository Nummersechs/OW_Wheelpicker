from PySide6 import QtCore, QtGui, QtWidgets
from html import escape
import i18n
from utils import flag_icons, theme as theme_util

class ResultOverlay(QtWidgets.QWidget):
    closed = QtCore.Signal()
    modeChosen = QtCore.Signal(bool)
    languageToggleRequested = QtCore.Signal()
    disableResultsRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)

        self.card = QtWidgets.QFrame(self)
        self.card.setObjectName("resultCard")

        v = QtWidgets.QVBoxLayout(self.card)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(10)

        # Top-Bar mit Sprache-Button rechts
        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)
        top_row.addStretch(1)
        self.btn_language = QtWidgets.QToolButton()
        self.btn_language.setAutoRaise(True)
        self.btn_language.setCursor(QtCore.Qt.PointingHandCursor)
        self.btn_language.setFixedSize(40, 32)
        self.btn_language.setIconSize(QtCore.QSize(28, 20))
        self.btn_language.clicked.connect(self.languageToggleRequested.emit)
        top_row.addWidget(self.btn_language, 0, QtCore.Qt.AlignRight)
        v.addLayout(top_row)

        self.title = QtWidgets.QLabel(i18n.t("overlay.title_result"))
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        v.addWidget(self.title)

        self.lab_tank = QtWidgets.QLabel("")
        self.lab_dps = QtWidgets.QLabel("")
        self.lab_sup = QtWidgets.QLabel("")
        for lab in (self.lab_tank, self.lab_dps, self.lab_sup):
            lab.setAlignment(QtCore.Qt.AlignCenter)
            lab.setWordWrap(True)
            v.addWidget(lab)

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
        self._apply_button_labels()
        self._set_min_widths()

        self.btn_online.clicked.connect(self._choose_online)
        self.btn_offline.clicked.connect(self._choose_offline)
        # Hover für Warmup blockierbar halten
        self._block_hover = False
        self.btn_online.installEventFilter(self)
        self.btn_offline.installEventFilter(self)

        # Buttons in einer Zeile anordnen
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_offline)
        btn_row.addWidget(self.btn_online)
        btn_row.addWidget(self.btn_disable)
        btn_row.addWidget(self.btn_close)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        self.hide()
        self._last_view: dict | None = None
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
        w = max(520, int(self.width() * 0.45))
        h = max(280, int(self.height() * 0.30))
        self.card.setGeometry((self.width() - w) // 2, (self.height() - h) // 2, w, h)

    def _show(self):
        if self.parent():
            self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        self.activateWindow()

    def show_result(self, tank, dps, sup):
        self._apply_button_labels()
        self.title.setText(i18n.t("overlay.title_result"))
        self.lab_tank.setText(f"Tank: <b>{escape(tank)}</b>")
        self.lab_dps.setText(f"Damage: <b>{escape(dps)}</b>")
        self.lab_sup.setText(f"Support: <b>{escape(sup)}</b>")
        self.btn_close.show()
        self.btn_disable.show()
        self.btn_online.hide()
        self.btn_offline.hide()
        self._last_view = {"type": "result", "data": (tank, dps, sup)}
        self._show()

    def show_message(self, title, lines):
        self._apply_button_labels()
        self.title.setText(escape(title))
        texts = list(lines) + ["", "", ""]
        self.lab_tank.setText(escape(texts[0]))
        self.lab_dps.setText(escape(texts[1]))
        self.lab_sup.setText(escape(texts[2]))
        self.btn_close.show()
        self.btn_disable.hide()
        self.btn_online.hide()
        self.btn_offline.hide()
        self._last_view = {"type": "message", "data": (title, list(lines))}
        self._show()

    def show_online_choice(self):
        """Overlay zur Wahl von Online/Offline anzeigen."""
        self._apply_button_labels()
        self.title.setText(i18n.t("overlay.mode_title"))

        # Deine drei Zeilen im bekannten Stil
        self.lab_tank.setText(i18n.t("overlay.mode_line1"))
        self.lab_dps.setText(i18n.t("overlay.mode_line2"))
        self.lab_sup.setText(i18n.t("overlay.mode_line3"))

        # Online/Offline-Buttons anzeigen, OK ausblenden
        self.btn_close.hide()
        self.btn_disable.hide()
        self.btn_online.show()
        self.btn_offline.show()
        self.set_choice_enabled(False)

        self._last_view = {"type": "online_choice"}
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


    def _close(self):
        self.hide()
        self.closed.emit()

    def set_language(self, lang: str):
        """Refresh labels while keeping current visibility."""
        # Zustand merken, damit Online/Offline nicht erneut deaktiviert wird
        prev_choice_enabled = self.btn_online.isEnabled() and self.btn_offline.isEnabled()
        prev_hover_block = getattr(self, "_block_hover", False)
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
            self.set_hover_blocked(prev_hover_block)

    def apply_theme(self, theme: theme_util.Theme, tool_style: str | None = None) -> None:
        """Update overlay colors to match the active theme."""
        self.card.setStyleSheet(
            "#resultCard { "
            f"background: {theme.card_bg}; "
            "border-radius: 16px; "
            f"border: 1px solid {theme.card_border}; "
            "}"
        )
        self.title.setStyleSheet(f"font-size:22px; font-weight:800; margin-bottom:8px; color:{theme.text};")
        for lab in (self.lab_tank, self.lab_dps, self.lab_sup):
            lab.setStyleSheet(f"font-size:17px; margin:4px 0; color:{theme.text};")
        if tool_style:
            self.btn_language.setStyleSheet(tool_style)

    def _apply_button_labels(self):
        self.btn_close.setText(i18n.t("overlay.button_ok"))
        self.btn_disable.setText(i18n.t("overlay.button_disable_results"))
        self.btn_online.setText(i18n.t("overlay.button_online"))
        self.btn_offline.setText(i18n.t("overlay.button_offline"))

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

        result_width = max_width(("overlay.button_ok", "overlay.button_disable_results"))
        for btn in (self.btn_close, self.btn_disable):
            btn.setMinimumWidth(result_width)
            btn.setMaximumWidth(result_width)

        choice_width = max_width(("overlay.button_online", "overlay.button_offline"))
        for btn in (self.btn_online, self.btn_offline):
            btn.setMinimumWidth(choice_width)
            btn.setMaximumWidth(choice_width)

    def _apply_flag(self):
        """Aktualisiert Text/Tooltip des Sprache-Buttons."""
        if not hasattr(self, "btn_language"):
            return
        flag = flag_icons.icon_for_language(i18n.get_language())
        tooltip = i18n.t("language.tooltip.de") if i18n.get_language() == "de" else i18n.t("language.tooltip.en")
        self.btn_language.setIcon(flag)
        self.btn_language.setText("")
        self.btn_language.setToolTip(tooltip)

    # --- Hover-Steuerung für Warmup ---
    def set_hover_blocked(self, blocked: bool):
        """Deaktiviert Hover-Effekte der Online/Offline-Buttons temporär."""
        self._block_hover = bool(blocked)

    def eventFilter(self, obj, event):
        if obj in (getattr(self, "btn_online", None), getattr(self, "btn_offline", None)):
            if self._block_hover and event.type() in (
                QtCore.QEvent.HoverEnter,
                QtCore.QEvent.HoverLeave,
                QtCore.QEvent.HoverMove,
                QtCore.QEvent.Enter,
                QtCore.QEvent.Leave,
            ):
                return True
        return super().eventFilter(obj, event)
