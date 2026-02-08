import unittest
from services.state_store import ModeStateStore
import config


class DummyBtn:
    def __init__(self, checked=True):
        self._checked = checked

    def isChecked(self):
        return self._checked


class DummyWheel:
    def __init__(self, entries, include=True, pair_mode=False, use_subroles=False):
        self._entries = entries
        self.btn_include_in_all = DummyBtn(include)
        self.pair_mode = pair_mode
        self.use_subrole_filter = use_subroles

    def get_current_entries(self):
        return self._entries


class TestStateStore(unittest.TestCase):
    def test_defaults_from_config(self):
        store = ModeStateStore.from_saved({})
        heroes = store.get_mode_state("heroes")
        self.assertTrue(heroes)
        self.assertEqual(
            len(heroes["Damage"]["entries"]), len(config.DEFAULT_HEROES["Damage"])
        )

    def test_capture_mode_from_wheels(self):
        store = ModeStateStore.from_saved({})
        wheels = {
            "Tank": DummyWheel([{"name": "Rein", "active": True, "subroles": []}], include=False),
            "Damage": DummyWheel([{"name": "Echo", "active": True, "subroles": []}], pair_mode=True),
            "Support": DummyWheel([{"name": "Ana", "active": True, "subroles": []}], use_subroles=True),
        }
        store.capture_mode_from_wheels("players", wheels, hero_ban_active=False)
        players = store.get_mode_state("players")
        self.assertFalse(players["Tank"]["include_in_all"])
        self.assertTrue(players["Damage"]["pair_mode"])
        self.assertTrue(players["Support"]["use_subroles"])
        self.assertEqual(players["Damage"]["entries"][0]["name"], "Echo")

    def test_to_saved_structure(self):
        store = ModeStateStore.from_saved({})
        saved = store.to_saved(volume=42)
        self.assertIn("players", saved)
        self.assertIn("heroes", saved)
        self.assertEqual(saved["volume"], 42)

    def test_normalize_entries_filters_invalid_rows(self):
        entries = ModeStateStore._normalize_entries_for_state(
            [
                "  Rein  ",
                "",
                {"name": " Ana ", "subroles": ["MS", "", " FS "], "active": 1},
                {"name": "   "},
                {"name": "Lucio", "subroles": "invalid"},
            ]
        )
        self.assertEqual(
            entries,
            [
                {"name": "Rein", "subroles": [], "active": True},
                {"name": "Ana", "subroles": ["MS", " FS "], "active": True},
                {"name": "Lucio", "subroles": [], "active": True},
            ],
        )

    def test_legacy_root_role_structure_is_migrated(self):
        saved = {
            "Tank": {"names": ["Ramattra"]},
            "Damage": {"entries": [{"name": "Echo", "active": True}]},
            "Support": {"names": ["Ana"]},
        }
        store = ModeStateStore.from_saved(saved)
        players = store.get_mode_state("players")
        self.assertEqual([e["name"] for e in players["Tank"]["entries"]], ["Ramattra"])
        self.assertEqual([e["name"] for e in players["Damage"]["entries"]], ["Echo"])
        self.assertEqual([e["name"] for e in players["Support"]["entries"]], ["Ana"])

    def test_players_guard_resets_if_hero_defaults_accidentally_saved(self):
        saved = {
            "players": {
                "Damage": {
                    "entries": [
                        {"name": name, "active": True, "subroles": []}
                        for name in config.DEFAULT_HEROES["Damage"]
                    ]
                }
            }
        }
        store = ModeStateStore.from_saved(saved)
        players_damage = store.get_mode_state("players")["Damage"]["entries"]
        self.assertEqual(
            [e["name"] for e in players_damage],
            list(config.DEFAULT_NAMES["Damage"]),
        )

    def test_map_include_defaults_from_config(self):
        store = ModeStateStore.from_saved({})
        maps = store.get_mode_state("maps")
        self.assertTrue(maps["Control"]["include_in_all"])
        self.assertFalse(maps["Assault"]["include_in_all"])
        self.assertFalse(maps["Clash"]["include_in_all"])

    def test_capture_mode_hero_ban_keeps_pair_and_subroles_from_base_state(self):
        store = ModeStateStore.from_saved({})
        base = store.get_mode_state("heroes")
        base["Tank"]["pair_mode"] = True
        base["Tank"]["use_subroles"] = True
        store.set_mode_state("heroes", base)
        wheels = {
            "Tank": DummyWheel([{"name": "Rein", "active": True, "subroles": []}], pair_mode=False, use_subroles=False),
            "Damage": DummyWheel([{"name": "Echo", "active": True, "subroles": []}], pair_mode=False, use_subroles=False),
            "Support": DummyWheel([{"name": "Ana", "active": True, "subroles": []}], pair_mode=False, use_subroles=False),
        }
        store.capture_mode_from_wheels("heroes", wheels, hero_ban_active=True)
        heroes = store.get_mode_state("heroes")
        self.assertTrue(heroes["Tank"]["pair_mode"])
        self.assertTrue(heroes["Tank"]["use_subroles"])
        self.assertEqual(heroes["Tank"]["entries"][0]["name"], "Rein")


if __name__ == "__main__":
    unittest.main()
