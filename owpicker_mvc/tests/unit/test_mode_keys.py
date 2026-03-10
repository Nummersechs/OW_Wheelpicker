from __future__ import annotations

import unittest

from model.mode_keys import AppMode, is_role_mode, normalize_mode


class TestModeKeys(unittest.TestCase):
    def test_normalize_mode_accepts_enum_and_string(self):
        self.assertEqual(normalize_mode(AppMode.PLAYERS), AppMode.PLAYERS.value)
        self.assertEqual(normalize_mode("HEROES"), AppMode.HEROES.value)
        self.assertEqual(normalize_mode("maps"), AppMode.MAPS.value)

    def test_normalize_mode_falls_back_for_unknown(self):
        self.assertEqual(normalize_mode("unknown"), AppMode.PLAYERS.value)
        self.assertEqual(normalize_mode(None, default=AppMode.HERO_BAN), AppMode.HERO_BAN.value)

    def test_is_role_mode(self):
        self.assertTrue(is_role_mode("players"))
        self.assertTrue(is_role_mode("heroes"))
        self.assertFalse(is_role_mode("maps"))
        self.assertFalse(is_role_mode("hero_ban"))


if __name__ == "__main__":
    unittest.main()

