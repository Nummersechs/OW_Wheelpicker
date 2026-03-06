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
        # Smart mode avoids missed redraws for rotations while keeping cost lower
        # than forcing full viewport updates on every frame.
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.SmartViewportUpdate)
        self._hover_trace_budget = int(getattr(config, "HOVER_TRACE_BUDGET_PER_VIEW", 0))
        self._cache_warmup_retry_scheduled = False
        self._rearm_hover_tracking()
        self.scene = QtWidgets.QGraphicsScene()
        self.setScene(self.scene)
        self._overlay_reserve_widget: QtWidgets.QWidget | None = None
        self._overlay_margin_top = 0
        self._overlay_margin_right = 0
        self._overlay_clearance_px = 6
        self._scene_pad_side = 14
        # Keep pointer row alignment deterministic; pointer top padding is
        # computed dynamically and already reserves the required top space.
        self._scene_pad_top = 0
        self._scene_pad_bottom = 0
        self._fit_pad = 2

        self.wheel = WheelDisc(names, radius=config.WHEEL_RADIUS)
        self.scene.addItem(self.wheel)
        self.wheel.setPos(0, 0)
        self.wheel.segmentToggled.connect(self.segmentToggled)

        r = self.wheel.radius
        self._apply_scene_rect()

        self.pointer = self._make_pointer()
        self.scene.addItem(self.pointer)

        size_w = int((2 * r) + (2 * self._scene_pad_side))
        size_h = int((2 * r) + self._scene_pad_top + self._scene_pad_bottom)
        size = max(size_w, size_h)
        self._preferred_canvas_size = max(180, size)
        self._minimum_canvas_size = max(120, min(200, self._preferred_canvas_size))
        self.setMinimumSize(self._minimum_canvas_size, self._minimum_canvas_size)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding,
        )
        self.setAlignment(QtCore.Qt.AlignCenter)
        QtCore.QTimer.singleShot(0, self._refit_view)

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(self._minimum_canvas_size, self._minimum_canvas_size)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(self._preferred_canvas_size, self._preferred_canvas_size)

    def _pointer_geometry(self, radius: int) -> tuple[int, int, int]:
        ref_radius = max(1, int(getattr(config, "WHEEL_RADIUS", radius or 1)))
        scale = float(max(1, int(radius))) / float(ref_radius)
        # Keep pointer readable on very small wheels and avoid oversized growth.
        scale = max(0.55, min(1.8, scale))
        half_width = max(8, int(round(14 * scale)))
        tip_gap = max(8, int(round(14 * scale)))
        base_gap = max(tip_gap + 10, int(round(46 * scale)))
        return half_width, base_gap, tip_gap

    def _pointer_top_padding_for_radius(self, radius: int) -> int:
        _half_width, base_gap, _tip_gap = self._pointer_geometry(radius)
        return max(0, int(base_gap))

    def _make_pointer(self) -> QtWidgets.QGraphicsItem:
        r = self.wheel.radius
        half_width, base_gap, tip_gap = self._pointer_geometry(r)
        path = QtGui.QPainterPath()
        tri = QtGui.QPolygonF(
            [
                QtCore.QPointF(-half_width, -r - base_gap),
                QtCore.QPointF(half_width, -r - base_gap),
                QtCore.QPointF(0, -r - tip_gap),
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
        self._maybe_warm_cache(reason="resize")

    def showEvent(self, event):
        super().showEvent(event)
        # Ensure hover events remain active after show/hide cycles.
        self._rearm_hover_tracking()
        # Sobald der View sichtbar ist, Cache/Geometrie auf finale Größe bringen
        self._refit_view()
        self._maybe_warm_cache(reason="show")

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

    def set_overlay_reserve_widget(
        self,
        widget: QtWidgets.QWidget | None,
        *,
        margin_top: int = 0,
        margin_right: int = 0,
    ) -> None:
        prev = getattr(self, "_overlay_reserve_widget", None)
        if isinstance(prev, QtWidgets.QWidget):
            try:
                prev.removeEventFilter(self)
            except Exception:
                pass
        self._overlay_reserve_widget = widget if isinstance(widget, QtWidgets.QWidget) else None
        self._overlay_margin_top = max(0, int(margin_top))
        self._overlay_margin_right = max(0, int(margin_right))
        if self._overlay_reserve_widget is not None:
            try:
                self._overlay_reserve_widget.installEventFilter(self)
            except Exception:
                pass
        self._refit_view()

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        reserve_widget = getattr(self, "_overlay_reserve_widget", None)
        if obj is reserve_widget and event.type() in (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
            QtCore.QEvent.Hide,
            QtCore.QEvent.Move,
        ):
            QtCore.QTimer.singleShot(0, self._refit_view)
        return super().eventFilter(obj, event)

    def _overlay_reserve_size(self) -> tuple[int, int]:
        widget = getattr(self, "_overlay_reserve_widget", None)
        if not isinstance(widget, QtWidgets.QWidget):
            return 0, 0
        if not widget.isVisible():
            return 0, 0
        reserve_right = max(
            0,
            int(widget.width()) + int(self._overlay_margin_right) + int(self._overlay_clearance_px),
        )
        reserve_top = max(
            0,
            int(widget.height()) + int(self._overlay_margin_top) + int(self._overlay_clearance_px),
        )
        return reserve_right, reserve_top

    def _apply_scene_rect(self) -> None:
        r = int(getattr(self.wheel, "radius", 0))
        side = max(0, int(self._scene_pad_side))
        top = max(
            max(0, int(self._scene_pad_top)),
            self._pointer_top_padding_for_radius(r),
        )
        bottom = max(0, int(self._scene_pad_bottom))
        self.scene.setSceneRect(
            -r - side,
            -r - top,
            (2 * r) + (2 * side),
            (2 * r) + top + bottom,
        )

    def _update_wheel_radius(self):
        if not hasattr(self, "wheel") or not hasattr(self, "scene"):
            return
        vp = self.viewport().size()
        vw, vh = vp.width(), vp.height()
        if vw <= 0 or vh <= 0:
            return
        reserve_right, reserve_top = self._overlay_reserve_size()
        avail_w = max(0, int(vw) - int(self._fit_pad) - int(reserve_right))
        avail_h = max(0, int(vh) - int(self._fit_pad) - int(reserve_top))
        radius_w = int((avail_w - (2 * int(self._scene_pad_side))) / 2)
        scene_top = max(0, int(self._scene_pad_top))
        scene_bottom = max(0, int(self._scene_pad_bottom))
        radius_h = int((avail_h - scene_top - scene_bottom) / 2)
        new_r = max(32, min(radius_w, radius_h))
        if new_r > 0:
            dyn_top = max(scene_top, self._pointer_top_padding_for_radius(new_r))
            radius_h_dyn = int((avail_h - dyn_top - scene_bottom) / 2)
            new_r = max(32, min(new_r, radius_h_dyn))
        if new_r <= 0:
            return
        if new_r != self.wheel.radius:
            self.wheel.set_radius(new_r)
            self._apply_scene_rect()
            if hasattr(self, "pointer") and self.pointer is not None:
                self.scene.removeItem(self.pointer)
            self.pointer = self._make_pointer()
            self.scene.addItem(self.pointer)

    def _can_warm_cache_now(self) -> bool:
        if not self.isVisible():
            return False
        if not self.updatesEnabled():
            return False
        viewport = self.viewport()
        if viewport is None or not viewport.updatesEnabled():
            return False
        win = self.window()
        if win is None:
            return True
        if bool(getattr(win, "_closing", False)):
            return False
        overlay_active_fn = getattr(win, "_overlay_choice_active", None)
        if callable(overlay_active_fn):
            try:
                if overlay_active_fn():
                    return False
            except Exception:
                pass
        try:
            if int(getattr(win, "pending", 0) or 0) > 0:
                return False
        except Exception:
            pass
        if bool(getattr(win, "_background_services_paused", False)):
            return False
        return True

    def _schedule_cache_warmup_retry(self, delay_ms: int | None = None) -> None:
        if self._cache_warmup_retry_scheduled:
            return
        self._cache_warmup_retry_scheduled = True
        retry_ms = delay_ms
        if retry_ms is None:
            retry_ms = int(getattr(config, "WHEEL_CACHE_WARMUP_RETRY_MS", 180))
        QtCore.QTimer.singleShot(max(60, int(retry_ms)), self._run_cache_warmup_retry)

    def _run_cache_warmup_retry(self) -> None:
        self._cache_warmup_retry_scheduled = False
        self._maybe_warm_cache(reason="retry")

    def _maybe_warm_cache(self, reason: str = "") -> None:
        del reason
        wheel = getattr(self, "wheel", None)
        if wheel is None or not hasattr(wheel, "_ensure_cache"):
            return
        if not self.isVisible():
            return
        if self._can_warm_cache_now():
            try:
                wheel._ensure_cache(force=False)
            except Exception:
                pass
            return
        self._schedule_cache_warmup_retry()

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
