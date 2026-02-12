from __future__ import annotations

import unicodedata


def normalize_name_casefold(value: str) -> str:
    """NFKC-normalize + trim + casefold for stable name matching."""
    return unicodedata.normalize("NFKC", str(value or "").strip()).casefold()


def normalize_name_alnum_key(value: str) -> str:
    """Aggressive key for OCR de-duplication (drops non-alnum when possible)."""
    normalized = normalize_name_casefold(value)
    alnum_only = "".join(ch for ch in normalized if ch.isalnum())
    return alnum_only or normalized


def normalize_name_tokens(value: str) -> list[str]:
    """Tokenize normalized names for fuzzy-tail matching."""
    normalized = normalize_name_casefold(value)
    return [token for token in normalized.split(" ") if token]
