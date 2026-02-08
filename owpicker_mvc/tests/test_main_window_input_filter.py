import unittest
import time
from unittest.mock import patch

from PySide6 import QtCore

import config
from controller import spin_service
from controller.main_window import MainWindow


class _FakeButton:
    def __init__(self, enabled: bool):
        self._enabled = bool(enabled)

    def isEnabled(self) -> bool:
        return self._enabled


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

    def isVisible(self) -> bool:
        return self._visible


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

    def test_spin_single_ignored_during_post_choice_guard(self):
        mw = MainWindow.__new__(MainWindow)
        mw.current_mode = "players"
        mw._post_choice_input_guard_until = time.monotonic() + 1.0
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))
        dummy_wheel = object()

        with patch.object(spin_service, "spin_single") as mocked:
            mw._spin_single(dummy_wheel, mult=1.0, hero_ban_override=True)
            mocked.assert_not_called()

        self.assertTrue(traces)
        self.assertEqual(traces[0][0], "spin_single_ignored")

    def test_mode_button_ignored_during_post_choice_guard(self):
        mw = MainWindow.__new__(MainWindow)
        mw._post_choice_input_guard_until = time.monotonic() + 1.0
        traces: list[tuple[str, dict]] = []
        mw._trace_event = lambda name, **extra: traces.append((name, extra))

        mw._on_mode_button_clicked("hero_ban")

        self.assertEqual(traces[0][0], "mode_button_clicked")
        self.assertEqual(traces[1][0], "mode_switch_ignored")


if __name__ == "__main__":
    unittest.main()
