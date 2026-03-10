from __future__ import annotations

from PySide6 import QtWidgets


class AdaptiveSummaryLabel(QtWidgets.QLabel):
    """Compact summary label: reserve less space when text is empty."""

    def __init__(self, text: str = "", *, empty_height: int = 10, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._empty_height = max(0, int(empty_height))
        self._apply_compact_state(text)

    def setText(self, text: str) -> None:  # type: ignore[override]
        super().setText(text)
        self._apply_compact_state(text)

    def _apply_compact_state(self, text: str) -> None:
        has_text = bool(str(text or "").strip())
        self.setVisible(has_text)
        if has_text:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            return
        self.setMinimumHeight(0)
        self.setMaximumHeight(0)

