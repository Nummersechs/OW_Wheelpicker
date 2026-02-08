from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from difflib import SequenceMatcher
import re
import shutil
import subprocess
import unicodedata
from typing import Iterable


@dataclass
class OCRRunResult:
    text: str
    error: str | None = None


def tesseract_available(cmd: str = "tesseract") -> bool:
    return shutil.which(cmd) is not None


@lru_cache(maxsize=8)
def _list_tesseract_languages(cmd: str) -> tuple[str, ...] | None:
    if not tesseract_available(cmd):
        return None
    try:
        completed = subprocess.run(
            [cmd, "--list-langs"],
            capture_output=True,
            text=True,
            check=False,
            timeout=3.0,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    langs: list[str] = []
    for raw_line in (completed.stdout or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("list of available languages"):
            continue
        langs.append(line)
    if not langs:
        return None
    return tuple(sorted(set(langs)))


def _resolve_tesseract_lang(cmd: str, lang: str | None) -> str | None:
    if not lang:
        return None
    tokens = [token.strip() for token in str(lang).split("+") if token.strip()]
    if not tokens:
        return None
    available = _list_tesseract_languages(cmd)
    if not available:
        return "+".join(tokens)
    available_set = set(available)
    filtered = [token for token in tokens if token in available_set]
    if filtered:
        return "+".join(filtered)
    if "eng" in available_set:
        return "eng"
    return None


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
    resolved_lang = _resolve_tesseract_lang(cmd, lang)
    if resolved_lang:
        proc_args.extend(["-l", resolved_lang])
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


_OCR_NUMBERING_RE = re.compile(r"^\s*\d+\s*[\)\].:\-]+\s*")
_OCR_BULLET_RE = re.compile(r"^\s*[-*•|]+\s*")
_OCR_SPACE_RE = re.compile(r"\s+")
_OCR_ALLOWED_CHARS_RE = re.compile(r"[^\w .\-#]", flags=re.UNICODE)
_OCR_HAS_ALPHA_RE = re.compile(r"[^\W\d_]", flags=re.UNICODE)
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
    total_chars = sum(1 for ch in value if ch.isalnum())
    if total_chars <= 0:
        return False
    digit_chars = sum(1 for ch in value if ch.isdigit())
    if (digit_chars / total_chars) > max(0.0, float(max_digit_ratio)):
        return False
    return True


def _candidate_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    alnum_only = "".join(ch for ch in normalized if ch.isalnum())
    return alnum_only or normalized


def _display_name_quality(value: str) -> tuple[int, int]:
    separators = sum(1 for ch in value if not ch.isalnum())
    return (separators, -len(value))


def _normalized_tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return [token for token in normalized.split(" ") if token]


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


def extract_candidate_names(
    text: str,
    *,
    min_chars: int = 2,
    max_chars: int = 24,
    max_words: int = 2,
    max_digit_ratio: float = 0.45,
) -> list[str]:
    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()
    min_len = max(1, int(min_chars))
    max_len = max(0, int(max_chars))
    word_limit = max(0, int(max_words))
    digit_ratio = max(0.0, float(max_digit_ratio))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = _OCR_NUMBERING_RE.sub("", line)
        line = _OCR_BULLET_RE.sub("", line)
        # The OCR list is expected to be line-based. Ignore any metadata suffix after "|".
        line = line.split("|", 1)[0].strip()
        if not line:
            continue
        line = _OCR_EMOJI_ICON_RE.sub(" ", line)
        part = _OCR_ALLOWED_CHARS_RE.sub(" ", line)
        part = _OCR_SPACE_RE.sub(" ", part).strip(" .-_")
        if not part:
            continue
        if not _looks_like_name(
            part,
            min_chars=min_len,
            max_chars=max_len,
            max_words=word_limit,
            max_digit_ratio=digit_ratio,
        ):
            continue
        candidate_key = _candidate_key(part)
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        found.append(part)

    return found


def extract_candidate_names_multi(
    texts: Iterable[str],
    *,
    min_chars: int = 2,
    max_chars: int = 24,
    max_words: int = 2,
    max_digit_ratio: float = 0.45,
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
        seen_in_text: set[str] = set()
        for name in extract_candidate_names(
            text,
            min_chars=min_chars,
            max_chars=max_chars,
            max_words=max_words,
            max_digit_ratio=max_digit_ratio,
        ):
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
                    and _display_name_quality(name) < _display_name_quality(current_name)
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
