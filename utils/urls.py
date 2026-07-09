"""
URL normalization helpers.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urldefrag, urlsplit, urlunsplit


def canonicalize_url(value: str) -> str:
    """Canonicalize a URL for matching and deduplication."""
    if not value:
        return ""

    cleaned_value, _ = urldefrag(value.strip())
    parsed = urlsplit(cleaned_value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""

    normalized_query = urlencode(
        sorted(parse_qsl(parsed.query, keep_blank_values=True)),
        doseq=True,
    )
    normalized_path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            normalized_path,
            normalized_query,
            "",
        )
    )
