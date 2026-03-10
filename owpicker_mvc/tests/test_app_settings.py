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
                "DEFAULT_LANGUAGE": "DE",
                "SPIN_WATCHDOG_ENABLED": "1",
            }
        )

        self.assertEqual(settings.resolve("QUIET", False), True)
        self.assertEqual(settings.resolve("NETWORK_SYNC_WORKERS", 99), 1)
        self.assertEqual(settings.resolve("DEFAULT_DURATION_MS", 0), 1000)
        self.assertEqual(settings.resolve("DEFAULT_LANGUAGE", "en"), "de")
        self.assertEqual(settings.resolve("SPIN_WATCHDOG_ENABLED", False), True)

    def test_update_rebuilds_sections(self):
        settings = AppSettings(values={"QUIET": False, "OCR_ENGINE": "easyocr"})
        self.assertEqual(settings.runtime.quiet, False)
        self.assertEqual(settings.ocr.engine, "easyocr")

        settings.update({"QUIET": "1", "OCR_ENGINE": " EASYOCR "})

        self.assertEqual(settings.runtime.quiet, True)
        self.assertEqual(settings.ocr.engine, "EASYOCR")

    def test_shutdown_section_exposes_thread_and_defer_controls(self):
        settings = AppSettings(
            values={
                "SHUTDOWN_OCR_PRELOAD_GRACEFUL_WAIT_MS": "1600",
                "SHUTDOWN_OCR_PRELOAD_TERMINATE_WAIT_MS": "250",
                "SHUTDOWN_THREAD_MAX_DEFER_MS": "3300",
                "SHUTDOWN_OCR_PRELOAD_FORCE_STOP_ON_CLOSE": "1",
                "SHUTDOWN_APP_FORCE_EXIT_LOOP_MS": "1900",
            }
        )

        self.assertEqual(settings.shutdown.ocr_preload_graceful_wait_ms, 1600)
        self.assertEqual(settings.shutdown.ocr_preload_terminate_wait_ms, 250)
        self.assertEqual(settings.shutdown.thread_max_defer_ms, 3300)
        self.assertEqual(settings.shutdown.ocr_preload_force_stop_on_close, True)
        self.assertEqual(settings.shutdown.app_force_exit_loop_ms, 1900)
        self.assertEqual(settings.resolve("SHUTDOWN_THREAD_MAX_DEFER_MS", 0), 3300)

    def test_ocr_section_exposes_preload_and_cache_controls(self):
        settings = AppSettings(
            values={
                "OCR_EASYOCR_GPU": "cpu",
                "OCR_PRELOAD_INPROCESS_CACHE_WARMUP": "0",
                "OCR_BACKGROUND_PRELOAD_BUSY_RETRY_MS": "2100",
                "OCR_IDLE_CACHE_RELEASE_MS": "12000",
                "OCR_RELEASE_CACHE_ON_SPIN": "true",
            }
        )

        self.assertEqual(settings.ocr.easyocr_gpu, "cpu")
        self.assertEqual(settings.ocr.preload_inprocess_cache_warmup, False)
        self.assertEqual(settings.ocr.background_preload_busy_retry_ms, 2100)
        self.assertEqual(settings.ocr.idle_cache_release_ms, 12000)
        self.assertEqual(settings.ocr.release_cache_on_spin, True)
        self.assertEqual(settings.resolve("OCR_IDLE_CACHE_RELEASE_MS", 0), 12000)

    def test_startup_section_exposes_online_choice_flag(self):
        settings = AppSettings(values={"MODE_CHOICE_ONLINE_ENABLED": "1"})

        self.assertEqual(settings.startup.mode_choice_online_enabled, True)
        self.assertEqual(settings.resolve("MODE_CHOICE_ONLINE_ENABLED", False), True)


if __name__ == "__main__":
    unittest.main()
