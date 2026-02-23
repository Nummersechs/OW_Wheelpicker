import unittest
from unittest.mock import patch

from controller import spin_service


class DummySound:
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


class DummySummary:
    def __init__(self):
        self.value = ""

    def setText(self, value: str):
        self.value = value


class DummyOverlay:
    def __init__(self):
        self.messages = []
        self.hidden = False

    def show_message(self, title, lines):
        self.messages.append((title, list(lines)))

    def hide(self):
        self.hidden = True


class DummyWheel:
    def __init__(self):
        self.clear_calls = 0

    def clear_result(self):
        self.clear_calls += 1


class DummySpinWheel(DummyWheel):
    def __init__(self, names, *, role_name: str = "", call_log: list | None = None):
        super().__init__()
        self._entries = [{"name": name, "active": True, "subroles": []} for name in names]
        self._override_entries = None
        self._disabled_indices = set()
        self._disabled_labels = set()
        self.use_subrole_filter = False
        self.subrole_labels = []
        self.pair_mode = False
        self.spin_targets = []
        self.too_few = False
        self.role_name = role_name
        self.call_log = call_log

    def _active_entries(self):
        return list(self._entries)

    def _effective_names_from(self, entries, include_disabled=True):
        del include_disabled
        return [entry.get("name", "") for entry in entries if entry.get("name")]

    def set_result_too_few(self):
        self.too_few = True

    def set_override_entries(self, entries):
        self._override_entries = entries

    def _refresh_disabled_indices(self):
        return None

    def spin_to_name(self, target_label, duration_ms=0):
        self.spin_targets.append((target_label, duration_ms))
        if self.call_log is not None:
            self.call_log.append((self.role_name, target_label, int(duration_ms)))
        return True


class DummyRoleMode:
    def __init__(self, wheels):
        self._wheels = list(wheels)

    def active_wheels(self):
        return list(self._wheels)


