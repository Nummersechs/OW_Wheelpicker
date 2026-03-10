from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import warnings

from PySide6 import QtCore


class OCRPreloadWorker(QtCore.QObject):
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
        except (TypeError, ValueError):
            self._subprocess_timeout_s = 60.0

    def _trace_runtime(self, event: str, **payload) -> None:
        try:
            from . import ocr_runtime_trace

            ocr_runtime_trace.trace(str(event or ""), **payload)
        except Exception:
            pass

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
        self._trace_runtime(
            "ocr_preload_worker:subprocess_stop_requested",
            where=str(where or ""),
            child_pid=child_pid,
        )
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
            self._trace_runtime(
                "ocr_preload_worker:subprocess_stopped",
                where=str(where or ""),
                child_pid=child_pid,
                mode="terminate",
            )
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
        self._trace_runtime(
            "ocr_preload_worker:subprocess_stopped",
            where=str(where or ""),
            child_pid=child_pid,
            mode="kill",
        )
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
            from . import ocr_import
        except Exception as exc:
            return False, f"inprocess-import-error:{exc!r}"

        self._trace_runtime("ocr_preload_worker:inprocess_warmup_start")

        availability_fn = getattr(ocr_import, "easyocr_available", None)
        if not callable(availability_fn):
            return False, "inprocess-availability-missing"
        try:
            ok = bool(availability_fn(**self._easyocr_kwargs))
        except Exception as exc:
            return False, f"inprocess-availability-error:{exc!r}"
        if ok:
            self._trace_runtime("ocr_preload_worker:inprocess_warmup_done", ok=True)
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
        self._trace_runtime(
            "ocr_preload_worker:inprocess_warmup_done",
            ok=False,
            detail=str(detail or ""),
        )
        return False, detail

    @QtCore.Slot()
    def run(self) -> None:
        self._trace_runtime("ocr_preload_worker:start", frozen=bool(getattr(sys, "frozen", False)))

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

        try:
            QtCore.QThread.setTerminationEnabled(True)
        except Exception as exc:
            self._warn_suppressed_exception("worker_run:set_termination_enabled", exc)
        if _interrupted():
            self._trace_runtime("ocr_preload_worker:interrupted_early")
            self.finished.emit(False, "interrupted")
            return

        if not bool(self._use_subprocess_probe):
            self._trace_runtime("ocr_preload_worker:inprocess_only_mode")
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
            self._trace_runtime("ocr_preload_worker:subprocess_start_error", error=repr(exc))
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
        self._trace_runtime(
            "ocr_preload_worker:subprocess_spawned",
            child_pid=child_pid,
            timeout_s=float(self._subprocess_timeout_s),
        )
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
                    self._trace_runtime(
                        "ocr_preload_worker:subprocess_interrupted",
                        child_pid=child_pid,
                        runtime_ms=int((time.monotonic() - started_at) * 1000.0),
                    )
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
                    self._trace_runtime(
                        "ocr_preload_worker:subprocess_exited",
                        child_pid=child_pid,
                        returncode=int(rc),
                        runtime_ms=int((time.monotonic() - started_at) * 1000.0),
                    )
                    self._emit_lifecycle(
                        "ocr_preload_worker:subprocess_exited",
                        child_pid=child_pid,
                        returncode=int(rc),
                        runtime_ms=int((time.monotonic() - started_at) * 1000.0),
                    )
                    break
                if (time.monotonic() - started_at) >= self._subprocess_timeout_s:
                    self._trace_runtime(
                        "ocr_preload_worker:subprocess_timeout",
                        child_pid=child_pid,
                        timeout_s=float(self._subprocess_timeout_s),
                        runtime_ms=int((time.monotonic() - started_at) * 1000.0),
                    )
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
                self._trace_runtime(
                    "ocr_preload_worker:subprocess_error",
                    child_pid=child_pid,
                    returncode=int(proc.returncode or 1),
                    message=message,
                )
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
            self._trace_runtime("ocr_preload_worker:done", ok=bool(ok), detail=str(detail or ""))
            self.finished.emit(ok, detail or ("ready" if ok else "not-ready"))
        finally:
            self._clear_proc(proc)


class OCRPreloadRelay(QtCore.QObject):
    done = QtCore.Signal(bool, str)

    @QtCore.Slot(bool, str)
    def forward_done(self, ok: bool, detail: str) -> None:
        self.done.emit(bool(ok), str(detail or ""))
