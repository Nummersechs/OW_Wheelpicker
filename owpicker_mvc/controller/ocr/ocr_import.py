from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from difflib import SequenceMatcher
import gc
import re
import sys
import warnings
from typing import Any, Iterable
from logic.name_normalization import normalize_name_alnum_key, normalize_name_tokens


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
    "de": "de",
}
_TORCH_WARN_FILTERS_APPLIED = False


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
        import torch  # type: ignore
    except Exception:
        return (False, False)
    has_cuda = False
    has_mps = False
    try:
        has_cuda = bool(torch.cuda.is_available())
    except Exception:
        has_cuda = False
    try:
        has_mps = bool(torch.backends.mps.is_available())
    except Exception:
        has_mps = False
    return (has_cuda, has_mps)


def _resolve_easyocr_device(mode: str) -> str:
    normalized = _normalize_easyocr_gpu_mode(mode)
    has_cuda, has_mps = _torch_device_support()
    if normalized == "cpu":
        return "cpu"
    if normalized == "cuda":
        return "cuda" if has_cuda else "cpu"
    if normalized == "mps":
        return "mps" if has_mps else "cpu"
    if has_cuda:
        return "cuda"
    if has_mps:
        return "mps"
    return "cpu"


def _apply_torch_warning_filters(quiet: bool) -> None:
    global _TORCH_WARN_FILTERS_APPLIED
    if not bool(quiet):
        return
    if _TORCH_WARN_FILTERS_APPLIED:
        return
    warnings.filterwarnings(
        "ignore",
        message=r".*'pin_memory' argument is set as true but not supported on MPS now.*",
        category=UserWarning,
    )
    _TORCH_WARN_FILTERS_APPLIED = True


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
        import torch  # type: ignore
    except Exception:
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
        except Exception:
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
            except Exception:
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
    except Exception:
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
        except Exception:
            key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        if _looks_like_easyocr_model_dir(candidate):
            try:
                return str(candidate.resolve())
            except Exception:
                return str(candidate)
    return None


def _import_easyocr_module() -> tuple[Any | None, str | None]:
    try:
        import easyocr  # type: ignore
    except Exception as exc:
        return None, f"easyocr-import-error:{exc}"
    return easyocr, None


def _runtime_search_roots() -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(str(meipass)))
    if getattr(sys, "frozen", False):
        try:
            roots.append(Path(sys.executable).resolve().parent)
        except Exception:
            pass
    here = Path(__file__).resolve()
    roots.extend([here.parent, here.parent.parent, Path.cwd()])

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            key = str(root.resolve())
        except Exception:
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
    _apply_torch_warning_filters(bool(quiet))
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
    except Exception as exc:
        return None, f"easyocr-init-error:{exc}"
    return reader, None


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
        f"requested_lang={requested_lang}",
        f"normalized_langs={'+'.join(parsed_langs)}",
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
    reader, reader_error = _resolve_easyocr_reader(
        lang=lang,
        model_dir=model_dir,
        user_network_dir=user_network_dir,
        gpu=gpu,
        download_enabled=download_enabled,
        quiet=quiet,
    )
    lines.append(f"reader={'ready' if reader is not None else 'failed'}")
    if reader_error:
        lines.append(f"reader_error={reader_error}")
        reader_err_l = str(reader_error).lower()
        if "certificate verify failed" in reader_err_l:
            lines.append("hint=python SSL trust store failed for HTTPS model download")
            lines.append("hint_action=run Install Certificates.command or set SSL_CERT_FILE to certifi bundle")
        if "nodename nor servname provided" in reader_err_l or "temporary failure in name resolution" in reader_err_l:
            lines.append("hint=network or DNS unavailable for model download")
            lines.append("hint_action=check internet/proxy or place model files manually in ~/.EasyOCR/model")
        if (
            bool(download_enabled) is False
            and (effective_model_dir is None or str(effective_model_dir).strip() == "")
        ):
            lines.append("hint=offline mode active and no model directory resolved")
            lines.append("hint_action=set OCR_EASYOCR_MODEL_DIR or enable OCR_EASYOCR_DOWNLOAD_ENABLED")
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
    reader, _ = _resolve_easyocr_reader(
        lang=lang,
        model_dir=model_dir,
        user_network_dir=user_network_dir,
        gpu=gpu,
        download_enabled=download_enabled,
        quiet=quiet,
    )
    return reader is not None


