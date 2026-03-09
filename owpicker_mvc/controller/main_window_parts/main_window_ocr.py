from __future__ import annotations

from collections import deque
from difflib import SequenceMatcher
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import warnings
from PySide6 import QtCore, QtGui, QtWidgets

import i18n
from logic.name_normalization import normalize_name_alnum_key
from ..ocr.ocr_role_import import (
    PendingOCRImport,
    normalize_name_key as normalize_ocr_name_key,
    resolve_selected_candidates as resolve_selected_ocr_candidates,
)
from utils import ui_helpers


class _OCRPreloadWorker(QtCore.QObject):
    finished = QtCore.Signal(bool, str)
    lifecycle = QtCore.Signal(str, object)

    def __init__(
        self,
        *,
        easyocr_kwargs: dict[str, object],
        project_root: str,
        subprocess_timeout_s: float,
        use_subprocess_probe: bool = True,
        inprocess_cache_warmup: bool = True,
    ) -> None:
        super().__init__()
        self._easyocr_kwargs = dict(easyocr_kwargs)
        self._project_root = str(project_root or "").strip()
        self._quiet = bool(self._easyocr_kwargs.get("quiet", False))
        self._use_subprocess_probe = bool(use_subprocess_probe)
        self._inprocess_cache_warmup = bool(inprocess_cache_warmup)
        self._suppressed_exception_seen: set[tuple[str, str, str]] = set()
        self._cancel_requested = False
        self._proc_lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        try:
            self._subprocess_timeout_s = max(1.0, float(subprocess_timeout_s))
        except Exception:
            self._subprocess_timeout_s = 60.0

    def _warn_suppressed_exception(self, where: str, exc: Exception) -> None:
        if self._quiet:
            return
        signature = (str(where or "ocr_preload_worker"), type(exc).__name__, str(exc))
        if signature in self._suppressed_exception_seen:
            return
        self._suppressed_exception_seen.add(signature)
        try:
            warnings.warn(
                f"OCR preload worker suppressed exception at {where}: {exc!r}",
                RuntimeWarning,
                stacklevel=2,
            )
        except Exception:
            pass

    def _set_proc(self, proc: subprocess.Popen[str] | None) -> None:
        with self._proc_lock:
            self._proc = proc

    def _clear_proc(self, proc: subprocess.Popen[str] | None) -> None:
        with self._proc_lock:
            if self._proc is proc:
                self._proc = None

    def _emit_lifecycle(self, event_name: str, **payload) -> None:
        try:
            self.lifecycle.emit(str(event_name or "").strip(), dict(payload))
        except Exception:
            pass

    def _terminate_subprocess(self, proc: subprocess.Popen[str] | None, *, where: str) -> None:
        if proc is None:
            return
        child_pid = ""
        try:
            raw_pid = getattr(proc, "pid", None)
            if raw_pid is not None:
                child_pid = str(int(raw_pid))
        except Exception:
            child_pid = ""
        try:
            if proc.poll() is not None:
                return
        except Exception:
            return
        try:
            from ..ocr import ocr_runtime_trace

            ocr_runtime_trace.trace(
                "ocr_preload_worker:subprocess_stop_requested",
                where=str(where or ""),
                child_pid=child_pid,
            )
        except Exception:
            pass
        self._emit_lifecycle(
            "ocr_preload_worker:subprocess_stop_requested",
            where=str(where or ""),
            child_pid=child_pid,
        )
        try:
            proc.terminate()
        except Exception as exc:
            self._warn_suppressed_exception(f"{where}:terminate", exc)
        try:
            proc.wait(timeout=0.25)
            try:
                from ..ocr import ocr_runtime_trace

                ocr_runtime_trace.trace(
                    "ocr_preload_worker:subprocess_stopped",
                    where=str(where or ""),
                    child_pid=child_pid,
                    mode="terminate",
                )
            except Exception:
                pass
            self._emit_lifecycle(
                "ocr_preload_worker:subprocess_stopped",
                where=str(where or ""),
                child_pid=child_pid,
                mode="terminate",
            )
            return
        except Exception:
            pass
        try:
            proc.kill()
        except Exception as exc:
            self._warn_suppressed_exception(f"{where}:kill", exc)
        try:
            proc.wait(timeout=0.25)
        except Exception:
            pass
        try:
            from ..ocr import ocr_runtime_trace

            ocr_runtime_trace.trace(
                "ocr_preload_worker:subprocess_stopped",
                where=str(where or ""),
                child_pid=child_pid,
                mode="kill",
            )
        except Exception:
            pass
        self._emit_lifecycle(
            "ocr_preload_worker:subprocess_stopped",
            where=str(where or ""),
            child_pid=child_pid,
            mode="kill",
        )

    @QtCore.Slot()
    def cancel(self) -> None:
        self._cancel_requested = True
        try:
            thread = self.thread()
        except Exception:
            thread = None
        if thread is not None:
            try:
                thread.requestInterruption()
            except Exception:
                pass
        proc: subprocess.Popen[str] | None = None
        with self._proc_lock:
            proc = self._proc
        self._terminate_subprocess(proc, where="cancel")

    def _run_inprocess_warmup(self) -> tuple[bool, str]:
        try:
            from ..ocr import ocr_import, ocr_runtime_trace
        except Exception as exc:
            return False, f"inprocess-import-error:{exc!r}"

        try:
            ocr_runtime_trace.trace("ocr_preload_worker:inprocess_warmup_start")
        except Exception:
            pass

        availability_fn = getattr(ocr_import, "easyocr_available", None)
        if not callable(availability_fn):
            return False, "inprocess-availability-missing"
        try:
            ok = bool(availability_fn(**self._easyocr_kwargs))
        except Exception as exc:
            return False, f"inprocess-availability-error:{exc!r}"
        if ok:
            try:
                ocr_runtime_trace.trace("ocr_preload_worker:inprocess_warmup_done", ok=True)
            except Exception:
                pass
            return True, "ready"

        detail = "inprocess-not-ready"
        diag_fn = getattr(ocr_import, "easyocr_resolution_diagnostics", None)
        if callable(diag_fn):
            try:
                diag = str(diag_fn(**self._easyocr_kwargs)).strip()
                if diag:
                    detail = diag
            except Exception as exc:
                detail = f"inprocess-diagnostics-error:{exc!r}"
        try:
            ocr_runtime_trace.trace(
                "ocr_preload_worker:inprocess_warmup_done",
                ok=False,
                detail=str(detail or ""),
            )
        except Exception:
            pass
        return False, detail

    @QtCore.Slot()
    def run(self) -> None:
        try:
            from ..ocr import ocr_runtime_trace

            ocr_runtime_trace.trace("ocr_preload_worker:start", frozen=bool(getattr(sys, "frozen", False)))
        except Exception:
            pass
        def _interrupted() -> bool:
            if bool(self._cancel_requested):
                return True
            try:
                thread = QtCore.QThread.currentThread()
            except Exception:
                thread = None
            if thread is None:
                return False
            try:
                return bool(thread.isInterruptionRequested())
            except Exception:
                return False

        # Allow forceful termination during app shutdown if OCR preload
        # is still running; without this, Qt may keep waiting for seconds.
        try:
            QtCore.QThread.setTerminationEnabled(True)
        except Exception as exc:
            self._warn_suppressed_exception("worker_run:set_termination_enabled", exc)
        if _interrupted():
            try:
                from ..ocr import ocr_runtime_trace

                ocr_runtime_trace.trace("ocr_preload_worker:interrupted_early")
            except Exception:
                pass
            self.finished.emit(False, "interrupted")
            return

        if not bool(self._use_subprocess_probe):
            try:
                from ..ocr import ocr_runtime_trace

                ocr_runtime_trace.trace("ocr_preload_worker:inprocess_only_mode")
            except Exception:
                pass
            self._emit_lifecycle("ocr_preload_worker:inprocess_only_mode")
            warm_ok, warm_detail = self._run_inprocess_warmup()
            if _interrupted():
                self.finished.emit(False, "interrupted")
                return
            self.finished.emit(bool(warm_ok), str(warm_detail or ("ready" if warm_ok else "not-ready")))
            return

        script = (
            "import json, pathlib, sys\n"
            "payload = json.loads(sys.argv[1])\n"
            "root = pathlib.Path(sys.argv[2]).resolve()\n"
            "if str(root) not in sys.path:\n"
            "    sys.path.insert(0, str(root))\n"
            "from controller.ocr import ocr_import\n"
            "ok = bool(ocr_import.easyocr_available(**payload))\n"
            "if ok:\n"
            "    detail = 'ready'\n"
            "else:\n"
            "    diag_fn = getattr(ocr_import, 'easyocr_resolution_diagnostics', None)\n"
            "    detail = str(diag_fn(**payload)).strip() if callable(diag_fn) else 'not-ready'\n"
            "print(json.dumps({'ok': ok, 'detail': detail}))\n"
        )
        python_exe = str(sys.executable or "").strip() or "python3"
        payload = json.dumps(self._easyocr_kwargs)
        proc: subprocess.Popen[str] | None = None
        try:
            proc = subprocess.Popen(
                [python_exe, "-c", script, payload, self._project_root],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception as exc:
            try:
                from ..ocr import ocr_runtime_trace

                ocr_runtime_trace.trace("ocr_preload_worker:subprocess_start_error", error=repr(exc))
            except Exception:
                pass
            self._emit_lifecycle("ocr_preload_worker:subprocess_start_error", error=repr(exc))
            self.finished.emit(False, f"preload-subprocess-start-error:{exc!r}")
            return
        child_pid = ""
        try:
            raw_pid = getattr(proc, "pid", None)
            if raw_pid is not None:
                child_pid = str(int(raw_pid))
        except Exception:
            child_pid = ""
        spawn_started_at = time.monotonic()
        try:
            from ..ocr import ocr_runtime_trace

            ocr_runtime_trace.trace(
                "ocr_preload_worker:subprocess_spawned",
                child_pid=child_pid,
                timeout_s=float(self._subprocess_timeout_s),
            )
        except Exception:
            pass
        self._emit_lifecycle(
            "ocr_preload_worker:subprocess_spawned",
            child_pid=child_pid,
            timeout_s=float(self._subprocess_timeout_s),
        )
        self._set_proc(proc)

        try:
            started_at = spawn_started_at
            while True:
                if _interrupted():
                    try:
                        from ..ocr import ocr_runtime_trace

                        ocr_runtime_trace.trace(
                            "ocr_preload_worker:subprocess_interrupted",
                            child_pid=child_pid,
                            runtime_ms=int((time.monotonic() - started_at) * 1000.0),
                        )
                    except Exception:
                        pass
                    self._emit_lifecycle(
                        "ocr_preload_worker:subprocess_interrupted",
                        child_pid=child_pid,
                        runtime_ms=int((time.monotonic() - started_at) * 1000.0),
                    )
                    self._terminate_subprocess(proc, where="worker_run:interrupt")
                    self.finished.emit(False, "interrupted")
                    return
                rc = proc.poll()
                if rc is not None:
                    try:
                        from ..ocr import ocr_runtime_trace

                        ocr_runtime_trace.trace(
                            "ocr_preload_worker:subprocess_exited",
                            child_pid=child_pid,
                            returncode=int(rc),
                            runtime_ms=int((time.monotonic() - started_at) * 1000.0),
                        )
                    except Exception:
                        pass
                    self._emit_lifecycle(
                        "ocr_preload_worker:subprocess_exited",
                        child_pid=child_pid,
                        returncode=int(rc),
                        runtime_ms=int((time.monotonic() - started_at) * 1000.0),
                    )
                    break
                if (time.monotonic() - started_at) >= self._subprocess_timeout_s:
                    try:
                        from ..ocr import ocr_runtime_trace

                        ocr_runtime_trace.trace(
                            "ocr_preload_worker:subprocess_timeout",
                            child_pid=child_pid,
                            timeout_s=float(self._subprocess_timeout_s),
                            runtime_ms=int((time.monotonic() - started_at) * 1000.0),
                        )
                    except Exception:
                        pass
                    self._emit_lifecycle(
                        "ocr_preload_worker:subprocess_timeout",
                        child_pid=child_pid,
                        timeout_s=float(self._subprocess_timeout_s),
                        runtime_ms=int((time.monotonic() - started_at) * 1000.0),
                    )
                    self._terminate_subprocess(proc, where="worker_run:timeout")
                    self.finished.emit(False, "preload-timeout")
                    return
                time.sleep(0.05)

            try:
                stdout, stderr = proc.communicate(timeout=0.2)
            except Exception:
                stdout, stderr = "", ""

            if int(proc.returncode or 1) != 0:
                message = (stderr or stdout or "").strip()
                try:
                    from ..ocr import ocr_runtime_trace

                    ocr_runtime_trace.trace(
                        "ocr_preload_worker:subprocess_error",
                        child_pid=child_pid,
                        returncode=int(proc.returncode or 1),
                        message=message,
                    )
                except Exception:
                    pass
                self._emit_lifecycle(
                    "ocr_preload_worker:subprocess_error",
                    child_pid=child_pid,
                    returncode=int(proc.returncode or 1),
                    message=message,
                )
                if message:
                    self.finished.emit(False, f"preload-subprocess-error:{message}")
                else:
                    self.finished.emit(False, "preload-subprocess-error")
                return

            line = ""
            for raw_line in reversed((stdout or "").splitlines()):
                text = str(raw_line or "").strip()
                if text:
                    line = text
                    break
            if not line:
                self.finished.emit(False, "preload-no-output")
                return
            try:
                data = json.loads(line)
                ok = bool(data.get("ok", False))
                detail = str(data.get("detail", "") or "").strip()
            except Exception as exc:
                self.finished.emit(False, f"preload-parse-error:{exc!r}")
                return
            if ok and self._inprocess_cache_warmup:
                if _interrupted():
                    self.finished.emit(False, "interrupted")
                    return
                warm_ok, warm_detail = self._run_inprocess_warmup()
                if not warm_ok:
                    self.finished.emit(False, warm_detail or "inprocess-warmup-failed")
                    return
                if str(warm_detail or "").strip():
                    detail = str(warm_detail).strip()
            try:
                from ..ocr import ocr_runtime_trace

                ocr_runtime_trace.trace("ocr_preload_worker:done", ok=bool(ok), detail=str(detail or ""))
            except Exception:
                pass
            self.finished.emit(ok, detail or ("ready" if ok else "not-ready"))
        finally:
            self._clear_proc(proc)


class _OCRPreloadRelay(QtCore.QObject):
    done = QtCore.Signal(bool, str)

    @QtCore.Slot(bool, str)
    def forward_done(self, ok: bool, detail: str) -> None:
        self.done.emit(bool(ok), str(detail or ""))


class MainWindowOCRMixin:
    def _warn_ocr_suppressed_exception(self, where: str, exc: Exception) -> None:
        try:
            if bool(self._cfg("QUIET", False)):
                return
        except Exception:
            pass
        signature = (str(where or "ocr"), type(exc).__name__, str(exc))
        seen = getattr(self, "_ocr_suppressed_exception_seen", None)
        if not isinstance(seen, set):
            seen = set()
            setattr(self, "_ocr_suppressed_exception_seen", seen)
        if signature in seen:
            return
        seen.add(signature)
        try:
            warnings.warn(
                f"OCR suppressed exception at {where}: {exc!r}",
                RuntimeWarning,
                stacklevel=2,
            )
        except Exception:
            pass
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "ocr_suppressed_exception",
                    where=str(where or "ocr"),
                    error=repr(exc),
                )
            except Exception:
                pass

    def _ocr_name_hint_candidates(self, role_key: str) -> list[str]:
        key = str(role_key or "").strip().casefold()
        names: list[str] = []
        seen: set[str] = set()

        def _add(value: str) -> None:
            text = str(value or "").strip()
            if not text:
                return
            norm = normalize_ocr_name_key(text)
            if not norm or norm in seen:
                return
            seen.add(norm)
            names.append(text)

        cfg_hints = self._cfg("OCR_NAME_HINTS", [])
        if isinstance(cfg_hints, (list, tuple, set)):
            for raw in cfg_hints:
                _add(str(raw or ""))
        if names and bool(self._cfg("OCR_NAME_HINTS_ONLY_WHEN_SET", True)):
            return names

        if key in {"tank", "dps", "support"}:
            wheel = self._target_wheel_for_ocr_role(key)
            if wheel is not None and hasattr(wheel, "get_current_names"):
                try:
                    for current in wheel.get_current_names():
                        _add(str(current or ""))
                except Exception as exc:
                    self._warn_ocr_suppressed_exception("name_hint_candidates:role_list", exc)
        else:
            for role in self._ocr_distribution_role_keys():
                wheel = self._target_wheel_for_ocr_role(role)
                if wheel is None or not hasattr(wheel, "get_current_names"):
                    continue
                try:
                    for current in wheel.get_current_names():
                        _add(str(current or ""))
                except Exception as exc:
                    self._warn_ocr_suppressed_exception("name_hint_candidates:all_roles_list", exc)

        return names

    def _ocr_name_similarity_score_keys(self, left: str, right: str) -> float:
        left_key = str(left or "").strip()
        right_key = str(right or "").strip()
        if not left_key or not right_key:
            return 0.0
        if left_key == right_key:
            return 1.0

        max_len = max(len(left_key), len(right_key))
        if max_len >= 8:
            len_delta_ratio = abs(len(left_key) - len(right_key)) / max_len
            if len_delta_ratio > 0.45:
                return 0.0

        score = SequenceMatcher(None, left_key, right_key).ratio()
        if left_key in right_key or right_key in left_key:
            score += 0.12
        if left_key[:1] == right_key[:1]:
            score += 0.05
        return min(1.0, score)

    def _apply_ocr_name_hints(self, role_key: str, names: list[str]) -> list[str]:
        if not bool(self._cfg("OCR_USE_NAME_HINTS", False)):
            return list(names or [])
        hints = self._ocr_name_hint_candidates(role_key)
        if not hints:
            return list(names or [])

        min_score = float(self._cfg("OCR_HINT_CORRECTION_MIN_SCORE", 0.62))
        low_conf_min_score = float(self._cfg("OCR_HINT_CORRECTION_LOW_CONF_MIN_SCORE", 0.28))

        hint_entries: list[tuple[str, str]] = []
        seen_hint_keys: set[str] = set()
        for hint in list(hints or []):
            hint_text = str(hint or "").strip()
            hint_key = normalize_ocr_name_key(hint_text)
            if not hint_key or hint_key in seen_hint_keys:
                continue
            seen_hint_keys.add(hint_key)
            hint_entries.append((hint_text, hint_key))
        if not hint_entries:
            return list(names or [])

        normalized_input = [str(value or "").strip() for value in list(names or []) if str(value or "").strip()]
        if not normalized_input:
            return []
        expected = max(5, len(normalized_input))

        corrected: list[str] = []
        used_hints: set[str] = set()
        hint_keys = {hint_key for _hint, hint_key in hint_entries}
        unmatched_input = 0
        short_count = 0

        for raw_name in normalized_input:
            raw_key = normalize_ocr_name_key(raw_name)
            if len(raw_name) <= 3:
                short_count += 1
            best_hint = ""
            best_hint_key = ""
            best_score = 0.0
            for hint, hint_key in hint_entries:
                if not hint_key or hint_key in used_hints:
                    continue
                score = self._ocr_name_similarity_score_keys(raw_key, hint_key)
                if score > best_score:
                    best_score = score
                    best_hint = hint
                    best_hint_key = hint_key
            if best_hint and best_score >= min_score:
                corrected.append(best_hint)
                used_hints.add(best_hint_key)
            else:
                corrected.append(raw_name)
                unmatched_input += 1

        looks_noisy = (
            unmatched_input >= max(1, len(normalized_input) // 2)
            or (short_count / max(1, len(normalized_input))) >= 0.34
        )
        if looks_noisy:
            for idx, raw_name in enumerate(list(corrected)):
                raw_key = normalize_ocr_name_key(raw_name)
                if raw_key in hint_keys:
                    continue
                best_hint = ""
                best_hint_key = ""
                best_score = 0.0
                for hint, hint_key in hint_entries:
                    if not hint_key or hint_key in used_hints:
                        continue
                    score = self._ocr_name_similarity_score_keys(raw_key, hint_key)
                    if score > best_score:
                        best_score = score
                        best_hint = hint
                        best_hint_key = hint_key
                if best_hint and best_score >= low_conf_min_score:
                    corrected[idx] = best_hint
                    used_hints.add(best_hint_key)

            if len(hint_entries) <= (expected + 3):
                for idx, raw_name in enumerate(list(corrected)):
                    if normalize_ocr_name_key(raw_name) in hint_keys:
                        continue
                    replacement = ""
                    replacement_key = ""
                    for hint, hint_key in hint_entries:
                        if not hint_key or hint_key in used_hints:
                            continue
                        replacement = hint
                        replacement_key = hint_key
                        break
                    if replacement:
                        corrected[idx] = replacement
                        used_hints.add(replacement_key)

        deduped: list[str] = []
        seen: set[str] = set()
        for value in corrected:
            key_norm = normalize_ocr_name_key(value)
            if not key_norm or key_norm in seen:
                continue
            seen.add(key_norm)
            deduped.append(value)

        if looks_noisy and len(deduped) < expected:
            for hint, key_norm in hint_entries:
                if not key_norm or key_norm in seen:
                    continue
                deduped.append(hint)
                seen.add(key_norm)
                if len(deduped) >= expected:
                    break

        return deduped

    def _target_wheel_for_ocr_role(self, role_key: str):
        attr_map = {
            "tank": "tank",
            "dps": "dps",
            "support": "support",
        }
        attr = attr_map.get(str(role_key or "").strip().casefold())
        if not attr:
            return None
        return getattr(self, attr, None)

    def _register_role_ocr_button(self, role_key: str, button: QtWidgets.QPushButton) -> None:
        key = str(role_key or "").strip().casefold()
        if not key or button is None:
            return
        self._role_ocr_buttons[key] = button
        self._refresh_role_ocr_button_text(key)

    def _ocr_role_button_meta(self, role_key: str) -> tuple[str, str, int]:
        key = str(role_key or "").strip().casefold()
        meta = {
            "tank": ("ocr.tank_button", "ocr.tank_button_tooltip", 44),
            "dps": ("ocr.dps_button", "ocr.dps_button_tooltip", 44),
            "support": ("ocr.support_button", "ocr.support_button_tooltip", 44),
        }
        return meta.get(key, ("ocr.dps_button", "ocr.dps_button_tooltip", 44))

    def _ocr_role_display_name(self, role_key: str) -> str:
        key = str(role_key or "").strip().casefold()
        labels = {
            "tank": "Tank",
            "dps": "DPS",
            "support": "Support",
        }
        return labels.get(key, key.upper() or "DPS")

    def _refresh_role_ocr_button_text(self, role_key: str) -> None:
        key = str(role_key or "").strip().casefold()
        btn = self._role_ocr_buttons.get(key)
        if btn is None:
            return
        text_key, tooltip_key, padding = self._ocr_role_button_meta(key)
        btn.setText(i18n.t(text_key))
        self._set_ocr_button_tooltip(btn, self._ocr_button_tooltip_text(tooltip_key))
        ui_helpers.set_fixed_width_from_translations([btn], [text_key], padding=max(0, int(padding)))

    def _refresh_all_role_ocr_button_texts(self) -> None:
        for role_key in tuple(self._role_ocr_buttons.keys()):
            self._refresh_role_ocr_button_text(role_key)

    def _role_ocr_import_available(self, role_key: str) -> bool:
        key = str(role_key or "").strip().casefold()
        if getattr(self, "_closing", False):
            return False
        if getattr(self, "pending", 0) > 0:
            return False
        if getattr(self, "current_mode", "") == "maps":
            return False
        if getattr(self, "hero_ban_active", False):
            return False
        if key == "all":
            role_keys = self._ocr_distribution_role_keys()
            return bool(role_keys) and all(self._target_wheel_for_ocr_role(k) is not None for k in role_keys)
        return self._target_wheel_for_ocr_role(key) is not None

    def _ocr_preload_ui_block_active(self) -> bool:
        if not self._ocr_background_preload_enabled():
            return False
        if bool(getattr(self, "_ocr_runtime_activated", False)):
            return False
        if bool(getattr(self, "_ocr_preload_done", False)):
            return False
        return not bool(getattr(self, "_ocr_preload_attempted", False))

    def _ocr_button_tooltip_text(self, default_tooltip_key: str) -> str:
        key = str(default_tooltip_key or "").strip() or "ocr.dps_button_tooltip"
        if self._ocr_preload_ui_block_active():
            return i18n.t("ocr.loading_tooltip")
        return i18n.t(key)

    def _refresh_live_tooltip_for_widget(self, widget: QtWidgets.QWidget, text: str) -> None:
        if widget is None:
            return
        try:
            if not QtWidgets.QToolTip.isVisible():
                return
        except Exception:
            return
        try:
            global_pos = QtGui.QCursor.pos()
        except Exception:
            return
        try:
            local_pos = widget.mapFromGlobal(global_pos)
            if not widget.rect().contains(local_pos):
                return
        except Exception:
            try:
                if not bool(widget.underMouse()):
                    return
            except Exception:
                return
        try:
            QtWidgets.QToolTip.showText(global_pos, str(text or ""), widget, widget.rect())
        except Exception as exc:
            self._warn_ocr_suppressed_exception("refresh_live_tooltip:show_text", exc)

    def _set_ocr_button_tooltip(self, btn: QtWidgets.QWidget, text: str) -> None:
        if btn is None:
            return
        value = str(text or "")
        btn.setToolTip(value)
        self._refresh_live_tooltip_for_widget(btn, value)

    def _update_role_ocr_button_enabled(self, role_key: str) -> None:
        key = str(role_key or "").strip().casefold()
        btn = self._role_ocr_buttons.get(key)
        if btn is None:
            return
        _, tooltip_key, _ = self._ocr_role_button_meta(key)
        enabled = self._role_ocr_import_available(role_key)
        if self._overlay_choice_active():
            enabled = False
        waiting_preload = self._ocr_preload_ui_block_active()
        if waiting_preload:
            enabled = False
        btn.setEnabled(enabled)
        self._set_ocr_button_tooltip(btn, self._ocr_button_tooltip_text(tooltip_key))

    def _update_role_ocr_buttons_enabled(self) -> None:
        waiting_preload = self._ocr_preload_ui_block_active()
        for role_key in tuple(self._role_ocr_buttons.keys()):
            self._update_role_ocr_button_enabled(role_key)
        if hasattr(self, "btn_open_q_ocr"):
            enabled = self._role_ocr_import_available("all")
            if self._overlay_choice_active():
                enabled = False
            if waiting_preload:
                enabled = False
            self.btn_open_q_ocr.setEnabled(enabled)
            self._set_ocr_button_tooltip(
                self.btn_open_q_ocr,
                self._ocr_button_tooltip_text("ocr.open_q_button_tooltip"),
            )

    def _ocr_runtime_sleep_until_used(self) -> bool:
        return bool(self._cfg("OCR_RUNTIME_SLEEP_UNTIL_USED", True))

    def _mark_ocr_runtime_activated(self) -> None:
        self._ocr_runtime_activated = True
        self._ocr_preload_done = True
        self._ocr_preload_attempted = True
        if hasattr(self, "_update_role_ocr_buttons_enabled") and hasattr(self, "_role_ocr_buttons"):
            try:
                self._update_role_ocr_buttons_enabled()
            except Exception as exc:
                self._warn_ocr_suppressed_exception("mark_runtime_activated:update_buttons", exc)
        if hasattr(self, "_cancel_ocr_background_preload"):
            try:
                self._cancel_ocr_background_preload()
            except Exception as exc:
                self._warn_ocr_suppressed_exception("mark_runtime_activated:cancel_preload", exc)

    def _ocr_background_preload_enabled(self) -> bool:
        return bool(self._cfg("OCR_BACKGROUND_PRELOAD_ENABLED", True))

    def _easyocr_resolution_kwargs(self) -> dict[str, object]:
        def _optional_str(key: str) -> str | None:
            value = str(self._cfg(key, "") or "").strip()
            return value or None

        return {
            "lang": _optional_str("OCR_EASYOCR_LANG"),
            "model_dir": _optional_str("OCR_EASYOCR_MODEL_DIR"),
            "user_network_dir": _optional_str("OCR_EASYOCR_USER_NETWORK_DIR"),
            "gpu": self._cfg("OCR_EASYOCR_GPU", "auto"),
            "download_enabled": bool(self._cfg("OCR_EASYOCR_DOWNLOAD_ENABLED", False)),
            "quiet": bool(self._cfg("QUIET", False)),
        }

    def _ensure_ocr_background_preload_timer(self) -> QtCore.QTimer:
        timer = getattr(self, "_ocr_preload_timer", None)
        if timer is not None:
            return timer
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._run_ocr_background_preload)
        if hasattr(self, "_timers"):
            self._timers.register(timer)
        self._ocr_preload_timer = timer
        return timer

    def _cancel_ocr_background_preload(self) -> None:
        timer = getattr(self, "_ocr_preload_timer", None)
        if timer is None:
            return
        try:
            timer.stop()
        except Exception as exc:
            self._warn_ocr_suppressed_exception("cancel_preload_timer:stop", exc)

    def _stop_ocr_background_preload_job(
        self,
        *,
        reason: str = "",
        wait_ms: int = 0,
    ) -> None:
        job = getattr(self, "_ocr_preload_job", None)
        if not isinstance(job, dict):
            self._ocr_preload_job = None
            return
        thread = job.get("thread")
        worker = job.get("worker")
        cancel_slot = getattr(worker, "cancel", None)
        if callable(cancel_slot):
            try:
                cancel_slot()
            except Exception as exc:
                self._warn_ocr_suppressed_exception("stop_preload_job:worker_cancel", exc)
        was_running = False
        if thread is not None:
            try:
                was_running = bool(thread.isRunning())
            except Exception:
                was_running = False
        if was_running:
            try:
                thread.requestInterruption()
            except Exception as exc:
                self._warn_ocr_suppressed_exception("stop_preload_job:request_interruption", exc)
            try:
                thread.quit()
            except Exception as exc:
                self._warn_ocr_suppressed_exception("stop_preload_job:quit", exc)
        waited = False
        if was_running and int(wait_ms) > 0 and thread is not None:
            try:
                waited = bool(thread.wait(int(wait_ms)))
            except Exception:
                waited = False
        if was_running and not waited and thread is not None and hasattr(thread, "terminate"):
            try:
                thread.terminate()
            except Exception as exc:
                self._warn_ocr_suppressed_exception("stop_preload_job:terminate", exc)
        keep_job = bool(was_running and not waited)
        if not keep_job:
            self._ocr_preload_job = None
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "ocr_preload_cancelled",
                    reason=str(reason or "unspecified"),
                    was_running=bool(was_running),
                    waited=bool(waited),
                    keep_job=bool(keep_job),
                )
            except Exception as exc:
                self._warn_ocr_suppressed_exception("stop_preload_job:trace_cancelled", exc)

    def _schedule_ocr_background_preload(
        self,
        *,
        delay_ms: int | None = None,
        reason: str = "",
    ) -> None:
        if getattr(self, "_closing", False):
            return
        if not self._ocr_background_preload_enabled():
            return
        if bool(getattr(self, "_ocr_preload_done", False)):
            return
        if bool(getattr(self, "_ocr_preload_attempted", False)):
            return
        if bool(getattr(self, "_ocr_runtime_activated", False)):
            self._ocr_preload_done = True
            self._ocr_preload_attempted = True
            return
        if getattr(self, "_ocr_async_job", None) or getattr(self, "_ocr_preload_job", None):
            return
        if delay_ms is None:
            delay_ms = int(self._cfg("OCR_BACKGROUND_PRELOAD_DELAY_MS", 2500))
        timer = self._ensure_ocr_background_preload_timer()
        delay = max(0, int(delay_ms))
        timer.start(delay)
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event(
                    "ocr_preload_scheduled",
                    delay_ms=delay,
                    reason=str(reason or "unspecified"),
                )
            except Exception as exc:
                self._warn_ocr_suppressed_exception("schedule_preload:trace_scheduled", exc)

    def _ocr_background_preload_block_reason(self) -> str | None:
        startup_warmup = bool(getattr(self, "_startup_warmup_running", False))
        allow_during_startup = bool(self._cfg("OCR_BACKGROUND_PRELOAD_ALLOW_DURING_STARTUP", True))
        if getattr(self, "_closing", False):
            return "closing"
        if self._overlay_choice_active() and not (startup_warmup and allow_during_startup):
            return "overlay_choice"
        min_uptime_ms = max(0, int(self._cfg("OCR_BACKGROUND_PRELOAD_MIN_UPTIME_MS", 8000)))
        if min_uptime_ms > 0 and not (startup_warmup and allow_during_startup):
            shown_at = getattr(self, "_choice_shown_at", None)
            if shown_at is not None:
                try:
                    elapsed_ms = int((time.monotonic() - float(shown_at)) * 1000.0)
                except Exception:
                    elapsed_ms = min_uptime_ms
                if elapsed_ms < min_uptime_ms:
                    return "startup_cooldown"
        if bool(getattr(self, "_background_services_paused", False)) and not (
            startup_warmup and allow_during_startup
        ):
            return "background_services_paused"
        try:
            if int(getattr(self, "pending", 0) or 0) > 0:
                return "spin_pending"
        except Exception as exc:
            self._warn_ocr_suppressed_exception("preload_block_reason:pending", exc)
        has_spin_anim = getattr(self, "_has_active_spin_animations", None)
        if callable(has_spin_anim):
            try:
                if bool(has_spin_anim(include_internal_flags=True)):
                    return "spin_anim_running"
            except Exception as exc:
                self._warn_ocr_suppressed_exception("preload_block_reason:spin_anim", exc)
        return None

    def _run_ocr_background_preload(self) -> None:
        if getattr(self, "_closing", False):
            return
        if not self._ocr_background_preload_enabled():
            return
        if bool(getattr(self, "_ocr_preload_done", False)):
            return
        if bool(getattr(self, "_ocr_preload_attempted", False)):
            return
        if bool(getattr(self, "_ocr_runtime_activated", False)):
            self._ocr_preload_done = True
            self._ocr_preload_attempted = True
            return
        if getattr(self, "_ocr_async_job", None) or getattr(self, "_ocr_preload_job", None):
            return

        block_reason = self._ocr_background_preload_block_reason()
        if block_reason:
            retry_ms = max(250, int(self._cfg("OCR_BACKGROUND_PRELOAD_BUSY_RETRY_MS", 1800)))
            self._schedule_ocr_background_preload(delay_ms=retry_ms, reason="busy")
            if hasattr(self, "_trace_event"):
                try:
                    self._trace_event(
                        "ocr_preload_deferred",
                        reason=block_reason,
                        retry_ms=retry_ms,
                    )
                except Exception as exc:
                    self._warn_ocr_suppressed_exception("run_preload:trace_deferred", exc)
            return

        kwargs = self._easyocr_resolution_kwargs()
        preload_project_root = str(Path(__file__).resolve().parents[2])
        preload_timeout_s = float(self._cfg("OCR_PRELOAD_SUBPROCESS_TIMEOUT_S", 60.0))
        use_subprocess_probe = bool(self._cfg("OCR_PRELOAD_USE_SUBPROCESS_PROBE", True))
        if bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win"):
            use_subprocess_probe = bool(
                self._cfg("OCR_PRELOAD_USE_SUBPROCESS_PROBE_WIN_FROZEN", False)
            )
        inprocess_cache_warmup = bool(self._cfg("OCR_PRELOAD_INPROCESS_CACHE_WARMUP", True))
        thread = QtCore.QThread(self)
        try:
            thread.setObjectName("ocr_preload_thread")
        except Exception:
            pass
        worker = _OCRPreloadWorker(
            easyocr_kwargs=kwargs,
            project_root=preload_project_root,
            subprocess_timeout_s=preload_timeout_s,
            use_subprocess_probe=use_subprocess_probe,
            inprocess_cache_warmup=inprocess_cache_warmup,
        )
        try:
            worker.setObjectName("ocr_preload_worker")
        except Exception:
            pass
        worker.moveToThread(thread)
        relay = _OCRPreloadRelay(self)
        job = {
            "thread": thread,
            "worker": worker,
            "relay": relay,
        }
        self._ocr_preload_job = job

        def _finalize_preload(ok: bool, detail: str) -> None:
            current = getattr(self, "_ocr_preload_job", None)
            # Allow finalize delivery even if thread.finished already cleared
            # the job reference in a race window; only ignore if a *different*
            # preload job is active.
            if current is not None and current is not job:
                return
            if bool(job.get("_finalized", False)):
                return
            job["_finalized"] = True
            self._ocr_preload_attempted = True
            if bool(ok):
                self._ocr_preload_done = True
                self._ocr_runtime_activated = True
                self._schedule_ocr_runtime_cache_release()
            if hasattr(self, "_update_role_ocr_buttons_enabled"):
                try:
                    self._update_role_ocr_buttons_enabled()
                except Exception as exc:
                    self._warn_ocr_suppressed_exception("run_preload:finalize_update_buttons", exc)
            if hasattr(self, "_trace_event"):
                try:
                    self._trace_event(
                        "ocr_preload_finished",
                        ok=bool(ok),
                        detail=str(detail or ""),
                    )
                except Exception as exc:
                    self._warn_ocr_suppressed_exception("run_preload:finalize_trace_finished", exc)
            # If the worker thread already stopped, clear the job reference now.
            if current is job:
                thread_ref = job.get("thread")
                running = False
                if thread_ref is not None and hasattr(thread_ref, "isRunning"):
                    try:
                        running = bool(thread_ref.isRunning())
                    except Exception:
                        running = False
                if not running:
                    self._ocr_preload_job = None

        def _trace_preload_lifecycle(event_name: str, payload: object) -> None:
            if not hasattr(self, "_trace_event"):
                return
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
                self._trace_event(event, **trace_payload)
            except Exception as exc:
                self._warn_ocr_suppressed_exception("run_preload:lifecycle_trace", exc)

        try:
            job["worker_done_connection"] = worker.finished.connect(
                relay.forward_done,
                QtCore.Qt.QueuedConnection,
            )
        except Exception:
            worker.finished.connect(relay.forward_done, QtCore.Qt.QueuedConnection)
            job["worker_done_connection"] = None
        try:
            job["done_connection"] = relay.done.connect(_finalize_preload)
        except Exception:
            relay.done.connect(_finalize_preload)
            job["done_connection"] = None
        try:
            job["worker_quit_connection"] = worker.finished.connect(thread.quit)
        except Exception:
            worker.finished.connect(thread.quit)
            job["worker_quit_connection"] = None
        try:
            job["lifecycle_connection"] = worker.lifecycle.connect(
                _trace_preload_lifecycle,
                QtCore.Qt.QueuedConnection,
            )
        except Exception:
            worker.lifecycle.connect(_trace_preload_lifecycle, QtCore.Qt.QueuedConnection)
            job["lifecycle_connection"] = None
        def _cleanup_cancelled_preload() -> None:
            current = getattr(self, "_ocr_preload_job", None)
            if current is job:
                self._ocr_preload_job = None
                if hasattr(self, "_trace_event"):
                    try:
                        self._trace_event("ocr_preload_thread_finished")
                    except Exception as exc:
                        self._warn_ocr_suppressed_exception("run_preload:cleanup_trace_finished", exc)
        try:
            job["cleanup_connection"] = thread.finished.connect(_cleanup_cancelled_preload)
        except Exception:
            thread.finished.connect(_cleanup_cancelled_preload)
            job["cleanup_connection"] = None
        try:
            job["started_connection"] = thread.started.connect(worker.run)
        except Exception:
            thread.started.connect(worker.run)
            job["started_connection"] = None
        try:
            job["worker_delete_connection"] = thread.finished.connect(worker.deleteLater)
        except Exception:
            thread.finished.connect(worker.deleteLater)
            job["worker_delete_connection"] = None
        try:
            job["thread_delete_connection"] = thread.finished.connect(thread.deleteLater)
        except Exception:
            thread.finished.connect(thread.deleteLater)
            job["thread_delete_connection"] = None
        if getattr(self, "_closing", False):
            # Close was requested while we prepared the preload job.
            self._ocr_preload_job = None
            try:
                worker.deleteLater()
            except Exception as exc:
                self._warn_ocr_suppressed_exception("run_preload:closing_delete_worker", exc)
            try:
                relay.deleteLater()
            except Exception as exc:
                self._warn_ocr_suppressed_exception("run_preload:closing_delete_relay", exc)
            try:
                thread.deleteLater()
            except Exception as exc:
                self._warn_ocr_suppressed_exception("run_preload:closing_delete_thread", exc)
            return
        startup_warmup = bool(getattr(self, "_startup_warmup_running", False))
        desired_priority = QtCore.QThread.NormalPriority if startup_warmup else QtCore.QThread.LowPriority
        try:
            thread.start(desired_priority)
        except Exception:
            thread.start()

    def _ensure_ocr_cache_release_timer(self) -> QtCore.QTimer:
        timer = getattr(self, "_ocr_cache_release_timer", None)
        if timer is not None:
            return timer
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._release_ocr_runtime_cache)
        if hasattr(self, "_timers"):
            self._timers.register(timer)
        self._ocr_cache_release_timer = timer
        return timer

    def _cancel_ocr_runtime_cache_release(self) -> None:
        timer = getattr(self, "_ocr_cache_release_timer", None)
        if timer is None:
            return
        try:
            timer.stop()
        except Exception as exc:
            self._warn_ocr_suppressed_exception("cancel_cache_release_timer:stop", exc)

    def _schedule_ocr_runtime_cache_release(self) -> None:
        if getattr(self, "_closing", False):
            return
        if bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win"):
            if not bool(getattr(self, "_ocr_cache_release_disabled_trace_logged", False)):
                try:
                    from ..ocr import ocr_runtime_trace

                    ocr_runtime_trace.trace("ocr_cache_release:disabled", reason="win_frozen")
                except Exception:
                    pass
                self._ocr_cache_release_disabled_trace_logged = True
            return
        if getattr(self, "_ocr_async_job", None):
            return
        if self._ocr_runtime_sleep_until_used() and not bool(
            getattr(self, "_ocr_runtime_activated", False)
        ):
            return
        delay_ms = max(0, int(self._cfg("OCR_IDLE_CACHE_RELEASE_MS", 30000)))
        if delay_ms <= 0:
            return
        timer = self._ensure_ocr_cache_release_timer()
        timer.start(delay_ms)
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event("ocr_cache_release_scheduled", delay_ms=delay_ms)
            except Exception as exc:
                self._warn_ocr_suppressed_exception("schedule_cache_release:trace_scheduled", exc)

    def _spin_active_for_ocr_cache_release(self) -> bool:
        try:
            if int(getattr(self, "pending", 0)) > 0:
                return True
        except Exception as exc:
            self._warn_ocr_suppressed_exception("spin_active_for_cache_release:pending", exc)
        role_wheels_fn = getattr(self, "_role_wheels", None)
        if callable(role_wheels_fn):
            try:
                for _role, wheel in role_wheels_fn():
                    try:
                        if hasattr(wheel, "is_anim_running") and bool(wheel.is_anim_running()):
                            return True
                    except Exception:
                        continue
            except Exception as exc:
                self._warn_ocr_suppressed_exception("spin_active_for_cache_release:role_wheels", exc)
        map_main = getattr(self, "map_main", None)
        if map_main is not None and hasattr(map_main, "is_anim_running"):
            try:
                return bool(map_main.is_anim_running())
            except Exception as exc:
                self._warn_ocr_suppressed_exception("spin_active_for_cache_release:map_main", exc)
        return False

    def _release_ocr_runtime_cache(self) -> None:
        if bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win"):
            try:
                from ..ocr import ocr_runtime_trace

                ocr_runtime_trace.trace("ocr_cache_release:skip", reason="win_frozen")
            except Exception:
                pass
            return
        if getattr(self, "_ocr_async_job", None):
            self._schedule_ocr_runtime_cache_release()
            return
        if self._spin_active_for_ocr_cache_release():
            retry_ms = max(200, int(self._cfg("OCR_IDLE_CACHE_RELEASE_BUSY_RETRY_MS", 2500)))
            timer = self._ensure_ocr_cache_release_timer()
            timer.start(retry_ms)
            if hasattr(self, "_trace_event"):
                try:
                    self._trace_event("ocr_cache_release_deferred_busy", retry_ms=retry_ms)
                except Exception as exc:
                    self._warn_ocr_suppressed_exception("release_cache:trace_deferred_busy", exc)
            return
        try:
            from ..ocr import ocr_import
        except Exception:
            return
        release_fn = getattr(ocr_import, "clear_ocr_runtime_caches", None)
        if not callable(release_fn):
            return
        try:
            gpu_setting = str(self._cfg("OCR_EASYOCR_GPU", "auto")).strip().casefold()
            release_gpu = gpu_setting not in {"", "0", "false", "off", "no", "cpu", "none"}
            release_fn(release_gpu=release_gpu)
        except Exception:
            return
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event("ocr_cache_released")
            except Exception as exc:
                self._warn_ocr_suppressed_exception("release_cache:trace_released", exc)

    def _release_ocr_runtime_cache_for_spin(self) -> None:
        """Optionally release OCR runtime cache on spin start."""
        if bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win"):
            try:
                from ..ocr import ocr_runtime_trace

                ocr_runtime_trace.trace("ocr_cache_release_for_spin:skip", reason="win_frozen")
            except Exception:
                pass
            return
        self._cancel_ocr_runtime_cache_release()
        if getattr(self, "_ocr_async_job", None):
            return
        if not bool(self._cfg("OCR_RELEASE_CACHE_ON_SPIN", False)):
            self._schedule_ocr_runtime_cache_release()
            return
        try:
            from ..ocr import ocr_import
        except Exception:
            return
        release_fn = getattr(ocr_import, "clear_ocr_runtime_caches", None)
        if not callable(release_fn):
            return
        try:
            release_fn(
                release_gpu=False,
                collect_garbage=False,
            )
        except Exception:
            return
        if hasattr(self, "_trace_event"):
            try:
                self._trace_event("ocr_cache_released_for_spin")
            except Exception as exc:
                self._warn_ocr_suppressed_exception("release_cache_for_spin:trace_released", exc)

    def _ocr_distribution_role_keys(self) -> tuple[str, ...]:
        return ("tank", "dps", "support")

    def _ocr_subrole_labels_for_role(self, role_key: str) -> list[str]:
        wheel = self._target_wheel_for_ocr_role(role_key)
        if wheel is None:
            return []
        values: list[str] = []
        for raw in getattr(wheel, "subrole_labels", []) or []:
            text = str(raw or "").strip()
            if text:
                values.append(text)
        return values

    def _ocr_assignment_options(
        self,
        role_key: str,
    ) -> tuple[
        list[str],
        dict[str, str],
        dict[str, str],
        str,
    ]:
        key = str(role_key or "").strip().casefold()
        if key == "all":
            labels = [
                i18n.t("ocr.assign_tank"),
                i18n.t("ocr.assign_dps"),
                i18n.t("ocr.assign_support"),
                i18n.t("ocr.assign_main"),
                i18n.t("ocr.assign_flex"),
            ]
            assignment_mapping: dict[str, str] = {}
            subrole_code_mapping: dict[str, str] = {}
            role_codes = self._ocr_distribution_role_keys()
            for idx, role in enumerate(role_codes):
                if idx >= 3:
                    break
                label = labels[idx]
                norm_label = normalize_ocr_name_key(label)
                if not norm_label:
                    continue
                assignment_mapping[norm_label] = role
            main_label_key = normalize_ocr_name_key(labels[3])
            flex_label_key = normalize_ocr_name_key(labels[4])
            if main_label_key:
                subrole_code_mapping[main_label_key] = "main"
            if flex_label_key:
                subrole_code_mapping[flex_label_key] = "flex"
            return labels, assignment_mapping, subrole_code_mapping, "ocr.pick_hint_all_roles"

        labels: list[str] = []
        assignment_mapping = {}
        subrole_code_mapping: dict[str, str] = {}
        for subrole in self._ocr_subrole_labels_for_role(key):
            labels.append(subrole)
            norm_label = normalize_ocr_name_key(subrole)
            if not norm_label:
                continue
            assignment_mapping[norm_label] = key
        return labels, assignment_mapping, subrole_code_mapping, "ocr.pick_hint"

    def _normalize_ocr_candidate_names(self, names: list[str]) -> list[str]:
        # Keep OCR candidates in original order and keep duplicates visible in picker.
        # Duplicate filtering happens during import (add/replace).
        normalized: list[str] = []
        for raw in names or []:
            name = str(raw or "").strip()
            if not name:
                continue
            normalized.append(name)
        return normalized

    def _request_ocr_import_selection(self, role_key: str, names: list[str]) -> bool:
        overlay = getattr(self, "overlay", None)
        if overlay is None:
            return False
        display_names = [str(name).strip() for name in names if str(name).strip()]
        if not display_names:
            return False
        normalized_role_key = str(role_key or "").strip().casefold()
        (
            option_labels,
            option_assignment_by_label_key,
            option_subrole_code_by_label_key,
            hint_key,
        ) = self._ocr_assignment_options(normalized_role_key)
        hint_kwargs: dict[str, str] = {}
        if normalized_role_key != "all":
            hint_kwargs["role"] = self._ocr_role_display_name(normalized_role_key)
        self._pending_ocr_import = PendingOCRImport(
            role_key=normalized_role_key,
            candidates=list(display_names),
            option_labels=list(option_labels),
            option_assignment_by_label_key=dict(option_assignment_by_label_key),
            option_subrole_code_by_label_key=dict(option_subrole_code_by_label_key),
            hint_key=hint_key,
            hint_kwargs=hint_kwargs,
        )
        try:
            overlay.show_ocr_name_picker(
                display_names,
                subrole_labels=option_labels,
                hint_key=hint_key,
                hint_kwargs=hint_kwargs,
            )
        except Exception:
            self._pending_ocr_import = None
            return False
        return True

    def _selected_ocr_entries_for_pending(
        self,
        pending: PendingOCRImport,
        selected_payload,
    ) -> list[dict]:
        pending_role_key = str(pending.role_key or "").strip().casefold()
        allowed_assignments = {
            str(k).strip().casefold(): str(v).strip().casefold()
            for k, v in (pending.option_assignment_by_label_key or {}).items()
            if str(k).strip() and str(v).strip()
        }
        allowed_subrole_options: dict[str, tuple[str, str]] = {}
        if pending_role_key != "all":
            for label in pending.option_labels or []:
                subrole = str(label or "").strip()
                if not subrole:
                    continue
                label_key = normalize_ocr_name_key(subrole)
                if not label_key:
                    continue
                allowed_subrole_options[label_key] = (pending_role_key, subrole)
        allowed_subrole_codes = {
            str(k).strip().casefold(): str(v).strip().casefold()
            for k, v in (pending.option_subrole_code_by_label_key or {}).items()
            if str(k).strip() and str(v).strip()
        }
        role_codes = self._ocr_distribution_role_keys()

        raw_selected: list[dict] = []
        for item in selected_payload or []:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                payload_subroles = item.get("subroles", [])
            else:
                name = str(item or "").strip()
                payload_subroles = []
            if not name:
                continue
            codes: list[str] = []
            subrole_codes: list[str] = []
            subroles_by_role: dict[str, list[str]] = {}
            if isinstance(payload_subroles, (list, tuple, set)):
                for value in payload_subroles:
                    label_key = normalize_ocr_name_key(value)
                    code = allowed_assignments.get(label_key)
                    if code and code in role_codes and code not in codes:
                        codes.append(code)
                    subrole_code = allowed_subrole_codes.get(label_key)
                    if subrole_code in {"main", "flex"} and subrole_code not in subrole_codes:
                        subrole_codes.append(subrole_code)
                    subrole_info = allowed_subrole_options.get(label_key)
                    if subrole_info:
                        subrole_role, subrole_value = subrole_info
                        if subrole_role in role_codes and subrole_role not in codes:
                            codes.append(subrole_role)
                        if subrole_role in role_codes and subrole_value:
                            bucket = subroles_by_role.setdefault(subrole_role, [])
                            if subrole_value not in bucket:
                                bucket.append(subrole_value)
            if subrole_codes and codes:
                for role in codes:
                    bucket = subroles_by_role.setdefault(role, [])
                    for value in self._role_subroles_from_main_flex_codes(role, subrole_codes):
                        if value not in bucket:
                            bucket.append(value)
            raw_selected.append(
                {
                    "name": name,
                    "assignments": codes,
                    "subrole_codes": list(subrole_codes),
                    "subroles_by_role": subroles_by_role,
                }
            )

        selected_names = [entry.get("name", "") for entry in raw_selected]
        names_in_order = resolve_selected_ocr_candidates(pending.candidates, selected_names)

        entries_by_name_key: dict[str, deque[dict]] = {}
        entries_in_order: list[dict] = []
        for entry in raw_selected:
            key = normalize_ocr_name_key(entry.get("name", ""))
            if not key:
                continue
            payload = {
                "name": str(entry.get("name", "")).strip(),
                "assignments": list(entry.get("assignments", [])),
                "subrole_codes": [
                    str(code).strip().casefold()
                    for code in list(entry.get("subrole_codes", []) or [])
                    if str(code).strip()
                ],
                "subroles_by_role": {
                    str(role).strip().casefold(): [
                        str(subrole).strip()
                        for subrole in list(values or [])
                        if str(subrole).strip()
                    ]
                    for role, values in (entry.get("subroles_by_role", {}) or {}).items()
                    if str(role).strip()
                },
            }
            entries_in_order.append(payload)
            queue = entries_by_name_key.setdefault(key, deque())
            queue.append(payload)

        resolved_entries: list[dict] = []
        consumed_payload_ids: set[int] = set()
        for name in names_in_order:
            key = normalize_ocr_name_key(name)
            payload = None
            if key:
                queue = entries_by_name_key.get(key)
                if queue:
                    payload = queue.popleft()
                    consumed_payload_ids.add(id(payload))
            assignments = list((payload or {}).get("assignments", []))
            subrole_codes = list((payload or {}).get("subrole_codes", []))
            subroles_by_role = dict((payload or {}).get("subroles_by_role", {}))
            resolved_entries.append(
                {
                    "name": name,
                    "assignments": assignments,
                    "subrole_codes": subrole_codes,
                    "subroles_by_role": subroles_by_role,
                    "active": True,
                }
            )

        # Keep manual OCR edits/new rows: anything not matched against the
        # original OCR candidates is appended in picker order.
        for entry in entries_in_order:
            if id(entry) in consumed_payload_ids:
                continue
            resolved_entries.append(
                {
                    "name": str(entry.get("name", "")).strip(),
                    "assignments": list(entry.get("assignments", [])),
                    "subrole_codes": list(entry.get("subrole_codes", [])),
                    "subroles_by_role": dict(entry.get("subroles_by_role", {})),
                    "active": True,
                }
            )

        if not resolved_entries:
            return []
        return resolved_entries

    def _role_subroles_from_main_flex_codes(self, role_key: str, codes: list[str] | None) -> list[str]:
        labels = self._ocr_subrole_labels_for_role(role_key)
        if not labels:
            return []
        code_set = {
            str(code).strip().casefold()
            for code in list(codes or [])
            if str(code).strip()
        }
        mapped: list[str] = []
        if "main" in code_set and len(labels) >= 1:
            mapped.append(labels[0])
        if "flex" in code_set and len(labels) >= 2:
            mapped.append(labels[1])
        return mapped

    def _plan_distributed_ocr_entries_for_add(self, entries: list[dict]) -> dict[str, list[dict]]:
        role_keys = self._ocr_distribution_role_keys()
        plan: dict[str, list[dict]] = {role_key: [] for role_key in role_keys}

        existing_by_role: dict[str, set[str]] = {}
        for role_key in role_keys:
            wheel = self._target_wheel_for_ocr_role(role_key)
            role_existing: set[str] = set()
            if wheel is not None and hasattr(wheel, "get_current_names"):
                try:
                    for current_name in wheel.get_current_names():
                        key = normalize_ocr_name_key(current_name)
                        if key:
                            role_existing.add(key)
                except Exception:
                    role_existing = set()
            existing_by_role[role_key] = role_existing

        next_start_idx = 0
        role_count = len(role_keys)
        if role_count <= 0:
            return plan

        for entry in entries or []:
            name = str((entry or {}).get("name", "")).strip()
            if not name:
                continue
            key = normalize_ocr_name_key(name)
            if not key:
                continue
            subroles_by_role = dict((entry or {}).get("subroles_by_role", {}) or {})
            subrole_codes = [
                str(code).strip().casefold()
                for code in list((entry or {}).get("subrole_codes", []) or [])
                if str(code).strip()
            ]
            explicit_targets_raw = list((entry or {}).get("assignments", []) or [])
            explicit_targets: list[str] = []
            for value in explicit_targets_raw:
                role_key = str(value or "").strip().casefold()
                if role_key in role_keys and role_key not in explicit_targets:
                    explicit_targets.append(role_key)

            if explicit_targets:
                for target_role in explicit_targets:
                    if key in existing_by_role.get(target_role, set()):
                        continue
                    role_subroles = [
                        str(subrole).strip()
                        for subrole in list(subroles_by_role.get(target_role, []) or [])
                        if str(subrole).strip()
                    ]
                    if not role_subroles:
                        role_subroles = self._role_subroles_from_main_flex_codes(target_role, subrole_codes)
                    plan[target_role].append({"name": name, "subroles": role_subroles, "active": True})
                    existing_by_role[target_role].add(key)
                continue

            if all(key in existing_by_role.get(role_key, set()) for role_key in role_keys):
                continue

            chosen_idx: int | None = None
            for offset in range(role_count):
                idx = (next_start_idx + offset) % role_count
                role_key = role_keys[idx]
                if key in existing_by_role.get(role_key, set()):
                    continue
                chosen_idx = idx
                break
            if chosen_idx is None:
                continue

            chosen_role = role_keys[chosen_idx]
            role_subroles = [
                str(subrole).strip()
                for subrole in list(subroles_by_role.get(chosen_role, []) or [])
                if str(subrole).strip()
            ]
            if not role_subroles:
                role_subroles = self._role_subroles_from_main_flex_codes(chosen_role, subrole_codes)
            plan[chosen_role].append({"name": name, "subroles": role_subroles, "active": True})
            existing_by_role[chosen_role].add(key)
            next_start_idx = (chosen_idx + 1) % role_count

        return plan

    def _add_ocr_entries_distributed(self, entries: list[dict]) -> tuple[int, dict[str, int]]:
        role_keys = self._ocr_distribution_role_keys()
        added_counts: dict[str, int] = {role_key: 0 for role_key in role_keys}
        planned = self._plan_distributed_ocr_entries_for_add(entries)

        for role_key in role_keys:
            wheel = self._target_wheel_for_ocr_role(role_key)
            if wheel is None or not hasattr(wheel, "add_name"):
                continue
            for entry in planned.get(role_key, []):
                name = str((entry or {}).get("name", "")).strip()
                if not name:
                    continue
                role_subroles = [
                    str(subrole).strip()
                    for subrole in list((entry or {}).get("subroles", []) or [])
                    if str(subrole).strip()
                ]
                if wheel.add_name(name, active=True, subroles=role_subroles):
                    added_counts[role_key] = int(added_counts.get(role_key, 0)) + 1

        total_added = int(sum(added_counts.values()))
        if total_added > 0:
            self.state_sync.save_state()
            self._update_spin_all_enabled()
        return total_added, added_counts

    def _replace_ocr_entries_distributed(self, entries: list[dict]) -> tuple[int, dict[str, int]]:
        role_keys = self._ocr_distribution_role_keys()
        distributed: dict[str, list[dict]] = {role_key: [] for role_key in role_keys}
        if not role_keys:
            return 0, {role_key: 0 for role_key in role_keys}

        unique_names: list[str] = []
        seen_keys: set[str] = set()
        for entry in entries or []:
            name = str((entry or {}).get("name", "")).strip()
            if not name:
                continue
            key = normalize_ocr_name_key(name)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            unique_names.append(name)

        explicit_targets_by_name_key: dict[str, set[str]] = {}
        subrole_codes_by_name_key: dict[str, list[str]] = {}
        subroles_by_name_key: dict[str, dict[str, list[str]]] = {}
        for entry in entries or []:
            name = str((entry or {}).get("name", "")).strip()
            if not name:
                continue
            key = normalize_ocr_name_key(name)
            if not key:
                continue
            explicit_targets = explicit_targets_by_name_key.setdefault(key, set())
            for raw_role in list((entry or {}).get("assignments", []) or []):
                role_key = str(raw_role or "").strip().casefold()
                if role_key in role_keys:
                    explicit_targets.add(role_key)
            subrole_codes_by_name_key[key] = [
                str(code).strip().casefold()
                for code in list((entry or {}).get("subrole_codes", []) or [])
                if str(code).strip()
            ]
            raw_subroles = dict((entry or {}).get("subroles_by_role", {}) or {})
            normalized_subroles: dict[str, list[str]] = {}
            for raw_role, raw_values in raw_subroles.items():
                role = str(raw_role or "").strip().casefold()
                if role not in role_keys:
                    continue
                normalized = [
                    str(value).strip()
                    for value in list(raw_values or [])
                    if str(value).strip()
                ]
                if normalized:
                    normalized_subroles[role] = normalized
            if normalized_subroles:
                subroles_by_name_key[key] = normalized_subroles

        next_start_idx = 0
        for name in unique_names:
            key = normalize_ocr_name_key(name)
            explicit_targets = sorted(explicit_targets_by_name_key.get(key, set()))
            subrole_codes = list(subrole_codes_by_name_key.get(key, []))
            subroles_for_name = dict(subroles_by_name_key.get(key, {}))
            if explicit_targets:
                for role_key in explicit_targets:
                    role_subroles = list(subroles_for_name.get(role_key, []))
                    if not role_subroles:
                        role_subroles = self._role_subroles_from_main_flex_codes(role_key, subrole_codes)
                    distributed[role_key].append(
                        {
                            "name": name,
                            "subroles": role_subroles,
                            "active": True,
                        }
                    )
                continue

            role_key = role_keys[next_start_idx % len(role_keys)]
            role_subroles = list(subroles_for_name.get(role_key, []))
            if not role_subroles:
                role_subroles = self._role_subroles_from_main_flex_codes(role_key, subrole_codes)
            distributed[role_key].append(
                {
                    "name": name,
                    "subroles": role_subroles,
                    "active": True,
                }
            )
            next_start_idx = (next_start_idx + 1) % len(role_keys)

        assigned_counts: dict[str, int] = {role_key: 0 for role_key in role_keys}
        for role_key in role_keys:
            wheel = self._target_wheel_for_ocr_role(role_key)
            if wheel is None or not hasattr(wheel, "load_entries"):
                continue
            entries_for_role: list[dict] = []
            for entry in distributed.get(role_key, []):
                name = str((entry or {}).get("name", "")).strip()
                if not name:
                    continue
                entries_for_role.append(
                    {
                        "name": name,
                        "subroles": [
                            str(subrole).strip()
                            for subrole in list((entry or {}).get("subroles", []) or [])
                            if str(subrole).strip()
                        ],
                        "active": True,
                    }
                )
            wheel.load_entries(entries_for_role)
            assigned_counts[role_key] = len(entries_for_role)

        total_assigned = int(sum(assigned_counts.values()))
        self.state_sync.save_state()
        self._update_spin_all_enabled()
        return total_assigned, assigned_counts

    def _add_ocr_entries_for_role(self, role_key: str, entries: list[dict]) -> int:
        wheel = self._target_wheel_for_ocr_role(role_key)
        if wheel is None or not hasattr(wheel, "add_name"):
            return 0
        normalized_role_key = str(role_key or "").strip().casefold()
        added = 0
        for entry in entries or []:
            name = str((entry or {}).get("name", "")).strip()
            if not name:
                continue
            subroles_by_role = dict((entry or {}).get("subroles_by_role", {}) or {})
            role_subroles = [
                str(subrole).strip()
                for subrole in list(subroles_by_role.get(normalized_role_key, []) or [])
                if str(subrole).strip()
            ]
            if not role_subroles:
                role_subroles = self._role_subroles_from_main_flex_codes(
                    normalized_role_key,
                    list((entry or {}).get("subrole_codes", []) or []),
                )
            if wheel.add_name(name, active=True, subroles=role_subroles):
                added += 1
        if added > 0:
            self.state_sync.save_state()
            self._update_spin_all_enabled()
        return added

    def _replace_ocr_entries_for_role(self, role_key: str, entries: list[dict]) -> int:
        wheel = self._target_wheel_for_ocr_role(role_key)
        if wheel is None or not hasattr(wheel, "load_entries"):
            return 0
        normalized_role_key = str(role_key or "").strip().casefold()
        unique_names: list[str] = []
        seen_keys: set[str] = set()
        subroles_by_name_key: dict[str, list[str]] = {}
        for entry in entries or []:
            name = str((entry or {}).get("name", "")).strip()
            if not name:
                continue
            key = normalize_ocr_name_key(name)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            unique_names.append(name)
            subrole_codes = [
                str(code).strip().casefold()
                for code in list((entry or {}).get("subrole_codes", []) or [])
                if str(code).strip()
            ]
            raw_subroles = dict((entry or {}).get("subroles_by_role", {}) or {})
            role_subroles = [
                str(subrole).strip()
                for subrole in list(raw_subroles.get(normalized_role_key, []) or [])
                if str(subrole).strip()
            ]
            if not role_subroles:
                role_subroles = self._role_subroles_from_main_flex_codes(
                    normalized_role_key,
                    subrole_codes,
                )
            subroles_by_name_key[key] = role_subroles
        wheel.load_entries(
            [
                {
                    "name": name,
                    "subroles": list(subroles_by_name_key.get(normalize_ocr_name_key(name), [])),
                    "active": True,
                }
                for name in unique_names
            ]
        )
        self.state_sync.save_state()
        self._update_spin_all_enabled()
        return len(unique_names)

    def _show_ocr_import_result_for_role(self, role_key: str, *, added: int, total: int) -> None:
        role_name = self._ocr_role_display_name(role_key)
        if added > 0:
            message = i18n.t(
                "ocr.result_added_role",
                added=added,
                total=total,
                role=role_name,
            )
        else:
            message = i18n.t("ocr.result_duplicates_only_role", total=total, role=role_name)
        QtWidgets.QMessageBox.information(self, i18n.t("ocr.result_title"), message)

    def _show_ocr_import_result_distributed(self, *, added: int, total: int, counts: dict[str, int]) -> None:
        if added > 0:
            message = i18n.t(
                "ocr.result_added_distributed",
                added=added,
                total=total,
                tank=int(counts.get("tank", 0)),
                dps=int(counts.get("dps", 0)),
                support=int(counts.get("support", 0)),
            )
        else:
            message = i18n.t("ocr.result_duplicates_only_distributed", total=total)
        QtWidgets.QMessageBox.information(self, i18n.t("ocr.result_title"), message)

    def _on_overlay_ocr_import_confirmed(self, selected_names):
        pending = getattr(self, "_pending_ocr_import", None)
        self._pending_ocr_import = None
        if pending is None:
            return
        entries_to_add = self._selected_ocr_entries_for_pending(pending, selected_names)
        if not entries_to_add:
            QtWidgets.QMessageBox.information(
                self,
                i18n.t("ocr.result_title"),
                i18n.t("ocr.result_none_selected"),
            )
            return
        target_key = str(getattr(pending, "role_key", "") or "").strip().casefold()
        if target_key == "all":
            added, added_counts = self._add_ocr_entries_distributed(entries_to_add)
            self._show_ocr_import_result_distributed(added=added, total=len(entries_to_add), counts=added_counts)
            return
        added = self._add_ocr_entries_for_role(target_key, entries_to_add)
        self._show_ocr_import_result_for_role(target_key, added=added, total=len(entries_to_add))

    def _on_overlay_ocr_import_replace_requested(self, selected_names):
        pending = getattr(self, "_pending_ocr_import", None)
        self._pending_ocr_import = None
        if pending is None:
            return
        entries_to_replace = self._selected_ocr_entries_for_pending(pending, selected_names)
        if not entries_to_replace:
            QtWidgets.QMessageBox.information(
                self,
                i18n.t("ocr.result_title"),
                i18n.t("ocr.result_none_selected"),
            )
            return
        target_key = str(getattr(pending, "role_key", "") or "").strip().casefold()
        if target_key == "all":
            total, assigned_counts = self._replace_ocr_entries_distributed(entries_to_replace)
            QtWidgets.QMessageBox.information(
                self,
                i18n.t("ocr.result_title"),
                i18n.t(
                    "ocr.result_replaced_distributed",
                    total=total,
                    tank=int(assigned_counts.get("tank", 0)),
                    dps=int(assigned_counts.get("dps", 0)),
                    support=int(assigned_counts.get("support", 0)),
                ),
            )
            return
        total = self._replace_ocr_entries_for_role(target_key, entries_to_replace)
        QtWidgets.QMessageBox.information(
            self,
            i18n.t("ocr.result_title"),
            i18n.t(
                "ocr.result_replaced_role",
                role=self._ocr_role_display_name(target_key),
                total=total,
            ),
        )

    def _on_overlay_ocr_import_cancelled(self):
        self._pending_ocr_import = None
