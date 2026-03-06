import unittest
from unittest.mock import patch

from controller.main_window import MainWindow


class _FakeCloseEvent:
    def __init__(self) -> None:
        self.ignored = False

    def ignore(self) -> None:
        self.ignored = True


class _AlwaysRunningThread:
    def __init__(self) -> None:
        self.interrupt_calls = 0
        self.quit_calls = 0
        self.wait_calls = 0
        self.terminate_calls = 0
        self.wait_timeouts: list[int] = []

    def isRunning(self) -> bool:
        return True

    def requestInterruption(self) -> None:
        self.interrupt_calls += 1

    def quit(self) -> None:
        self.quit_calls += 1

    def wait(self, _timeout_ms: int) -> bool:
        self.wait_calls += 1
        self.wait_timeouts.append(int(_timeout_ms))
        return False

    def terminate(self) -> None:
        self.terminate_calls += 1


class _StopsAfterTerminateThread:
    def __init__(self) -> None:
        self._running = True
        self.interrupt_calls = 0
        self.quit_calls = 0
        self.wait_calls = 0
        self.terminate_calls = 0

    def isRunning(self) -> bool:
        return self._running

    def requestInterruption(self) -> None:
        self.interrupt_calls += 1

    def quit(self) -> None:
        self.quit_calls += 1

    def wait(self, _timeout_ms: int) -> bool:
        self.wait_calls += 1
        return False

    def terminate(self) -> None:
        self.terminate_calls += 1
        self._running = False


class _NotRunningNotFinishedThread:
    def __init__(self) -> None:
        self.interrupt_calls = 0
        self.quit_calls = 0
        self.wait_calls = 0
        self.terminate_calls = 0

    def isRunning(self) -> bool:
        return False

    def isFinished(self) -> bool:
        return False

    def requestInterruption(self) -> None:
        self.interrupt_calls += 1

    def quit(self) -> None:
        self.quit_calls += 1

    def wait(self, _timeout_ms: int) -> bool:
        self.wait_calls += 1
        return False

    def terminate(self) -> None:
        self.terminate_calls += 1


