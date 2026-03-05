import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from controller.ocr.ocr_import import (
    OCRRunResult,
    _build_easyocr_lang_groups,
    _parse_easyocr_langs,
    _normalize_easyocr_gpu_mode,
    _resolve_easyocr_device,
    clear_ocr_runtime_caches,
    easyocr_available,
    extract_candidate_names,
    extract_candidate_names_debug,
    extract_candidate_names_multi,
    run_easyocr,
    run_ocr_multi,
)


class TestOCRImport(unittest.TestCase):
    def test_build_easyocr_lang_groups_splits_cjk_and_general_langs(self):
        groups = _build_easyocr_lang_groups(("en", "de", "ja", "ch_sim", "ko"))
        self.assertEqual(
            groups,
            (
                ("en", "de"),
                ("ja", "en"),
                ("ch_sim", "en"),
                ("ko", "en"),
            ),
        )

    def test_parse_easyocr_langs_supports_de_ja_zh_ko(self):
        self.assertEqual(
            _parse_easyocr_langs("de,ja,zh,ko"),
            ("de", "ja", "ch_sim", "ko"),
        )

    def test_parse_easyocr_langs_supports_chinese_aliases(self):
        self.assertEqual(
            _parse_easyocr_langs("zh-tw,ch_tra,zh-cn"),
            ("ch_tra", "ch_sim"),
        )

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

    def test_extract_candidate_names_keeps_special_chars_when_constraint_disabled(self):
        text = "Witziger|Name2\nMogojyan (Lacie) Lover"
        self.assertEqual(
            extract_candidate_names(
                text,
                max_words=4,
                enforce_special_char_constraint=False,
            ),
            ["Witziger|Name2", "Mogojyan (Lacie) Lover"],
        )

    def test_extract_candidate_names_extracts_left_side_from_assignment_constants(self):
        text = (
            "MAP_PREBUILD_ON_START = False\n"
            "SOUND_WARMUP_ON_START = False\n"
            "TOOLTIP_CACHE_ON_START = False\n"
            "SOUND_WARMUP_LAZY_STEP_MS = 25\n"
        )
        self.assertEqual(
            extract_candidate_names(
                text,
                max_words=4,
                max_chars=24,
                enforce_special_char_constraint=False,
            ),
            [
                "MAP_PREBUILD_ON_START",
                "SOUND_WARMUP_ON_START",
                "TOOLTIP_CACHE_ON_START",
                "SOUND_WARMUP_LAZY_STEP_MS",
            ],
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

    def test_extract_candidate_names_trims_trailing_parenthetical_metadata(self):
        text = "Rontarou (Best Gojo Main)\nThe Bookseller (The Food lover)\nMogojyan The Lacie Lover"
        self.assertEqual(
            extract_candidate_names(text, max_words=4),
            ["Rontarou", "The Bookseller", "Mogojyan The Lacie Lover"],
        )

    def test_extract_candidate_names_trims_trailing_short_upper_noise_suffix(self):
        text = "The Bookseller TK\nRontarou\nAJ TK"
        self.assertEqual(
            extract_candidate_names(text, max_words=4),
            ["The Bookseller", "Rontarou", "AJ TK"],
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

    def test_extract_candidate_names_multi_keeps_numeric_suffix_names_from_same_text(self):
        texts = [
            "witzigerName\nwitzigerName2",
        ]
        self.assertEqual(
            extract_candidate_names_multi(
                texts,
                high_count_threshold=99,
                near_dup_min_chars=4,
                near_dup_max_len_delta=1,
                near_dup_similarity=0.9,
            ),
            ["witzigerName", "witzigerName2"],
        )

    def test_extract_candidate_names_multi_merges_numeric_suffix_variant_across_texts(self):
        texts = [
            "witzigerName",
            "witzigerName2",
        ]
        result = extract_candidate_names_multi(
            texts,
            high_count_threshold=99,
            near_dup_min_chars=4,
            near_dup_max_len_delta=1,
            near_dup_similarity=0.9,
        )
        self.assertEqual(len(result), 1)
        self.assertIn(result[0], {"witzigerName", "witzigerName2"})

    def test_extract_candidate_names_multi_merges_constant_prefix_truncation_variants(self):
        texts = [
            "MAP_PREBUILD_ON_ST",
            "MAP_PREBUILD_ON_START",
        ]
        self.assertEqual(
            extract_candidate_names_multi(
                texts,
                high_count_threshold=99,
            ),
            ["MAP_PREBUILD_ON_START"],
        )

    def test_extract_candidate_names_multi_prefers_longer_constant_variant_on_tie(self):
        texts = [
            "SOUND_WARMUP_LAZY_ST",
            "SOUND_WARMUP_LAZY_STEP_MS",
        ]
        self.assertEqual(
            extract_candidate_names_multi(
                texts,
                high_count_threshold=99,
            ),
            ["SOUND_WARMUP_LAZY_STEP_MS"],
        )

    def test_run_easyocr_groups_same_row_tokens_into_one_line(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            image_path = Path(tmp.name)

            class _Reader:
                device = "cpu"

                @staticmethod
                def readtext(_path, detail=1, paragraph=False):
                    _ = (detail, paragraph)
                    return [
                        (
                            [(10, 10), (60, 10), (60, 24), (10, 24)],
                            "Nummer",
                            0.94,
                        ),
                        (
                            [(70, 9), (118, 9), (118, 25), (70, 25)],
                            "sechs",
                            0.92,
                        ),
                        (
                            [(9, 44), (68, 44), (68, 60), (9, 60)],
                            "Massith",
                            0.89,
                        ),
                    ]

            with patch("controller.ocr.ocr_import._resolve_easyocr_reader", return_value=(_Reader(), None)):
                result = run_easyocr(image_path, quiet=True)

        self.assertIsNone(result.error)
        self.assertEqual([line.text for line in result.lines], ["Nummer sechs", "Massith"])
        self.assertEqual(result.text, "Nummer sechs\nMassith")

    def test_run_easyocr_dedupes_identical_grouped_lines(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            image_path = Path(tmp.name)

            class _Reader:
                device = "cpu"

                @staticmethod
                def readtext(_path, detail=1, paragraph=False):
                    _ = (detail, paragraph)
                    return [
                        (
                            [(10, 10), (66, 10), (66, 25), (10, 25)],
                            "Massith",
                            0.80,
                        ),
                        (
                            [(12, 11), (67, 11), (67, 26), (12, 26)],
                            "Massith",
                            0.93,
                        ),
                    ]

            with patch("controller.ocr.ocr_import._resolve_easyocr_reader", return_value=(_Reader(), None)):
                result = run_easyocr(image_path, quiet=True)

        self.assertIsNone(result.error)
        self.assertEqual([line.text for line in result.lines], ["Massith"])
        self.assertEqual(result.text, "Massith")

    def test_run_easyocr_prevents_cross_row_merge_on_tall_box_noise(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            image_path = Path(tmp.name)

            class _Reader:
                device = "cpu"

                @staticmethod
                def readtext(_path, detail=1, paragraph=False):
                    _ = (detail, paragraph)
                    return [
                        (
                            [(8, 10), (60, 10), (60, 44), (8, 44)],
                            "Alpha",
                            0.89,
                        ),
                        (
                            [(8, 48), (62, 48), (62, 62), (8, 62)],
                            "Bravo",
                            0.90,
                        ),
                    ]

            with patch("controller.ocr.ocr_import._resolve_easyocr_reader", return_value=(_Reader(), None)):
                result = run_easyocr(image_path, quiet=True)

        self.assertIsNone(result.error)
        self.assertEqual([line.text for line in result.lines], ["Alpha", "Bravo"])
        self.assertEqual(result.text, "Alpha\nBravo")

    def test_clear_ocr_runtime_caches_clears_cached_layers(self):
        with (
            patch("controller.ocr.ocr_import._cached_easyocr_reader.cache_clear") as easyocr_clear,
            patch("controller.ocr.ocr_import.gc.collect") as gc_collect,
        ):
            clear_ocr_runtime_caches(release_gpu=False)

        easyocr_clear.assert_called_once()
        gc_collect.assert_called_once()

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
        with patch("controller.ocr.ocr_import.run_easyocr", return_value=OCRRunResult("Aero")) as easy_mock:
            result = run_ocr_multi(Path("dummy.png"), engine="easyocr")
        self.assertEqual(result.text, "Aero")
        easy_mock.assert_called_once()

    def test_run_ocr_multi_dispatches_to_easyocr_by_default(self):
        with patch("controller.ocr.ocr_import.run_easyocr", return_value=OCRRunResult("Aero")) as easy_mock:
            result = run_ocr_multi(Path("dummy.png"))
        self.assertEqual(result.text, "Aero")
        easy_mock.assert_called_once()

    def test_gpu_mode_normalization(self):
        self.assertEqual(_normalize_easyocr_gpu_mode(False), "cpu")
        self.assertEqual(_normalize_easyocr_gpu_mode(True), "auto")
        self.assertEqual(_normalize_easyocr_gpu_mode("cpu"), "cpu")
        self.assertEqual(_normalize_easyocr_gpu_mode("mps"), "mps")
        self.assertEqual(_normalize_easyocr_gpu_mode("cuda"), "cuda")
        self.assertEqual(_normalize_easyocr_gpu_mode("auto"), "auto")
        self.assertEqual(_normalize_easyocr_gpu_mode("unexpected"), "auto")

    def test_resolve_easyocr_device_auto_prefers_accelerator(self):
        with patch("controller.ocr.ocr_import._torch_device_support", return_value=(False, False)):
            self.assertEqual(_resolve_easyocr_device("auto"), "cpu")
        with patch("controller.ocr.ocr_import._torch_device_support", return_value=(False, True)):
            self.assertEqual(_resolve_easyocr_device("auto"), "mps")
        with patch("controller.ocr.ocr_import._torch_device_support", return_value=(True, True)):
            self.assertEqual(_resolve_easyocr_device("auto"), "cuda")

    def test_run_ocr_multi_passes_gpu_mode_through(self):
        with patch("controller.ocr.ocr_import.run_easyocr", return_value=OCRRunResult("Aero")) as easy_mock:
            result = run_ocr_multi(Path("dummy.png"), easyocr_gpu="mps")
        self.assertEqual(result.text, "Aero")
        easy_mock.assert_called_once()
        kwargs = easy_mock.call_args.kwargs
        self.assertEqual(kwargs.get("gpu"), "mps")

    def test_easyocr_available_succeeds_with_split_lang_groups(self):
        called_langs: list[str] = []

        def _fake_resolve_reader(*, lang, model_dir, user_network_dir, gpu, download_enabled, quiet):
            _ = (model_dir, user_network_dir, gpu, download_enabled, quiet)
            called_langs.append(str(lang or ""))
            return object(), None

        with patch("controller.ocr.ocr_import._resolve_easyocr_reader", side_effect=_fake_resolve_reader):
            ok = easyocr_available(lang="en,de,ja,ch_sim,ko")

        self.assertTrue(ok)
        self.assertEqual(
            called_langs,
            ["en,de", "ja,en", "ch_sim,en", "ko,en"],
        )

    def test_easyocr_available_uses_english_fallback_when_group_model_is_missing(self):
        called_langs: list[str] = []

        def _fake_resolve_reader(*, lang, model_dir, user_network_dir, gpu, download_enabled, quiet):
            _ = (model_dir, user_network_dir, gpu, download_enabled, quiet)
            key = str(lang or "")
            called_langs.append(key)
            if key == "en,de":
                return None, "easyocr-init-error:Missing /tmp/latin_g2.pth and downloads disabled"
            if key == "en":
                return object(), None
            return None, "easyocr-init-error:unexpected"

        with patch("controller.ocr.ocr_import._resolve_easyocr_reader", side_effect=_fake_resolve_reader):
            ok = easyocr_available(lang="en,de", download_enabled=False)

        self.assertTrue(ok)
        self.assertEqual(called_langs, ["en,de", "en"])

    def test_run_easyocr_merges_results_from_split_lang_groups(self):
        class _Reader:
            def __init__(self, device: str, detections):
                self.device = device
                self._detections = list(detections or [])

            def readtext(self, *_args, **_kwargs):
                return list(self._detections)

        detection_alpha = (
            [(8, 10), (90, 10), (90, 28), (8, 28)],
            "Alpha",
            0.92,
        )
        detection_ja = (
            [(8, 40), (90, 40), (90, 58), (8, 58)],
            "ミカ",
            0.90,
        )

        def _fake_resolve_reader(*, lang, model_dir, user_network_dir, gpu, download_enabled, quiet):
            _ = (model_dir, user_network_dir, gpu, download_enabled, quiet)
            lang_key = str(lang or "")
            if lang_key == "en,de":
                return _Reader("cpu", [detection_alpha]), None
            if lang_key == "ja,en":
                return _Reader("cpu", [detection_ja]), None
            return _Reader("cpu", []), None

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "sample.png"
            image_path.write_bytes(b"stub")
            with patch("controller.ocr.ocr_import._resolve_easyocr_reader", side_effect=_fake_resolve_reader):
                result = run_easyocr(image_path, lang="en,de,ja")

        self.assertIsNone(result.error)
        self.assertIn("Alpha", [line.text for line in result.lines])
        self.assertIn("ミカ", [line.text for line in result.lines])

    def test_run_easyocr_uses_english_fallback_when_group_model_is_missing(self):
        class _Reader:
            device = "cpu"

            @staticmethod
            def readtext(_path, detail=1, paragraph=False):
                _ = (detail, paragraph)
                return [
                    (
                        [(8, 10), (90, 10), (90, 28), (8, 28)],
                        "Alpha",
                        0.92,
                    )
                ]

        def _fake_resolve_reader(*, lang, model_dir, user_network_dir, gpu, download_enabled, quiet):
            _ = (model_dir, user_network_dir, gpu, download_enabled, quiet)
            key = str(lang or "")
            if key == "en,de":
                return None, "easyocr-init-error:Missing /tmp/latin_g2.pth and downloads disabled"
            if key == "en":
                return _Reader(), None
            return None, "easyocr-init-error:unexpected"

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "sample.png"
            image_path.write_bytes(b"stub")
            with patch("controller.ocr.ocr_import._resolve_easyocr_reader", side_effect=_fake_resolve_reader):
                result = run_easyocr(image_path, lang="en,de", download_enabled=False)

        self.assertIsNone(result.error)
        self.assertEqual(result.text, "Alpha")

    def test_run_easyocr_prefers_primary_group_on_overlapping_tokens(self):
        class _Reader:
            def __init__(self, detections):
                self.device = "cpu"
                self._detections = list(detections)

            def readtext(self, *_args, **_kwargs):
                return list(self._detections)

        primary_detection = (
            [(10, 10), (120, 10), (120, 30), (10, 30)],
            "Mika",
            0.63,
        )
        secondary_detection = (
            [(11, 11), (121, 11), (121, 31), (11, 31)],
            "Mik4",
            0.95,
        )

        def _fake_resolve_reader(*, lang, model_dir, user_network_dir, gpu, download_enabled, quiet):
            _ = (model_dir, user_network_dir, gpu, download_enabled, quiet)
            key = str(lang or "")
            if key == "en,de":
                return _Reader([primary_detection]), None
            if key == "ja,en":
                return _Reader([secondary_detection]), None
            return _Reader([]), None

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "sample.png"
            image_path.write_bytes(b"stub")
            with patch("controller.ocr.ocr_import._resolve_easyocr_reader", side_effect=_fake_resolve_reader):
                result = run_easyocr(image_path, lang="en,de,ja")

        self.assertIsNone(result.error)
        self.assertEqual(result.text, "Mika")

    def test_run_easyocr_allows_secondary_to_replace_very_weak_primary_overlap(self):
        class _Reader:
            def __init__(self, detections):
                self.device = "cpu"
                self._detections = list(detections)

            def readtext(self, *_args, **_kwargs):
                return list(self._detections)

        primary_detection = (
            [(10, 10), (120, 10), (120, 30), (10, 30)],
            "Mik4",
            0.09,
        )
        secondary_detection = (
            [(11, 11), (121, 11), (121, 31), (11, 31)],
            "ミカ",
            0.82,
        )

        def _fake_resolve_reader(*, lang, model_dir, user_network_dir, gpu, download_enabled, quiet):
            _ = (model_dir, user_network_dir, gpu, download_enabled, quiet)
            key = str(lang or "")
            if key == "en,de":
                return _Reader([primary_detection]), None
            if key == "ja,en":
                return _Reader([secondary_detection]), None
            return _Reader([]), None

        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "sample.png"
            image_path.write_bytes(b"stub")
            with patch("controller.ocr.ocr_import._resolve_easyocr_reader", side_effect=_fake_resolve_reader):
                result = run_easyocr(image_path, lang="en,de,ja")

        self.assertIsNone(result.error)
        self.assertEqual(result.text, "ミカ")

    def test_run_easyocr_disables_pin_memory_patch_for_non_cuda_device(self):
        class _Reader:
            device = "mps"

            def readtext(self, *_args, **_kwargs):
                return []

        patch_calls: list[bool] = []

        @contextmanager
        def _fake_patch(enabled: bool):
            patch_calls.append(bool(enabled))
            yield

        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "sample.png"
            img.write_bytes(b"stub")
            with (
                patch("controller.ocr.ocr_import._resolve_easyocr_reader", return_value=(_Reader(), None)),
                patch("controller.ocr.ocr_import._patch_dataloader_pin_memory", side_effect=_fake_patch),
            ):
                result = run_easyocr(img)

        self.assertEqual(result.text, "")
        self.assertEqual(patch_calls, [True])

    def test_run_easyocr_keeps_pin_memory_patch_off_for_cuda_device(self):
        class _Reader:
            device = "cuda"

            def readtext(self, *_args, **_kwargs):
                return []

        patch_calls: list[bool] = []

        @contextmanager
        def _fake_patch(enabled: bool):
            patch_calls.append(bool(enabled))
            yield

        with tempfile.TemporaryDirectory() as tmp:
            img = Path(tmp) / "sample.png"
            img.write_bytes(b"stub")
            with (
                patch("controller.ocr.ocr_import._resolve_easyocr_reader", return_value=(_Reader(), None)),
                patch("controller.ocr.ocr_import._patch_dataloader_pin_memory", side_effect=_fake_patch),
            ):
                result = run_easyocr(img)

        self.assertEqual(result.text, "")
        self.assertEqual(patch_calls, [False])


if __name__ == "__main__":
    unittest.main()