def clear_ocr_runtime_caches(
    *,
    release_gpu: bool = False,
    collect_garbage: bool = True,
) -> None:
    """Release cached OCR runtime resources after idle periods."""
    try:
        _cached_easyocr_reader.cache_clear()
    except Exception:
        pass
    if release_gpu:
        try:
            import torch  # type: ignore

            if bool(getattr(torch, "cuda", None)) and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
    if collect_garbage:
        try:
            gc.collect()
        except Exception:
            pass


def _easyocr_sort_key(detection: Any) -> tuple[float, float]:
    try:
        bbox = detection[0]
    except Exception:
        return (0.0, 0.0)
    if not bbox:
        return (0.0, 0.0)
    xs: list[float] = []
    ys: list[float] = []
    try:
        for point in bbox:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            xs.append(float(point[0]))
            ys.append(float(point[1]))
    except Exception:
        return (0.0, 0.0)
    if not xs or not ys:
        return (0.0, 0.0)
    return (min(ys), min(xs))


def _easyocr_detection_to_token(detection: Any) -> dict[str, float | str] | None:
    try:
        text = str(detection[1] or "").strip()
    except Exception:
        text = ""
    if not text:
        return None
    try:
        raw_conf = float(detection[2])
        confidence = raw_conf * 100.0 if raw_conf <= 1.0 else raw_conf
    except Exception:
        confidence = -1.0

    y0, x0 = _easyocr_sort_key(detection)
    x1 = x0
    y1 = y0
    try:
        bbox = detection[0]
    except Exception:
        bbox = ()
    xs: list[float] = []
    ys: list[float] = []
    try:
        for point in bbox or ():
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                continue
            xs.append(float(point[0]))
            ys.append(float(point[1]))
    except Exception:
        xs = []
        ys = []
    if xs:
        x0 = min(xs)
        x1 = max(xs)
    if ys:
        y0 = min(ys)
        y1 = max(ys)
    if x1 < x0:
        x1 = x0
    if y1 < y0:
        y1 = y0
    return {
        "text": text,
        "confidence": float(confidence),
        "x0": float(x0),
        "x1": float(x1),
        "y0": float(y0),
        "y1": float(y1),
    }


