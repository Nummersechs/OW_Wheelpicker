from __future__ import annotations

from typing import List, Set
from PySide6 import QtCore, QtGui, QtWidgets
from view.wheel_disc import WheelDisc
from logic.spin_engine import plan_spin
import config
import random


class WheelWidget(QtWidgets.QGraphicsView):
    """
    Isoliert das Rendering und die Animation des Rads.
    """
    segmentToggled = QtCore.Signal(int, bool, str)

    def __init__(self, names: List[str], parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QGraphicsView { background: transparent; border: none; }")
        self.setMouseTracking(True)
        self.scene = QtWidgets.QGraphicsScene()
        self.setScene(self.scene)

        self.wheel = WheelDisc(names, radius=config.WHEEL_RADIUS)
        self.scene.addItem(self.wheel)
        self.wheel.setPos(0, 0)
        self.wheel.segmentToggled.connect(self.segmentToggled)

        r = self.wheel.radius
        self.scene.setSceneRect(-r - 80, -r - 100, 2 * r + 160, 2 * r + 160)

        self.pointer = self._make_pointer()
        self.scene.addItem(self.pointer)

        size = int(2 * r + 80)
        self.setMinimumSize(size, size)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )
        self.setAlignment(QtCore.Qt.AlignCenter)
        QtCore.QTimer.singleShot(0, self._refit_view)

    def _make_pointer(self) -> QtWidgets.QGraphicsItem:
        r = self.wheel.radius
        path = QtGui.QPainterPath()
        tri = QtGui.QPolygonF(
            [
                QtCore.QPointF(-14, -r - 46),
                QtCore.QPointF(14, -r - 46),
                QtCore.QPointF(0, -r - 14),
            ]
        )
        path.addPolygon(tri)
        item = QtWidgets.QGraphicsPathItem(path)
        item.setBrush(QtGui.QBrush(QtGui.QColor(220, 50, 40)))
        item.setPen(QtGui.QPen(QtCore.Qt.NoPen))
        return item

    def _refit_view(self):
        self._update_wheel_radius()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refit_view()

    def _update_wheel_radius(self):
        if not hasattr(self, "wheel") or not hasattr(self, "scene"):
            return
        vp = self.viewport().size()
        vw, vh = vp.width(), vp.height()
        if vw <= 0 or vh <= 0:
            return
        pad = 20
        extra = 80
        avail = max(0, min(vw, vh) - pad)
        if avail <= extra:
            return
        new_r = max(40, int((avail - extra) / 2))
        if new_r <= 0:
            return
        if new_r != self.wheel.radius:
            self.wheel.set_radius(new_r)
            r = self.wheel.radius
            self.scene.setSceneRect(-r - 40, -r - 60, 2 * r + 80, 2 * r + 80)
            if hasattr(self, "pointer") and self.pointer is not None:
                self.scene.removeItem(self.pointer)
            self.pointer = self._make_pointer()
            self.scene.addItem(self.pointer)

    # ----- API-Wrapper -----
    def set_names(self, names: List[str]):
        self.wheel.set_names(names)

    def set_show_labels(self, show: bool):
        self.wheel.set_show_labels(show)

    def set_disabled_indices(self, disabled: Set[int]):
        self.wheel.set_disabled_indices(disabled)

    def names_list(self) -> List[str]:
        return list(getattr(self.wheel, "names", []))

    def spin(self, idx: int, duration_ms: int) -> random.Random:
        """
        Führt die Animation auf den gegebenen Index aus und gibt den Target-Namen zurück.
        """
        names = self.names_list()
        if not names:
            return None
        idx = max(0, min(idx, len(names) - 1))
        step = 360.0 / len(names)
        slice_center = (idx + 0.5) * step

        self._prepare_anim(slice_center, duration_ms)
        return names[idx]

    def spin_to_random(self, enabled_indices: List[int], duration_ms: int):
        names = self.names_list()
        if not names or not enabled_indices:
            return None
        idx = random.choice(enabled_indices)
        target_name = names[idx]
        step = 360.0 / len(names)
        slice_center = (idx + 0.5) * step
        self._prepare_anim(slice_center, duration_ms)
        return target_name

    def _prepare_anim(self, slice_center: float, duration_ms: int):
        self._reset_anim()
        current = float(self.wheel.rotation()) % 360.0
        self.wheel.setRotation(current)
        plan = plan_spin(current_deg=current, slice_center_deg=slice_center, duration_ms=duration_ms)
        self.anim = QtCore.QPropertyAnimation(self.wheel, b"rotation", self)
        self.anim.setDuration(plan.duration_ms)
        self.anim.setStartValue(plan.start_deg)
        self.anim.setEndValue(plan.end_deg)
        self.anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self.anim.start()

    def _reset_anim(self):
        if hasattr(self, "anim"):
            try:
                if self.anim.state() == QtCore.QAbstractAnimation.Running:
                    self.anim.stop()
            finally:
                self.anim.deleteLater()
                delattr(self, "anim")
