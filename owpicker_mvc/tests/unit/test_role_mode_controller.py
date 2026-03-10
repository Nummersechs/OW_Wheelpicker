import unittest

from controller.role_mode import RoleModeController


class DummyWheel:
    def __init__(self, selected: bool):
        self._selected = bool(selected)

    def is_selected_for_global_spin(self) -> bool:
        return self._selected


class DummyOpenQueue:
    def __init__(self, active: bool):
        self._active = bool(active)

    def is_mode_active(self) -> bool:
        return self._active


class DummyMW:
    def __init__(self):
        self.tank = DummyWheel(True)
        self.dps = DummyWheel(False)
        self.support = DummyWheel(True)
        self.pending = 0
        self.current_mode = "players"
        self.hero_ban_active = False
        self.open_queue = DummyOpenQueue(False)


class TestRoleModeController(unittest.TestCase):
    def test_role_and_active_wheels(self):
        mw = DummyMW()
        ctrl = RoleModeController(mw)
        roles = [role for role, _ in ctrl.role_wheels()]
        active_roles = [role for role, _ in ctrl.active_wheels()]
        self.assertEqual(roles, ["Tank", "Damage", "Support"])
        self.assertEqual(active_roles, ["Tank", "Support"])

    def test_any_selected_and_can_spin_all(self):
        mw = DummyMW()
        ctrl = RoleModeController(mw)
        self.assertTrue(ctrl.any_selected())
        self.assertTrue(ctrl.can_spin_all())
        mw.pending = 1
        self.assertFalse(ctrl.can_spin_all())

    def test_is_active_mode_guards(self):
        mw = DummyMW()
        ctrl = RoleModeController(mw)
        self.assertTrue(ctrl.is_active_mode())

        mw.current_mode = "maps"
        self.assertFalse(ctrl.is_active_mode())
        mw.current_mode = "players"

        mw.hero_ban_active = True
        self.assertFalse(ctrl.is_active_mode())
        mw.hero_ban_active = False

        mw.open_queue = DummyOpenQueue(True)
        self.assertFalse(ctrl.is_active_mode())


if __name__ == "__main__":
    unittest.main()
