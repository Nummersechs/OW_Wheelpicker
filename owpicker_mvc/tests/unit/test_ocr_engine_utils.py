import unittest

from controller.ocr import ocr_import
from controller.ocr.ocr_engine_utils import _extract_names_from_texts


def _base_cfg() -> dict:
    return {
        "name_min_chars": 2,
        "name_max_chars": 24,
        "name_max_words": 2,
        "name_max_digit_ratio": 0.45,
        "name_special_char_constraint": True,
        "name_min_support": 1,
        "name_high_count_threshold": 8,
        "name_high_count_min_support": 2,
        "name_max_candidates": 12,
        "name_near_dup_min_chars": 8,
        "name_near_dup_max_len_delta": 1,
        "name_near_dup_similarity": 0.90,
        "name_near_dup_tail_min_chars": 3,
        "name_near_dup_tail_head_similarity": 0.70,
        "single_name_per_line": False,
        "line_recall_max_additions": 2,
    }


class TestOCREngineUtils(unittest.TestCase):
    def test_extract_names_from_texts_dense_line_fallback(self):
        cfg = _base_cfg()
        texts = ["Alpha Bravo Charlie Delta Echo Foxtrot"]
        names = _extract_names_from_texts(ocr_import, texts, cfg)

        self.assertIn("Alpha", names)
        self.assertIn("Bravo", names)
        self.assertGreaterEqual(len(names), 4)

    def test_extract_names_from_texts_keeps_regular_line_behavior(self):
        cfg = _base_cfg()
        texts = ["Alpha Bravo"]
        names = _extract_names_from_texts(ocr_import, texts, cfg)
        self.assertEqual(names, ["Alpha Bravo"])


if __name__ == "__main__":
    unittest.main()
