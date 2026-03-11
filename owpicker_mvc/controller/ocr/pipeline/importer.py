from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
import importlib
from pathlib import Path
import gc
import os
import sys
import threading
import time
import types
from typing import Any, Iterable
from . import easyocr_token_utils as _easyocr_token_utils
from . import name_extraction as _ocr_name_extraction
from ..runtime import trace as _ocr_runtime_trace


@dataclass
class OCRRunResult:
    text: str
    error: str | None = None
    lines: tuple["OCRLineResult", ...] = ()


@dataclass(frozen=True)
class OCRLineResult:
    text: str
    confidence: float = -1.0


_EASYOCR_LANG_ALIAS: dict[str, str] = {
    "eng": "en",
    "en": "en",
    "deu": "de",
    "ger": "de",
    "german": "de",
    "deutsch": "de",
    "de": "de",
    "ja": "ja",
    "jpn": "ja",
    "jp": "ja",
    "japanese": "ja",
    "ko": "ko",
    "kor": "ko",
    "kr": "ko",
    "korean": "ko",
    "zh": "ch_sim",
    "zho": "ch_sim",
    "chi": "ch_sim",
    "cn": "ch_sim",
    "ch": "ch_sim",
    "chs": "ch_sim",
    "zh-cn": "ch_sim",
    "zh_hans": "ch_sim",
    "ch_sim": "ch_sim",
    "cht": "ch_tra",
    "zh-tw": "ch_tra",
    "zh-hk": "ch_tra",
    "zh_hant": "ch_tra",
    "ch_tra": "ch_tra",
}
_EASYOCR_RESTRICTED_LANGS: set[str] = {"ch_sim", "ch_tra", "ja", "ko"}
_EASYOCR_IMPORT_LOCK = threading.Lock()
_TORCH_RUNTIME_IMPORT_LOCK = threading.RLock()
_EASYOCR_IMPORT_FAILURE_TTL_FATAL_S = 45.0
_EASYOCR_IMPORT_FAILURE_TTL_SOFT_S = 15.0
_EASYOCR_IMPORT_FAILURE_UNTIL_MONO = 0.0
_EASYOCR_IMPORT_FAILURE_TEXT: str | None = None
_EASYOCR_IMPORT_FAILURE_FATAL = False
_OCR_IMPORT_GUARD_ERRORS = (
    AttributeError,
    RuntimeError,
    TypeError,
    ValueError,
    LookupError,
    OSError,
    ImportError,
    ModuleNotFoundError,
    AssertionError,
    SystemError,
    UnicodeError,
)


def _looks_like_partial_torch_import_error(exc: Exception) -> bool:
    text = str(exc or "").strip().lower()
    if not text:
        return False
    if "partially initialized module 'torch'" in text:
        return True
    if "cannot import name 'nn' from partially initialized module 'torch'" in text:
        return True
    return False


def _looks_like_torch_docstring_reimport_error(exc: Exception) -> bool:
    text = str(exc or "").strip().lower()
    if not text:
        return False
    return "_has_torch_function" in text and "already has a docstring" in text


def _looks_like_torchvision_ops_missing_error(exc: Exception) -> bool:
    text = str(exc or "").strip().lower()
    if not text:
        return False
    if "operator torchvision::nms does not exist" in text:
        return True
    if "torchvision::nms" in text and "does not exist" in text:
        return True
    if "couldn't load custom c++ ops" in text and "torchvision" in text:
        return True
    if "no module named" in text and "torchvision._c" in text:
        return True
    return False


def _looks_like_torch_source_unavailable_error(exc: Exception) -> bool:
    text = str(exc or "").strip().lower()
    if not text:
        return False
    return ("source code" in text) and ("could not get" in text or "not available" in text)


def _looks_like_torch_related_error(exc: Exception) -> bool:
    text = str(exc or "").strip().lower()
    if not text:
        return False
    return "torch" in text or "easyocr" in text


def _looks_like_missing_torch_rpc_module_error(exc: Exception) -> bool:
    text = str(exc or "").strip().lower()
    if not text:
        return False
    return ("no module named" in text) and ("torch.distributed.rpc" in text)


def _set_easyocr_import_failure_cache(
    error: Exception | str,
    *,
    fatal: bool,
    ttl_s: float,
) -> None:
    global _EASYOCR_IMPORT_FAILURE_UNTIL_MONO
    global _EASYOCR_IMPORT_FAILURE_TEXT
    global _EASYOCR_IMPORT_FAILURE_FATAL
    error_text = str(error or "").strip() or "unknown-easyocr-import-error"
    _EASYOCR_IMPORT_FAILURE_TEXT = error_text
    _EASYOCR_IMPORT_FAILURE_FATAL = bool(fatal)
    _EASYOCR_IMPORT_FAILURE_UNTIL_MONO = time.monotonic() + max(0.0, float(ttl_s))


def _clear_easyocr_import_failure_cache() -> None:
    global _EASYOCR_IMPORT_FAILURE_UNTIL_MONO
    global _EASYOCR_IMPORT_FAILURE_TEXT
    global _EASYOCR_IMPORT_FAILURE_FATAL
    _EASYOCR_IMPORT_FAILURE_UNTIL_MONO = 0.0
    _EASYOCR_IMPORT_FAILURE_TEXT = None
    _EASYOCR_IMPORT_FAILURE_FATAL = False