def _easyocr_group_tokens_to_lines(tokens: Iterable[dict[str, float | str]]) -> tuple[OCRLineResult, ...]:
    prepared: list[dict[str, float | str]] = []
    for token in tokens:
        text = str(token.get("text", "") or "").strip()
        if not text:
            continue
        try:
            x0 = float(token.get("x0", 0.0))
            x1 = float(token.get("x1", x0))
            y0 = float(token.get("y0", 0.0))
            y1 = float(token.get("y1", y0))
            confidence = float(token.get("confidence", -1.0))
        except Exception:
            continue
        if x1 < x0:
            x1 = x0
        if y1 < y0:
            y1 = y0
        prepared.append(
            {
                "text": text,
                "x0": x0,
                "x1": x1,
                "y0": y0,
                "y1": y1,
                "confidence": confidence,
            }
        )
    if not prepared:
        return ()

    token_heights = sorted(max(1.0, float(item["y1"]) - float(item["y0"])) for item in prepared)
    median_height = token_heights[len(token_heights) // 2] if token_heights else 12.0
    # Avoid chaining nearby rows into one giant line on noisy detections.
    max_line_height = max(8.0, median_height * 1.85)

    prepared.sort(key=lambda item: (float(item["y0"]), float(item["x0"])))
    line_groups: list[dict[str, Any]] = []

    for token in prepared:
        token_y0 = float(token["y0"])
        token_y1 = float(token["y1"])
        token_h = max(1.0, token_y1 - token_y0)
        token_center = (token_y0 + token_y1) * 0.5

        best_idx = -1
        best_score = float("-inf")
        for idx, line in enumerate(line_groups):
            line_y0 = float(line["y0"])
            line_y1 = float(line["y1"])
            line_h = max(1.0, line_y1 - line_y0)
            line_center = float(line["center"])

            prospective_h = max(line_y1, token_y1) - min(line_y0, token_y0)
            if len(line["tokens"]) >= 1 and prospective_h > max_line_height:
                continue

            overlap = max(0.0, min(token_y1, line_y1) - max(token_y0, line_y0))
            overlap_ratio = overlap / max(1.0, min(token_h, line_h))
            center_delta = abs(token_center - line_center)
            center_limit = max(token_h, line_h) * 0.55 + 1.0
            if overlap_ratio < 0.34 and center_delta > center_limit:
                continue

            score = (overlap_ratio * 2.0) - (center_delta / max(1.0, center_limit))
            if score > best_score:
                best_score = score
                best_idx = idx

        if best_idx < 0:
            line_groups.append(
                {
                    "y0": token_y0,
                    "y1": token_y1,
                    "center": token_center,
                    "tokens": [token],
                }
            )
            continue

        line = line_groups[best_idx]
        line["tokens"].append(token)
        line["y0"] = min(float(line["y0"]), token_y0)
        line["y1"] = max(float(line["y1"]), token_y1)
        line["center"] = (float(line["y0"]) + float(line["y1"])) * 0.5

    line_groups.sort(key=lambda item: float(item["y0"]))
    lines: list[OCRLineResult] = []
    for line in line_groups:
        ordered_tokens = sorted(line["tokens"], key=lambda item: float(item["x0"]))
        merged_tokens: list[dict[str, float | str]] = []
        for token in ordered_tokens:
            token_text = str(token.get("text", "") or "").strip()
            if not token_text:
                continue
            token_key = normalize_name_alnum_key(token_text)
            if merged_tokens:
                prev = merged_tokens[-1]
                prev_text = str(prev.get("text", "") or "").strip()
                prev_key = normalize_name_alnum_key(prev_text)
                try:
                    token_x0 = float(token.get("x0", 0.0))
                    token_x1 = float(token.get("x1", token_x0))
                    prev_x0 = float(prev.get("x0", 0.0))
                    prev_x1 = float(prev.get("x1", prev_x0))
                    overlap = max(0.0, min(token_x1, prev_x1) - max(token_x0, prev_x0))
                    min_width = max(1.0, min(token_x1 - token_x0, prev_x1 - prev_x0))
                    overlap_ratio = overlap / min_width
                except Exception:
                    overlap_ratio = 0.0
                if token_key and token_key == prev_key and overlap_ratio >= 0.45:
                    if float(token.get("confidence", -1.0)) > float(prev.get("confidence", -1.0)):
                        merged_tokens[-1] = token
                    continue
            merged_tokens.append(token)

        if not merged_tokens:
            continue

        text = " ".join(str(item.get("text", "") or "").strip() for item in merged_tokens).strip()
        text = re.sub(r"\s+", " ", text)
        if not text:
            continue
        conf_sum = 0.0
        conf_weight = 0.0
        for item in merged_tokens:
            conf = float(item.get("confidence", -1.0))
            if conf < 0.0:
                continue
            weight = max(1.0, float(len(str(item.get("text", "") or "").strip())))
            conf_sum += conf * weight
            conf_weight += weight
        confidence = (conf_sum / conf_weight) if conf_weight > 0.0 else -1.0
        lines.append(OCRLineResult(text=text, confidence=confidence))

    if not lines:
        return ()

    deduped_lines: list[OCRLineResult] = []
    seen_index_by_key: dict[str, int] = {}
    for line in lines:
        text = str(line.text or "").strip()
        if not text:
            continue
        key = text.lower()
        existing_idx = seen_index_by_key.get(key)
        if existing_idx is None:
            seen_index_by_key[key] = len(deduped_lines)
            deduped_lines.append(line)
            continue
        existing = deduped_lines[existing_idx]
        if float(line.confidence) > float(existing.confidence):
            deduped_lines[existing_idx] = line
    return tuple(deduped_lines)


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
    reader, reader_error = _resolve_easyocr_reader(
        lang=lang,
        model_dir=model_dir,
        user_network_dir=user_network_dir,
        gpu=gpu,
        download_enabled=download_enabled,
        quiet=quiet,
    )
    if reader is None:
        return OCRRunResult("", error=reader_error or "easyocr-reader-not-ready")
    try:
        _apply_torch_warning_filters(bool(quiet))
        device = str(getattr(reader, "device", "") or "").strip().lower()
        disable_pin_memory = device != "cuda"
        with _patch_dataloader_pin_memory(disable_pin_memory):
            detections = reader.readtext(str(image_path), detail=1, paragraph=False)
    except Exception as exc:
        return OCRRunResult("", error=f"easyocr-run-error:{exc}")
    if not detections:
        return OCRRunResult("")
    ordered = list(detections)
    ordered.sort(key=_easyocr_sort_key)
    tokens: list[dict[str, float | str]] = []
    for detection in ordered:
        token = _easyocr_detection_to_token(detection)
        if token is not None:
            tokens.append(token)

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


_OCR_NUMBERING_RE = re.compile(r"^\s*\d+\s*[\)\].:\-]+\s*")
_OCR_BULLET_RE = re.compile(r"^\s*[-*•|]+\s*")
_OCR_METADATA_PIPE_RE = re.compile(r"\s*[|¦｜┃│┆┇╎╏]+\s*")
_OCR_SPACE_RE = re.compile(r"\s+")
_OCR_ALLOWED_CHARS_RE = re.compile(r"[^\w .\-#]", flags=re.UNICODE)
_OCR_ASSIGNMENT_SPLIT_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]{2,95})\s*(?::=|=)\s*(.+?)\s*$")
_OCR_HAS_ALPHA_RE = re.compile(r"[^\W\d_]", flags=re.UNICODE)
_OCR_LEADING_ICON_RE = re.compile(r"^\s*[@©®™$%&*]+\s*")
_OCR_TRAILING_PAREN_METADATA_RE = re.compile(r"\s*(?:[\(\[\{<][^\)\]\}>]{1,48}[\)\]\}>])+\s*$")
_OCR_EMOJI_ICON_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "\u200d"
    "\ufe0f"
    "]",
    flags=re.UNICODE,
)


