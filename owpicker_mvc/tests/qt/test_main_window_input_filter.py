import unittest
import time
from unittest.mock import patch

from tests.qt_test_guard import import_qt
QtCore, = import_qt("QtCore")

import config
from controller import spin_service
from controller.main_window import MainWindow


class _FakeButton:
    def __init__(self, enabled: bool):
        self._enabled = bool(enabled)

    def isEnabled(self) -> bool:
        return self._enabled


class _FakeSpinAllButton:
    def __init__(
        self,
        *,
        enabled: bool,
        tooltip: str,
        top_left: QtCore.QPoint | None = None,
        size: QtCore.QSize | None = None,
    ):
        self._enabled = bool(enabled)
        self._tooltip = str(tooltip)
        self._top_left = top_left or QtCore.QPoint(0, 0)
        self._size = size or QtCore.QSize(140, 44)

    def isEnabled(self) -> bool:
        return self._enabled

    def setEnabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def toolTip(self) -> str:
        return self._tooltip

    def setToolTip(self, text: str) -> None:
        self._tooltip = str(text)

    def mapToGlobal(self, point: QtCore.QPoint) -> QtCore.QPoint:
        return self._top_left + point

    def size(self) -> QtCore.QSize:
        return QtCore.QSize(self._size)

    def rect(self) -> QtCore.QRect:
        return QtCore.QRect(0, 0, self._size.width(), self._size.height())


class _FakeOverlay:
    def __init__(
        self,
        *,
        visible: bool = True,
        view_type: str = "online_choice",
        offline_enabled: bool = False,
        online_enabled: bool = False,
    ):
        self._visible = bool(visible)
        self._last_view = {"type": view_type}
        self.btn_offline = _FakeButton(offline_enabled)
        self.btn_online = _FakeButton(online_enabled)
        self.show_online_choice_calls = 0
        self.choice_enabled_calls: list[bool] = []

    def isVisible(self) -> bool:
        return self._visible

    def show_online_choice(self) -> None:
        self.show_online_choice_calls += 1

    def set_choice_enabled(self, enabled: bool) -> None:
        self.choice_enabled_calls.append(bool(enabled))


class _FakeSender:
    def __init__(self, object_name: str, text: str = ""):
        self._object_name = str(object_name)
        self._text = str(text)

    def objectName(self) -> str:
        return self._object_name

    def text(self) -> str:
        return self._text


