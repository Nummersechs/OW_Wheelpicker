from __future__ import annotations

from pathlib import Path
import subprocess

from PySide6 import QtCore, QtGui, QtWidgets


class ScreenRegionSelectorDialog(QtWidgets.QDialog):
    """Simple full-screen region selector over a screenshot."""

    def __init__(
        self,
        screenshot: QtGui.QPixmap,
        *,
        hint_text: str = "",
        auto_accept_on_release: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._screenshot = screenshot
        self._hint_text = hint_text
        self._auto_accept_on_release = bool(auto_accept_on_release)
        self._drag_origin: QtCore.QPoint | None = None
        self._selection = QtCore.QRect()

        self.setWindowFlag(QtCore.Qt.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint, True)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        self.setCursor(QtCore.Qt.CrossCursor)
        self.setMouseTracking(True)

    def selection_rect(self) -> QtCore.QRect:
        return self._selection.normalized().intersected(self.rect())

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(self.rect(), self._screenshot)

        overlay = QtGui.QColor(0, 0, 0, 96)
        painter.fillRect(self.rect(), overlay)

        sel = self.selection_rect()
        if sel.isValid() and sel.width() > 1 and sel.height() > 1:
            painter.drawPixmap(sel, self._screenshot, sel)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 2))
            painter.drawRect(sel)

        if self._hint_text:
            pad = 12
            text_rect = QtCore.QRect(pad, pad, self.width() - (2 * pad), 52)
            painter.setPen(QtGui.QColor(255, 255, 255))
            painter.drawText(
                text_rect,
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop | QtCore.Qt.TextWordWrap,
                self._hint_text,
            )

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.LeftButton:
            return
        self._drag_origin = event.position().toPoint()
        self._selection = QtCore.QRect(self._drag_origin, self._drag_origin)
        self.update()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_origin is None:
            return
        self._selection = QtCore.QRect(self._drag_origin, event.position().toPoint())
        self.update()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.LeftButton:
            return
        if self._drag_origin is None:
            return
        self._selection = QtCore.QRect(self._drag_origin, event.position().toPoint())
        self._drag_origin = None
        self.update()
        if self._auto_accept_on_release:
            sel = self.selection_rect()
            if sel.width() > 5 and sel.height() > 5:
                # Defer accept to avoid re-entrancy while release event is processing.
                QtCore.QTimer.singleShot(0, self.accept)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.LeftButton:
            return
        sel = self.selection_rect()
        if sel.width() > 5 and sel.height() > 5:
            self.accept()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            sel = self.selection_rect()
            if sel.width() > 5 and sel.height() > 5:
                self.accept()
            return
        if event.key() == QtCore.Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)


def select_region_from_primary_screen(
    *,
    hint_text: str = "",
    auto_accept_on_release: bool = False,
    parent: QtWidgets.QWidget | None = None,
) -> tuple[QtGui.QPixmap | None, str | None]:
    screen = QtGui.QGuiApplication.primaryScreen()
    if screen is None:
        return None, "no-screen"

    screenshot = screen.grabWindow(0)
    if screenshot.isNull():
        return None, "screenshot-failed"

    dialog = ScreenRegionSelectorDialog(
        screenshot,
        hint_text=hint_text,
        auto_accept_on_release=auto_accept_on_release,
        parent=parent,
    )
    dialog.setGeometry(screen.geometry())
    result = dialog.exec()
    if result != QtWidgets.QDialog.Accepted:
        return None, "cancelled"

    selection = dialog.selection_rect()
    if selection.width() <= 5 or selection.height() <= 5:
        return None, "selection-too-small"

    ratio = float(screenshot.devicePixelRatio())
    x = int(selection.x() * ratio)
    y = int(selection.y() * ratio)
    w = int(selection.width() * ratio)
    h = int(selection.height() * ratio)
    cropped = screenshot.copy(QtCore.QRect(x, y, max(1, w), max(1, h)))
    if cropped.isNull():
        return None, "crop-failed"
    return cropped, None


def select_region_with_macos_screencapture(
    output_path: Path,
    *,
    timeout_s: float = 45.0,
) -> tuple[QtGui.QPixmap | None, str | None]:
    """Use macOS native interactive region capture via `screencapture -i`."""
    try:
        completed = subprocess.run(
            ["screencapture", "-i", "-x", str(output_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=max(1.0, float(timeout_s)),
        )
    except FileNotFoundError:
        return None, "screencapture-not-found"
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as exc:
        return None, f"exec-error:{exc}"

    # Some macOS builds can still write the file even with a non-zero exit code.
    # If we got a valid image, treat it as success.
    if output_path.exists():
        pix = QtGui.QPixmap(str(output_path))
        if not pix.isNull():
            # Detach from file-backed data before caller removes the temp file.
            return pix.copy(), None
        return None, "capture-invalid-image"

    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stderr_l = stderr.lower()
        # Real user cancel: rc=1 and no useful stderr, or explicit cancel wording.
        if completed.returncode == 1 and (not stderr or "cancel" in stderr_l or "aborted" in stderr_l):
            return None, "cancelled"
        if stderr:
            return None, f"capture-failed:{stderr}"
        return None, f"capture-failed:{completed.returncode}"
    if not output_path.exists():
        return None, "capture-missing-file"

    pix = QtGui.QPixmap(str(output_path))
    if pix.isNull():
        return None, "capture-invalid-image"
    # Detach from file-backed data before caller removes the temp file.
    return pix.copy(), None