def _active_easyocr_import_failure_cache() -> tuple[str | None, bool]:
    error_text = str(_EASYOCR_IMPORT_FAILURE_TEXT or "").strip()
    if not error_text:
        return None, False
    if time.monotonic() >= float(_EASYOCR_IMPORT_FAILURE_UNTIL_MONO):
        _clear_easyocr_import_failure_cache()
        return None, False
    return error_text, bool(_EASYOCR_IMPORT_FAILURE_FATAL)


def _reader_error_is_global_import_failure(reader_error: str | None) -> bool:
    token = str(reader_error or "").strip().lower()
    if not token:
        return False
    if "easyocr-import-error:" in token:
        return True
    if "operator torchvision::nms does not exist" in token:
        return True
    if "_has_torch_function" in token and "already has a docstring" in token:
        return True
    if "torchvision._c" in token and "no module named" in token:
        return True
    if "couldn't load custom c++ ops" in token and "torchvision" in token:
        return True
    return False


def _install_torch_distributed_rpc_stub() -> bool:
    existing = sys.modules.get("torch.distributed.rpc")
    if existing is not None:
        return False
    try:
        rpc_stub = types.ModuleType("torch.distributed.rpc")
        rpc_stub.__dict__["__package__"] = "torch.distributed"
        rpc_stub.__dict__["__file__"] = "<owpicker-rpc-stub>"

        def _rpc_unavailable(*_args, **_kwargs):
            raise RuntimeError("torch.distributed.rpc unavailable in this runtime build")

        rpc_stub.is_available = lambda: False
        rpc_stub.init_rpc = _rpc_unavailable
        rpc_stub.shutdown = _rpc_unavailable
        rpc_stub.rpc_sync = _rpc_unavailable
        rpc_stub.rpc_async = _rpc_unavailable
        rpc_stub.remote = _rpc_unavailable
        rpc_stub.__all__ = (
            "is_available",
            "init_rpc",
            "shutdown",
            "rpc_sync",
            "rpc_async",
            "remote",
        )
        sys.modules["torch.distributed.rpc"] = rpc_stub
        parent = sys.modules.get("torch.distributed")
        if parent is not None and getattr(parent, "rpc", None) is None:
            try:
                setattr(parent, "rpc", rpc_stub)
            except _OCR_IMPORT_GUARD_ERRORS:
                pass
        return True
    except _OCR_IMPORT_GUARD_ERRORS:
        return False


def _purge_import_modules(prefixes: tuple[str, ...]) -> int:
    """
    Best-effort cleanup for broken partial-import states.
    Used only after transient torch/easyocr import failures.
    """
    normalized = tuple(str(prefix or "").strip() for prefix in tuple(prefixes or ()) if str(prefix or "").strip())
    if not normalized:
        return 0
    removed = 0
    for name in list(sys.modules.keys()):
        token = str(name or "")
        for prefix in normalized:
            if token == prefix or token.startswith(prefix + "."):
                try:
                    sys.modules.pop(token, None)
                    removed += 1
                except _OCR_IMPORT_GUARD_ERRORS:
                    pass
                break
    try:
        importlib.invalidate_caches()
    except _OCR_IMPORT_GUARD_ERRORS:
        pass
    return removed


def _import_torch_module():
    with _TORCH_RUNTIME_IMPORT_LOCK:
        is_win_frozen = bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win")
        if is_win_frozen:
            # Torch can inspect Python source while importing JIT internals.
            # In frozen builds this may fail with "could not get source code".
            os.environ.setdefault("PYTORCH_JIT", "0")
        _ocr_runtime_trace.trace(
            "torch_import:start",
            frozen=bool(getattr(sys, "frozen", False)),
            executable=sys.executable,
        )
        try:
            import torch  # type: ignore
        except _OCR_IMPORT_GUARD_ERRORS as exc:
            if _looks_like_missing_torch_rpc_module_error(exc):
                installed = _install_torch_distributed_rpc_stub()
                _ocr_runtime_trace.trace(
                    "torch_import:rpc_stub",
                    installed=bool(installed),
                    error=repr(exc),
                )
                if installed:
                    try:
                        import torch  # type: ignore
                    except _OCR_IMPORT_GUARD_ERRORS as retry_exc:
                        _ocr_runtime_trace.trace("torch_import:error", error=repr(retry_exc))
                        raise
                else:
                    _ocr_runtime_trace.trace("torch_import:error", error=repr(exc))
                    raise
            else:
                _ocr_runtime_trace.trace("torch_import:error", error=repr(exc))
                raise
    _ocr_runtime_trace.trace(
        "torch_import:ok",
        torch_file=getattr(torch, "__file__", None),
        torch_version=getattr(torch, "__version__", None),
    )
    return torch


def _parse_ocr_lang_tokens(value: str | None) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    normalized = raw.replace("+", ",").replace(";", ",")
    tokens = [token.strip() for token in normalized.split(",") if token.strip()]
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(token)
    return result


def _parse_easyocr_langs(lang: str | None) -> tuple[str, ...]:
    raw_tokens = _parse_ocr_lang_tokens(lang)
    if not raw_tokens:
        return ("en",)
    normalized: list[str] = []
    seen: set[str] = set()
    for token in raw_tokens:
        key = token.lower()
        mapped = _EASYOCR_LANG_ALIAS.get(key)
        if mapped is None:
            if len(key) == 2 and key.isalpha():
                mapped = key
            else:
                continue
        if mapped in seen:
            continue
        seen.add(mapped)
        normalized.append(mapped)
    if not normalized:
        return ("en",)
    return tuple(normalized)