class DummyOpenQueue:
    def __init__(self, mw):
        self._mw = mw
        self.apply_calls = 0
        self._spin_active = False

    def apply_slider_combination(self):
        self.apply_calls += 1

    def slot_plan(self):
        return [
            ("Tank", self._mw.tank, 1),
            ("Damage", self._mw.dps, 1),
            ("Support", self._mw.support, 1),
        ]

    def names(self):
        names: list[str] = []
        seen: set[str] = set()
        for wheel in (self._mw.tank, self._mw.dps, self._mw.support):
            for entry in wheel._active_entries():
                name = entry.get("name", "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                names.append(name)
        return names

    def begin_spin_override(self, entries_by_wheel, *, mode_overrides=None):
        self.entries_by_wheel = dict(entries_by_wheel)
        self.mode_overrides = dict(mode_overrides or {})
        self._spin_active = True

    def spin_active(self):
        return self._spin_active

    def restore_spin_overrides(self):
        self._spin_active = False


class DummyMW:
    def __init__(self):
        self.sound = DummySound()
        self.summary = DummySummary()
        self.overlay = DummyOverlay()
        self.pending = 2
        self.controls_enabled = None
        self.snapshot_calls = 0
        self.stop_all_wheels_calls = 0
        self.spin_watchdog_armed: list[int] = []
        self.spin_watchdog_disarmed = 0

    def _set_controls_enabled(self, enabled: bool):
        self.controls_enabled = bool(enabled)

    def _snapshot_results(self):
        self.snapshot_calls += 1

    def _stop_all_wheels(self):
        self.stop_all_wheels_calls += 1

    def _arm_spin_watchdog(self, duration_ms: int):
        self.spin_watchdog_armed.append(int(duration_ms))

    def _disarm_spin_watchdog(self):
        self.spin_watchdog_disarmed += 1


class DummyMWOpenQueue(DummyMW):
    class _Duration:
        def value(self):
            return 2000

    def __init__(self):
        super().__init__()
        self.hero_ban_active = False
        self.current_mode = "players"
        self._result_sent_this_spin = False
        self.pending = 0
        self.spin_call_log: list[tuple[str, str, int]] = []
        self.tank = DummySpinWheel(["Ana", "Bap", "Cass"], role_name="Tank", call_log=self.spin_call_log)
        self.dps = DummySpinWheel(["Ana", "Bap", "Cass"], role_name="Damage", call_log=self.spin_call_log)
        self.support = DummySpinWheel(["Ana", "Bap", "Cass"], role_name="Support", call_log=self.spin_call_log)
        self.duration = self._Duration()
        self.open_queue = DummyOpenQueue(self)
        self.cancel_updates = 0

    def _update_cancel_enabled(self):
        self.cancel_updates += 1


class DummyMWRoleSpin(DummyMW):
    class _Duration:
        def value(self):
            return 2000

    def __init__(self):
        super().__init__()
        self.hero_ban_active = False
        self.current_mode = "players"
        self._result_sent_this_spin = False
        self.pending = 0
        self.spin_call_log: list[tuple[str, str, int]] = []
        self.tank = DummySpinWheel([], role_name="Tank", call_log=self.spin_call_log)
        self.dps = DummySpinWheel(["Aero", "Mika"], role_name="Damage", call_log=self.spin_call_log)
        self.support = DummySpinWheel(["Nikeos", "Massith"], role_name="Support", call_log=self.spin_call_log)
        self.duration = self._Duration()
        self.role_mode = DummyRoleMode(
            [
                ("Tank", self.tank),
                ("Damage", self.dps),
                ("Support", self.support),
            ]
        )
        self.cancel_updates = 0

    def _update_cancel_enabled(self):
        self.cancel_updates += 1


class DummyMWRoleSpinAllCandidates(DummyMW):
    class _Duration:
        def value(self):
            return 2000

    def __init__(self):
        super().__init__()
        self.hero_ban_active = False
        self.current_mode = "players"
        self._result_sent_this_spin = False
        self.pending = 0
        self.spin_call_log: list[tuple[str, str, int]] = []
        self.tank = DummySpinWheel(["Aero", "Mika"], role_name="Tank", call_log=self.spin_call_log)
        self.dps = DummySpinWheel(["Nikeos", "Massith"], role_name="Damage", call_log=self.spin_call_log)
        self.support = DummySpinWheel(["AJAR", "Mika"], role_name="Support", call_log=self.spin_call_log)
        self.duration = self._Duration()
        self.role_mode = DummyRoleMode(
            [
                ("Tank", self.tank),
                ("Damage", self.dps),
                ("Support", self.support),
            ]
        )
        self.cancel_updates = 0

    def _update_cancel_enabled(self):
        self.cancel_updates += 1


class TestSpinServiceHelpers(unittest.TestCase):
    def test_labels_to_candidates_filters_empty_parts(self):
        labels = ["A + B", " C ", " + ", "", "D+E+F"]
        got = spin_service._labels_to_candidates(labels)
        self.assertEqual(
            got,
            [
                ("A + B", ["A", "B"]),
                (" C ", ["C"]),
                ("D+E+F", ["D", "E", "F"]),
            ],
        )

    def test_show_team_impossible_updates_ui_and_state(self):
        mw = DummyMW()
        with patch("controller.spin_service.i18n.t", side_effect=lambda key, **kwargs: key):
            spin_service._show_team_impossible(mw)
        self.assertEqual(mw.sound.stop_spin_calls, 1)
        self.assertEqual(mw.sound.stop_ding_calls, 1)
        self.assertTrue(mw.controls_enabled)
        self.assertEqual(mw.pending, 0)
        self.assertEqual(mw.summary.value, "summary.team_impossible")
        self.assertTrue(mw.overlay.messages)
        title, lines = mw.overlay.messages[-1]
        self.assertEqual(title, "overlay.team_impossible_title")
        self.assertEqual(lines[:2], ["overlay.team_impossible_line1", "overlay.team_impossible_line2"])

    def test_begin_spin_run_stops_existing_sounds_before_play(self):
        mw = DummyMW()
        wheel = DummyWheel()

        spin_service._begin_spin_run(mw, [("tank", wheel)])

        self.assertEqual(mw.snapshot_calls, 1)
        self.assertEqual(wheel.clear_calls, 1)
        self.assertEqual(mw.sound.stop_spin_calls, 1)
        self.assertEqual(mw.sound.stop_ding_calls, 1)
        self.assertEqual(mw.sound.play_spin_calls, 1)
        self.assertEqual(mw.stop_all_wheels_calls, 1)
        self.assertEqual(mw.spin_watchdog_disarmed, 1)
        self.assertEqual(mw.pending, 0)
        self.assertEqual(mw.summary.value, "")
        self.assertFalse(mw.controls_enabled)
        self.assertTrue(mw.overlay.hidden)

    def test_spin_single_starts_with_duration(self):
        class _Duration:
            def value(self):
                return 2000

        class _SingleWheel:
            def __init__(self):
                self.calls = []

            def spin(self, duration_ms=0):
                self.calls.append(int(duration_ms))
                return True

        mw = DummyMW()
        mw.pending = 0
        mw.hero_ban_active = False
        mw._result_sent_this_spin = False
        mw.duration = _Duration()
        mw._update_cancel_enabled = lambda: None
        wheel = _SingleWheel()

        spin_service.spin_single(mw, wheel, mult=1.0, hero_ban_override=True)
        self.assertEqual(wheel.calls, [2000])

    def test_spin_open_queue_starts_spin_for_planned_roles(self):
        mw = DummyMWOpenQueue()
        with patch("controller.spin_service.random.shuffle", side_effect=lambda vals: None):
            spin_service.spin_open_queue(mw)

        self.assertEqual(mw.open_queue.apply_calls, 1)
        self.assertTrue(mw.open_queue.spin_active())
        self.assertEqual(mw.pending, 3)
        self.assertEqual(len(mw.tank.spin_targets), 1)
        self.assertEqual(len(mw.dps.spin_targets), 1)
        self.assertEqual(len(mw.support.spin_targets), 1)
        self.assertEqual(mw.spin_watchdog_armed, [2700])
        self.assertFalse(mw.controls_enabled)
        self.assertEqual(mw.cancel_updates, 1)

    def test_spin_open_queue_uses_open_queue_name_pool(self):
        mw = DummyMWOpenQueue()
        mw.tank._entries = [{"name": "TankOnly", "active": True, "subroles": []}]
        mw.dps._entries = [{"name": "DpsOnly", "active": True, "subroles": []}]
        mw.support._entries = [{"name": "SupportOnly", "active": True, "subroles": []}]

        class DummyOpenQueueTwoSlots(DummyOpenQueue):
            def slot_plan(self):
                return [
                    ("Tank", self._mw.tank, 1),
                    ("Damage", self._mw.dps, 1),
                    ("Support", self._mw.support, 0),
                ]

        mw.open_queue = DummyOpenQueueTwoSlots(mw)

        with patch("controller.spin_service.random.shuffle", side_effect=lambda vals: None):
            spin_service.spin_open_queue(mw)

        tank_names = [entry["name"] for entry in mw.open_queue.entries_by_wheel[mw.tank]]
        dps_names = [entry["name"] for entry in mw.open_queue.entries_by_wheel[mw.dps]]
        self.assertIn("SupportOnly", tank_names)
        self.assertIn("SupportOnly", dps_names)

    def test_spin_all_spins_available_roles_when_one_role_has_no_candidates(self):
        mw = DummyMWRoleSpin()
        with patch("controller.spin_service.random.shuffle", side_effect=lambda vals: None):
            spin_service.spin_all(mw)

        self.assertEqual(mw.pending, 2)
        self.assertTrue(mw.tank.too_few)
        self.assertEqual(len(mw.tank.spin_targets), 0)
        self.assertEqual(len(mw.dps.spin_targets), 1)
        self.assertEqual(len(mw.support.spin_targets), 1)
        self.assertEqual(mw.spin_watchdog_armed, [2000])
        self.assertFalse(mw.controls_enabled)
        self.assertEqual(mw.cancel_updates, 1)

    def test_spin_all_dispatches_in_role_order_with_expected_durations(self):
        mw = DummyMWRoleSpinAllCandidates()
        with patch("controller.spin_service.random.shuffle", side_effect=lambda vals: None):
            spin_service.spin_all(mw)

        # duration=2000 with multipliers [0.85, 1.00, 1.35]
        self.assertEqual(
            mw.spin_call_log,
            [
                ("Tank", mw.tank.spin_targets[0][0], 1700),
                ("Damage", mw.dps.spin_targets[0][0], 2000),
                ("Support", mw.support.spin_targets[0][0], 2700),
            ],
        )
        self.assertEqual(mw.pending, 3)


if __name__ == "__main__":
    unittest.main()