def _strip_after_first_emoji(value: str) -> str:
    if not value:
        return value
    match = _OCR_EMOJI_ICON_RE.search(value)
    if not match:
        return value
    return value[: match.start()].rstrip()


def _strip_trailing_short_noise_suffix(line: str) -> str:
    """
    Drop OCR noise suffixes like trailing 'TK' in chat list lines
    while keeping short all-caps names intact.
    """
    words = [tok for tok in str(line or "").split(" ") if tok]
    if len(words) < 2:
        return str(line or "")

    tail_raw = words[-1].strip(" .-_")
    if not tail_raw:
        return str(line or "")
    tail_key = "".join(ch for ch in tail_raw if ch.isalnum())
    if not tail_key:
        return str(line or "")
    if len(tail_key) > 2:
        return str(line or "")
    if not any(ch.isalpha() for ch in tail_key):
        return str(line or "")

    tail_lower = tail_key.lower()
    tail_is_noise = tail_raw.isupper() or tail_lower in {"k", "tk", "ik", "lk", "hk", "vk", "ok", "kk"}
    if not tail_is_noise:
        return str(line or "")

    head = " ".join(words[:-1]).strip(" .-_")
    if not head:
        return str(line or "")
    # Keep compact uppercase tags like "AJ TK" and only trim for longer
    # human-like names where OCR often appends a stray short token.
    if len(head) < 5:
        return str(line or "")
    if not any(ch.islower() for ch in head):
        return str(line or "")
    return head


