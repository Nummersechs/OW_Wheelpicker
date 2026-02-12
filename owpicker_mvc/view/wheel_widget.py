from __future__ import annotations

from typing import List, Set
from PySide6 import QtCore, QtGui, QtWidgets
from view.wheel_disc import WheelDisc
from logic.spin_engine import plan_spin
import config


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
        self._hover_trace_budget = int(getattr(config, "HOVER_TRACE_BUDGET_PER_VIEW", 0))
        self._rearm_hover_tracking()
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
        if hasattr(self, "wheel") and hasattr(self.wheel, "_ensure_cache"):
            self.wheel._ensure_cache(force=False)

    def showEvent(self, event):
        super().showEvent(event)
        # Ensure hover events remain active after show/hide cycles.
        self._rearm_hover_tracking()
        # Sobald der View sichtbar ist, Cache/Geometrie auf finale Größe bringen
        self._refit_view()
        if hasattr(self, "wheel") and hasattr(self.wheel, "_ensure_cache"):
            self.wheel._ensure_cache(force=False)

    def enterEvent(self, event):
        # On some platforms, mouse tracking can drop after activation changes.
        self._rearm_hover_tracking()
        super().enterEvent(event)

    def viewportEvent(self, event: QtCore.QEvent) -> bool:
        try:
            etype = int(event.type())
            if getattr(config, "TRACE_HOVER", False) and getattr(self, "_hover_trace_budget", 0) > 0:
                if etype in (
                    QtCore.QEvent.MouseMove,
                    QtCore.QEvent.HoverMove,
                    QtCore.QEvent.Enter,
                    QtCore.QEvent.Leave,
                ):
                    self._hover_trace_budget -= 1
                    win = self.window()
                    if hasattr(win, "_trace_hover_event"):
                        try:
                            vp = self.viewport()
                            pos = None
                            if hasattr(event, "position"):
                                try:
                                    p = event.position()
                                    pos = f"{round(p.x(),1)},{round(p.y(),1)}"
                                except Exception:
                                    pos = None
                            active = False
                            try:
                                active = bool(win and win.isActiveWindow())
                            except Exception:
                                active = False
                            win._trace_hover_event(
                                "viewport_event",
                                etype=etype,
                                etype_name=QtCore.QEvent.Type(etype).name,
                                view=type(self).__name__,
                                pos=pos,
                                active=active,
                                visible=vp.isVisible() if vp else None,
                            )
                        except Exception:
                            pass
            if getattr(config, "HOVER_PUMP_ON_START", False):
                try:
                    if etype in (QtCore.QEvent.MouseMove, QtCore.QEvent.HoverMove):
                        if hasattr(event, "spontaneous") and event.spontaneous():
                            win = self.window()
                            if hasattr(win, "_mark_hover_seen"):
                                win._mark_hover_seen(source="viewport_spontaneous")
                except Exception:
                    pass
            if etype in (QtCore.QEvent.MouseMove, QtCore.QEvent.HoverMove):
                try:
                    win = self.window()
                    if hasattr(event, "spontaneous") and event.spontaneous():
                        if hasattr(win, "_mark_hover_user_move"):
                            win._mark_hover_user_move()
                    elif hasattr(win, "_mark_hover_activity"):
                        win._mark_hover_activity()
                except Exception:
                    pass
        except Exception:
            return super().viewportEvent(event)
        return super().viewportEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mousePressEvent(event)
        if not event.isAccepted():
            event.accept()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if not event.isAccepted():
            event.accept()

    def _rearm_hover_tracking(self) -> None:
        self.setMouseTracking(True)
        self.setInteractive(True)
        try:
            self.setAttribute(QtCore.Qt.WA_Hover, True)
        except Exception:
            pass
        try:
            vp = self.viewport()
            vp.setMouseTracking(True)
            vp.setAttribute(QtCore.Qt.WA_Hover, True)
        except Exception:
            pass

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
