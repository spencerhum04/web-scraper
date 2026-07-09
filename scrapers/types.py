"""
Internal scraper types.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobCandidate:
    """Pre-JobPosting job candidate extracted from the careers page."""

    title_text: str
    context_text: str
    url: str | None = None
    location: str | None = None
    posted_at: str | None = None
    source: str = "dom"


@dataclass(frozen=True)
class KeywordMatchResult:
    """Keyword match details for a job candidate."""

    matched_role_keywords: tuple[str, ...]
    matched_internship_keywords: tuple[str, ...]
    used_context: bool