def _strip_metadata_suffix_ocr_token(line: str) -> str:
    """Trim OCR lines like 'Massith I Marc ...' where '|' became 'I'/'l'/'1'."""
    tokens = [tok for tok in line.split(" ") if tok]
    if len(tokens) < 2:
        return line
    head = tokens[0].strip(" .-_")
    if not head:
        return line

    second = tokens[1]
    if second and second[0] in {"(", "[", "{", "<", "|", "¦", "｜", "┃", "│", "┆", "┇", "╎", "╏", "/", "\\"}:
        return head

    if len(tokens) < 3:
        return line

    sep = second
    if len(sep) != 1:
        return line
    if sep not in {"I", "i", "l", "1", "!", "|", "¦", "｜", "┃", "│", "┆", "┇", "╎", "╏", "/", "\\"}:
        return line
    return head or line


def _looks_like_constant_identifier(value: str) -> bool:
    token = str(value or "").strip(" .-_")
    if "_" not in token:
        return False
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{2,95}", token):
        return False
    alpha = [ch for ch in token if ch.isalpha()]
    if not alpha:
        return False
    upper_ratio = sum(1 for ch in alpha if ch.isupper()) / max(1, len(alpha))
    return upper_ratio >= 0.8


def _strip_assignment_suffix_ocr_token(line: str) -> str:
    """
    Convert assignment-like OCR lines into their left identifier, e.g.
    'MAP_PREBUILD_ON_START = False' -> 'MAP_PREBUILD_ON_START'.
    """
    text = str(line or "").strip()
    if not text:
        return text
    match = _OCR_ASSIGNMENT_SPLIT_RE.match(text)
    if not match:
        return text
    left = str(match.group(1) or "").strip()
    right = str(match.group(2) or "").strip()
    if not left or not right:
        return text
    if not _looks_like_constant_identifier(left):
        return text
    return left


def _looks_like_name(
    value: str,
    *,
    min_chars: int,
    max_chars: int,
    max_words: int,
    max_digit_ratio: float,
) -> bool:
    if not value:
        return False
    if len(value) < min_chars:
        return False
    if max_chars > 0 and len(value) > max_chars:
        return False
    words = [w for w in value.split(" ") if w]
    if max_words > 0 and len(words) > max_words:
        return False
    if not _OCR_HAS_ALPHA_RE.search(value):
        return False
    alpha_chars = [ch for ch in value if ch.isalpha()]
    # Apply short-token case heuristics only for scripts that have case.
    # CJK/Hangul scripts should not be penalized by uppercase/lowercase rules.
    cased_alpha_chars = [ch for ch in alpha_chars if ch.lower() != ch.upper()]
    if cased_alpha_chars:
        if len(value) <= 2 and not all(ch.isupper() for ch in cased_alpha_chars):
            return False
        if (
            len(value) <= 3
            and len(cased_alpha_chars) == len(alpha_chars)
            and all(ch.islower() for ch in cased_alpha_chars)
        ):
            return False
    total_chars = sum(1 for ch in value if ch.isalnum())
    if total_chars <= 0:
        return False
    digit_chars = sum(1 for ch in value if ch.isdigit())
    if (digit_chars / total_chars) > max(0.0, float(max_digit_ratio)):
        return False
    return True


def _candidate_key(value: str) -> str:
    return normalize_name_alnum_key(value)


def _display_name_quality(value: str) -> tuple[int, int]:
    separators = sum(1 for ch in value if not ch.isalnum())
    return (separators, -len(value))


def _should_prefer_display_name(current_name: str, candidate_name: str) -> bool:
    current = str(current_name or "").strip()
    candidate = str(candidate_name or "").strip()
    if not candidate:
        return False
    if not current:
        return True
    if _is_constant_prefix_variant(current, candidate):
        return len(candidate) > len(current)
    if _looks_like_constant_identifier(current) and _looks_like_constant_identifier(candidate):
        if len(candidate) != len(current):
            return len(candidate) > len(current)
    return _display_name_quality(candidate) < _display_name_quality(current)


def _normalized_tokens(value: str) -> list[str]:
    return normalize_name_tokens(value)