def _build_easyocr_lang_groups(langs: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    resolved = tuple(str(value or "").strip().lower() for value in tuple(langs or ()) if str(value or "").strip())
    if not resolved:
        return (("en",),)

    groups: list[tuple[str, ...]] = []
    has_en = "en" in resolved
    general = [lang for lang in resolved if lang not in _EASYOCR_RESTRICTED_LANGS and lang != "en"]
    if general:
        group: list[str] = []
        if has_en:
            group.append("en")
        group.extend(general)
        groups.append(tuple(group))

    for lang in resolved:
        if lang not in _EASYOCR_RESTRICTED_LANGS:
            continue
        # EasyOCR allows these CJK models reliably only in an EN pair.
        group = [lang]
        if lang != "en":
            group.append("en")
        groups.append(tuple(group))

    if not groups:
        groups.append(resolved)

    deduped: list[tuple[str, ...]] = []
    seen: set[str] = set()
    for group in groups:
        normalized_group: list[str] = []
        seen_group: set[str] = set()
        for lang in group:
            token = str(lang or "").strip().lower()
            if not token or token in seen_group:
                continue
            seen_group.add(token)
            normalized_group.append(token)
        if not normalized_group:
            continue
        key = "|".join(normalized_group)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(tuple(normalized_group))

    if not deduped:
        return (("en",),)
    return tuple(deduped)


def _normalize_easyocr_gpu_mode(value: bool | str | None) -> str:
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"", "auto", "best", "gpu", "true", "1", "yes", "on"}:
            return "auto"
        if token in {"cpu", "false", "0", "no", "off"}:
            return "cpu"
        if token in {"cuda", "mps"}:
            return token
        return "auto"
    return "auto" if bool(value) else "cpu"


@lru_cache(maxsize=1)
def _torch_device_support() -> tuple[bool, bool]:
    try:
        torch = _import_torch_module()
    except _OCR_IMPORT_GUARD_ERRORS:
        return (False, False)
    has_cuda = False
    has_mps = False
    try:
        has_cuda = bool(torch.cuda.is_available())
    except _OCR_IMPORT_GUARD_ERRORS:
        has_cuda = False
    try:
        has_mps = bool(torch.backends.mps.is_available())
    except _OCR_IMPORT_GUARD_ERRORS:
        has_mps = False
    return (has_cuda, has_mps)


def _resolve_easyocr_device(mode: str) -> str:
    normalized = _normalize_easyocr_gpu_mode(mode)
    if normalized == "cpu":
        return "cpu"
    has_cuda = False
    has_mps = False
    # In frozen onefile builds, probing torch before the first real OCR import
    # can trigger unstable partial-import states on some Windows setups.
    # Keep auto mode conservative there; explicit "cuda"/"mps" still probes.
    if normalized in {"cuda", "mps"} or not bool(getattr(sys, "frozen", False)):
        has_cuda, has_mps = _torch_device_support()
    if normalized == "cuda":
        return "cuda" if has_cuda else "cpu"
    if normalized == "mps":
        return "mps" if has_mps else "cpu"
    if has_cuda:
        return "cuda"
    if has_mps:
        return "mps"
    return "cpu"


@contextmanager
def _patch_dataloader_pin_memory(enable: bool):
    """
    EasyOCR hard-codes pin_memory=True in its DataLoader construction.
    On non-CUDA backends (CPU/MPS) this is unnecessary and may emit warnings.
    Patch only for the OCR call scope and restore afterwards.
    """
    if not bool(enable):
        yield
        return
    try:
        torch = _import_torch_module()
    except _OCR_IMPORT_GUARD_ERRORS:
        yield
        return
    data_ns = getattr(getattr(torch, "utils", None), "data", None)
    original_loader = getattr(data_ns, "DataLoader", None) if data_ns is not None else None
    if original_loader is None:
        yield
        return

    def _patched_loader(*args, **kwargs):
        if kwargs.get("pin_memory") is True:
            kwargs = dict(kwargs)
            kwargs["pin_memory"] = False
        return original_loader(*args, **kwargs)

    setattr(data_ns, "DataLoader", _patched_loader)
    try:
        yield
    finally:
        try:
            if getattr(data_ns, "DataLoader", None) is _patched_loader:
                setattr(data_ns, "DataLoader", original_loader)
        except _OCR_IMPORT_GUARD_ERRORS:
            pass


def _resolve_optional_directory(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    probe_paths = [candidate]
    if not candidate.is_absolute():
        for root in _runtime_search_roots():
            probe_paths.append(root / candidate)
    for probe in probe_paths:
        if probe.is_dir():
            try:
                return str(probe.resolve())
            except _OCR_IMPORT_GUARD_ERRORS:
                return str(probe)
    return str(candidate)


def _looks_like_easyocr_model_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        return any(
            entry.is_file() and entry.suffix.lower() in {".pth", ".pt"}
            for entry in path.iterdir()
        )
    except _OCR_IMPORT_GUARD_ERRORS:
        return False


def _discover_easyocr_model_dir() -> str | None:
    hints = (
        Path("EasyOCR/model"),
        Path("easyocr/model"),
    )
    candidates: list[Path] = []
    for root in _runtime_search_roots():
        for rel in hints:
            candidates.append(root / rel)
    candidates.append(Path.home() / ".EasyOCR" / "model")
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve()).lower()
        except _OCR_IMPORT_GUARD_ERRORS:
            key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if _looks_like_easyocr_model_dir(candidate):
            try:
                return str(candidate.resolve())
            except _OCR_IMPORT_GUARD_ERRORS:
                return str(candidate)
    return None


