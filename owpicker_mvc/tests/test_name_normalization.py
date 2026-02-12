from __future__ import annotations

import unittest

from logic.name_normalization import (
    normalize_name_alnum_key,
    normalize_name_casefold,
    normalize_name_tokens,
)


class TestNameNormalization(unittest.TestCase):
    def test_normalize_name_casefold_trims_and_nfkc_normalizes(self):
        self.assertEqual(normalize_name_casefold("  Alpha  "), "alpha")
        self.assertEqual(normalize_name_casefold("ＡＢＣ"), "abc")
        self.assertEqual(normalize_name_casefold(""), "")

    def test_normalize_name_alnum_key_prefers_alnum_only(self):
        self.assertEqual(normalize_name_alnum_key("Nummer sechs"), "nummersechs")
        self.assertEqual(normalize_name_alnum_key("NUMMER-SECHS"), "nummersechs")
        self.assertEqual(normalize_name_alnum_key("   "), "")

    def test_normalize_name_tokens_splits_on_spaces_after_normalization(self):
        self.assertEqual(normalize_name_tokens(" HIKEOS   MNKE "), ["hikeos", "mnke"])
        self.assertEqual(normalize_name_tokens("Ａ Ｂ"), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