def _is_numeric_suffix_variant(left_key: str, right_key: str) -> bool:
    left = str(left_key or "").strip()
    right = str(right_key or "").strip()
    if not left or not right or left == right:
        return False
    if left.startswith(right):
        suffix = left[len(right):]
    elif right.startswith(left):
        suffix = right[len(left):]
    else:
        return False
    return bool(suffix) and suffix.isdigit()


def _is_constant_prefix_variant(left_name: str, right_name: str) -> bool:
    left = str(left_name or "").strip()
    right = str(right_name or "").strip()
    if not left or not right or left == right:
        return False
    if not (_looks_like_constant_identifier(left) and _looks_like_constant_identifier(right)):
        return False
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if len(longer) - len(shorter) > 8:
        return False
    return longer.startswith(shorter)


def _find_near_duplicate_key(
    key: str,
    name: str,
    existing_keys: Iterable[str],
    display_names: dict[str, str],
    *,
    min_chars: int,
    max_len_delta: int,
    similarity: float,
    tail_min_chars: int,
    tail_head_similarity: float,
    coexisting_keys: set[str] | None = None,
) -> str | None:
    if len(key) < max(1, int(min_chars)):
        return None
    length_delta = max(0, int(max_len_delta))
    min_similarity = max(0.0, min(1.0, float(similarity)))
    min_tail_len = max(1, int(tail_min_chars))
    min_tail_head_similarity = max(0.0, min(1.0, float(tail_head_similarity)))
    name_tokens = _normalized_tokens(name)

    best_key: str | None = None
    best_score = 0.0
    for current in existing_keys:
        current_name = display_names.get(current, "")
        if current == key:
            return current
        if (
            coexisting_keys
            and current in coexisting_keys
            and _is_numeric_suffix_variant(current, key)
        ):
            # Keep explicit numeric suffix variants when both appear in the
            # same OCR text pass (likely distinct rows, e.g. Name / Name2).
            continue
        if _is_constant_prefix_variant(current_name, name):
            # Merge OCR truncation variants like *_ON_ST and *_ON_START.
            return current
        if len(current) < max(1, int(min_chars)):
            continue
        score = 0.0
        if abs(len(current) - len(key)) <= length_delta:
            score = SequenceMatcher(None, current, key).ratio()
        if score < min_similarity:
            current_tokens = _normalized_tokens(current_name)
            if len(name_tokens) >= 2 and len(current_tokens) >= 2:
                name_tail = name_tokens[-1]
                current_tail = current_tokens[-1]
                if (
                    name_tail == current_tail
                    and len(name_tail) >= min_tail_len
                ):
                    name_head = "".join(ch for ch in " ".join(name_tokens[:-1]) if ch.isalnum())
                    current_head = "".join(ch for ch in " ".join(current_tokens[:-1]) if ch.isalnum())
                    if name_head and current_head:
                        if abs(len(name_head) - len(current_head)) <= (length_delta + 1):
                            head_score = SequenceMatcher(None, current_head, name_head).ratio()
                            if head_score >= min_tail_head_similarity:
                                score = max(score, head_score)
        if score < min_similarity and score < min_tail_head_similarity:
            continue
        if score > best_score:
            best_score = score
            best_key = current
    return best_key