def _import_easyocr_module() -> tuple[Any | None, str | None]:
    # Serialize easyocr/torch imports to avoid transient partial-init states in
    # packaged Windows runs where OCR may warm up while user triggers OCR.
    with _EASYOCR_IMPORT_LOCK:
        cached_error, cached_fatal = _active_easyocr_import_failure_cache()
        if cached_error:
            _ocr_runtime_trace.trace(
                "easyocr_import:cached_error",
                fatal=bool(cached_fatal),
                error=cached_error,
            )
            return None, f"easyocr-import-error:{cached_error}"
        is_win_frozen = bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win")
        attempts = 3 if is_win_frozen else 4
        delay_s = 0.15
        last_exc: Exception | None = None
        previous_transient = False
        _ocr_runtime_trace.trace(
            "easyocr_import:start",
            attempts=attempts,
            frozen=bool(getattr(sys, "frozen", False)),
            optimize=getattr(sys.flags, "optimize", 0),
            executable=sys.executable,
        )
        for attempt in range(attempts):
            if previous_transient:
                purged = _purge_import_modules(("easyocr", "torch", "torchvision"))
                _ocr_runtime_trace.trace(
                    "easyocr_import:purge_modules",
                    attempt=int(attempt + 1),
                    removed=int(purged),
                )
                try:
                    gc.collect()
                except _OCR_IMPORT_GUARD_ERRORS:
                    pass
            existing = sys.modules.get("easyocr")
            if existing is not None:
                try:
                    if getattr(existing, "Reader", None) is not None:
                        _ocr_runtime_trace.trace("easyocr_import:reuse_existing", attempt=int(attempt + 1))
                        return existing, None
                except _OCR_IMPORT_GUARD_ERRORS:
                    pass
                try:
                    sys.modules.pop("easyocr", None)
                    _ocr_runtime_trace.trace("easyocr_import:drop_stale_module", attempt=int(attempt + 1))
                except _OCR_IMPORT_GUARD_ERRORS:
                    pass
            try:
                _ocr_runtime_trace.trace("easyocr_import:attempt", attempt=int(attempt + 1))
                with _TORCH_RUNTIME_IMPORT_LOCK:
                    # Import torch first; this avoids easyocr triggering a
                    # nested/partial torch init in some frozen Windows runs.
                    _import_torch_module()
                    easyocr = importlib.import_module("easyocr")  # type: ignore
                if getattr(easyocr, "Reader", None) is None:
                    raise RuntimeError("easyocr module loaded without Reader")
                _ocr_runtime_trace.trace(
                    "easyocr_import:ok",
                    attempt=int(attempt + 1),
                    easyocr_file=getattr(easyocr, "__file__", None),
                )
                _clear_easyocr_import_failure_cache()
                return easyocr, None
            except _OCR_IMPORT_GUARD_ERRORS as exc:
                last_exc = exc
                fatal = (
                    _looks_like_torch_docstring_reimport_error(exc)
                    or _looks_like_torch_source_unavailable_error(exc)
                    or _looks_like_torchvision_ops_missing_error(exc)
                )
                transient = (
                    _looks_like_partial_torch_import_error(exc)
                )
                previous_transient = bool(transient)
                _ocr_runtime_trace.trace(
                    "easyocr_import:error",
                    attempt=int(attempt + 1),
                    fatal=bool(fatal),
                    transient=bool(transient),
                    error=repr(exc),
                )
                if transient or _looks_like_torch_related_error(exc):
                    purged = _purge_import_modules(("easyocr", "torch", "torchvision"))
                    _ocr_runtime_trace.trace(
                        "easyocr_import:purge_modules_on_error",
                        attempt=int(attempt + 1),
                        removed=int(purged),
                    )
                    try:
                        gc.collect()
                    except _OCR_IMPORT_GUARD_ERRORS:
                        pass
                if fatal:
                    _set_easyocr_import_failure_cache(
                        exc,
                        fatal=True,
                        ttl_s=_EASYOCR_IMPORT_FAILURE_TTL_FATAL_S,
                    )
                    return None, f"easyocr-import-error:{exc}"
                if (not transient) or attempt >= (attempts - 1):
                    _set_easyocr_import_failure_cache(
                        exc,
                        fatal=False,
                        ttl_s=_EASYOCR_IMPORT_FAILURE_TTL_SOFT_S,
                    )
                    return None, f"easyocr-import-error:{exc}"
                try:
                    time.sleep(delay_s * float(attempt + 1))
                except _OCR_IMPORT_GUARD_ERRORS:
                    pass
        _ocr_runtime_trace.trace("easyocr_import:failed", error=repr(last_exc))
        return None, f"easyocr-import-error:{last_exc}"


