from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os
import sys
import threading
import time

from services import settings_provider


_TRACE_LOCK = threading.Lock()
_TRACE_HEADER_WRITTEN = False


def _settings():
    return settings_provider.get_settings()


def _cfg_bool(key: str, default: bool) -> bool:
    try:
        return bool(_settings().resolve(key, default))
    except (AttributeError, TypeError, ValueError):
        return bool(default)


def _cfg_int(key: str, default: int) -> int:
    try:
        return int(_settings().resolve(key, default))
    except (AttributeError, TypeError, ValueError):
        return int(default)


def _cfg_str(key: str, default: str) -> str:
    try:
        value = str(_settings().resolve(key, default) or "").strip()
    except (AttributeError, TypeError, ValueError):
        value = ""
    return value or str(default)


def _trace_enabled() -> bool:
    if _cfg_bool("QUIET", False):
        return False
    return _cfg_bool("TRACE_OCR_RUNTIME", False)


def _state_base_dir() -> Path:
    if bool(getattr(sys, "frozen", False)):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def _resolve_log_root() -> Path:
    configured = _cfg_str("LOG_OUTPUT_DIR", "logs")
    state_dir = _state_base_dir()
    if not configured:
        return state_dir
    configured_path = Path(configured).expanduser()
    if configured_path.is_absolute():
        return configured_path
    return state_dir / configured_path


def _resolve_trace_file() -> Path:
    configured = _cfg_str("OCR_RUNTIME_TRACE_FILE", "ocr_runtime_trace.log")
    if not configured:
        configured = "ocr_runtime_trace.log"
    path = Path(configured).expanduser()
    if path.is_absolute():
        return path
    return _resolve_log_root() / path


def _line_value(value) -> str:
    text = str(value)
    text = text.replace("\n", "\\n").replace("\r", "\\r")
    max_len = 1200
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def _trim_trace_if_needed(path: Path) -> None:
    max_bytes = _cfg_int("OCR_RUNTIME_TRACE_MAX_BYTES", 0)
    if max_bytes <= 0:
        return
    try:
        if not path.exists():
            return
        size = int(path.stat().st_size)
        if size <= max_bytes:
            return
        keep = max(64 * 1024, max_bytes // 2)
        with path.open("rb") as handle:
            handle.seek(max(0, size - keep))
            tail = handle.read()
        newline = tail.find(b"\n")
        if newline >= 0:
            tail = tail[newline + 1 :]
        with path.open("wb") as handle:
            handle.write(tail)
            handle.write(b"\n")
            handle.write(b"...<trimmed older OCR runtime trace entries>...\n")
    except OSError:
        return


def trace(event: str, **fields) -> None:
    if not _trace_enabled():
        return
    name = str(event or "").strip() or "event"
    now = datetime.now(timezone.utc).astimezone()
    mono = time.monotonic()
    base = [
        f"ts={now.isoformat(timespec='milliseconds')}",
        f"mono={round(mono, 3)}",
        f"pid={os.getpid()}",
        f"tid={threading.get_ident()}",
        f"thread={_line_value(threading.current_thread().name)}",
        f"event={_line_value(name)}",
    ]
    for key, value in fields.items():
        base.append(f"{_line_value(key)}={_line_value(value)}")
    line = " | ".join(base)

    path = _resolve_trace_file()
    with _TRACE_LOCK:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _trim_trace_if_needed(path)
            global _TRACE_HEADER_WRITTEN
            with path.open("a", encoding="utf-8") as handle:
                if not _TRACE_HEADER_WRITTEN:
                    handle.write(
                        f"=== ocr_runtime_trace run pid={os.getpid()} exe={_line_value(sys.executable)} ===\n"
                    )
                    _TRACE_HEADER_WRITTEN = True
                handle.write(line + "\n")
        except OSError:
            return
