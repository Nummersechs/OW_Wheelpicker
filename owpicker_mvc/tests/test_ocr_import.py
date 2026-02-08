import unittest

from controller.ocr_import import extract_candidate_names


class TestOCRImport(unittest.TestCase):
    def test_extract_candidate_names_normalizes_and_deduplicates(self):
        text = """
        1) Nummersechs
        - blue
        • Tillinski
        nummersechs
        """
        self.assertEqual(
            extract_candidate_names(text),
            ["Nummersechs", "blue", "Tillinski"],
        )

    def test_extract_candidate_names_splits_common_separators(self):
        text = "CoMaE, DenMuchel | Massith; Pledoras"
        self.assertEqual(
            extract_candidate_names(text),
            ["CoMaE", "DenMuchel", "Massith", "Pledoras"],
        )

    def test_extract_candidate_names_respects_min_length(self):
        text = "A\nBC\nD\nEF"
        self.assertEqual(extract_candidate_names(text, min_chars=2), ["BC", "EF"])

    def test_extract_candidate_names_keeps_unicode_letters(self):
        text = "Müller\nÜbertank\nMuller"
        self.assertEqual(
            extract_candidate_names(text),
            ["Müller", "Übertank", "Muller"],
        )


if __name__ == "__main__":
    unittest.main()