def _runtime_search_roots() -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(str(meipass)))
    if getattr(sys, "frozen", False):
        try:
            roots.append(Path(sys.executable).resolve().parent)
        except _OCR_IMPORT_GUARD_ERRORS:
            pass
    here = Path(__file__).resolve()
    roots.extend([here.parent, here.parent.parent, Path.cwd()])

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            key = str(root.resolve())
        except _OCR_IMPORT_GUARD_ERRORS:
            key = str(root)
        key = key.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


@lru_cache(maxsize=8)
def _cached_easyocr_reader(
    langs_key: str,
    model_dir: str,
    user_network_dir: str,
    gpu_device: str,
    download_enabled: bool,
    quiet: bool,
):
    easyocr, import_error = _import_easyocr_module()
    if easyocr is None:
        raise RuntimeError(import_error or "easyocr-import-error")
    lang_list = [token for token in str(langs_key).split("|") if token]
    if not lang_list:
        lang_list = ["en"]
    reader_kwargs: dict[str, Any] = {
        "lang_list": lang_list,
        "gpu": False if str(gpu_device).strip().lower() == "cpu" else str(gpu_device).strip().lower(),
        "download_enabled": bool(download_enabled),
        "verbose": not bool(quiet),
    }
    if model_dir:
        reader_kwargs["model_storage_directory"] = str(model_dir)
    if user_network_dir:
        reader_kwargs["user_network_directory"] = str(user_network_dir)
    return easyocr.Reader(**reader_kwargs)


def _resolve_easyocr_reader(
    *,
    lang: str | None,
    model_dir: str | None,
    user_network_dir: str | None,
    gpu: bool | str,
    download_enabled: bool,
    quiet: bool = False,
) -> tuple[Any | None, str | None]:
    langs = _parse_easyocr_langs(lang)
    langs_key = "|".join(langs)
    resolved_model_dir = _resolve_optional_directory(model_dir)
    if resolved_model_dir:
        model_path = Path(str(resolved_model_dir)).expanduser()
        if (not model_path.is_dir()) and (not bool(download_enabled)):
            resolved_model_dir = None
    if not resolved_model_dir:
        resolved_model_dir = _discover_easyocr_model_dir()
    resolved_user_network_dir = _resolve_optional_directory(user_network_dir)
    model_key = str(resolved_model_dir or "")
    user_network_key = str(resolved_user_network_dir or "")
    gpu_device = _resolve_easyocr_device(_normalize_easyocr_gpu_mode(gpu))
    try:
        reader = _cached_easyocr_reader(
            langs_key,
            model_key,
            user_network_key,
            gpu_device,
            bool(download_enabled),
            bool(quiet),
        )
    except _OCR_IMPORT_GUARD_ERRORS as exc:
        return None, f"easyocr-init-error:{exc}"
    return reader, None


def _resolve_easyocr_group_readers(
    *,
    lang: str | None,
    model_dir: str | None,
    user_network_dir: str | None,
    gpu: bool | str,
    download_enabled: bool,
    quiet: bool = False,
) -> tuple[list[tuple[tuple[str, ...], Any]], list[str], tuple[tuple[str, ...], ...]]:
    parsed_langs = _parse_easyocr_langs(lang)
    groups = _build_easyocr_lang_groups(parsed_langs)
    readers: list[tuple[tuple[str, ...], Any]] = []
    errors: list[str] = []
    for group in groups:
        group_lang = ",".join(group)
        reader, reader_error = _resolve_easyocr_reader(
            lang=group_lang,
            model_dir=model_dir,
            user_network_dir=user_network_dir,
            gpu=gpu,
            download_enabled=download_enabled,
            quiet=quiet,
        )
        if reader is None:
            group_name = "+".join(group)
            resolved_error = str(reader_error or "easyocr-reader-not-ready")
            errors.append(f"{group_name}:{resolved_error}")
            if _reader_error_is_global_import_failure(resolved_error):
                _ocr_runtime_trace.trace(
                    "easyocr_reader:global_import_failure",
                    group=group_name,
                    error=resolved_error,
                )
                break
            continue
        readers.append((group, reader))
    return readers, errors, groups


def _reader_errors_indicate_missing_models(reader_errors: Iterable[str]) -> bool:
    for error in list(reader_errors or ()):
        token = str(error or "").strip().lower()
        if not token:
            continue
        if "missing " in token and "download" in token and "disabled" in token:
            return True
    return False


def _should_try_easyocr_english_fallback(
    *,
    parsed_langs: tuple[str, ...],
    reader_errors: Iterable[str],
) -> bool:
    if any(_reader_error_is_global_import_failure(err) for err in list(reader_errors or ())):
        return False
    if "en" not in tuple(parsed_langs or ()):
        return False
    if len(tuple(parsed_langs or ())) <= 1:
        return False
    return _reader_errors_indicate_missing_models(reader_errors)


def _resolve_easyocr_english_fallback_reader(
    *,
    parsed_langs: tuple[str, ...],
    reader_errors: Iterable[str],
    model_dir: str | None,
    user_network_dir: str | None,
    gpu: bool | str,
    download_enabled: bool,
    quiet: bool,
) -> tuple[Any | None, str | None]:
    if not _should_try_easyocr_english_fallback(
        parsed_langs=parsed_langs,
        reader_errors=reader_errors,
    ):
        return None, None
    return _resolve_easyocr_reader(
        lang="en",
        model_dir=model_dir,
        user_network_dir=user_network_dir,
        gpu=gpu,
        download_enabled=download_enabled,
        quiet=quiet,
    )


