from __future__ import annotations

_SHUTDOWN_GUARD_ERRORS = (
    AttributeError,
    RuntimeError,
    TypeError,
    ValueError,
    LookupError,
    OSError,
    ImportError,
)


class ShutdownThreadCoordinator:
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

    def _warn(self, where: str, exc: Exception) -> None:
        warn_fn = getattr(self._mw, "_warn_shutdown_suppressed_exception", None)
        if callable(warn_fn):
            warn_fn(where, exc)

    def disconnect_connection(self, connection: object | None, *, connection_type: object | None) -> None:
        if connection is None:
            return
        if connection_type is not None and not isinstance(connection, connection_type):
            return
        try:
            is_valid = getattr(connection, "isValid", None)
            if callable(is_valid) and not bool(is_valid()):
                return
        except _SHUTDOWN_GUARD_ERRORS as exc:
            self._warn("disconnect_connection:is_valid", exc)
        try:
            if not bool(connection):
                return
        except _SHUTDOWN_GUARD_ERRORS as exc:
            self._warn("disconnect_connection:truthy", exc)
        try:
            from PySide6 import QtCore

            QtCore.QObject.disconnect(connection)
        except _SHUTDOWN_GUARD_ERRORS as exc:
            self._warn("disconnect_connection:disconnect", exc)

    def disconnect_signal_slots(self, source: object | None, signal_name: str, *slots: object | None) -> None:
        if source is None:
            return
        signal = getattr(source, signal_name, None)
        if signal is None or not slots:
            return
        for slot in slots:
            if slot is None:
                continue
            try:
                signal.disconnect(slot)
            except _SHUTDOWN_GUARD_ERRORS as exc:
                self._warn(f"disconnect_signal_slots:{signal_name}", exc)

    def disconnect_thread_worker_start(
        self,
        thread: object | None,
        worker: object | None,
        started_connection: object | None = None,
        *,
        disconnect_connection_fn,
    ) -> None:
        if started_connection is not None:
            disconnect_connection_fn(started_connection)
            return
        if thread is None or worker is None:
            return
        started_signal = getattr(thread, "started", None)
        run_slot = getattr(worker, "run", None)
        if started_signal is None or run_slot is None:
            return
        try:
            started_signal.disconnect(run_slot)
        except _SHUTDOWN_GUARD_ERRORS as exc:
            self._warn("disconnect_thread_worker_start:slot", exc)

    def stop_qthread_for_close(self, thread: object | None) -> bool:
        if thread is None:
            return True
        running = False
        if hasattr(thread, "isRunning"):
            try:
                running = bool(thread.isRunning())
            except _SHUTDOWN_GUARD_ERRORS:
                running = False
        finished = False
        if hasattr(thread, "isFinished"):
            try:
                finished = bool(thread.isFinished())
            except _SHUTDOWN_GUARD_ERRORS:
                finished = not running
        else:
            finished = not running
        if finished:
            return True
        if hasattr(thread, "requestInterruption"):
            try:
                thread.requestInterruption()
            except _SHUTDOWN_GUARD_ERRORS as exc:
                self._warn("stop_qthread:request_interruption", exc)
        if hasattr(thread, "quit"):
            try:
                thread.quit()
            except _SHUTDOWN_GUARD_ERRORS as exc:
                self._warn("stop_qthread:quit", exc)
        if hasattr(thread, "isFinished"):
            try:
                return bool(thread.isFinished())
            except _SHUTDOWN_GUARD_ERRORS:
                return False
        return False

    def qthread_wait_profile_ms(self, reason: str = "") -> tuple[int, int]:
        key = str(reason or "").strip().casefold()
        if key == "ocr_preload_thread":
            graceful_ms = self._shutdown_int(
                "ocr_preload_graceful_wait_ms",
                "SHUTDOWN_OCR_PRELOAD_GRACEFUL_WAIT_MS",
                1400,
            )
            terminate_ms = self._shutdown_int(
                "ocr_preload_terminate_wait_ms",
                "SHUTDOWN_OCR_PRELOAD_TERMINATE_WAIT_MS",
                350,
            )
            return graceful_ms, terminate_ms
        if key == "ocr_async_thread":
            graceful_ms = self._shutdown_int(
                "ocr_async_graceful_wait_ms",
                "SHUTDOWN_OCR_ASYNC_GRACEFUL_WAIT_MS",
                1200,
            )
            terminate_ms = self._shutdown_int(
                "ocr_async_terminate_wait_ms",
                "SHUTDOWN_OCR_ASYNC_TERMINATE_WAIT_MS",
                700,
            )
            return graceful_ms, terminate_ms
        graceful_ms = self._shutdown_int(
            "child_thread_graceful_wait_ms",
            "SHUTDOWN_CHILD_THREAD_GRACEFUL_WAIT_MS",
            350,
        )
        terminate_ms = self._shutdown_int(
            "child_thread_terminate_wait_ms",
            "SHUTDOWN_CHILD_THREAD_TERMINATE_WAIT_MS",
            250,
        )
        return graceful_ms, terminate_ms

    def force_stop_qthread_for_close(self, thread: object | None, *, reason: str = "") -> bool:
        if thread is None:
            return True
        running = False
        if hasattr(thread, "isRunning"):
            try:
                running = bool(thread.isRunning())
            except _SHUTDOWN_GUARD_ERRORS:
                running = False
        if not running:
            return True
        wait_graceful_ms, wait_terminate_ms = self.qthread_wait_profile_ms(reason=reason)
        if hasattr(thread, "requestInterruption"):
            try:
                thread.requestInterruption()
            except _SHUTDOWN_GUARD_ERRORS as exc:
                self._warn("force_stop_qthread:request_interruption", exc)
        if hasattr(thread, "quit"):
            try:
                thread.quit()
            except _SHUTDOWN_GUARD_ERRORS as exc:
                self._warn("force_stop_qthread:quit", exc)
        if hasattr(thread, "wait") and wait_graceful_ms > 0:
            try:
                if bool(thread.wait(int(wait_graceful_ms))):
                    return True
            except _SHUTDOWN_GUARD_ERRORS as exc:
                self._warn("force_stop_qthread:wait_graceful", exc)
        if hasattr(thread, "terminate"):
            try:
                thread.terminate()
            except _SHUTDOWN_GUARD_ERRORS as exc:
                self._warn("force_stop_qthread:terminate", exc)
        if hasattr(thread, "wait") and wait_terminate_ms > 0:
            try:
                if bool(thread.wait(int(wait_terminate_ms))):
                    return True
            except _SHUTDOWN_GUARD_ERRORS as exc:
                self._warn("force_stop_qthread:wait_terminate", exc)
        running_after = False
        if hasattr(thread, "isRunning"):
            try:
                running_after = bool(thread.isRunning())
            except _SHUTDOWN_GUARD_ERRORS:
                running_after = False
        return not running_after
