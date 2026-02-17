import unittest
from unittest.mock import patch

from controller.map_mode import MapModeController


class _DummySound:
    def __init__(self):
        self.stop_spin_calls = 0
        self.stop_ding_calls = 0
        self.play_spin_calls = 0

    def stop_spin(self):
        self.stop_spin_calls += 1

    def stop_ding(self):
        self.stop_ding_calls += 1

    def play_spin(self):
        self.play_spin_calls += 1


class _DummySummary:
    def __init__(self):
        self.text = ""

    def setText(self, value: str):
        self.text = str(value)


class _DummyOverlay:
    def __init__(self):
        self.hidden = False

    def hide(self):
        self.hidden = True


class _DummyDuration:
    def value(self) -> int:
        return 1200


class _DummyMapMain:
    def __init__(self, *, candidates: list[str], succeed: bool):
        self._candidates = list(candidates)
        self._succeed = bool(succeed)
        self.override_entries = None
        self.spin_to_name_calls: list[tuple[str, int]] = []
        self.spin_calls = 0

    def set_override_entries(self, entries):
        self.override_entries = entries

    def get_effective_wheel_names(self, include_disabled: bool = False):
        del include_disabled
        return list(self._candidates)

    def spin_to_name(self, choice: str, duration_ms: int = 0):
        self.spin_to_name_calls.append((str(choice), int(duration_ms)))
        return bool(self._succeed)

    def spin(self, duration_ms: int = 0):
        self.spin_calls += 1
        return bool(self._succeed)


class _DummyMapUI:
    def __init__(self):
        self.rebuild_calls = 0

    def combined_names(self) -> list[str]:
        return ["MapA", "MapB"]

    def rebuild_combined(self, emit_state: bool = False, force_wheel: bool = False):
        del emit_state, force_wheel
        self.rebuild_calls += 1

    def load_state(self):
        return None


class _DummyMW:
    def __init__(self, *, spin_success: bool):
        self.current_mode = "maps"
        self.hero_ban_active = False
        self.pending = 0
        self._result_sent_this_spin = False
        self._map_temp_override = False
        self._pending_map_choice = None
        self.map_ui = _DummyMapUI()
        self.map_main = _DummyMapMain(candidates=["MapA"], succeed=spin_success)
        self.sound = _DummySound()
        self.summary = _DummySummary()
        self.overlay = _DummyOverlay()
        self.duration = _DummyDuration()
        self.controls_enabled = None
        self.stop_all_wheels_calls = 0
        self.snapshot_calls = 0
        self.cancel_updates = 0
        self.spin_watchdogs: list[int] = []
        self.spin_all_enabled_updates = 0

    def _snapshot_results(self):
        self.snapshot_calls += 1

    def _stop_all_wheels(self):
        self.stop_all_wheels_calls += 1

    def _set_controls_enabled(self, enabled: bool, *, spin_mode: bool = False):
        del spin_mode
        self.controls_enabled = bool(enabled)

    def _update_cancel_enabled(self):
        self.cancel_updates += 1

    def _arm_spin_watchdog(self, duration_ms: int):
        self.spin_watchdogs.append(int(duration_ms))

    def _update_spin_all_enabled(self):
        self.spin_all_enabled_updates += 1


class TestMapModeController(unittest.TestCase):
    def test_subset_spin_failure_restores_temp_override_immediately(self):
        mw = _DummyMW(spin_success=False)
        controller = MapModeController(mw)

        with patch("controller.map_mode.i18n.t", side_effect=lambda key, **kwargs: key):
            controller.spin_all(subset=["MapA"])

        self.assertFalse(mw._map_temp_override)
        self.assertEqual(mw.map_ui.rebuild_calls, 1)
        self.assertTrue(mw.controls_enabled)
        self.assertEqual(mw.pending, 0)
        self.assertEqual(mw.summary.text, "map.summary.prompt")

    def test_subset_spin_success_keeps_temp_override_until_finish(self):
        mw = _DummyMW(spin_success=True)
        controller = MapModeController(mw)

        with patch("controller.map_mode.i18n.t", side_effect=lambda key, **kwargs: key):
            controller.spin_all(subset=["MapA"])

        self.assertTrue(mw._map_temp_override)
        self.assertEqual(mw.map_ui.rebuild_calls, 0)
        self.assertEqual(mw.pending, 1)
        self.assertFalse(mw.controls_enabled)
        self.assertEqual(len(mw.spin_watchdogs), 1)


if __name__ == "__main__":
    unittest.main()
