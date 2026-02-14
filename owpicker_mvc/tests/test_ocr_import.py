import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller.ocr_import import (
    OCRRunResult,
    extract_candidate_names,
    extract_candidate_names_debug,
    extract_candidate_names_multi,
    resolve_tesseract_cmd,
    resolve_tessdata_dir,
    run_ocr_multi,
)


class TestOCRImport(unittest.TestCase):
    def setUp(self):
        resolve_tesseract_cmd.cache_clear()
        resolve_tessdata_dir.cache_clear()

    def tearDown(self):
        resolve_tesseract_cmd.cache_clear()
        resolve_tessdata_dir.cache_clear()

    @staticmethod
    def _platform_tesseract_name() -> str:
        return "tesseract.exe" if sys.platform == "win32" else "tesseract"

    def test_resolve_tesseract_cmd_finds_bundled_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe_name = self._platform_tesseract_name()
            bundled_cmd = root / "OCR" / exe_name
            bundled_cmd.parent.mkdir(parents=True, exist_ok=True)
            bundled_cmd.write_text("stub", encoding="utf-8")
            with (
                patch("controller.ocr_import.shutil.which", return_value=None),
                patch("controller.ocr_import._runtime_search_roots", return_value=[root]),
            ):
                resolved = resolve_tesseract_cmd("tesseract")
            self.assertEqual(resolved, str(bundled_cmd))

    def test_resolve_tesseract_cmd_auto_prefers_bundled_over_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe_name = self._platform_tesseract_name()
            bundled_cmd = root / "OCR" / exe_name
            bundled_cmd.parent.mkdir(parents=True, exist_ok=True)
            bundled_cmd.write_text("stub", encoding="utf-8")
            with (
                patch("controller.ocr_import.shutil.which", return_value="/usr/bin/tesseract"),
                patch("controller.ocr_import._runtime_search_roots", return_value=[root]),
            ):
                resolved = resolve_tesseract_cmd("auto")
            self.assertEqual(resolved, str(bundled_cmd))

    def test_resolve_tesseract_cmd_manual_prefers_path_before_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe_name = self._platform_tesseract_name()
            bundled_cmd = root / "OCR" / exe_name
            bundled_cmd.parent.mkdir(parents=True, exist_ok=True)
            bundled_cmd.write_text("stub", encoding="utf-8")
            with (
                patch("controller.ocr_import.shutil.which", return_value="/usr/bin/tesseract"),
                patch("controller.ocr_import._runtime_search_roots", return_value=[root]),
            ):
                resolved = resolve_tesseract_cmd("tesseract")
            self.assertEqual(resolved, "/usr/bin/tesseract")

    def test_resolve_tesseract_cmd_finds_nested_bundled_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe_name = self._platform_tesseract_name()
            bundled_cmd = root / "OCR" / "Tesseract-OCR" / "bin" / exe_name
            bundled_cmd.parent.mkdir(parents=True, exist_ok=True)
            bundled_cmd.write_text("stub", encoding="utf-8")
            with (
                patch("controller.ocr_import.shutil.which", return_value=None),
                patch("controller.ocr_import._runtime_search_roots", return_value=[root]),
            ):
                resolved = resolve_tesseract_cmd("tesseract")
            self.assertEqual(resolved, str(bundled_cmd))

    def test_resolve_tessdata_dir_finds_bundled_traineddata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exe_name = self._platform_tesseract_name()
            bundled_cmd = root / "OCR" / exe_name
            bundled_cmd.parent.mkdir(parents=True, exist_ok=True)
            bundled_cmd.write_text("stub", encoding="utf-8")
            tessdata = root / "OCR" / "tessdata"
            tessdata.mkdir(parents=True, exist_ok=True)
            (tessdata / "eng.traineddata").write_text("stub", encoding="utf-8")
            with (
                patch("controller.ocr_import.shutil.which", return_value=None),
                patch("controller.ocr_import._runtime_search_roots", return_value=[root]),
            ):
                resolved = resolve_tessdata_dir("tesseract")
            self.assertEqual(resolved, str(tessdata))

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

    def test_extract_candidate_names_is_line_based_and_ignores_pipe_suffix(self):
        text = "CoMaE, DenMuchel | Massith; Pledoras\nAlpha | Beta\nGamma"
        self.assertEqual(
            extract_candidate_names(text),
            ["CoMaE DenMuchel", "Alpha", "Gamma"],
        )

    def test_extract_candidate_names_ignores_pipe_like_suffix_variants(self):
        text = "Massith ¦ Marc みのり\nMika ｜ Moonbrew\nAero │ AJAR"
        self.assertEqual(
            extract_candidate_names(text),
            ["Massith", "Mika", "Aero"],
        )

    def test_extract_candidate_names_ignores_misread_separator_token(self):
        text = "Massith I Marc みのり\nMika l Moonbrew\nAero 1 AJAR"
        self.assertEqual(
            extract_candidate_names(text),
            ["Massith", "Mika", "Aero"],
        )

    def test_extract_candidate_names_ignores_lower_i_separator_token(self):
        text = "NIKCOS i MNKE\nMassie i Marc"
        self.assertEqual(
            extract_candidate_names(text),
            ["NIKCOS", "Massie"],
        )

    def test_extract_candidate_names_ignores_punctuation_prefixed_separator_token(self):
        text = "Massie (arc i ak\nMiliu <Mowihrew @ Ao"
        self.assertEqual(
            extract_candidate_names(text),
            ["Massie", "Miliu"],
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

    def test_extract_candidate_names_keeps_cjk_scripts(self):
        text = "山田太郎\n张三\n김민수"
        self.assertEqual(
            extract_candidate_names(text),
            ["山田太郎", "张三", "김민수"],
        )

    def test_extract_candidate_names_ignores_emoji_and_icons(self):
        text = "Massith 💗 Moonbrew\nAero 😊\n😀 HiddenName\n🛡️"
        self.assertEqual(
            extract_candidate_names(text),
            ["Massith", "Aero"],
        )

    def test_extract_candidate_names_drops_icon_prefixed_short_upper_tokens(self):
        text = "@ MNKE\n® AJAR\nAero\nMassith"
        self.assertEqual(
            extract_candidate_names(text),
            ["Aero", "Massith"],
        )

    def test_extract_candidate_names_debug_reports_line_reasons(self):
        text = "Massith | Marc みのり\n😀 HiddenName\nAero\nAero\n1) 123456"
        names, line_debug = extract_candidate_names_debug(text)
        self.assertEqual(names, ["Massith", "Aero"])
        self.assertEqual(len(line_debug), 5)

        statuses = [str(entry.get("status", "")) for entry in line_debug]
        reasons = [str(entry.get("reason", "")) for entry in line_debug]
        accepted = [str(entry.get("candidate", "")) for entry in line_debug if entry.get("status") == "accepted"]

        self.assertEqual(statuses.count("accepted"), 2)
        self.assertIn("Massith", accepted)
        self.assertIn("Aero", accepted)
        self.assertIn("empty-after-metadata-trim", reasons)
        self.assertIn("duplicate-key", reasons)
        self.assertIn("failed-name-heuristics", reasons)

    def test_extract_candidate_names_deduplicates_spacing_and_dash_variants(self):
        text = "Nummersechs\nNummer sechs\nNUMMER-SECHS"
        self.assertEqual(
            extract_candidate_names(text),
            ["Nummersechs"],
        )

    def test_extract_candidate_names_filters_invalid_noise(self):
        text = """
        abcdefghijklmnopqrstuvwxyz
        123456
        12ab34cd56
        RealName
        """
        self.assertEqual(
            extract_candidate_names(
                text,
                max_chars=24,
                max_digit_ratio=0.45,
            ),
            ["RealName"],
        )

    def test_extract_candidate_names_filters_short_lowercase_noise(self):
        text = "cn\nal\nwl\nit\nly\nBC\nAJ\nPw"
        self.assertEqual(
            extract_candidate_names(text),
            ["BC", "AJ"],
        )

    def test_extract_candidate_names_multi_raises_support_floor_for_large_sets(self):
        texts = [
            "Alpha\nBravo\nCharlie\nDelta\nEcho\nFoxtrot",
            "Alpha\nBravo\nGolf\nHotel\nIndia",
            "Alpha\nBravo\nJuliet\nKilo",
        ]
        self.assertEqual(
            extract_candidate_names_multi(
                texts,
                high_count_threshold=8,
                high_count_min_support=2,
            ),
            ["Alpha", "Bravo"],
        )

    def test_extract_candidate_names_multi_honors_max_candidates(self):
        texts = [
            "Alpha\nBravo\nCharlie",
            "Alpha\nBravo",
            "Alpha\nDelta",
        ]
        self.assertEqual(
            extract_candidate_names_multi(
                texts,
                high_count_threshold=99,
                max_candidates=2,
            ),
            ["Alpha", "Bravo"],
        )

    def test_extract_candidate_names_multi_merges_near_duplicate_variants(self):
        texts = [
            "HIKEOS MNKE",
            "NIKEOS MNKE",
        ]
        self.assertEqual(
            extract_candidate_names_multi(
                texts,
                high_count_threshold=99,
                near_dup_min_chars=6,
                near_dup_max_len_delta=1,
                near_dup_similarity=0.9,
            ),
            ["HIKEOS MNKE"],
        )

    def test_extract_candidate_names_multi_merges_same_tail_with_noisy_head(self):
        texts = [
            "HIKEOS MNKE",
            "N1KEOS MNKE",
        ]
        self.assertEqual(
            extract_candidate_names_multi(
                texts,
                high_count_threshold=99,
                near_dup_min_chars=6,
                near_dup_max_len_delta=1,
                near_dup_similarity=0.9,
                near_dup_tail_min_chars=3,
                near_dup_tail_head_similarity=0.7,
            ),
            ["HIKEOS MNKE"],
        )

    def test_extract_candidate_names_multi_falls_back_if_support_filter_would_be_empty(self):
        texts = ["Alpha", "Bravo"]
        self.assertEqual(
            extract_candidate_names_multi(
                texts,
                min_support=3,
                high_count_threshold=99,
            ),
            ["Alpha", "Bravo"],
        )

    def test_run_ocr_multi_dispatches_to_easyocr(self):
        with (
            patch("controller.ocr_import.run_easyocr", return_value=OCRRunResult("Aero")) as easy_mock,
            patch("controller.ocr_import.run_tesseract_multi") as tess_mock,
        ):
            result = run_ocr_multi(Path("dummy.png"), engine="easyocr")
        self.assertEqual(result.text, "Aero")
        easy_mock.assert_called_once()
        tess_mock.assert_not_called()

    def test_run_ocr_multi_dispatches_to_easyocr_by_default(self):
        with (
            patch("controller.ocr_import.run_tesseract_multi") as tess_mock,
            patch("controller.ocr_import.run_easyocr", return_value=OCRRunResult("Aero")) as easy_mock,
        ):
            result = run_ocr_multi(Path("dummy.png"))
        self.assertEqual(result.text, "Aero")
        easy_mock.assert_called_once()
        tess_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
