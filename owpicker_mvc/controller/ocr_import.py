from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
from typing import Iterable


@dataclass
class OCRRunResult:
    text: str
    error: str | None = None


def tesseract_available(cmd: str = "tesseract") -> bool:
    return shutil.which(cmd) is not None


def run_tesseract(
    image_path: Path,
    *,
    cmd: str = "tesseract",
    psm: int = 6,
    timeout_s: float = 8.0,
    lang: str | None = None,
) -> OCRRunResult:
    if not tesseract_available(cmd):
        return OCRRunResult("", error=f"tesseract-not-found:{cmd}")
    if not image_path.exists():
        return OCRRunResult("", error=f"image-not-found:{image_path}")
    proc_args = [
        cmd,
        str(image_path),
        "stdout",
    ]
    if lang:
        proc_args.extend(["-l", str(lang)])
    proc_args.extend([
        "--psm",
        str(max(0, int(psm))),
    ])
    try:
        completed = subprocess.run(
            proc_args,
            capture_output=True,
            text=True,
            check=False,
            timeout=max(0.5, float(timeout_s)),
        )
    except subprocess.TimeoutExpired:
        return OCRRunResult("", error="timeout")
    except Exception as exc:
        return OCRRunResult("", error=f"exec-error:{exc}")

    output = (completed.stdout or "").strip()
    if completed.returncode != 0:
        err = (completed.stderr or "").strip() or f"exit:{completed.returncode}"
        return OCRRunResult(output, error=err)
    return OCRRunResult(output)


def run_tesseract_multi(
    image_path: Path,
    *,
    cmd: str = "tesseract",
    psm_values: Iterable[int] = (6, 11),
    timeout_s: float = 8.0,
    lang: str | None = None,
) -> OCRRunResult:
    merged_lines: list[str] = []
    seen_lines: set[str] = set()
    errors: list[str] = []
    successful_runs = 0

    for psm in psm_values:
        result = run_tesseract(
            image_path,
            cmd=cmd,
            psm=int(psm),
            timeout_s=timeout_s,
            lang=lang,
        )
        if result.error and not result.text:
            errors.append(f"psm={int(psm)}:{result.error}")
            continue
        successful_runs += 1
        for line in (result.text or "").splitlines():
            norm = line.strip()
            if not norm:
                continue
            key = norm.lower()
            if key in seen_lines:
                continue
            seen_lines.add(key)
            merged_lines.append(norm)

    if merged_lines:
        return OCRRunResult("\n".join(merged_lines))
    if errors:
        return OCRRunResult("", error="; ".join(errors))
    if successful_runs > 0:
        return OCRRunResult("")
    return OCRRunResult("", error="no-runs")


_OCR_SPLIT_RE = re.compile(r"[,\|;/]+|\s{2,}")
_OCR_NUMBERING_RE = re.compile(r"^\s*\d+\s*[\)\].:\-]+\s*")
_OCR_BULLET_RE = re.compile(r"^\s*[-*•|]+\s*")
_OCR_SPACE_RE = re.compile(r"\s+")
_OCR_ALLOWED_CHARS_RE = re.compile(r"[^\w .\-#]", flags=re.UNICODE)


def extract_candidate_names(text: str, *, min_chars: int = 2) -> list[str]:
    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()
    min_len = max(1, int(min_chars))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = _OCR_NUMBERING_RE.sub("", line)
        line = _OCR_BULLET_RE.sub("", line)
        parts = [p.strip() for p in _OCR_SPLIT_RE.split(line)]
        for part in parts:
            if not part:
                continue
            part = _OCR_ALLOWED_CHARS_RE.sub(" ", part)
            part = _OCR_SPACE_RE.sub(" ", part).strip(" .-_")
            if not part:
                continue
            if len(part) < min_len:
                continue
            normalized = part.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            found.append(part)

    return found
