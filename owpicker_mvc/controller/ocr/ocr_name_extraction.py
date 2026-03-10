from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Iterable

from logic.name_normalization import normalize_name_alnum_key, normalize_name_tokens


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