class TestMainWindowShutdownMixin(unittest.TestCase):
    def _make_window(self) -> MainWindow:
        mw = MainWindow.__new__(MainWindow)
        mw._closing = True
        mw._close_overlay_active = False
        mw._close_overlay_done = True
        mw._close_overlay_timer = None
        mw.overlay = None
        mw._ocr_async_job = None
        mw._ocr_preload_job = None
        mw._cfg = lambda key, default=None: default
        mw._trace_event = lambda *_args, **_kwargs: None
        mw._cancel_ocr_background_preload = lambda: None
        mw._cancel_ocr_runtime_cache_release = lambda: None
        mw._release_ocr_runtime_cache = lambda: None
        mw._set_app_event_filter_enabled = lambda _enabled: None
        mw.close = lambda: None
        return mw

    def test_close_event_defers_when_ocr_preload_thread_is_still_running(self):
        mw = self._make_window()
        thread = _AlwaysRunningThread()
        mw._ocr_preload_job = {"thread": thread}
        event = _FakeCloseEvent()

        with patch(
            "controller.main_window_parts.main_window_shutdown.QtCore.QTimer.singleShot",
        ) as single_shot, patch(
            "controller.main_window_parts.main_window_shutdown.shutdown_manager.handle_close_event"
        ) as handle_close:
            MainWindow.closeEvent(mw, event)

        self.assertTrue(event.ignored)
        single_shot.assert_called_once()
        self.assertGreaterEqual(thread.interrupt_calls, 1)
        self.assertGreaterEqual(thread.quit_calls, 1)
        self.assertGreaterEqual(thread.terminate_calls, 1)
        self.assertIsNotNone(mw._ocr_preload_job)
        handle_close.assert_not_called()

    def test_close_event_continues_shutdown_after_ocr_preload_thread_stops(self):
        mw = self._make_window()
        thread = _StopsAfterTerminateThread()
        mw._ocr_preload_job = {"thread": thread}
        event = _FakeCloseEvent()

        with patch(
            "controller.main_window_parts.main_window_shutdown.QtCore.QTimer.singleShot"
        ), patch(
            "controller.main_window_parts.main_window_shutdown.shutdown_manager.handle_close_event"
        ) as handle_close:
            MainWindow.closeEvent(mw, event)

        self.assertFalse(event.ignored)
        self.assertIsNone(mw._ocr_preload_job)
        self.assertGreaterEqual(thread.interrupt_calls, 1)
        self.assertGreaterEqual(thread.quit_calls, 1)
        self.assertGreaterEqual(thread.terminate_calls, 1)
        handle_close.assert_called_once()

    def test_close_event_uses_configured_wait_profile(self):
        mw = self._make_window()
        thread = _AlwaysRunningThread()
        mw._ocr_preload_job = {"thread": thread}
        cfg_values = {
            "SHUTDOWN_OCR_PRELOAD_GRACEFUL_WAIT_MS": 123,
            "SHUTDOWN_OCR_PRELOAD_TERMINATE_WAIT_MS": 42,
        }
        mw._cfg = lambda key, default=None: cfg_values.get(key, default)
        event = _FakeCloseEvent()

        with patch(
            "controller.main_window_parts.main_window_shutdown.QtCore.QTimer.singleShot"
        ) as single_shot, patch(
            "controller.main_window_parts.main_window_shutdown.shutdown_manager.handle_close_event"
        ) as handle_close:
            MainWindow.closeEvent(mw, event)

        self.assertTrue(event.ignored)
        single_shot.assert_called_once()
        self.assertGreaterEqual(thread.interrupt_calls, 1)
        self.assertGreaterEqual(thread.quit_calls, 1)
        self.assertGreaterEqual(thread.terminate_calls, 1)
        # Uses configured values, but applies shutdown safety cap.
        self.assertEqual(thread.wait_timeouts, [100, 42])
        self.assertIsNotNone(mw._ocr_preload_job)
        handle_close.assert_not_called()

    def test_close_event_defers_while_orphaned_preload_thread_still_running(self):
        mw = self._make_window()
        thread = _AlwaysRunningThread()
        mw._ocr_preload_job = {"thread": thread}
        # Simulate an already running close-retry window.
        mw._close_thread_wait_started_at = 1.0
        cfg_values = {
            "SHUTDOWN_THREAD_MAX_DEFER_MS": 1,
        }
        mw._cfg = lambda key, default=None: cfg_values.get(key, default)
        event = _FakeCloseEvent()

        with patch(
            "controller.main_window_parts.main_window_shutdown.QtCore.QTimer.singleShot"
        ) as single_shot, patch(
            "controller.main_window_parts.main_window_shutdown.shutdown_manager.handle_close_event"
        ) as handle_close:
            MainWindow.closeEvent(mw, event)

        self.assertTrue(event.ignored)
        single_shot.assert_called_once()
        self.assertIsNone(mw._ocr_preload_job)
        handle_close.assert_not_called()

    def test_close_event_defers_for_not_running_but_not_finished_thread(self):
        mw = self._make_window()
        thread = _NotRunningNotFinishedThread()
        mw._ocr_preload_job = {"thread": thread}
        event = _FakeCloseEvent()

        with patch(
            "controller.main_window_parts.main_window_shutdown.QtCore.QTimer.singleShot"
        ) as single_shot, patch(
            "controller.main_window_parts.main_window_shutdown.shutdown_manager.handle_close_event"
        ) as handle_close:
            MainWindow.closeEvent(mw, event)

        self.assertTrue(event.ignored)
        single_shot.assert_called_once()
        self.assertIsNotNone(mw._ocr_preload_job)
        self.assertGreaterEqual(thread.interrupt_calls, 1)
        self.assertGreaterEqual(thread.quit_calls, 1)
        handle_close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