def _extract_candidate_names_impl(
    text: str,
    *,
    min_chars: int = 2,
    max_chars: int = 24,
    max_words: int = 2,
    max_digit_ratio: float = 0.45,
    enforce_special_char_constraint: bool = True,
    include_debug: bool = False,
) -> tuple[list[str], list[dict]]:
    if not text:
        return [], []

    found: list[str] = []
    seen: set[str] = set()
    line_debug: list[dict] = []
    min_len = max(1, int(min_chars))
    max_len = max(0, int(max_chars))
    word_limit = max(0, int(max_words))
    digit_ratio = max(0.0, float(max_digit_ratio))

    for raw_line in text.splitlines():
        debug_entry: dict | None = None
        if include_debug:
            debug_entry = {"raw": str(raw_line)}
        line = raw_line.strip()
        if not line:
            if debug_entry is not None:
                debug_entry["status"] = "dropped"
                debug_entry["reason"] = "empty-line"
                line_debug.append(debug_entry)
            continue
        if debug_entry is not None:
            debug_entry["trimmed"] = str(line)

        normalized = _OCR_NUMBERING_RE.sub("", line)
        normalized = _OCR_BULLET_RE.sub("", normalized)
        had_leading_icon = bool(_OCR_LEADING_ICON_RE.match(normalized))
        normalized = _OCR_LEADING_ICON_RE.sub("", normalized)
        if enforce_special_char_constraint:
            # The OCR list is expected to be line-based. Ignore metadata suffix
            # after common pipe-like separators ("|", "¦", "｜", ...).
            normalized = _OCR_METADATA_PIPE_RE.split(normalized, 1)[0].strip()
            normalized = _strip_metadata_suffix_ocr_token(normalized)
            # Ignore everything after the first emoji/icon in a line.
            normalized = _strip_after_first_emoji(normalized)
            normalized = _OCR_TRAILING_PAREN_METADATA_RE.sub("", normalized).strip()
            normalized = _strip_trailing_short_noise_suffix(normalized).strip()
        if debug_entry is not None:
            debug_entry["after_metadata"] = str(normalized)
        if not normalized:
            if debug_entry is not None:
                debug_entry["status"] = "dropped"
                debug_entry["reason"] = "empty-after-metadata-trim"
                line_debug.append(debug_entry)
            continue
        if enforce_special_char_constraint:
            normalized = _OCR_EMOJI_ICON_RE.sub(" ", normalized)
            part = _OCR_ALLOWED_CHARS_RE.sub(" ", normalized)
        else:
            part = normalized
        part = _OCR_SPACE_RE.sub(" ", part).strip(" .-_")
        part = _strip_assignment_suffix_ocr_token(part)
        if debug_entry is not None:
            debug_entry["cleaned"] = str(part)
        if not part:
            if debug_entry is not None:
                debug_entry["status"] = "dropped"
                debug_entry["reason"] = "empty-after-char-cleanup"
                line_debug.append(debug_entry)
            continue
        if had_leading_icon and len(part) <= 5 and part.isupper():
            if debug_entry is not None:
                debug_entry["status"] = "dropped"
                debug_entry["reason"] = "icon-prefixed-short-upper"
                line_debug.append(debug_entry)
            continue
        effective_max_len = max_len
        if _looks_like_constant_identifier(part):
            # Config-like identifiers can be longer than player-name defaults.
            effective_max_len = max(max_len, 64)
        if not _looks_like_name(
            part,
            min_chars=min_len,
            max_chars=effective_max_len,
            max_words=word_limit,
            max_digit_ratio=digit_ratio,
        ):
            if debug_entry is not None:
                debug_entry["status"] = "dropped"
                debug_entry["reason"] = "failed-name-heuristics"
                line_debug.append(debug_entry)
            continue
        candidate_key = _candidate_key(part)
        if candidate_key in seen:
            if debug_entry is not None:
                debug_entry["status"] = "dropped"
                debug_entry["reason"] = "duplicate-key"
                debug_entry["key"] = candidate_key
                line_debug.append(debug_entry)
            continue
        seen.add(candidate_key)
        found.append(part)
        if debug_entry is not None:
            debug_entry["status"] = "accepted"
            debug_entry["key"] = candidate_key
            debug_entry["candidate"] = part
            line_debug.append(debug_entry)

    return found, line_debug


def extract_candidate_names(
    text: str,
    *,
    min_chars: int = 2,
    max_chars: int = 24,
    max_words: int = 2,
    max_digit_ratio: float = 0.45,
    enforce_special_char_constraint: bool = True,
) -> list[str]:
    found, _ = _extract_candidate_names_impl(
        text,
        min_chars=min_chars,
        max_chars=max_chars,
        max_words=max_words,
        max_digit_ratio=max_digit_ratio,
        enforce_special_char_constraint=enforce_special_char_constraint,
        include_debug=False,
    )
    return found