class TestMainWindowInputFilter(unittest.TestCase):
    def _make_window(self, *, startup_block: bool, startup_drain: bool, overlay: _FakeOverlay) -> MainWindow:
        mw = MainWindow.__new__(MainWindow)
        mw._startup_block_input = bool(startup_block)
        mw._startup_drain_active = bool(startup_drain)
        mw.overlay = overlay
        return mw

    def test_drops_clicks_for_disabled_choice_buttons_during_startup(self):
        mw = self._make_window(
            startup_block=True,
            startup_drain=False,
            overlay=_FakeOverlay(offline_enabled=False, online_enabled=False),
        )

        self.assertTrue(
            mw._should_drop_disabled_choice_mouse_event(
                int(QtCore.QEvent.MouseButtonPress),
            )
        )
        self.assertTrue(
            mw._should_drop_disabled_choice_mouse_event(
                int(QtCore.QEvent.MouseButtonRelease),
            )
        )
        self.assertTrue(
            mw._should_drop_disabled_choice_mouse_event(
                int(QtCore.QEvent.MouseButtonDblClick),
            )
        )

    def test_does_not_drop_when_choice_buttons_enabled(self):
        mw = self._make_window(
            startup_block=True,
            startup_drain=False,
            overlay=_FakeOverlay(offline_enabled=True, online_enabled=True),
        )

        self.assertFalse(
            mw._should_drop_disabled_choice_mouse_event(
                int(QtCore.QEvent.MouseButtonPress),
            )
        )

    def test_does_not_drop_outside_choice_view_or_startup(self):
        mw_not_choice = self._make_window(
            startup_block=True,
            startup_drain=False,
            overlay=_FakeOverlay(view_type="result", offline_enabled=False, online_enabled=False),
        )
        self.assertFalse(
            mw_not_choice._should_drop_disabled_choice_mouse_event(
                int(QtCore.QEvent.MouseButtonPress),
            )
        )

        mw_no_startup = self._make_window(
            startup_block=False,
            startup_drain=False,
            overlay=_FakeOverlay(offline_enabled=False, online_enabled=False),
        )
        self.assertFalse(
            mw_no_startup._should_drop_disabled_choice_mouse_event(
                int(QtCore.QEvent.MouseButtonPress),
            )
        )

    def test_drain_phase_still_drops_disabled_choice_clicks(self):
        mw = self._make_window(
            startup_block=False,
            startup_drain=True,
            overlay=_FakeOverlay(offline_enabled=False, online_enabled=False),
        )

        self.assertTrue(
            mw._should_drop_disabled_choice_mouse_event(
                int(QtCore.QEvent.MouseButtonPress),
            )
        )
        self.assertFalse(
            mw._should_drop_disabled_choice_mouse_event(
                int(QtCore.QEvent.HoverMove),
            )
        )

    def test_drops_all_clicks_when_choice_buttons_are_locked(self):
        mw = self._make_window(
            startup_block=True,
            startup_drain=False,
            overlay=_FakeOverlay(offline_enabled=False, online_enabled=False),
        )

        self.assertTrue(
            mw._should_drop_disabled_choice_mouse_event(
                int(QtCore.QEvent.MouseButtonPress),
            )
        )

    def test_drops_pointer_events_for_disabled_choice_buttons_during_startup(self):
        mw = self._make_window(
            startup_block=True,
            startup_drain=False,
            overlay=_FakeOverlay(offline_enabled=False, online_enabled=False),
        )

        self.assertTrue(
            mw._should_drop_disabled_choice_pointer_event(
                int(QtCore.QEvent.MouseMove),
            )
        )
        self.assertTrue(
            mw._should_drop_disabled_choice_pointer_event(
                int(QtCore.QEvent.HoverMove),
            )
        )
        self.assertTrue(
            mw._should_drop_disabled_choice_pointer_event(
                int(QtCore.QEvent.Wheel),
            )
        )

    def test_pointer_drop_can_be_disabled_via_config(self):
        mw = self._make_window(
            startup_block=True,
            startup_drain=False,
            overlay=_FakeOverlay(offline_enabled=False, online_enabled=False),
        )
        prev = getattr(config, "STARTUP_DROP_CHOICE_POINTER_EVENTS", True)
        try:
            config.STARTUP_DROP_CHOICE_POINTER_EVENTS = False
            self.assertFalse(
                mw._should_drop_disabled_choice_pointer_event(
                    int(QtCore.QEvent.MouseMove),
                )
            )
        finally:
            config.STARTUP_DROP_CHOICE_POINTER_EVENTS = prev

    def test_sync_disabled_spin_all_tooltip_shows_on_hover_inside_button(self):
        mw = MainWindow.__new__(MainWindow)
        mw.btn_spin_all = _FakeSpinAllButton(
            enabled=False,
            tooltip="disabled spin tooltip",
            top_left=QtCore.QPoint(100, 100),
            size=QtCore.QSize(160, 46),
        )
        mw._disabled_spin_all_hover_active = False

        with patch("controller.main_window_parts.main_window_input.QtWidgets.QToolTip.showText") as show_text:
            handled = mw._sync_disabled_spin_all_tooltip(QtCore.QPoint(120, 120), force_show=True)
            self.assertTrue(handled)
            show_text.assert_called_once()

    def test_sync_disabled_spin_all_tooltip_hides_when_button_enabled(self):
        mw = MainWindow.__new__(MainWindow)
        mw.btn_spin_all = _FakeSpinAllButton(
            enabled=True,
            tooltip="spin tooltip",
            top_left=QtCore.QPoint(100, 100),
            size=QtCore.QSize(160, 46),
        )
        mw._disabled_spin_all_hover_active = True

        with patch("controller.main_window_parts.main_window_input.QtWidgets.QToolTip.hideText") as hide_text:
            handled = mw._sync_disabled_spin_all_tooltip(QtCore.QPoint(120, 120), force_show=True)
            self.assertFalse(handled)
            hide_text.assert_called_once()

    def test_sync_disabled_choice_overlay_tooltip_shows_on_hover(self):
        class _Overlay:
            def __init__(self):
                self._last_view = {"type": "online_choice"}
                self.btn_offline = _FakeSpinAllButton(
                    enabled=False,
                    tooltip="loading offline",
                    top_left=QtCore.QPoint(100, 100),
                    size=QtCore.QSize(140, 44),
                )
                self.btn_online = _FakeSpinAllButton(
                    enabled=False,
                    tooltip="loading online",
                    top_left=QtCore.QPoint(280, 100),
                    size=QtCore.QSize(140, 44),
                )

            def isVisible(self) -> bool:
                return True

        mw = MainWindow.__new__(MainWindow)
        mw.overlay = _Overlay()
        mw._startup_block_input = True
        mw._startup_drain_active = False
        mw._disabled_choice_hover_active = False
        mw._disabled_choice_hover_button = None

        with patch("controller.main_window_parts.main_window_input.QtWidgets.QToolTip.showText") as show_text:
            handled = mw._sync_disabled_choice_overlay_tooltip(QtCore.QPoint(110, 110), force_show=True)
            self.assertTrue(handled)
            show_text.assert_called_once()

    def test_sync_disabled_choice_overlay_tooltip_hides_when_leaving_button(self):
        class _Overlay:
            def __init__(self):
                self._last_view = {"type": "online_choice"}
                self.btn_offline = _FakeSpinAllButton(
                    enabled=False,
                    tooltip="loading offline",
                    top_left=QtCore.QPoint(100, 100),
                    size=QtCore.QSize(140, 44),
                )
                self.btn_online = _FakeSpinAllButton(
                    enabled=False,
                    tooltip="loading online",
                    top_left=QtCore.QPoint(280, 100),
                    size=QtCore.QSize(140, 44),
                )

            def isVisible(self) -> bool:
                return True

        mw = MainWindow.__new__(MainWindow)
        mw.overlay = _Overlay()
        mw._startup_block_input = True
        mw._startup_drain_active = False
        mw._disabled_choice_hover_active = True
        mw._disabled_choice_hover_button = mw.overlay.btn_offline

        with patch("controller.main_window_parts.main_window_input.QtWidgets.QToolTip.hideText") as hide_text:
            handled = mw._sync_disabled_choice_overlay_tooltip(QtCore.QPoint(10, 10), force_show=True)
            self.assertFalse(handled)
            hide_text.assert_called_once()

    def test_focus_event_blocked_while_startup_input_lock_active(self):
        mw = MainWindow.__new__(MainWindow)
        mw._startup_block_input = True
        cleared: list[bool] = []
        traces: list[tuple[str, dict]] = []
        mw._clear_focus_now = lambda: cleared.append(True)
        mw._trace_event = lambda name, **extra: traces.append((name, extra))

        blocked = mw._should_block_startup_focus_event(int(QtCore.QEvent.WindowActivate))

        self.assertTrue(blocked)
        self.assertTrue(cleared)
        self.assertTrue(any(name == "startup_focus_blocked" for name, _extra in traces))

    def test_focus_event_not_blocked_when_disabled_in_config(self):
        mw = MainWindow.__new__(MainWindow)
        mw._startup_block_input = True
        mw._cfg = lambda key, default=None: False if key == "STARTUP_CLEAR_FOCUS_WHILE_BLOCKED" else default
        mw._clear_focus_now = lambda: None

        blocked = mw._should_block_startup_focus_event(int(QtCore.QEvent.WindowActivate))

        self.assertFalse(blocked)

    def test_hover_prime_deferred_events_are_coalesced(self):
        mw = MainWindow.__new__(MainWindow)
        traces: list[tuple[str, dict]] = []
        mw._hover_prime_pending = False
        mw._hover_prime_reason = None
        mw._hover_prime_deferred_count = 0
        mw._hover_prime_first_reason = None
        mw._hover_prime_last_reason = None
        mw._trace_hover_event = lambda name, **extra: traces.append((name, extra))

        mw._record_hover_prime_deferred(reason="WindowActivate")
        mw._record_hover_prime_deferred(reason="ActivationChange")
        mw._record_hover_prime_deferred(reason="ActivationChange")
        mw._flush_hover_prime_deferred_trace()

        self.assertEqual(traces[0][0], "hover_pump_deferred")
        self.assertEqual(traces[1][0], "hover_pump_deferred_coalesced")
        self.assertEqual(traces[1][1].get("count"), 3)
        self.assertEqual(mw._hover_prime_deferred_count, 0)

    def test_event_filter_pointer_spam_is_early_dropped_without_drain_restarts(self):
        mw = self._make_window(
            startup_block=False,
            startup_drain=True,
            overlay=_FakeOverlay(offline_enabled=False, online_enabled=False),
        )
        drained: list[int] = []
        restarts: list[int] = []
        mw._record_drained_input_event = lambda etype: drained.append(int(etype))
        mw._restart_startup_drain_timer = lambda: restarts.append(1)

        for _ in range(120):
            self.assertTrue(mw.eventFilter(None, QtCore.QEvent(QtCore.QEvent.MouseMove)))
            self.assertTrue(mw.eventFilter(None, QtCore.QEvent(QtCore.QEvent.HoverMove)))

        self.assertEqual(drained, [])
        self.assertEqual(restarts, [])

    def test_start_hover_pump_spam_coalesces_until_startup_unlock(self):
        mw = MainWindow.__new__(MainWindow)
        traces: list[tuple[str, dict]] = []
        mw._closing = False
        mw._startup_block_input = True
        mw._startup_drain_active = False
        mw._hover_seen = False
        mw._hover_pump_until = None
        mw._hover_pump_timer = None
        mw._hover_prime_pending = False
        mw._hover_prime_reason = None
        mw._hover_prime_deferred_count = 0
        mw._hover_prime_first_reason = None
        mw._hover_prime_last_reason = None
        mw._overlay_choice_active = lambda: False
        mw._trace_hover_event = lambda name, **extra: traces.append((name, extra))

        mw._start_hover_pump(reason="WindowActivate", duration_ms=900, force=True)
        mw._start_hover_pump(reason="ActivationChange", duration_ms=900, force=True)
        mw._start_hover_pump(reason="ApplicationActivate", duration_ms=900, force=True)
        self.assertEqual([name for name, _ in traces], ["hover_pump_deferred"])

        mw._startup_block_input = False
        mw._start_hover_pump(reason="startup_drain:done", duration_ms=900, force=True)

        self.assertEqual(traces[1][0], "hover_pump_deferred_coalesced")
        self.assertEqual(traces[1][1].get("count"), 3)
        self.assertEqual(traces[2][0], "hover_pump_start")

    def test_post_choice_guard_drops_clickthrough_events(self):
        mw = MainWindow.__new__(MainWindow)
        mw._post_choice_input_guard_until = time.monotonic() + 1.0
        mw._overlay_choice_active = lambda: False

        self.assertTrue(
            mw._should_drop_post_choice_clickthrough_event(
                int(QtCore.QEvent.MouseButtonPress),
            )
        )
        self.assertTrue(
            mw._should_drop_post_choice_clickthrough_event(
                int(QtCore.QEvent.MouseButtonRelease),
            )
        )
        self.assertFalse(
            mw._should_drop_post_choice_clickthrough_event(
                int(QtCore.QEvent.HoverMove),
            )
        )

    def test_post_choice_guard_does_not_drop_while_choice_overlay_active(self):
        mw = MainWindow.__new__(MainWindow)
        mw._post_choice_input_guard_until = time.monotonic() + 1.0
        mw._overlay_choice_active = lambda: True

        self.assertFalse(
            mw._should_drop_post_choice_clickthrough_event(
                int(QtCore.QEvent.MouseButtonPress),
            )
        )

    def test_post_choice_guard_does_not_drop_wheel_segment_click_targets(self):
        mw = MainWindow.__new__(MainWindow)
        mw._post_choice_input_guard_until = time.monotonic() + 1.0
        mw._overlay_choice_active = lambda: False
        mw._is_wheel_view_event_target = lambda _obj: True

        self.assertFalse(
            mw._should_drop_post_choice_clickthrough_event(
                int(QtCore.QEvent.MouseButtonPress),
                object(),
            )
        )

    def test_spin_single_not_blocked_by_post_choice_guard(self):
        mw = MainWindow.__new__(MainWindow)
        mw.current_mode = "players"
        mw._post_choice_input_guard_until = time.monotonic() + 1.0
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))
        dummy_wheel = object()

        with patch.object(spin_service, "spin_single") as mocked:
            mw._spin_single(dummy_wheel, mult=1.0, hero_ban_override=True)
            mocked.assert_called_once()

    def test_spin_all_not_blocked_by_post_choice_guard(self):
        mw = MainWindow.__new__(MainWindow)
        mw.current_mode = "players"
        mw._post_choice_input_guard_until = time.monotonic() + 1.0
        mw._overlay_choice_active = lambda: False
        mw._post_choice_init_done = True
        mw._restoring_state = False
        mw.open_queue = type("OpenQ", (), {"is_mode_active": lambda self: False})()
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))

        with patch.object(spin_service, "spin_all") as mocked:
            mw.spin_all()
            mocked.assert_called_once()

    def test_spin_all_uses_preinit_fallback_when_post_choice_not_ready(self):
        mw = MainWindow.__new__(MainWindow)
        mw.current_mode = "players"
        mw._post_choice_input_guard_until = 0.0
        mw._overlay_choice_active = lambda: False
        mw._post_choice_init_done = False
        mw._ensure_post_choice_ready = lambda: None
        mw._restoring_state = False
        mw.open_queue = type("OpenQ", (), {"is_mode_active": lambda self: False})()
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))

        with patch.object(spin_service, "spin_all") as mocked:
            mw.spin_all()
            mocked.assert_called_once()

        self.assertTrue(any(name == "spin_all_preinit_fallback" for name, _extra in traces))

    def test_flush_posted_events_uses_targeted_receivers(self):
        mw = MainWindow.__new__(MainWindow)
        mw.pending = 0
        mw.overlay = object()
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))

        removed: list[object] = []
        with patch("controller.main_window.QtCore.QCoreApplication.instance", return_value=object()):
            with patch(
                "controller.main_window.QtCore.QCoreApplication.removePostedEvents",
                side_effect=lambda target: removed.append(target),
            ):
                mw._flush_posted_events("unit_test")

        self.assertEqual(removed, [mw, mw.overlay])
        self.assertTrue(any(name == "posted_events_flushed" for name, _extra in traces))

    def test_flush_posted_events_is_skipped_while_spin_active(self):
        mw = MainWindow.__new__(MainWindow)
        mw.pending = 1
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))

        with patch("controller.main_window.QtCore.QCoreApplication.instance", return_value=object()):
            with patch("controller.main_window.QtCore.QCoreApplication.removePostedEvents") as remove_events:
                mw._flush_posted_events("unit_test")
                remove_events.assert_not_called()

        self.assertTrue(any(name == "posted_events_flush_skipped" for name, _extra in traces))

    def test_startup_warmup_cooldown_respects_minimum_input_lock(self):
        mw = MainWindow.__new__(MainWindow)
        mw._startup_warmup_done = False
        mw._startup_warmup_finalize_scheduled = False
        mw._startup_block_input_until = time.monotonic() + 2.4
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))
        mw._cfg = lambda key, default=None: 300 if key == "STARTUP_WARMUP_COOLDOWN_MS" else default

        with patch("controller.main_window.QtCore.QTimer.singleShot") as single_shot:
            mw._finish_startup_warmup()

        self.assertTrue(single_shot.called)
        delay_ms = int(single_shot.call_args[0][0])
        self.assertGreaterEqual(delay_ms, 2000)
        self.assertTrue(any(name == "startup_warmup:cooldown" for name, _extra in traces))

    def test_show_mode_choice_disables_choice_buttons_and_starts_warmup(self):
        overlay = _FakeOverlay(offline_enabled=True, online_enabled=True)
        mw = MainWindow.__new__(MainWindow)
        mw.overlay = overlay
        mw._choice_shown_at = None
        controls: list[bool] = []
        heavy_updates: list[bool] = []
        warmup_calls: list[bool] = []
        refresh_calls: list[bool] = []
        traces: list[tuple[str, dict]] = []
        mw._set_controls_enabled = lambda enabled: controls.append(bool(enabled))
        mw._set_heavy_ui_updates_enabled = lambda enabled: heavy_updates.append(bool(enabled))
        mw._start_startup_warmup = lambda: warmup_calls.append(True)
        mw._refresh_app_event_filter_state = lambda: refresh_calls.append(True)
        mw._trace_event = lambda name, **extra: traces.append((name, extra))

        mw._show_mode_choice()

        self.assertEqual(controls, [False])
        self.assertEqual(heavy_updates, [False])
        self.assertEqual(overlay.show_online_choice_calls, 1)
        self.assertEqual(overlay.choice_enabled_calls, [False])
        self.assertEqual(warmup_calls, [True])
        self.assertEqual(refresh_calls, [True])
        self.assertIsNotNone(mw._choice_shown_at)
        self.assertTrue(any(name == "show_mode_choice" for name, _extra in traces))

    def test_startup_warmup_queue_includes_ocr_preload_task_when_enabled(self):
        mw = MainWindow.__new__(MainWindow)
        mw._startup_warmup_done = False
        mw._startup_warmup_running = False
        mw._startup_task_queue = []
        mw._startup_task_done = lambda _name=None: None
        mw._startup_current_task = None
        mw._startup_block_input = False
        mw._startup_block_input_until = None
        mw._startup_drain_active = False
        mw._refresh_app_event_filter_state = lambda: None
        mw._trace_event = lambda *_args, **_kwargs: None
        run_next_calls: list[bool] = []
        mw._run_next_startup_task = lambda: run_next_calls.append(True)

        values = {
            "STARTUP_WHEEL_CACHE_WARMUP": False,
            "SOUND_WARMUP_ON_START": False,
            "MAP_PREBUILD_ON_START": False,
            "STARTUP_OCR_PRELOAD": True,
            "STARTUP_MIN_BLOCK_INPUT_MS": 0,
        }
        mw._cfg = lambda key, default=None: values.get(key, default)

        mw._start_startup_warmup()

        self.assertTrue(mw._startup_warmup_running)
        self.assertTrue(mw._startup_block_input)
        self.assertIsNone(mw._startup_block_input_until)
        self.assertEqual(len(mw._startup_task_queue), 1)
        self.assertEqual(mw._startup_task_queue[0][0], "ocr_preload")
        self.assertEqual(run_next_calls, [True])

    def test_poll_startup_ocr_preload_extends_wait_while_thread_is_running(self):
        class _RunningThread:
            def isRunning(self) -> bool:
                return True

        mw = MainWindow.__new__(MainWindow)
        mw._startup_waiting_for_ocr_preload = True
        mw._startup_ocr_preload_deadline = time.monotonic() - 0.01
        mw._startup_ocr_preload_started_at = time.monotonic() - 1.0
        mw._startup_ocr_preload_running_wait_logged = False
        mw._ocr_preload_done = False
        mw._ocr_preload_attempted = False
        mw._ocr_preload_job = {"thread": _RunningThread()}
        mw._trace_event = lambda *_args, **_kwargs: None
        done_calls: list[str] = []
        mw._startup_task_done = lambda name=None: done_calls.append(str(name or ""))
        mw._cfg = (
            lambda key, default=None: (
                220
                if key == "POST_CHOICE_INIT_BUSY_RETRY_MS"
                else 5000
                if key == "STARTUP_OCR_PRELOAD_RUNNING_MAX_WAIT_MS"
                else default
            )
        )

        with patch("controller.main_window.QtCore.QTimer.singleShot") as single_shot:
            mw._poll_startup_ocr_preload()

        self.assertTrue(single_shot.called)
        self.assertEqual(int(single_shot.call_args[0][0]), 220)
        self.assertEqual(done_calls, [])
        self.assertTrue(mw._startup_waiting_for_ocr_preload)
        self.assertTrue(bool(getattr(mw, "_startup_ocr_preload_running_wait_logged", False)))

    def test_poll_startup_ocr_preload_times_out_after_running_budget(self):
        class _RunningThread:
            def isRunning(self) -> bool:
                return True

        mw = MainWindow.__new__(MainWindow)
        mw._startup_waiting_for_ocr_preload = True
        mw._startup_ocr_preload_deadline = time.monotonic() - 0.01
        mw._startup_ocr_preload_started_at = time.monotonic() - 6.0
        mw._startup_ocr_preload_running_wait_logged = False
        mw._ocr_preload_done = False
        mw._ocr_preload_attempted = False
        mw._ocr_preload_job = {"thread": _RunningThread()}
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))
        done_calls: list[str] = []
        mw._startup_task_done = lambda name=None: done_calls.append(str(name or ""))
        mw._cfg = (
            lambda key, default=None: (
                220
                if key == "POST_CHOICE_INIT_BUSY_RETRY_MS"
                else 5000
                if key == "STARTUP_OCR_PRELOAD_RUNNING_MAX_WAIT_MS"
                else default
            )
        )

        with patch("controller.main_window.QtCore.QTimer.singleShot") as single_shot:
            mw._poll_startup_ocr_preload()

        single_shot.assert_not_called()
        self.assertEqual(done_calls, ["ocr_preload"])
        self.assertFalse(bool(getattr(mw, "_startup_waiting_for_ocr_preload", False)))
        self.assertIsNone(getattr(mw, "_startup_ocr_preload_deadline", None))
        self.assertTrue(any(name == "startup_warmup:ocr_preload_timeout" for name, _extra in traces))

    def test_finalize_startup_defers_visual_finalize(self):
        mw = MainWindow.__new__(MainWindow)
        mw._startup_finalize_done = False
        mw._startup_visual_finalize_pending = False
        mw._restoring_state = True
        mw._cfg = lambda key, default=None: True if key == "STARTUP_VISUAL_FINALIZE_DEFERRED" else default
        mw._update_spin_all_enabled = lambda: None
        mw._update_cancel_enabled = lambda: None
        mw._mode_key = lambda: "players"
        mw._apply_mode_results = lambda _key: None
        mw._set_tooltips_ready = lambda _ready=True: None
        apply_calls: list[str] = []
        mw._apply_theme = lambda defer_heavy=False: apply_calls.append(f"theme:{bool(defer_heavy)}")
        mw._apply_language = lambda defer_heavy=False: apply_calls.append(f"lang:{bool(defer_heavy)}")
        scheduled: list[int] = []
        mw._schedule_startup_visual_finalize = lambda delay_ms=None: scheduled.append(
            0 if delay_ms is None else int(delay_ms)
        )

        mw._finalize_startup()

        self.assertTrue(mw._startup_finalize_done)
        self.assertFalse(mw._restoring_state)
        self.assertTrue(mw._startup_visual_finalize_pending)
        self.assertTrue(scheduled)
        self.assertEqual(apply_calls, ["theme:True", "lang:True"])

    def test_run_startup_visual_finalize_retries_when_blocked(self):
        mw = MainWindow.__new__(MainWindow)
        mw._closing = False
        mw._startup_visual_finalize_pending = True
        mw.pending = 1
        mw._background_services_paused = False
        mw._stack_switching = False
        mw._overlay_choice_active = lambda: False
        mw._cfg = lambda key, default=None: 123 if key == "STARTUP_VISUAL_FINALIZE_BUSY_RETRY_MS" else default
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))
        scheduled: list[int] = []
        mw._schedule_startup_visual_finalize = lambda delay_ms=None: scheduled.append(
            0 if delay_ms is None else int(delay_ms)
        )
        apply_calls: list[str] = []
        mw._apply_theme = lambda defer_heavy=False: apply_calls.append(f"theme:{bool(defer_heavy)}")
        mw._apply_language = lambda defer_heavy=False: apply_calls.append(f"lang:{bool(defer_heavy)}")

        mw._run_startup_visual_finalize()

        self.assertTrue(mw._startup_visual_finalize_pending)
        self.assertEqual(scheduled, [123])
        self.assertEqual(apply_calls, [])
        self.assertTrue(any(name == "startup_visual_finalize:defer" for name, _extra in traces))

    def test_run_startup_visual_finalize_applies_when_idle(self):
        mw = MainWindow.__new__(MainWindow)
        mw._closing = False
        mw._startup_visual_finalize_pending = True
        mw.pending = 0
        mw._background_services_paused = False
        mw._stack_switching = False
        mw._overlay_choice_active = lambda: False
        mw._cfg = lambda _key, default=None: default
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))
        apply_calls: list[str] = []
        mw._apply_theme = lambda defer_heavy=False: apply_calls.append(f"theme:{bool(defer_heavy)}")
        mw._apply_language = lambda defer_heavy=False: apply_calls.append(f"lang:{bool(defer_heavy)}")

        mw._run_startup_visual_finalize()

        self.assertFalse(mw._startup_visual_finalize_pending)
        self.assertEqual(apply_calls, ["theme:True", "lang:True"])
        self.assertTrue(any(name == "startup_visual_finalize:done" for name, _extra in traces))

    def test_run_startup_visual_finalize_flushes_pending_heavy_when_warmup_done(self):
        mw = MainWindow.__new__(MainWindow)
        mw._closing = False
        mw._startup_visual_finalize_pending = True
        mw.pending = 0
        mw._background_services_paused = False
        mw._stack_switching = False
        mw._startup_warmup_done = True
        mw._post_choice_init_done = True
        mw._overlay_choice_active = lambda: False
        mw._post_choice_step_ms = 15
        mw._cfg = lambda _key, default=None: default
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))
        mw._set_heavy_ui_updates_enabled = lambda enabled=True: None
        apply_calls: list[str] = []
        mw._apply_theme = lambda defer_heavy=False: (
            apply_calls.append(f"theme:{bool(defer_heavy)}"),
            setattr(mw, "_theme_heavy_pending", True),
        )
        mw._apply_language = lambda defer_heavy=False: (
            apply_calls.append(f"lang:{bool(defer_heavy)}"),
            setattr(mw, "_language_heavy_pending", True),
        )
        heavy_calls: list[str] = []
        mw._apply_language_heavy = lambda: heavy_calls.append("lang_heavy")
        mw._apply_theme_heavy = lambda _theme, step_ms=0: heavy_calls.append(f"theme_heavy:{int(step_ms)}")

        mw._run_startup_visual_finalize()

        self.assertFalse(mw._startup_visual_finalize_pending)
        self.assertEqual(apply_calls, ["theme:True", "lang:True"])
        self.assertIn("lang_heavy", heavy_calls)
        self.assertIn("theme_heavy:15", heavy_calls)
        self.assertFalse(bool(getattr(mw, "_theme_heavy_pending", False)))
        self.assertFalse(bool(getattr(mw, "_language_heavy_pending", False)))
        self.assertTrue(any(name == "startup_visual_finalize:flushed_heavy" for name, _extra in traces))

    def test_spin_all_ignored_while_restoring_state(self):
        mw = MainWindow.__new__(MainWindow)
        mw.current_mode = "players"
        mw._post_choice_input_guard_until = 0.0
        mw._overlay_choice_active = lambda: False
        mw._post_choice_init_done = True
        mw._restoring_state = True
        mw.open_queue = type("OpenQ", (), {"is_mode_active": lambda self: False})()
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))

        with patch.object(spin_service, "spin_all") as mocked:
            mw.spin_all()
            mocked.assert_not_called()

        self.assertTrue(traces)
        self.assertEqual(traces[0][0], "spin_all_ignored")

    def test_cancel_spin_guard_ignores_early_cancel(self):
        mw = MainWindow.__new__(MainWindow)
        mw.pending = 2
        mw._spin_started_at_monotonic = time.monotonic()
        mw._cfg = lambda key, default=None: 1100 if key == "SPIN_CANCEL_GUARD_MS" else default
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))
        mw.sender = lambda: None

        mw._cancel_spin()

        self.assertEqual(mw.pending, 2)
        self.assertTrue(any(name == "spin_cancel_ignored" for name, _extra in traces))

    def test_cancel_spin_guard_does_not_block_cancel_button_click(self):
        class _Overlay:
            def show_message(self, *_args, **_kwargs):
                return None

        mw = MainWindow.__new__(MainWindow)
        mw.pending = 2
        mw._spin_started_at_monotonic = time.monotonic()
        mw._cfg = lambda key, default=None: 1100 if key == "SPIN_CANCEL_GUARD_MS" else default
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))
        mw.sender = lambda: _FakeSender("btn_cancel_spin", "Cancel")
        mw._disarm_spin_watchdog = lambda: None
        mw._clear_spin_started = lambda: setattr(mw, "_spin_started_at_monotonic", None)
        mw._stop_spin_audio = lambda: None
        mw._stop_all_wheels = lambda: None
        mw._restore_results_snapshot = lambda: None
        mw._restore_open_queue_spin_overrides_if_active = lambda: None
        mw.overlay = _Overlay()
        mw._set_controls_enabled = lambda _enabled: None
        mw._update_cancel_enabled = lambda: None

        mw._cancel_spin()

        self.assertEqual(mw.pending, 0)
        self.assertTrue(any(name == "spin_cancel_requested" for name, _extra in traces))
        self.assertFalse(any(name == "spin_cancel_ignored" for name, _extra in traces))

    def test_watchdog_forces_finish_for_stalled_wheels_before_recovery(self):
        class _FakeWheel:
            def __init__(self, owner):
                self._owner = owner
                self._is_spinning = True
                self._pending_result = "A"
                self.emit_calls = 0

            def is_anim_running(self):
                return False

            def _emit_result(self):
                self.emit_calls += 1
                if self._owner.pending > 0:
                    self._owner.pending -= 1
                self._is_spinning = False
                if hasattr(self, "_pending_result"):
                    delattr(self, "_pending_result")

        class _FakeTimer:
            def __init__(self):
                self.started = []

            def start(self, timeout):
                self.started.append(int(timeout))

        mw = MainWindow.__new__(MainWindow)
        mw.pending = 2
        mw._cfg = lambda key, default=None: True if key == "SPIN_WATCHDOG_ENABLED" else default
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))
        wheel_a = _FakeWheel(mw)
        wheel_b = _FakeWheel(mw)
        mw._role_wheels = lambda: [("Tank", wheel_a), ("Damage", wheel_b)]
        mw._spin_watchdog_timer = _FakeTimer()
        mw.open_queue = type("OpenQ", (), {"spin_active": lambda self: False})()
        mw.sound = type("Sound", (), {"stop_spin": lambda self: None, "stop_ding": lambda self: None})()
        mw._set_controls_enabled = lambda _enabled: None
        mw._update_cancel_enabled = lambda: None

        mw._on_spin_watchdog_timeout()

        self.assertEqual(mw.pending, 0)
        self.assertEqual(wheel_a.emit_calls, 1)
        self.assertEqual(wheel_b.emit_calls, 1)
        self.assertTrue(any(name == "spin_watchdog_force_finish" for name, _extra in traces))
        self.assertFalse(any(name == "spin_watchdog_recovery" for name, _extra in traces))

    def test_mode_button_ignored_during_post_choice_guard(self):
        mw = MainWindow.__new__(MainWindow)
        mw._post_choice_input_guard_until = time.monotonic() + 1.0
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))

        mw._on_mode_button_clicked("hero_ban")

        self.assertEqual(traces[0][0], "mode_button_clicked")
        self.assertEqual(traces[1][0], "mode_switch_ignored")

    def test_update_spin_all_enabled_syncs_open_slider_count_in_role_mode(self):
        class _SetEnabledButton:
            def __init__(self):
                self.enabled = None

            def setEnabled(self, enabled: bool):
                self.enabled = bool(enabled)

        class _OpenQueue:
            def __init__(self):
                self.sync_calls = 0
                self.preview_calls = 0

            def is_mode_active(self):
                return False

            def spin_mode_allowed(self):
                return True

            def sync_player_count_from_wheels(self):
                self.sync_calls += 1

            def apply_preview(self, _names):
                self.preview_calls += 1

        class _RoleMode:
            def can_spin_all(self):
                return True

        mw = MainWindow.__new__(MainWindow)
        mw.hero_ban_active = False
        mw.current_mode = "players"
        mw.pending = 0
        mw.open_queue = _OpenQueue()
        mw.role_mode = _RoleMode()
        mw.btn_spin_all = _SetEnabledButton()
        mw._update_spin_mode_ui = lambda: None
        mw._update_cancel_enabled = lambda: None
        mw._update_role_ocr_buttons_enabled = lambda: None

        mw._update_spin_all_enabled()

        self.assertEqual(mw.open_queue.sync_calls, 1)
        self.assertEqual(mw.open_queue.preview_calls, 1)
        self.assertTrue(mw.btn_spin_all.enabled)

    def test_update_spin_all_enabled_in_open_mode_applies_preview(self):
        class _SetEnabledButton:
            def __init__(self):
                self.enabled = None

            def setEnabled(self, enabled: bool):
                self.enabled = bool(enabled)

        class _OpenQueue:
            def __init__(self):
                self.preview_calls = 0
                self.clear_calls = 0

            def is_mode_active(self):
                return True

            def is_applying_combination(self):
                return False

            def apply_slider_combination(self):
                return None

            def slot_plan(self):
                return [("Tank", object(), 1)]

            def names(self):
                return ["A"]

            def clear_preview(self, *, force: bool = False):
                self.clear_calls += 1

            def apply_preview(self, _names):
                self.preview_calls += 1

        mw = MainWindow.__new__(MainWindow)
        mw.hero_ban_active = False
        mw.current_mode = "players"
        mw.pending = 0
        mw.open_queue = _OpenQueue()
        mw.btn_spin_all = _SetEnabledButton()
        mw.sender = lambda: None
        mw._update_spin_mode_ui = lambda: None
        mw._update_cancel_enabled = lambda: None
        mw._update_role_ocr_buttons_enabled = lambda: None

        mw._update_spin_all_enabled()

        self.assertEqual(mw.open_queue.clear_calls, 0)
        self.assertEqual(mw.open_queue.preview_calls, 1)
        self.assertTrue(mw.btn_spin_all.enabled)


if __name__ == "__main__":
    unittest.main()
