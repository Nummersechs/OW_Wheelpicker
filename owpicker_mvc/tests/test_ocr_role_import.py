import unittest

from controller.ocr_role_import import (
    add_names,
    collect_new_names,
    normalize_name_key,
    resolve_selected_candidates,
)


class TestOCRRoleImport(unittest.TestCase):
    def test_normalize_name_key_casefolds_and_trims(self):
        self.assertEqual(normalize_name_key("  Alpha  "), "alpha")
        self.assertEqual(normalize_name_key(""), "")

    def test_collect_new_names_excludes_existing_and_duplicates(self):
        existing = ["Alpha", "Bravo"]
        raw = [" alpha ", "Charlie", "charlie", "Delta", "", "  "]
        self.assertEqual(collect_new_names(existing, raw), ["Charlie", "Delta"])

    def test_resolve_selected_candidates_preserves_pending_order(self):
        pending = ["Alpha", "Bravo", "Charlie", "Bravo"]
        selected = ["charlie", "alpha", "ALPHA"]
        self.assertEqual(resolve_selected_candidates(pending, selected), ["Alpha", "Charlie"])

    def test_resolve_selected_candidates_preserves_duplicate_counts(self):
        pending = ["Alpha", "Alpha", "Bravo", "Alpha"]
        selected = ["alpha", "ALPHA"]
        self.assertEqual(resolve_selected_candidates(pending, selected), ["Alpha", "Alpha"])

    def test_add_names_counts_successful_adds(self):
        added_names = []

        def _add_name(value: str) -> bool:
            if value in {"Alpha", "Charlie"}:
                added_names.append(value)
                return True
            return False

        count = add_names(_add_name, ["Alpha", "Bravo", " ", "Charlie"])
        self.assertEqual(count, 2)
        self.assertEqual(added_names, ["Alpha", "Charlie"])


if __name__ == "__main__":
    unittest.main()