def extract_candidate_names_debug(
    text: str,
    *,
    min_chars: int = 2,
    max_chars: int = 24,
    max_words: int = 2,
    max_digit_ratio: float = 0.45,
    enforce_special_char_constraint: bool = True,
) -> tuple[list[str], list[dict]]:
    return _extract_candidate_names_impl(
        text,
        min_chars=min_chars,
        max_chars=max_chars,
        max_words=max_words,
        max_digit_ratio=max_digit_ratio,
        enforce_special_char_constraint=enforce_special_char_constraint,
        include_debug=True,
    )


def extract_candidate_names_multi(
    texts: Iterable[str],
    *,
    min_chars: int = 2,
    max_chars: int = 24,
    max_words: int = 2,
    max_digit_ratio: float = 0.45,
    enforce_special_char_constraint: bool = True,
    min_support: int = 1,
    high_count_threshold: int = 8,
    high_count_min_support: int = 2,
    max_candidates: int = 12,
    near_dup_min_chars: int = 8,
    near_dup_max_len_delta: int = 1,
    near_dup_similarity: float = 0.90,
    near_dup_tail_min_chars: int = 3,
    near_dup_tail_head_similarity: float = 0.70,
) -> list[str]:
    ordered_keys: list[str] = []
    display_names: dict[str, str] = {}
    variant_counts: dict[str, dict[str, int]] = {}
    support_count: dict[str, int] = {}

    for text in texts:
        if not text:
            continue
        extracted_names = extract_candidate_names(
            text,
            min_chars=min_chars,
            max_chars=max_chars,
            max_words=max_words,
            max_digit_ratio=max_digit_ratio,
            enforce_special_char_constraint=enforce_special_char_constraint,
        )
        coexisting_keys = {
            _candidate_key(candidate)
            for candidate in extracted_names
            if _candidate_key(candidate)
        }
        seen_in_text: set[str] = set()
        for name in extracted_names:
            key = _candidate_key(name)
            if key not in display_names:
                near_key = _find_near_duplicate_key(
                    key,
                    name,
                    ordered_keys,
                    display_names,
                    min_chars=near_dup_min_chars,
                    max_len_delta=near_dup_max_len_delta,
                    similarity=near_dup_similarity,
                    tail_min_chars=near_dup_tail_min_chars,
                    tail_head_similarity=near_dup_tail_head_similarity,
                    coexisting_keys=coexisting_keys,
                )
                if near_key is not None:
                    key = near_key
            if key not in display_names:
                ordered_keys.append(key)
                display_names[key] = name
            variants = variant_counts.setdefault(key, {})
            variants[name] = variants.get(name, 0) + 1
            current_name = display_names.get(key, name)
            current_count = variants.get(current_name, 0)
            new_count = variants.get(name, 0)
            if (
                new_count > current_count
                or (
                    new_count == current_count
                    and _should_prefer_display_name(current_name, name)
                )
            ):
                display_names[key] = name
            if key in seen_in_text:
                continue
            seen_in_text.add(key)
            support_count[key] = support_count.get(key, 0) + 1

    if not ordered_keys:
        return []

    support_floor = max(1, int(min_support))
    if len(ordered_keys) >= max(1, int(high_count_threshold)):
        support_floor = max(support_floor, max(1, int(high_count_min_support)))

    filtered_keys = [key for key in ordered_keys if support_count.get(key, 0) >= support_floor]
    if not filtered_keys:
        filtered_keys = list(ordered_keys)

    limit = max(0, int(max_candidates))
    if limit > 0 and len(filtered_keys) > limit:
        order_index = {key: idx for idx, key in enumerate(ordered_keys)}
        ranked = sorted(
            filtered_keys,
            key=lambda key: (-support_count.get(key, 0), order_index.get(key, 0)),
        )
        keep = set(ranked[:limit])
        filtered_keys = [key for key in filtered_keys if key in keep]

    return [display_names[key] for key in filtered_keys]
