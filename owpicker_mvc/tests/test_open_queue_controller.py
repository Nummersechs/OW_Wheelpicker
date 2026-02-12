import unittest

from controller.open_queue import OpenQueueController


class DummyToggle:
    def __init__(self, value: int):
        self._value = value

    def value(self) -> int:
        return self._value


class DummyWheel:
    def __init__(
        self,
        entries,
        *,
        selected=True,
        pair_mode=False,
        use_subrole_filter=False,
        subrole_labels=None,
        disabled_labels=None,
    ):
        self._entries = list(entries)
        self._selected = bool(selected)
        self.pair_mode = bool(pair_mode)
        self.use_subrole_filter = bool(use_subrole_filter)
        self.subrole_labels = list(subrole_labels or [])
        self._disabled_labels = set(disabled_labels or set())
        self._disabled_indices = set()
        self._override_entries = None
        self.refresh_calls = 0
        self.override_calls = 0

    def is_selected_for_global_spin(self) -> bool:
        return self._selected

    def _active_entries(self):
        return list(self._entries)

    def set_override_entries(self, entries):
        self._override_entries = entries
        self.override_calls += 1

    def _refresh_disabled_indices(self):
        self.refresh_calls += 1


class DummyMW:
    def __init__(self):
        self.current_mode = "players"
        self.hero_ban_active = False
        self.spin_mode_toggle = DummyToggle(1)
        self.tank = DummyWheel([{"name": "Ana"}, {"name": "Bap"}], selected=True)
        self.dps = DummyWheel([{"name": "Bap"}, {"name": "Cass"}], selected=True, pair_mode=True)
        self.support = DummyWheel([{"name": "Ana"}, {"name": "Moira"}], selected=False)


class TestOpenQueueController(unittest.TestCase):
    def test_spin_mode_allowed_and_mode_active(self):
        mw = DummyMW()
        ctrl = OpenQueueController(mw)
        self.assertTrue(ctrl.spin_mode_allowed())
        self.assertTrue(ctrl.is_mode_active())

        mw.current_mode = "maps"
        self.assertFalse(ctrl.spin_mode_allowed())
        self.assertFalse(ctrl.is_mode_active())

    def test_names_dedupes_and_excludes_disabled_labels(self):
        mw = DummyMW()
        mw.dps._disabled_labels = {"Cass"}
        ctrl = OpenQueueController(mw)
        self.assertEqual(ctrl.names(), ["Ana", "Bap"])

    def test_slots_count_pair_modes(self):
        mw = DummyMW()
        ctrl = OpenQueueController(mw)
        # tank=1, dps(pair)=2, support deselected -> total 3
        self.assertEqual(ctrl.slots(), 3)

    def test_apply_preview_builds_override_entries_and_reuses_same_key(self):
        mw = DummyMW()
        mw.tank.use_subrole_filter = True
        mw.tank.subrole_labels = ["MT", "OT"]
        ctrl = OpenQueueController(mw)

        ctrl.apply_preview(["Ana", "Bap"])
        self.assertEqual(mw.tank.override_calls, 1)
        self.assertEqual(mw.dps.override_calls, 1)
        self.assertEqual(mw.tank._override_entries[0]["subroles"], ["MT", "OT"])

        # Same key and existing override -> no second write.
        ctrl.apply_preview(["Ana", "Bap"])
        self.assertEqual(mw.tank.override_calls, 1)
        self.assertEqual(mw.dps.override_calls, 1)

    def test_clear_preview_restores_original_state(self):
        mw = DummyMW()
        mw.tank._override_entries = [{"name": "Old", "subroles": [], "active": True}]
        mw.tank._disabled_indices = {1}
        ctrl = OpenQueueController(mw)

        ctrl.apply_preview(["Ana"])
        self.assertIsNotNone(mw.tank._override_entries)
        ctrl.clear_preview()

        self.assertEqual(mw.tank._override_entries, [{"name": "Old", "subroles": [], "active": True}])
        self.assertEqual(mw.tank._disabled_indices, {1})
        self.assertGreaterEqual(mw.tank.refresh_calls, 1)

    def test_clear_preview_skips_wheel_if_override_changed_externally(self):
        mw = DummyMW()
        ctrl = OpenQueueController(mw)
        ctrl.apply_preview(["Ana"])

        # External change after preview - controller should not overwrite it.
        mw.tank._override_entries = [{"name": "External", "subroles": [], "active": True}]
        ctrl.clear_preview()
        self.assertEqual(mw.tank._override_entries, [{"name": "External", "subroles": [], "active": True}])

    def test_clear_preview_force_restores_even_after_external_change(self):
        mw = DummyMW()
        ctrl = OpenQueueController(mw)
        base_override = [{"name": "Base", "subroles": [], "active": True}]
        mw.tank._override_entries = base_override
        ctrl.apply_preview(["Ana"])
        self.assertNotEqual(mw.tank._override_entries, base_override)

        mw.tank._override_entries = [{"name": "External", "subroles": [], "active": True}]
        ctrl.clear_preview(force=True)

        self.assertEqual(mw.tank._override_entries, base_override)

    def test_apply_preview_when_mode_inactive_forces_restore(self):
        mw = DummyMW()
        ctrl = OpenQueueController(mw)
        base_override = [{"name": "Base", "subroles": [], "active": True}]
        mw.tank._override_entries = base_override
        ctrl.apply_preview(["Ana"])
        self.assertNotEqual(mw.tank._override_entries, base_override)

        mw.tank._override_entries = [{"name": "External", "subroles": [], "active": True}]
        mw.spin_mode_toggle = DummyToggle(0)
        ctrl.apply_preview(["Ana"])

        self.assertEqual(mw.tank._override_entries, base_override)

    def test_begin_and_restore_spin_overrides_roundtrip(self):
        mw = DummyMW()
        mw.tank._override_entries = [{"name": "Base", "subroles": [], "active": True}]
        mw.tank._disabled_indices = {2}
        ctrl = OpenQueueController(mw)

        ctrl.begin_spin_override(
            {
                mw.tank: [{"name": "Spin", "subroles": [], "active": True}],
                mw.dps: [{"name": "Spin2", "subroles": [], "active": True}],
            }
        )
        self.assertTrue(ctrl.spin_active())
        self.assertEqual(mw.tank._override_entries, [{"name": "Spin", "subroles": [], "active": True}])

        ctrl.restore_spin_overrides()
        self.assertFalse(ctrl.spin_active())
        self.assertEqual(mw.tank._override_entries, [{"name": "Base", "subroles": [], "active": True}])
        self.assertEqual(mw.tank._disabled_indices, {2})

    def test_restore_spin_overrides_clears_preview_when_mode_disabled_mid_spin(self):
        mw = DummyMW()
        ctrl = OpenQueueController(mw)
        ctrl.apply_preview(["Ana", "Bap", "Cass"])
        self.assertIsNotNone(mw.tank._override_entries)

        ctrl.begin_spin_override(
            {
                mw.tank: [{"name": "Spin", "subroles": [], "active": True}],
                mw.dps: [{"name": "Spin2", "subroles": [], "active": True}],
            }
        )
        self.assertTrue(ctrl.spin_active())

        # User switched back to role mode while spin was running.
        mw.spin_mode_toggle = DummyToggle(0)
        ctrl.restore_spin_overrides()

        self.assertFalse(ctrl.spin_active())
        self.assertIsNone(mw.tank._override_entries)
        self.assertIsNone(mw.dps._override_entries)


if __name__ == "__main__":
    unittest.main()