def easyocr_resolution_diagnostics(
    *,
    lang: str | None = None,
    model_dir: str | None = None,
    user_network_dir: str | None = None,
    gpu: bool | str = "auto",
    download_enabled: bool = False,
    quiet: bool = False,
) -> str:
    requested_lang = str(lang or "").strip() or "-"
    parsed_langs = _parse_easyocr_langs(lang)
    lang_groups = _build_easyocr_lang_groups(parsed_langs)
    resolved_model_dir = _resolve_optional_directory(model_dir)
    if resolved_model_dir:
        model_path = Path(str(resolved_model_dir)).expanduser()
        if (not model_path.is_dir()) and (not bool(download_enabled)):
            resolved_model_dir = None
    auto_model_dir = _discover_easyocr_model_dir() if not resolved_model_dir else None
    effective_model_dir = resolved_model_dir or auto_model_dir
    resolved_user_network_dir = _resolve_optional_directory(user_network_dir)
    gpu_mode = _normalize_easyocr_gpu_mode(gpu)
    gpu_device = _resolve_easyocr_device(gpu_mode)
    easyocr_mod, import_error = _import_easyocr_module()
    lines = [
        f"engine=easyocr",
        f"python_optimize={getattr(sys.flags, 'optimize', 0)}",
        f"requested_lang={requested_lang}",
        f"normalized_langs={'+'.join(parsed_langs)}",
        "lang_groups=" + ";".join("+".join(group) for group in lang_groups),
        f"model_dir={effective_model_dir or '-'}",
        f"user_network_dir={resolved_user_network_dir or '-'}",
        f"gpu_requested={gpu}",
        f"gpu_mode={gpu_mode}",
        f"gpu_device={gpu_device}",
        f"quiet={bool(quiet)}",
        f"download_enabled={bool(download_enabled)}",
        f"import={'ok' if easyocr_mod is not None else 'failed'}",
    ]
    if import_error:
        lines.append(f"import_error={import_error}")
        err_l = str(import_error).lower()
        if "no module named" in err_l and "easyocr" in err_l:
            lines.append("hint=install local OCR dependencies")
            lines.append("hint_cmd=pip install -r requirements-ocr-local.txt")
    if auto_model_dir and not resolved_model_dir:
        lines.append("model_dir_source=auto-discovered")
    readers, reader_errors, _ = _resolve_easyocr_group_readers(
        lang=lang,
        model_dir=model_dir,
        user_network_dir=user_network_dir,
        gpu=gpu,
        download_enabled=download_enabled,
        quiet=quiet,
    )
    fallback_reader, fallback_error = _resolve_easyocr_english_fallback_reader(
        parsed_langs=parsed_langs,
        reader_errors=reader_errors,
        model_dir=model_dir,
        user_network_dir=user_network_dir,
        gpu=gpu,
        download_enabled=download_enabled,
        quiet=quiet,
    )
    fallback_used = False
    if (not readers) and fallback_reader is not None:
        readers = [(("en",), fallback_reader)]
        fallback_used = True

    if readers and reader_errors:
        reader_status = "partial"
    elif readers:
        reader_status = "ready"
    else:
        reader_status = "failed"
    lines.append(f"reader={reader_status}")
    if readers:
        lines.append("reader_groups_ready=" + ";".join("+".join(group) for group, _ in readers))
    if fallback_used:
        lines.append("reader_fallback=en")
    if reader_errors:
        reader_error = "; ".join(reader_errors)
        lines.append(f"reader_error={reader_error}")
        reader_err_l = str(reader_error).lower()
        if "certificate verify failed" in reader_err_l:
            lines.append("hint=python SSL trust store failed for HTTPS model download")
            lines.append("hint_action=run Install Certificates.command or set SSL_CERT_FILE to certifi bundle")
        if "nodename nor servname provided" in reader_err_l or "temporary failure in name resolution" in reader_err_l:
            lines.append("hint=network or DNS unavailable for model download")
            lines.append("hint_action=check internet/proxy or place model files manually in ~/.EasyOCR/model")
        if _reader_errors_indicate_missing_models(reader_errors):
            lines.append("hint=one or more EasyOCR model files are missing locally")
            if bool(download_enabled) is False:
                lines.append("hint_action=set OCR_EASYOCR_DOWNLOAD_ENABLED=True once, run OCR once, then set it back to False")
        if (
            bool(download_enabled) is False
            and (effective_model_dir is None or str(effective_model_dir).strip() == "")
        ):
            lines.append("hint=offline mode active and no model directory resolved")
            lines.append("hint_action=set OCR_EASYOCR_MODEL_DIR or enable OCR_EASYOCR_DOWNLOAD_ENABLED")
    if fallback_error:
        lines.append(f"reader_fallback_error={fallback_error}")
    return "\n".join(lines)


