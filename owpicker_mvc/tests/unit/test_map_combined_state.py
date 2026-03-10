import unittest

from controller.map.combined_state import (
    build_override_entries,
    collect_combined_active_names,
)


class _CheckBox:
    def __init__(self, checked: bool):
        self._checked = bool(checked)

    def isChecked(self) -> bool:
        return self._checked


class _Wheel:
    def __init__(self, checked: bool, entries: list[dict]):
        self.btn_include_in_all = _CheckBox(checked)
        self._entries = list(entries)

    def get_active_entries(self):
        return list(self._entries)


class TestMapCombinedState(unittest.TestCase):
    def test_collect_combined_active_names_skips_unchecked_lists(self):
        wheels = {
            "Control": _Wheel(True, [{"name": "Ilios"}, {"name": "  "}]),
            "Escort": _Wheel(False, [{"name": "Dorado"}]),
            "Hybrid": _Wheel(True, [{"name": "King's Row"}]),
        }
        self.assertEqual(
            collect_combined_active_names(wheels),
            ["Ilios", "King's Row"],
        )

    def test_build_override_entries_marks_all_active_without_subroles(self):
        entries = build_override_entries(["Ilios", "Numbani"])
        self.assertEqual(
            entries,
            [
                {"name": "Ilios", "subroles": [], "active": True},
                {"name": "Numbani", "subroles": [], "active": True},
            ],
        )


if __name__ == "__main__":
    unittest.main()

