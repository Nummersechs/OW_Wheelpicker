from __future__ import annotations

from contextlib import contextmanager

from PySide6 import QtCore, QtGui, QtWidgets


class NamesListGeometryMixin:
    @contextmanager
    def batch_update(self):
        self._begin_bulk_update()
        try:
            yield
        finally:
            self._end_bulk_update()

    def _set_updates_enabled_recursive(self, enabled: bool) -> None:
        try:
            self.setUpdatesEnabled(bool(enabled))
        except (AttributeError, RuntimeError, TypeError):
            pass
        viewport = self.viewport()
        if viewport is not None:
            try:
                viewport.setUpdatesEnabled(bool(enabled))
            except (AttributeError, RuntimeError, TypeError):
                pass

    def _begin_bulk_update(self) -> None:
        if self._bulk_update_depth <= 0:
            self._bulk_prev_updates_enabled = bool(self.updatesEnabled())
            self._bulk_geometry_dirty = False
            self._set_updates_enabled_recursive(False)
        self._bulk_update_depth += 1

    def _end_bulk_update(self) -> None:
        if self._bulk_update_depth <= 0:
            return
        self._bulk_update_depth -= 1
        if self._bulk_update_depth > 0:
            return
        self._set_updates_enabled_recursive(self._bulk_prev_updates_enabled)
        if self._bulk_geometry_dirty:
            self._bulk_geometry_dirty = False
            self._schedule_geometry_sync()
        else:
            self._refresh_row_widget_geometry()
        viewport = self.viewport()
        if viewport is not None:
            try:
                viewport.update()
            except (AttributeError, RuntimeError, TypeError):
                pass
        try:
            # QListWidget exposes an overload update(item), which can mask the
            # QWidget.update() no-arg variant in some PySide builds.
            QtWidgets.QWidget.update(self)
        except (AttributeError, RuntimeError, TypeError):
            pass

    def _schedule_geometry_sync(self) -> None:
        if self._bulk_update_depth > 0:
            self._bulk_geometry_dirty = True
            return
        if self._geometry_sync_pending:
            return
        self._geometry_sync_pending = True
        QtCore.QTimer.singleShot(0, self._run_scheduled_geometry_sync)

    def _run_scheduled_geometry_sync(self) -> None:
        self._geometry_sync_pending = False
        if self._bulk_update_depth > 0:
            self._bulk_geometry_dirty = True
            return
        changed = self._sync_viewport_right_padding()
        if not changed:
            self._refresh_row_widget_geometry()

    def _scrollbar_extent(self, sb: QtWidgets.QScrollBar | None = None) -> int:
        scrollbar = sb if sb is not None else self.verticalScrollBar()
        if scrollbar is None:
            return 0
        extent = self.style().pixelMetric(QtWidgets.QStyle.PM_ScrollBarExtent, None, scrollbar)
        hint = scrollbar.sizeHint().width()
        return max(0, int(extent), int(hint))

    def _sync_viewport_right_padding(self, *_args) -> bool:
        if self._bulk_update_depth > 0:
            self._bulk_geometry_dirty = True
            return False
        if self._syncing_viewport_margin:
            return False
        viewport = self.viewport()
        viewport_width = int(viewport.width()) if viewport is not None else -1
        # Keep viewport margins at 0 so row widgets are always laid out to the
        # actually visible width and right-side controls cannot be clipped.
        margin_right = 0
        if margin_right == self._viewport_right_margin and viewport_width == self._last_viewport_width:
            return False
        self._last_viewport_width = viewport_width
        self._viewport_right_margin = margin_right
        self._syncing_viewport_margin = True
        try:
            self.setViewportMargins(0, 0, margin_right, 0)
        finally:
            self._syncing_viewport_margin = False
        # Viewport margin changes can make previously laid-out row widgets too wide.
        # Re-layout immediately so right-side controls do not get clipped.
        self._refresh_row_widget_geometry()
        return True

    def _refresh_row_widget_geometry(self) -> None:
        try:
            self.doItemsLayout()
        except (AttributeError, RuntimeError, TypeError):
            pass
        for i in range(self.count()):
            item = self.item(i)
            if item is None:
                continue
            row_widget = self.itemWidget(item)
            apply_constraints = getattr(row_widget, "_apply_name_edit_width_constraints", None)
            if callable(apply_constraints):
                apply_constraints()

    def resizeEvent(self, ev: QtGui.QResizeEvent) -> None:
        super().resizeEvent(ev)
        self._schedule_geometry_sync()

    def showEvent(self, ev: QtGui.QShowEvent) -> None:
        super().showEvent(ev)
        try:
            self.doItemsLayout()
        except (AttributeError, RuntimeError, TypeError):
            pass
        self._schedule_geometry_sync()

    def wheelEvent(self, ev: QtGui.QWheelEvent):
        """Slightly less sensitive scrolling than Qt default."""
        sb = self.verticalScrollBar()
        if not sb:
            return super().wheelEvent(ev)
        angle = ev.angleDelta().y()
        pixel = ev.pixelDelta().y()
        factor = 0.4  # <1 -> slower

        if angle:
            base = (angle / 120.0) * sb.singleStep()
            step = int(base * factor)
        elif pixel:
            step = int(pixel * factor)
        else:
            return super().wheelEvent(ev)

        if step == 0:
            step = 1 if (angle or pixel) > 0 else -1

        sb.setValue(sb.value() - step)
        ev.accept()