def easyocr_available(
    *,
    lang: str | None = None,
    model_dir: str | None = None,
    user_network_dir: str | None = None,
    gpu: bool | str = "auto",
    download_enabled: bool = False,
    quiet: bool = False,
) -> bool:
    parsed_langs = _parse_easyocr_langs(lang)
    readers, reader_errors, _ = _resolve_easyocr_group_readers(
        lang=lang,
        model_dir=model_dir,
        user_network_dir=user_network_dir,
        gpu=gpu,
        download_enabled=download_enabled,
        quiet=quiet,
    )
    if readers:
        return True
    fallback_reader, _fallback_error = _resolve_easyocr_english_fallback_reader(
        parsed_langs=parsed_langs,
        reader_errors=reader_errors,
        model_dir=model_dir,
        user_network_dir=user_network_dir,
        gpu=gpu,
        download_enabled=download_enabled,
        quiet=quiet,
    )
    return bool(fallback_reader)


def _build_easyocr_warmup_image() -> Any | None:
    """
    Build a tiny synthetic image for one cheap readtext() call.

    The goal is not OCR accuracy, only triggering first-run model/runtime paths
    during preload instead of the first user-triggered OCR import.
    """
    try:
        import numpy as np  # type: ignore
    except _OCR_IMPORT_GUARD_ERRORS as exc:
        _ocr_runtime_trace.trace("easyocr_warmup:image_numpy_import_error", error=repr(exc))
        return None

    try:
        image = np.full((96, 384, 3), 255, dtype="uint8")
    except _OCR_IMPORT_GUARD_ERRORS as exc:
        _ocr_runtime_trace.trace("easyocr_warmup:image_alloc_error", error=repr(exc))
        return None

    # Draw simple high-contrast block glyphs ("OWP") to increase the chance of
    # running both detection and recognition code paths.
    image[20:76, 24:32] = 0
    image[20:76, 72:80] = 0
    image[20:28, 32:72] = 0
    image[68:76, 32:72] = 0

    image[20:76, 116:124] = 0
    image[20:76, 164:172] = 0
    image[68:76, 124:164] = 0

    image[20:76, 220:228] = 0
    image[20:28, 228:276] = 0
    image[44:52, 228:268] = 0
    image[20:76, 268:276] = 0
    return image


def easyocr_warmup_runtime(
    *,
    lang: str | None = None,
    model_dir: str | None = None,
    user_network_dir: str | None = None,
    gpu: bool | str = "auto",
    download_enabled: bool = False,
    quiet: bool = False,
) -> tuple[bool, str]:
    """
    Warm EasyOCR beyond reader construction by running one synthetic inference
    call per active language reader group.
    """
    parsed_langs = _parse_easyocr_langs(lang)
    readers, reader_errors, _ = _resolve_easyocr_group_readers(
        lang=lang,
        model_dir=model_dir,
        user_network_dir=user_network_dir,
        gpu=gpu,
        download_enabled=download_enabled,
        quiet=quiet,
    )
    fallback_error: str | None = None
    fallback_reader, fallback_error = _resolve_easyocr_english_fallback_reader(
        parsed_langs=parsed_langs,
        reader_errors=reader_errors,
        model_dir=model_dir,
        user_network_dir=user_network_dir,
        gpu=gpu,
        download_enabled=download_enabled,
        quiet=quiet,
    )
    if (not readers) and fallback_reader is not None:
        readers = [(("en",), fallback_reader)]
    if not readers:
        details = [str(value).strip() for value in list(reader_errors or []) if str(value).strip()]
        if fallback_error:
            details.append(f"en:{fallback_error}")
        error_text = "; ".join(details) if details else "easyocr-reader-not-ready"
        return False, error_text

    warmup_image = _build_easyocr_warmup_image()
    if warmup_image is None:
        return True, "reader-ready-no-inference-image"

    _ocr_runtime_trace.trace(
        "easyocr_warmup:start",
        reader_groups=";".join("+".join(group) for group, _ in readers),
    )
    failures: list[str] = []
    warmed_groups: list[str] = []
    for group, reader in readers:
        group_name = "+".join(group)
        try:
            device = str(getattr(reader, "device", "") or "").strip().lower()
            disable_pin_memory = device != "cuda"
            with _patch_dataloader_pin_memory(disable_pin_memory):
                # We only need runtime/model warmup side-effects; OCR result is irrelevant.
                reader.readtext(warmup_image, detail=1, paragraph=False)
            warmed_groups.append(group_name)
            _ocr_runtime_trace.trace("easyocr_warmup:group_done", group=group_name)
        except _OCR_IMPORT_GUARD_ERRORS as exc:
            failures.append(f"{group_name}:{exc}")
            _ocr_runtime_trace.trace("easyocr_warmup:group_error", group=group_name, error=repr(exc))

    if warmed_groups and not failures:
        return True, "inference-warmed"
    if warmed_groups:
        return True, "inference-warmed-partial:" + "; ".join(failures)
    return False, "easyocr-warmup-failed:" + "; ".join(failures)


def clear_ocr_runtime_caches(
    *,
    release_gpu: bool = False,
    collect_garbage: bool = True,
) -> None:
    """Release cached OCR runtime resources after idle periods."""
    _ocr_runtime_trace.trace(
        "ocr_cache_clear:start",
        release_gpu=bool(release_gpu),
        collect_garbage=bool(collect_garbage),
    )
    try:
        _cached_easyocr_reader.cache_clear()
    except _OCR_IMPORT_GUARD_ERRORS:
        pass
    if release_gpu:
        try:
            torch = _import_torch_module()

            if bool(getattr(torch, "cuda", None)) and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except _OCR_IMPORT_GUARD_ERRORS:
            pass
    if collect_garbage:
        try:
            gc.collect()
        except _OCR_IMPORT_GUARD_ERRORS:
            pass
    _ocr_runtime_trace.trace("ocr_cache_clear:done")


