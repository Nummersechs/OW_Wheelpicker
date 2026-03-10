from __future__ import annotations

from pathlib import Path
import sys
import time

from PySide6 import QtCore

from model.main_window_runtime_state import OCRPreloadPhase

_OCR_PRELOAD_COORDINATOR_GUARD_ERRORS = (
    AttributeError,
    RuntimeError,
    RecursionError,
    TypeError,
    ValueError,
    LookupError,
    OSError,
    ImportError,
)


class OCRPreloadCoordinator:
    def __init__(self, mw: object, *, worker_cls: type, relay_cls: type) -> None:
        self._mw = mw
        self._worker_cls = worker_cls
        self._relay_cls = relay_cls

    def _cfg(self, key: str, default=None):
        getter = getattr(self._mw, "_cfg", None)
        if callable(getter):
            try:
                return getter(key, default)
            except (TypeError, ValueError):
                return default
        return default

    def _settings(self):
        mw = self._mw
        try:
            return object.__getattribute__(mw, "settings")
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            pass
        try:
            namespace = object.__getattribute__(mw, "__dict__")
            if isinstance(namespace, dict):
                return namespace.get("settings")
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            pass
        return None

    def _runtime_settings(self):
        settings = self._settings()
        return getattr(settings, "runtime", None)

    def _startup_settings(self):
        settings = self._settings()
        return getattr(settings, "startup", None)

    def _ocr_settings(self):
        settings = self._settings()
        return getattr(settings, "ocr", None)

    def _runtime_bool(self, attr: str, key: str, default: bool) -> bool:
        section = self._runtime_settings()
        if section is not None and hasattr(section, attr):
            try:
                return bool(getattr(section, attr))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg(key, default))

    def _ocr_bool(self, attr: str, key: str, default: bool) -> bool:
        section = self._ocr_settings()
        if section is not None and hasattr(section, attr):
            try:
                return bool(getattr(section, attr))
            except (TypeError, ValueError):
                pass
        return bool(self._cfg(key, default))

    def _ocr_str(self, attr: str, key: str, default: str) -> str:
        section = self._ocr_settings()
        if section is not None and hasattr(section, attr):
            value = str(getattr(section, attr, default) or "").strip()
            return value or str(default)
        value = str(self._cfg(key, default) or "").strip()
        return value or str(default)

    def _ocr_int(self, attr: str, key: str, default: int, *, min_value: int = 0) -> int:
        section = self._ocr_settings()
        if section is not None and hasattr(section, attr):
            try:
                return max(int(min_value), int(getattr(section, attr)))
            except (TypeError, ValueError):
                pass
        try:
            return max(int(min_value), int(self._cfg(key, default)))
        except (TypeError, ValueError):
            return max(int(min_value), int(default))

    def _ocr_float(self, attr: str, key: str, default: float, *, min_value: float = 0.0) -> float:
        section = self._ocr_settings()
        if section is not None and hasattr(section, attr):
            try:
                return max(float(min_value), float(getattr(section, attr)))
            except (TypeError, ValueError):
                pass
        try:
            return max(float(min_value), float(self._cfg(key, default)))
        except (TypeError, ValueError):
            return max(float(min_value), float(default))

    def _warn(self, where: str, exc: Exception) -> None:
        warn_fn = getattr(self._mw, "_warn_ocr_suppressed_exception", None)
        if callable(warn_fn):
            warn_fn(where, exc)

    def _trace(self, event: str, **payload) -> None:
        trace_fn = getattr(self._mw, "_trace_event", None)
        if callable(trace_fn):
            trace_fn(event, **payload)

    def _set_preload_phase(self, phase: OCRPreloadPhase, *, reason: str = "") -> None:
        setter = getattr(self._mw, "_set_ocr_preload_phase", None)
        if callable(setter):
            try:
                setter(phase, reason=str(reason or ""))
                return
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
                pass
        set_state = getattr(self._mw, "_set_startup_runtime_state", None)
        if callable(set_state):
            try:
                set_state(
                    ocr_preload_phase=phase.value,
                    ocr_preload_phase_reason=str(reason or "") or None,
                )
                return
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
                pass
        setattr(self._mw, "_ocr_preload_phase", phase.value)
        setattr(self._mw, "_ocr_preload_phase_reason", str(reason or "") or None)

    def _mw_method_is_default(self, name: str, fn: object) -> bool:
        cls_fn = getattr(type(self._mw), name, None)
        bound_func = getattr(fn, "__func__", None)
        return cls_fn is not None and bound_func is cls_fn

    def _call_override_noargs(self, name: str, fallback):
        fn = getattr(self._mw, name, None)
        if callable(fn) and not self._mw_method_is_default(name, fn):
            return fn()
        return fallback()

    def _call_override_kwargs(self, name: str, fallback, **kwargs):
        fn = getattr(self._mw, name, None)
        if callable(fn) and not self._mw_method_is_default(name, fn):
            return fn(**kwargs)
        return fallback(**kwargs)

    def background_preload_enabled(self) -> bool:
        return self._ocr_bool("background_preload_enabled", "OCR_BACKGROUND_PRELOAD_ENABLED", True)

    def easyocr_resolution_kwargs(self) -> dict[str, object]:
        def _optional_str(*, attr: str, key: str) -> str | None:
            value = self._ocr_str(attr, key, "").strip()
            return value or None

        return {
            "lang": _optional_str(attr="easyocr_lang", key="OCR_EASYOCR_LANG"),
            "model_dir": _optional_str(attr="easyocr_model_dir", key="OCR_EASYOCR_MODEL_DIR"),
            "user_network_dir": _optional_str(attr="easyocr_user_network_dir", key="OCR_EASYOCR_USER_NETWORK_DIR"),
            "gpu": self._ocr_str("easyocr_gpu", "OCR_EASYOCR_GPU", "auto"),
            "download_enabled": self._ocr_bool(
                "easyocr_download_enabled",
                "OCR_EASYOCR_DOWNLOAD_ENABLED",
                False,
            ),
            "quiet": self._runtime_bool("quiet", "QUIET", False),
        }

    def ensure_background_preload_timer(self) -> QtCore.QTimer:
        timer = getattr(self._mw, "_ocr_preload_timer", None)
        if timer is not None:
            return timer
        try:
            timer = QtCore.QTimer(self._mw)
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(getattr(self._mw, "_run_ocr_background_preload"))
        if hasattr(self._mw, "_timers"):
            getattr(self._mw, "_timers").register(timer)
        setattr(self._mw, "_ocr_preload_timer", timer)
        return timer

    def cancel_background_preload(self) -> None:
        timer = getattr(self._mw, "_ocr_preload_timer", None)
        if timer is None:
            return
        try:
            timer.stop()
            self._set_preload_phase(OCRPreloadPhase.CANCELLED, reason="timer_cancelled")
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
            self._warn("cancel_preload_timer:stop", exc)

    def stop_background_preload_job(self, *, reason: str = "", wait_ms: int = 0) -> None:
        job = getattr(self._mw, "_ocr_preload_job", None)
        if not isinstance(job, dict):
            setattr(self._mw, "_ocr_preload_job", None)
            return
        thread = job.get("thread")
        worker = job.get("worker")
        cancel_slot = getattr(worker, "cancel", None)
        if callable(cancel_slot):
            try:
                cancel_slot()
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("stop_preload_job:worker_cancel", exc)
        was_running = False
        if thread is not None:
            try:
                was_running = bool(thread.isRunning())
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
                was_running = False
        if was_running:
            try:
                thread.requestInterruption()
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("stop_preload_job:request_interruption", exc)
            try:
                thread.quit()
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("stop_preload_job:quit", exc)
        waited = False
        if was_running and int(wait_ms) > 0 and thread is not None:
            try:
                waited = bool(thread.wait(int(wait_ms)))
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
                waited = False
        if was_running and not waited and thread is not None and hasattr(thread, "terminate"):
            try:
                thread.terminate()
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("stop_preload_job:terminate", exc)
        keep_job = bool(was_running and not waited)
        if not keep_job:
            setattr(self._mw, "_ocr_preload_job", None)
            self._set_preload_phase(OCRPreloadPhase.CANCELLED, reason=str(reason or "cancelled"))
        try:
            self._trace(
                "ocr_preload_cancelled",
                reason=str(reason or "unspecified"),
                was_running=bool(was_running),
                waited=bool(waited),
                keep_job=bool(keep_job),
            )
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
            self._warn("stop_preload_job:trace_cancelled", exc)

    def schedule_background_preload(self, *, delay_ms: int | None = None, reason: str = "") -> None:
        if getattr(self._mw, "_closing", False):
            return
        if not self.background_preload_enabled():
            return
        if bool(getattr(self._mw, "_ocr_preload_done", False)):
            return
        if bool(getattr(self._mw, "_ocr_preload_attempted", False)):
            return
        if bool(getattr(self._mw, "_ocr_runtime_activated", False)):
            setattr(self._mw, "_ocr_preload_done", True)
            setattr(self._mw, "_ocr_preload_attempted", True)
            return
        if getattr(self._mw, "_ocr_async_job", None) or getattr(self._mw, "_ocr_preload_job", None):
            return
        if delay_ms is None:
            delay_ms = self._ocr_int(
                "background_preload_delay_ms",
                "OCR_BACKGROUND_PRELOAD_DELAY_MS",
                2500,
            )
        timer = self._call_override_noargs(
            "_ensure_ocr_background_preload_timer",
            self.ensure_background_preload_timer,
        )
        delay = max(0, int(delay_ms))
        timer.start(delay)
        self._set_preload_phase(OCRPreloadPhase.SCHEDULED, reason=str(reason or "scheduled"))
        try:
            self._trace(
                "ocr_preload_scheduled",
                delay_ms=delay,
                reason=str(reason or "unspecified"),
            )
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
            self._warn("schedule_preload:trace_scheduled", exc)

    def background_preload_block_reason(self) -> str | None:
        startup_warmup = bool(getattr(self._mw, "_startup_warmup_running", False))
        allow_during_startup = self._ocr_bool(
            "background_preload_allow_during_startup",
            "OCR_BACKGROUND_PRELOAD_ALLOW_DURING_STARTUP",
            True,
        )
        if getattr(self._mw, "_closing", False):
            return "closing"
        overlay_choice_active = getattr(self._mw, "_overlay_choice_active", None)
        if callable(overlay_choice_active):
            if overlay_choice_active() and not (startup_warmup and allow_during_startup):
                return "overlay_choice"
        min_uptime_ms = self._ocr_int(
            "background_preload_min_uptime_ms",
            "OCR_BACKGROUND_PRELOAD_MIN_UPTIME_MS",
            8000,
        )
        if min_uptime_ms > 0 and not (startup_warmup and allow_during_startup):
            shown_at = getattr(self._mw, "_choice_shown_at", None)
            if shown_at is not None:
                try:
                    elapsed_ms = int((time.monotonic() - float(shown_at)) * 1000.0)
                except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
                    elapsed_ms = min_uptime_ms
                if elapsed_ms < min_uptime_ms:
                    return "startup_cooldown"
        if bool(getattr(self._mw, "_background_services_paused", False)) and not (
            startup_warmup and allow_during_startup
        ):
            return "background_services_paused"
        try:
            if int(getattr(self._mw, "pending", 0) or 0) > 0:
                return "spin_pending"
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
            self._warn("preload_block_reason:pending", exc)
        has_spin_anim = getattr(self._mw, "_has_active_spin_animations", None)
        if callable(has_spin_anim):
            try:
                if bool(has_spin_anim(include_internal_flags=True)):
                    return "spin_anim_running"
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("preload_block_reason:spin_anim", exc)
        return None

    def run_background_preload(self) -> None:
        if getattr(self._mw, "_closing", False):
            return
        if not self.background_preload_enabled():
            return
        if bool(getattr(self._mw, "_ocr_preload_done", False)):
            return
        if bool(getattr(self._mw, "_ocr_preload_attempted", False)):
            return
        if bool(getattr(self._mw, "_ocr_runtime_activated", False)):
            setattr(self._mw, "_ocr_preload_done", True)
            setattr(self._mw, "_ocr_preload_attempted", True)
            self._set_preload_phase(OCRPreloadPhase.DONE, reason="already_ready")
            return
        if getattr(self._mw, "_ocr_async_job", None) or getattr(self._mw, "_ocr_preload_job", None):
            return

        block_reason = self.background_preload_block_reason()
        if block_reason:
            self._set_preload_phase(OCRPreloadPhase.DEFERRED, reason=str(block_reason))
            retry_ms = max(
                250,
                self._ocr_int(
                    "background_preload_busy_retry_ms",
                    "OCR_BACKGROUND_PRELOAD_BUSY_RETRY_MS",
                    1800,
                ),
            )
            self._call_override_kwargs(
                "_schedule_ocr_background_preload",
                self.schedule_background_preload,
                delay_ms=retry_ms,
                reason="busy",
            )
            try:
                self._trace(
                    "ocr_preload_deferred",
                    reason=block_reason,
                    retry_ms=retry_ms,
                )
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("run_preload:trace_deferred", exc)
            return

        kwargs = self.easyocr_resolution_kwargs()
        preload_project_root = str(Path(__file__).resolve().parents[2])
        preload_timeout_s = self._ocr_float(
            "preload_subprocess_timeout_s",
            "OCR_PRELOAD_SUBPROCESS_TIMEOUT_S",
            60.0,
            min_value=1.0,
        )
        use_subprocess_probe = self._ocr_bool(
            "preload_use_subprocess_probe",
            "OCR_PRELOAD_USE_SUBPROCESS_PROBE",
            True,
        )
        if bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win"):
            use_subprocess_probe = self._ocr_bool(
                "preload_use_subprocess_probe_win_frozen",
                "OCR_PRELOAD_USE_SUBPROCESS_PROBE_WIN_FROZEN",
                False,
            )
        inprocess_cache_warmup = self._ocr_bool(
            "preload_inprocess_cache_warmup",
            "OCR_PRELOAD_INPROCESS_CACHE_WARMUP",
            True,
        )
        thread = QtCore.QThread(self._mw)
        try:
            thread.setObjectName("ocr_preload_thread")
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            pass
        worker = self._worker_cls(
            easyocr_kwargs=kwargs,
            project_root=preload_project_root,
            subprocess_timeout_s=preload_timeout_s,
            use_subprocess_probe=use_subprocess_probe,
            inprocess_cache_warmup=inprocess_cache_warmup,
        )
        try:
            worker.setObjectName("ocr_preload_worker")
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            pass
        worker.moveToThread(thread)
        relay = self._relay_cls(self._mw)
        job = {
            "thread": thread,
            "worker": worker,
            "relay": relay,
        }
        setattr(self._mw, "_ocr_preload_job", job)
        self._set_preload_phase(OCRPreloadPhase.RUNNING, reason="worker_started")

        def _finalize_preload(ok: bool, detail: str) -> None:
            current = getattr(self._mw, "_ocr_preload_job", None)
            if current is not None and current is not job:
                return
            if bool(job.get("_finalized", False)):
                return
            job["_finalized"] = True
            setattr(self._mw, "_ocr_preload_attempted", True)
            if bool(ok):
                setattr(self._mw, "_ocr_preload_done", True)
                setattr(self._mw, "_ocr_runtime_activated", True)
                self.schedule_cache_release()
                self._set_preload_phase(OCRPreloadPhase.DONE, reason="worker_finished")
            else:
                self._set_preload_phase(OCRPreloadPhase.FAILED, reason="worker_failed")
            update_buttons = getattr(self._mw, "_update_role_ocr_buttons_enabled", None)
            if callable(update_buttons):
                try:
                    update_buttons()
                except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                    self._warn("run_preload:finalize_update_buttons", exc)
            try:
                self._trace(
                    "ocr_preload_finished",
                    ok=bool(ok),
                    detail=str(detail or ""),
                )
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("run_preload:finalize_trace_finished", exc)
            if current is job:
                thread_ref = job.get("thread")
                running = False
                if thread_ref is not None and hasattr(thread_ref, "isRunning"):
                    try:
                        running = bool(thread_ref.isRunning())
                    except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
                        running = False
                if not running:
                    setattr(self._mw, "_ocr_preload_job", None)

        def _trace_preload_lifecycle(event_name: str, payload: object) -> None:
            event = str(event_name or "").strip() or "ocr_preload_worker:lifecycle"
            values = payload if isinstance(payload, dict) else {}

            def _clean(value: object, *, max_len: int = 220) -> str:
                text = str(value if value is not None else "")
                if len(text) > max_len:
                    return text[: max_len - 1] + "…"
                return text

            trace_payload: dict[str, object] = {}
            for key in ("child_pid", "returncode", "runtime_ms", "timeout_s", "where", "mode"):
                if key in values:
                    trace_payload[key] = values.get(key)
            if "message" in values:
                trace_payload["message"] = _clean(values.get("message"))
            if "error" in values:
                trace_payload["error"] = _clean(values.get("error"))
            try:
                self._trace(event, **trace_payload)
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("run_preload:lifecycle_trace", exc)

        try:
            job["worker_done_connection"] = worker.finished.connect(
                relay.forward_done,
                QtCore.Qt.QueuedConnection,
            )
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            worker.finished.connect(relay.forward_done, QtCore.Qt.QueuedConnection)
            job["worker_done_connection"] = None
        try:
            job["done_connection"] = relay.done.connect(_finalize_preload)
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            relay.done.connect(_finalize_preload)
            job["done_connection"] = None
        try:
            job["worker_quit_connection"] = worker.finished.connect(thread.quit)
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            worker.finished.connect(thread.quit)
            job["worker_quit_connection"] = None
        try:
            job["lifecycle_connection"] = worker.lifecycle.connect(
                _trace_preload_lifecycle,
                QtCore.Qt.QueuedConnection,
            )
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            worker.lifecycle.connect(_trace_preload_lifecycle, QtCore.Qt.QueuedConnection)
            job["lifecycle_connection"] = None

        def _cleanup_cancelled_preload() -> None:
            current = getattr(self._mw, "_ocr_preload_job", None)
            if current is job:
                setattr(self._mw, "_ocr_preload_job", None)
                try:
                    self._trace("ocr_preload_thread_finished")
                except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                    self._warn("run_preload:cleanup_trace_finished", exc)

        try:
            job["cleanup_connection"] = thread.finished.connect(_cleanup_cancelled_preload)
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            thread.finished.connect(_cleanup_cancelled_preload)
            job["cleanup_connection"] = None
        try:
            job["started_connection"] = thread.started.connect(worker.run)
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            thread.started.connect(worker.run)
            job["started_connection"] = None
        try:
            job["worker_delete_connection"] = thread.finished.connect(worker.deleteLater)
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            thread.finished.connect(worker.deleteLater)
            job["worker_delete_connection"] = None
        try:
            job["thread_delete_connection"] = thread.finished.connect(thread.deleteLater)
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            thread.finished.connect(thread.deleteLater)
            job["thread_delete_connection"] = None
        if getattr(self._mw, "_closing", False):
            setattr(self._mw, "_ocr_preload_job", None)
            self._set_preload_phase(OCRPreloadPhase.CANCELLED, reason="closing_before_start")
            try:
                worker.deleteLater()
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("run_preload:closing_delete_worker", exc)
            try:
                relay.deleteLater()
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("run_preload:closing_delete_relay", exc)
            try:
                thread.deleteLater()
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("run_preload:closing_delete_thread", exc)
            return
        startup_warmup = bool(getattr(self._mw, "_startup_warmup_running", False))
        desired_priority = QtCore.QThread.NormalPriority if startup_warmup else QtCore.QThread.LowPriority
        try:
            thread.start(desired_priority)
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            thread.start()

    def ensure_cache_release_timer(self) -> QtCore.QTimer:
        timer = getattr(self._mw, "_ocr_cache_release_timer", None)
        if timer is not None:
            return timer
        try:
            timer = QtCore.QTimer(self._mw)
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(getattr(self._mw, "_release_ocr_runtime_cache"))
        if hasattr(self._mw, "_timers"):
            getattr(self._mw, "_timers").register(timer)
        setattr(self._mw, "_ocr_cache_release_timer", timer)
        return timer

    def cancel_cache_release(self) -> None:
        timer = getattr(self._mw, "_ocr_cache_release_timer", None)
        if timer is None:
            return
        try:
            timer.stop()
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
            self._warn("cancel_cache_release_timer:stop", exc)

    def schedule_cache_release(self) -> None:
        if getattr(self._mw, "_closing", False):
            return
        if bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win"):
            if not bool(getattr(self._mw, "_ocr_cache_release_disabled_trace_logged", False)):
                try:
                    from ..runtime import trace as ocr_runtime_trace

                    ocr_runtime_trace.trace("ocr_cache_release:disabled", reason="win_frozen")
                except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
                    pass
                setattr(self._mw, "_ocr_cache_release_disabled_trace_logged", True)
            return
        if getattr(self._mw, "_ocr_async_job", None):
            return
        runtime_sleep_until_used = getattr(self._mw, "_ocr_runtime_sleep_until_used", None)
        if callable(runtime_sleep_until_used):
            if runtime_sleep_until_used() and not bool(getattr(self._mw, "_ocr_runtime_activated", False)):
                return
        delay_ms = self._ocr_int(
            "idle_cache_release_ms",
            "OCR_IDLE_CACHE_RELEASE_MS",
            30000,
        )
        if delay_ms <= 0:
            return
        timer = self._call_override_noargs(
            "_ensure_ocr_cache_release_timer",
            self.ensure_cache_release_timer,
        )
        timer.start(delay_ms)
        try:
            self._trace("ocr_cache_release_scheduled", delay_ms=delay_ms)
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
            self._warn("schedule_cache_release:trace_scheduled", exc)

    def spin_active_for_cache_release(self) -> bool:
        try:
            if int(getattr(self._mw, "pending", 0)) > 0:
                return True
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
            self._warn("spin_active_for_cache_release:pending", exc)
        role_wheels_fn = getattr(self._mw, "_role_wheels", None)
        if callable(role_wheels_fn):
            try:
                for _role, wheel in role_wheels_fn():
                    try:
                        if hasattr(wheel, "is_anim_running") and bool(wheel.is_anim_running()):
                            return True
                    except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
                        continue
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("spin_active_for_cache_release:role_wheels", exc)
        map_main = getattr(self._mw, "map_main", None)
        if map_main is not None and hasattr(map_main, "is_anim_running"):
            try:
                return bool(map_main.is_anim_running())
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("spin_active_for_cache_release:map_main", exc)
        return False

    def release_cache(self) -> None:
        if bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win"):
            try:
                from ..runtime import trace as ocr_runtime_trace

                ocr_runtime_trace.trace("ocr_cache_release:skip", reason="win_frozen")
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
                pass
            return
        if getattr(self._mw, "_ocr_async_job", None):
            self._call_override_noargs(
                "_schedule_ocr_runtime_cache_release",
                self.schedule_cache_release,
            )
            return
        if self.spin_active_for_cache_release():
            retry_ms = max(
                200,
                self._ocr_int(
                    "idle_cache_release_busy_retry_ms",
                    "OCR_IDLE_CACHE_RELEASE_BUSY_RETRY_MS",
                    2500,
                ),
            )
            timer = self._call_override_noargs(
                "_ensure_ocr_cache_release_timer",
                self.ensure_cache_release_timer,
            )
            timer.start(retry_ms)
            try:
                self._trace("ocr_cache_release_deferred_busy", retry_ms=retry_ms)
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
                self._warn("release_cache:trace_deferred_busy", exc)
            return
        try:
            from ..pipeline import importer as ocr_import
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            return
        release_fn = getattr(ocr_import, "clear_ocr_runtime_caches", None)
        if not callable(release_fn):
            return
        try:
            gpu_setting = self._ocr_str("easyocr_gpu", "OCR_EASYOCR_GPU", "auto").strip().casefold()
            release_gpu = gpu_setting not in {"", "0", "false", "off", "no", "cpu", "none"}
            release_fn(release_gpu=release_gpu)
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            return
        try:
            self._trace("ocr_cache_released")
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
            self._warn("release_cache:trace_released", exc)

    def release_cache_for_spin(self) -> None:
        if bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win"):
            try:
                from ..runtime import trace as ocr_runtime_trace

                ocr_runtime_trace.trace("ocr_cache_release_for_spin:skip", reason="win_frozen")
            except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
                pass
            return
        self._call_override_noargs(
            "_cancel_ocr_runtime_cache_release",
            self.cancel_cache_release,
        )
        if getattr(self._mw, "_ocr_async_job", None):
            return
        if not self._ocr_bool("release_cache_on_spin", "OCR_RELEASE_CACHE_ON_SPIN", False):
            self._call_override_noargs(
                "_schedule_ocr_runtime_cache_release",
                self.schedule_cache_release,
            )
            return
        try:
            from ..pipeline import importer as ocr_import
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            return
        release_fn = getattr(ocr_import, "clear_ocr_runtime_caches", None)
        if not callable(release_fn):
            return
        try:
            release_fn(
                release_gpu=False,
                collect_garbage=False,
            )
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS:
            return
        try:
            self._trace("ocr_cache_released_for_spin")
        except _OCR_PRELOAD_COORDINATOR_GUARD_ERRORS as exc:
            self._warn("release_cache_for_spin:trace_released", exc)
