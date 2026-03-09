import types
import unittest

from services.app_settings import AppSettings


class TestAppSettings(unittest.TestCase):
    def test_from_module_uses_only_uppercase_keys(self):
        module = types.SimpleNamespace(
            DEBUG=True,
            TRACE_FLOW=False,
            lower_value=123,
            MixedCase="ignored",
        )

        settings = AppSettings.from_module(module)

        self.assertEqual(settings.get("DEBUG"), True)
        self.assertEqual(settings.get("TRACE_FLOW"), False)
        self.assertIsNone(settings.get("lower_value"))
        self.assertIsNone(settings.get("MixedCase"))

    def test_from_module_handles_none(self):
        settings = AppSettings.from_module(None)
        self.assertEqual(settings.values, {})

    def test_int_and_float_fallbacks(self):
        settings = AppSettings(
            values={
                "INT_OK": "7",
                "INT_BAD": "abc",
                "FLOAT_OK": "2.5",
                "FLOAT_BAD": object(),
            }
        )

        self.assertEqual(settings.int("INT_OK", 1), 7)
        self.assertEqual(settings.int("INT_BAD", 11), 11)
        self.assertAlmostEqual(settings.float("FLOAT_OK", 1.0), 2.5)
        self.assertAlmostEqual(settings.float("FLOAT_BAD", 9.0), 9.0)

    def test_resolve_prefers_typed_values_and_normalizes(self):
        settings = AppSettings(
            values={
                "QUIET": "true",
                "NETWORK_SYNC_WORKERS": "0",
                "DEFAULT_DURATION_MS": "999999",
                "MIN_DURATION_MS": "100",
                "MAX_DURATION_MS": "1000",
            }
        )

        self.assertEqual(settings.resolve("QUIET", False), True)
        self.assertEqual(settings.resolve("NETWORK_SYNC_WORKERS", 99), 1)
        self.assertEqual(settings.resolve("DEFAULT_DURATION_MS", 0), 1000)

    def test_update_rebuilds_sections(self):
        settings = AppSettings(values={"QUIET": False, "OCR_ENGINE": "easyocr"})
        self.assertEqual(settings.runtime.quiet, False)
        self.assertEqual(settings.ocr.engine, "easyocr")

        settings.update({"QUIET": "1", "OCR_ENGINE": " EASYOCR "})

        self.assertEqual(settings.runtime.quiet, True)
        self.assertEqual(settings.ocr.engine, "EASYOCR")


if __name__ == "__main__":
    unittest.main()