_easyocr_sort_key = _easyocr_token_utils._easyocr_sort_key
_easyocr_detection_to_token = _easyocr_token_utils._easyocr_detection_to_token
_easyocr_token_overlap_ratio = _easyocr_token_utils._easyocr_token_overlap_ratio
_easyocr_token_quality_score = _easyocr_token_utils._easyocr_token_quality_score
_easyocr_should_replace_overlapping_token = _easyocr_token_utils._easyocr_should_replace_overlapping_token
_easyocr_reduce_cross_group_tokens = _easyocr_token_utils._easyocr_reduce_cross_group_tokens


def _easyocr_group_tokens_to_lines(tokens: Iterable[dict[str, float | str]]) -> tuple[OCRLineResult, ...]:
    lines = _easyocr_token_utils._easyocr_group_tokens_to_text_conf_lines(tokens)
    return tuple(OCRLineResult(text=text, confidence=float(conf)) for text, conf in lines)


def run_easyocr(
    image_path: Path,
    *,
    lang: str | None = None,
    model_dir: str | None = None,
    user_network_dir: str | None = None,
    gpu: bool | str = "auto",
    download_enabled: bool = False,
    quiet: bool = False,
) -> OCRRunResult:
    if not image_path.exists():
        return OCRRunResult("", error=f"image-not-found:{image_path}")
    parsed_langs = _parse_easyocr_langs(lang)
    readers, reader_errors, _ = _resolve_easyocr_group_readers(
        lang=lang,
        model_dir=model_dir,
        user_network_dir=user_network_dir,
        gpu=gpu,
        download_enabled=download_enabled,
        quiet=quiet,
    )
    fallback_error: str | None = None
    fallback_reader, fallback_error = _resolve_easyocr_english_fallback_reader(
        parsed_langs=parsed_langs,
        reader_errors=reader_errors,
        model_dir=model_dir,
        user_network_dir=user_network_dir,
        gpu=gpu,
        download_enabled=download_enabled,
        quiet=quiet,
    )
    if (not readers) and fallback_reader is not None:
        readers = [(("en",), fallback_reader)]
    if not readers:
        details = [str(value).strip() for value in list(reader_errors or []) if str(value).strip()]
        if fallback_error:
            details.append(f"en:{fallback_error}")
        error_text = "; ".join(details) if details else "easyocr-reader-not-ready"
        return OCRRunResult("", error=error_text)

    all_detections: list[tuple[int, Any]] = []
    for group_index, (group, reader) in enumerate(readers):
        try:
            device = str(getattr(reader, "device", "") or "").strip().lower()
            disable_pin_memory = device != "cuda"
            with _patch_dataloader_pin_memory(disable_pin_memory):
                detections = reader.readtext(str(image_path), detail=1, paragraph=False)
        except _OCR_IMPORT_GUARD_ERRORS as exc:
            return OCRRunResult("", error=f"easyocr-run-error[{'+'.join(group)}]:{exc}")
        if detections:
            all_detections.extend((group_index, detection) for detection in list(detections))

    if not all_detections:
        return OCRRunResult("")
    ordered = list(all_detections)
    ordered.sort(key=lambda item: _easyocr_sort_key(item[1]))
    tokens: list[dict[str, float | str]] = []
    for group_index, detection in ordered:
        token = _easyocr_detection_to_token(detection, group_index=group_index)
        if token is not None:
            tokens.append(token)
    if len(readers) > 1 and len(tokens) > 1:
        tokens = _easyocr_reduce_cross_group_tokens(tokens)

    lines = _easyocr_group_tokens_to_lines(tokens)
    if not lines and tokens:
        lines = tuple(
            OCRLineResult(
                text=str(token.get("text", "") or "").strip(),
                confidence=float(token.get("confidence", -1.0)),
            )
            for token in tokens
            if str(token.get("text", "") or "").strip()
        )

    merged_text = "\n".join(line.text for line in lines if str(line.text).strip())
    return OCRRunResult(merged_text, lines=tuple(lines))


def run_ocr_multi(
    image_path: Path,
    *,
    engine: str = "easyocr",
    cmd: str = "auto",
    psm_values: Iterable[int] = (6, 11),
    timeout_s: float = 8.0,
    lang: str | None = None,
    stop_on_first_success: bool = False,
    easyocr_model_dir: str | None = None,
    easyocr_user_network_dir: str | None = None,
    easyocr_gpu: bool | str = "auto",
    easyocr_download_enabled: bool = False,
    easyocr_quiet: bool = False,
) -> OCRRunResult:
    _ = (
        engine,
        cmd,
        psm_values,
        timeout_s,
        stop_on_first_success,
    )
    return run_easyocr(
        image_path,
        lang=lang,
        model_dir=easyocr_model_dir,
        user_network_dir=easyocr_user_network_dir,
        gpu=easyocr_gpu,
        download_enabled=easyocr_download_enabled,
        quiet=easyocr_quiet,
    )


extract_candidate_names = _ocr_name_extraction.extract_candidate_names
extract_candidate_names_debug = _ocr_name_extraction.extract_candidate_names_debug
extract_candidate_names_multi = _ocr_name_extraction.extract_candidate_names_multi
