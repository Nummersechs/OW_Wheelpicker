from __future__ import annotations

import weakref

from PySide6 import QtCore, QtWidgets

from .layout import compute_map_list_names_target_height, compute_map_panel_metrics

QWIDGETSIZE_MAX = getattr(QtWidgets, "QWIDGETSIZE_MAX", getattr(QtCore, "QWIDGETSIZE_MAX", 16777215))


class MapUIDynamicSizingController:
    def __init__(self, owner) -> None:
        self._owner = owner
        self._dynamic_height_bound: weakref.WeakSet = weakref.WeakSet()
        self._dynamic_height_pending: weakref.WeakSet = weakref.WeakSet()
        self._dynamic_height_callbacks: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
        self._cap_heights_timer = QtCore.QTimer(owner)
        self._cap_heights_timer.setSingleShot(True)
        self._cap_heights_timer.timeout.connect(self.cap_heights)
        self._last_cap_signature: tuple[int, int, int, int] | None = None
        self._resize_watch_targets: tuple[QtWidgets.QWidget, ...] = tuple()

    @staticmethod
    def names_canvas(wheel) -> QtWidgets.QListWidget | None:
        if wheel is None:
            return None
        names_canvas = getattr(wheel, "names", None)
        return names_canvas if isinstance(names_canvas, QtWidgets.QListWidget) else None

    @staticmethod
    def row_height_hint(names_canvas: QtWidgets.QListWidget) -> int:
        try:
            row_height = int(names_canvas.sizeHintForRow(0))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            row_height = 0
        if row_height <= 0:
            row_height_attr = getattr(names_canvas, "_row_height", 20)
            try:
                row_height = int(row_height_attr)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                row_height = 20
            row_height = max(18, row_height)
        return row_height

    def unbind_widget(self, wheel) -> None:
        names_canvas = self.names_canvas(wheel)
        callback = self._dynamic_height_callbacks.pop(names_canvas, None) if names_canvas else None
        if names_canvas is not None and callable(callback):
            model = names_canvas.model()
            if model is not None:
                for sig_name in ("rowsInserted", "rowsRemoved", "modelReset"):
                    sig = getattr(model, sig_name, None)
                    if sig is None:
                        continue
                    try:
                        sig.disconnect(callback)
                    except (AttributeError, RuntimeError, TypeError):
                        pass
            self._dynamic_height_bound.discard(names_canvas)
            self._dynamic_height_pending.discard(names_canvas)

    def map_list_target_names_height(self, wheel) -> int | None:
        names_canvas = self.names_canvas(wheel)
        if names_canvas is None:
            return None
        row_height = self.row_height_hint(names_canvas)
        row_count = max(1, int(names_canvas.count()))
        min_rows = self._owner._map_int(
            "list_names_min_visible_rows",
            "MAP_LIST_NAMES_MIN_VISIBLE_ROWS",
            2,
            minimum=1,
        )
        max_rows = self._owner._map_int(
            "list_names_max_visible_rows",
            "MAP_LIST_NAMES_MAX_VISIBLE_ROWS",
            6,
            minimum=min_rows,
        )
        frame_width = max(0, int(names_canvas.frameWidth()))
        extra_padding = self._owner._map_int(
            "list_names_extra_padding_px",
            "MAP_LIST_NAMES_EXTRA_PADDING_PX",
            8,
            minimum=0,
        )
        return compute_map_list_names_target_height(
            row_height=row_height,
            row_count=row_count,
            min_rows=min_rows,
            max_rows=max_rows,
            frame_width=frame_width,
            extra_padding=extra_padding,
            min_height=40,
        )

    def apply_dynamic_map_list_height(self, wheel) -> None:
        names_canvas = self.names_canvas(wheel)
        if names_canvas is None:
            return
        target_height = self.map_list_target_names_height(wheel)
        if target_height is None:
            return
        if int(names_canvas.minimumHeight()) != int(target_height):
            names_canvas.setMinimumHeight(target_height)
        if int(names_canvas.maximumHeight()) != int(target_height):
            names_canvas.setMaximumHeight(target_height)

    def bind_dynamic_map_list_height(self, wheel) -> None:
        names_canvas = self.names_canvas(wheel)
        if names_canvas is None:
            return
        if names_canvas in self._dynamic_height_bound:
            return
        self._dynamic_height_bound.add(names_canvas)

        def _schedule_resize(*_args, _wheel=wheel, _canvas=names_canvas):
            if _canvas in self._dynamic_height_pending:
                return
            self._dynamic_height_pending.add(_canvas)

            def _apply() -> None:
                self._dynamic_height_pending.discard(_canvas)
                self.apply_dynamic_map_list_height(_wheel)

            QtCore.QTimer.singleShot(0, _apply)

        self._dynamic_height_callbacks[names_canvas] = _schedule_resize
        model = names_canvas.model()
        if model is not None:
            model.rowsInserted.connect(_schedule_resize)
            model.rowsRemoved.connect(_schedule_resize)
            model.modelReset.connect(_schedule_resize)
        _schedule_resize()

    def install_resize_watch(self, *widgets) -> None:
        self._resize_watch_targets = tuple(
            w for w in widgets if isinstance(w, QtWidgets.QWidget)
        )
        for widget in self._resize_watch_targets:
            try:
                widget.installEventFilter(self._owner)
            except (AttributeError, RuntimeError, TypeError):
                pass

    def clear_resize_watch(self) -> None:
        for widget in self._resize_watch_targets:
            try:
                widget.removeEventFilter(self._owner)
            except (AttributeError, RuntimeError, TypeError):
                pass
        self._resize_watch_targets = tuple()

    def schedule_cap_heights(self) -> None:
        if self._cap_heights_timer.isActive():
            return
        self._cap_heights_timer.start(25)

    def cap_heights(self) -> None:
        def _set_min_max_width(
            widget: QtWidgets.QWidget,
            *,
            min_width: int | None = None,
            max_width: int | None = None,
        ) -> None:
            if min_width is not None and int(widget.minimumWidth()) != int(min_width):
                widget.setMinimumWidth(int(min_width))
            if max_width is not None and int(widget.maximumWidth()) != int(max_width):
                widget.setMaximumWidth(int(max_width))

        def _set_min_max_height(
            widget: QtWidgets.QWidget,
            *,
            min_height: int | None = None,
            max_height: int | None = None,
        ) -> None:
            if min_height is not None and int(widget.minimumHeight()) != int(min_height):
                widget.setMinimumHeight(int(min_height))
            if max_height is not None and int(widget.maximumHeight()) != int(max_height):
                widget.setMaximumHeight(int(max_height))

        role_widgets = getattr(self._owner, "_role_widgets", ())
        if not role_widgets or not isinstance(role_widgets, tuple):
            role_ref_h = 0
        else:
            tank, dps, support = role_widgets
            role_ref_h = max(
                0,
                tank.height() or tank.sizeHint().height(),
                dps.height() or dps.sizeHint().height(),
                support.height() or support.sizeHint().height(),
            )

        container = getattr(self._owner, "container", None)
        container_h = 0
        if container is not None:
            try:
                container_h = int(container.height())
            except (AttributeError, RuntimeError, TypeError, ValueError):
                container_h = 0
            if container_h <= 0:
                try:
                    container_h = int(container.sizeHint().height())
                except (AttributeError, RuntimeError, TypeError, ValueError):
                    container_h = 0

        ref_h = max(role_ref_h, container_h)
        metrics = compute_map_panel_metrics(ref_h)
        signature = (
            int(metrics.soft_canvas),
            int(metrics.panel_min_width),
            int(metrics.panel_min_height),
            int(metrics.frame_min_height),
        )
        if signature == self._last_cap_signature:
            return
        self._last_cap_signature = signature

        map_main = getattr(self._owner, "map_main", None)
        if map_main is not None:
            _set_min_max_height(map_main.view, min_height=metrics.soft_canvas, max_height=QWIDGETSIZE_MAX)
            _set_min_max_width(map_main.view, min_width=metrics.soft_canvas, max_width=QWIDGETSIZE_MAX)
            _set_min_max_height(map_main, min_height=metrics.panel_min_height, max_height=QWIDGETSIZE_MAX)
            _set_min_max_width(map_main, min_width=metrics.panel_min_width, max_width=QWIDGETSIZE_MAX)

        map_lists_frame = getattr(self._owner, "map_lists_frame", None)
        if map_lists_frame is not None:
            _set_min_max_height(map_lists_frame, min_height=metrics.frame_min_height, max_height=QWIDGETSIZE_MAX)

        map_lists_wrapper = getattr(self._owner, "map_lists_wrapper", None)
        if map_lists_wrapper is not None:
            _set_min_max_height(
                map_lists_wrapper,
                min_height=metrics.frame_min_height,
                max_height=QWIDGETSIZE_MAX,
            )

        map_sidebar = getattr(self._owner, "map_sidebar", None)
        if map_sidebar is not None:
            _set_min_max_height(map_sidebar, min_height=metrics.frame_min_height, max_height=QWIDGETSIZE_MAX)

    def handle_event(self, obj: QtCore.QObject, event: QtCore.QEvent) -> None:
        if obj in self._resize_watch_targets and event.type() in (
            QtCore.QEvent.Resize,
            QtCore.QEvent.Show,
            QtCore.QEvent.LayoutRequest,
        ):
            self.schedule_cap_heights()

    def shutdown(self) -> None:
        if self._cap_heights_timer.isActive():
            self._cap_heights_timer.stop()
        self.clear_resize_watch()

