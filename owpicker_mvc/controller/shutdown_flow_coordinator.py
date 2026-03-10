from __future__ import annotations

import time

from PySide6 import QtCore, QtGui

import i18n

_SHUTDOWN_GUARD_ERRORS = (
    AttributeError,
    RuntimeError,
    TypeError,
    ValueError,
    LookupError,
    OSError,
)


class ShutdownFlowCoordinator:
    def __init__(self, mw: object) -> None:
        self._mw = mw

    def _cfg(self, key: str, default=None):
        getter = getattr(self._mw, "_cfg", None)
        if callable(getter):
            try:
                return getter(key, default)
            except (TypeError, ValueError):
                return default
        return default

    def _shutdown_settings(self):
        settings = getattr(self._mw, "settings", None)
        return getattr(settings, "shutdown", None)

    def _shutdown_bool(self, attr: str, key: str, default: bool) -> bool:
        section = self._shutdown_settings()
        if section is not None and hasattr(section, attr):
            try:
                return bool(getattr(section, attr))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg(key, default))

    def _shutdown_int(self, attr: str, key: str, default: int) -> int:
        section = self._shutdown_settings()
        if section is not None and hasattr(section, attr):
            try:
                return max(0, int(getattr(section, attr)))
            except (TypeError, ValueError):
                pass
        try:
            return max(0, int(self._cfg(key, default)))
        except (TypeError, ValueError):
            return max(0, int(default))

    def _trace(self, event: str, **payload) -> None:
        tracer = getattr(self._mw, "_trace_event", None)
        if callable(tracer):
            try:
                tracer(event, **payload)
            except _SHUTDOWN_GUARD_ERRORS:
                pass

    def trace_shutdown_blockers(
        self,
        *,
        stage: str,
        reason: str = "",
        force: bool = False,
        detached_threads: list[object],
    ) -> None:
        tracer = getattr(self._mw, "_trace_event", None)
        if not callable(tracer):
            return

        now = time.monotonic()
        if not force:
            interval_ms = self._shutdown_int(
                "blocker_trace_interval_ms",
                "SHUTDOWN_BLOCKER_TRACE_INTERVAL_MS",
                250,
            )
            if interval_ms > 0:
                last = getattr(self._mw, "_shutdown_blocker_trace_last_at", None)
                if isinstance(last, (int, float)):
                    if (now - float(last)) * 1000.0 < float(interval_ms):
                        return
        set_state = getattr(self._mw, "_set_shutdown_runtime_state", None)
        if callable(set_state):
            set_state(shutdown_blocker_trace_last_at=now)

        async_job = getattr(self._mw, "_ocr_async_job", None)
        preload_job = getattr(self._mw, "_ocr_preload_job", None)
        async_thread = async_job.get("thread") if isinstance(async_job, dict) else None
        preload_thread = preload_job.get("thread") if isinstance(preload_job, dict) else None

        running_child_qthreads = getattr(self._mw, "_running_child_qthreads", None)
        running_children = []
        if callable(running_child_qthreads):
            running_children = running_child_qthreads(exclude=(async_thread, preload_thread))
        detached_running: list[object] = []
        for thread in list(detached_threads):
            try:
                if thread is not None and bool(thread.isRunning()):
                    detached_running.append(thread)
            except _SHUTDOWN_GUARD_ERRORS:
                continue
        running_py_threads = getattr(self._mw, "_running_non_daemon_python_threads", None)
        py_threads = running_py_threads() if callable(running_py_threads) else []

        qthread_preview_entry = getattr(self._mw, "_qthread_preview_entry", None)
        python_preview_entry = getattr(self._mw, "_python_thread_preview_entry", None)
        child_preview = ""
        detached_preview = ""
        py_preview = ""
        if callable(qthread_preview_entry):
            child_preview = "|".join(
                entry
                for entry in (
                    qthread_preview_entry(thread, label="child")
                    for thread in running_children[:6]
                )
                if entry
            )
            detached_preview = "|".join(
                entry
                for entry in (
                    qthread_preview_entry(thread, label="detached")
                    for thread in detached_running[:6]
                )
                if entry
            )
        if callable(python_preview_entry):
            py_preview = "|".join(
                entry
                for entry in (
                    python_preview_entry(thread)
                    for thread in py_threads[:8]
                )
                if entry
            )

        try:
            tracer(
                "shutdown_blockers",
                stage=str(stage or "unknown"),
                reason=str(reason or ""),
                ocr_async_job=int(isinstance(async_job, dict)),
                ocr_preload_job=int(isinstance(preload_job, dict)),
                ocr_async_thread=qthread_preview_entry(async_thread, label="ocr_async") if callable(qthread_preview_entry) else "",
                ocr_preload_thread=qthread_preview_entry(preload_thread, label="ocr_preload") if callable(qthread_preview_entry) else "",
                child_qthreads=int(len(running_children)),
                child_qthreads_preview=str(child_preview),
                detached_qthreads=int(len(detached_running)),
                detached_qthreads_preview=str(detached_preview),
                py_threads=int(len(py_threads)),
                py_threads_preview=str(py_preview),
            )
        except _SHUTDOWN_GUARD_ERRORS:
            pass

    def defer_close_for_running_thread(self, event: QtGui.QCloseEvent, *, reason: str) -> None:
        retry_ms = 80 if str(reason or "") == "ocr_preload_thread" else 120
        now = time.monotonic()
        wait_started = getattr(self._mw, "_close_thread_wait_started_at", None)
        if wait_started is None:
            set_state = getattr(self._mw, "_set_shutdown_runtime_state", None)
            if callable(set_state):
                set_state(close_thread_wait_started_at=now)
            elapsed_ms = 0
        else:
            elapsed_ms = max(0, int((now - float(wait_started)) * 1000.0))

        self._trace(
            "shutdown_deferred_for_thread",
            reason=str(reason or "thread_running"),
            retry_ms=int(retry_ms),
            elapsed_ms=int(elapsed_ms),
        )

        trace_blockers = getattr(self._mw, "_trace_shutdown_blockers", None)
        if callable(trace_blockers):
            trace_blockers(stage="defer", reason=str(reason or "thread_running"))
        event.ignore()
        if not isinstance(self._mw, QtCore.QObject):
            QtCore.QTimer.singleShot(int(retry_ms), getattr(self._mw, "close"))
            return
        timer = getattr(self._mw, "_close_retry_timer", None)
        if timer is None:
            try:
                timer = QtCore.QTimer(self._mw)
            except _SHUTDOWN_GUARD_ERRORS:
                timer = None
            try:
                if timer is not None:
                    timer.setSingleShot(True)
                    timer.timeout.connect(getattr(self._mw, "close"))
                    if hasattr(self._mw, "_timers"):
                        getattr(self._mw, "_timers").register(timer)
                    set_state = getattr(self._mw, "_set_shutdown_runtime_state", None)
                    if callable(set_state):
                        set_state(close_retry_timer=timer)
            except _SHUTDOWN_GUARD_ERRORS:
                timer = None
        if timer is None:
            QtCore.QTimer.singleShot(int(retry_ms), getattr(self._mw, "close"))
            return
        if not timer.isActive():
            timer.start(int(retry_ms))

    def ensure_close_overlay_timer(self) -> QtCore.QTimer:
        timer = getattr(self._mw, "_close_overlay_timer", None)
        if timer is not None:
            return timer
        timer = QtCore.QTimer(self._mw)
        timer.setSingleShot(True)
        timer.timeout.connect(getattr(self._mw, "_continue_close_after_overlay"))
        if hasattr(self._mw, "_timers"):
            getattr(self._mw, "_timers").register(timer)
        set_state = getattr(self._mw, "_set_shutdown_runtime_state", None)
        if callable(set_state):
            set_state(close_overlay_timer=timer)
        return timer

    def continue_close_after_overlay(self) -> None:
        if not bool(getattr(self._mw, "_close_overlay_active", False)):
            return
        set_state = getattr(self._mw, "_set_shutdown_runtime_state", None)
        if callable(set_state):
            set_state(
                close_overlay_active=False,
                close_overlay_done=True,
            )
        close_fn = getattr(self._mw, "close", None)
        if callable(close_fn):
            close_fn()

    def show_close_overlay(self) -> bool:
        if not self._shutdown_bool("overlay_enabled", "SHUTDOWN_OVERLAY_ENABLED", True):
            return False
        delay_ms = self._shutdown_int("overlay_delay_ms", "SHUTDOWN_OVERLAY_DELAY_MS", 320)
        if delay_ms <= 0:
            return False
        overlay = getattr(self._mw, "overlay", None)
        if overlay is None:
            return False
        try:
            overlay.show_status_message(
                i18n.t("overlay.shutdown_title"),
                [i18n.t("overlay.shutdown_line1"), i18n.t("overlay.shutdown_line2"), ""],
            )
            overlay.setEnabled(False)
        except _SHUTDOWN_GUARD_ERRORS:
            return False
        set_state = getattr(self._mw, "_set_shutdown_runtime_state", None)
        if callable(set_state):
            set_state(
                close_overlay_active=True,
                close_overlay_done=False,
                closing=True,
            )
        timer = self.ensure_close_overlay_timer()
        timer.start(delay_ms)
        return True
