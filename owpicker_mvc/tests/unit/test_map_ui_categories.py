import unittest

from controller.map.categories import (
    build_map_type_rebuild_payload,
    normalize_map_categories,
    unique_non_empty_labels,
)


def _default_state() -> dict:
    return {"entries": [], "pair_mode": False, "use_subroles": False}


class TestMapUICategories(unittest.TestCase):
    def test_normalize_map_categories_casefold_dedupes_and_strips(self):
        categories = normalize_map_categories(" Control, escort ,CONTROL, , Push ")
        self.assertEqual(categories, ["Control", "escort", "Push"])

    def test_unique_non_empty_labels_preserves_order(self):
        labels = unique_non_empty_labels([" Control ", "", "Escort", "Control", "  "])
        self.assertEqual(labels, ["Control", "Escort"])

    def test_build_rebuild_payload_prefers_current_then_saved_then_index_then_default(self):
        new_types = ["Control", "Hybrid", "Clash", "Flashpoint"]
        current_states = {
            "Control": {"entries": [{"name": "A"}]},
            "Escort": {"entries": [{"name": "B"}]},
        }
        include_map = {"Control": False, "Escort": True}
        saved_state = {
            "Hybrid": {"entries": [{"name": "C"}]},
            "Push": {"entries": [{"name": "D"}]},
        }
        old_categories = ["Control", "Escort", "Push", "Assault"]

        new_state, new_include = build_map_type_rebuild_payload(
            new_types=new_types,
            current_states=current_states,
            include_map=include_map,
            saved_state=saved_state,
            old_categories=old_categories,
            default_role_state_factory=_default_state,
        )

        self.assertEqual(new_state["Control"], {"entries": [{"name": "A"}]})
        self.assertEqual(new_include["Control"], False)

        self.assertEqual(new_state["Hybrid"], {"entries": [{"name": "C"}]})
        self.assertEqual(new_include["Hybrid"], True)

        self.assertEqual(new_state["Clash"], {"entries": [{"name": "D"}]})
        self.assertEqual(new_include["Clash"], True)

        self.assertEqual(new_state["Flashpoint"], _default_state())
        self.assertEqual(new_include["Flashpoint"], True)


if __name__ == "__main__":
    unittest.main()
