from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui

import i18n

from .. import shutdown_manager


class MainWindowShutdownMixin:
    def _merge_shutdown_snapshot(self, prefix: str, payload: dict | None, target: dict) -> None:
        shutdown_manager.merge_shutdown_snapshot(prefix, payload, target)

    def _shutdown_resource_snapshot(self) -> dict:
        return shutdown_manager.shutdown_resource_snapshot(self)

    def _run_shutdown_step(self, step: str, callback) -> None:
        shutdown_manager.run_shutdown_step(self, step, callback)

    def _ensure_close_overlay_timer(self) -> QtCore.QTimer:
        timer = getattr(self, "_close_overlay_timer", None)
        if timer is not None:
            return timer
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._continue_close_after_overlay)
        if hasattr(self, "_timers"):
            self._timers.register(timer)
        self._close_overlay_timer = timer
        return timer

    def _continue_close_after_overlay(self) -> None:
        if not bool(getattr(self, "_close_overlay_active", False)):
            return
        self._close_overlay_active = False
        self._close_overlay_done = True
        overlay = getattr(self, "overlay", None)
        if overlay is not None:
            try:
                overlay.setEnabled(True)
                overlay.hide()
            except Exception:
                pass
        self.close()

    def _show_close_overlay(self) -> bool:
        if not bool(self._cfg("SHUTDOWN_OVERLAY_ENABLED", True)):
            return False
        delay_ms = max(0, int(self._cfg("SHUTDOWN_OVERLAY_DELAY_MS", 320)))
        if delay_ms <= 0:
            return False
        overlay = getattr(self, "overlay", None)
        if overlay is None:
            return False
        try:
            overlay.show_status_message(
                i18n.t("overlay.shutdown_title"),
                [i18n.t("overlay.shutdown_line1"), i18n.t("overlay.shutdown_line2"), ""],
            )
            overlay.setEnabled(False)
        except Exception:
            return False
        self._close_overlay_active = True
        self._close_overlay_done = False
        timer = self._ensure_close_overlay_timer()
        timer.start(delay_ms)
        return True

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if not getattr(self, "_closing", False):
            if bool(getattr(self, "_close_overlay_active", False)):
                event.ignore()
                return
            if not bool(getattr(self, "_close_overlay_done", False)):
                if self._show_close_overlay():
                    event.ignore()
                    return

        timer = getattr(self, "_close_overlay_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
        overlay = getattr(self, "overlay", None)
        if overlay is not None:
            try:
                overlay.setEnabled(True)
                overlay.hide()
            except Exception:
                pass

        job = getattr(self, "_ocr_async_job", None)
        if isinstance(job, dict):
            for path in list(job.get("paths") or []):
                try:
                    Path(path).unlink(missing_ok=True)
                except Exception:
                    pass
            thread = job.get("thread")
            try:
                if thread is not None and thread.isRunning():
                    thread.quit()
                    thread.wait(300)
            except Exception:
                pass
            self._ocr_async_job = None
        if hasattr(self, "_cancel_ocr_runtime_cache_release"):
            try:
                self._cancel_ocr_runtime_cache_release()
            except Exception:
                pass
        if hasattr(self, "_release_ocr_runtime_cache"):
            try:
                self._release_ocr_runtime_cache()
            except Exception:
                pass
        self._set_app_event_filter_enabled(False)
        shutdown_manager.handle_close_event(self, event)
