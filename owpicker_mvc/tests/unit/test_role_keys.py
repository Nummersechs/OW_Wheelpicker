from __future__ import annotations

import unittest

from model.role_keys import ROLE_KEYS, role_for_wheel, role_wheel_map, role_wheels


class _DummyMainWindow:
    def __init__(self):
        self.tank = object()
        self.dps = object()
        self.support = object()


class TestRoleKeys(unittest.TestCase):
    def test_role_wheels_order_matches_role_keys(self):
        mw = _DummyMainWindow()
        roles = [role for role, _wheel in role_wheels(mw)]
        self.assertEqual(roles, list(ROLE_KEYS))

    def test_role_wheel_map_contains_all_roles(self):
        mw = _DummyMainWindow()
        mapping = role_wheel_map(mw)
        self.assertEqual(set(mapping.keys()), set(ROLE_KEYS))

    def test_role_for_wheel_returns_expected_role(self):
        mw = _DummyMainWindow()
        self.assertEqual(role_for_wheel(mw, mw.tank), "Tank")
        self.assertEqual(role_for_wheel(mw, mw.dps), "Damage")
        self.assertEqual(role_for_wheel(mw, mw.support), "Support")
        self.assertIsNone(role_for_wheel(mw, object()))


if __name__ == "__main__":
    unittest.main()
