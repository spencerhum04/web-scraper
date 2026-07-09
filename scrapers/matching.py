"""
Keyword normalization and matching for scraper candidates.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from config.loader import KeywordConfig
from scrapers.types import JobCandidate, KeywordMatchResult

_NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Normalize text for whole-word and phrase-aware matching."""
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = _NON_ALNUM_RE.sub(" ", normalized)
    return _WHITESPACE_RE.sub(" ", normalized).strip()


@dataclass(frozen=True)
class _KeywordPattern:
    keyword: str
    pattern: re.Pattern[str]


class KeywordMatcher:
    """Matches candidates against the configured role + internship keywords."""

    def __init__(self, keywords: KeywordConfig):
        self._role_patterns = self._build_patterns(keywords.role_keywords)
        self._internship_patterns = self._build_patterns(keywords.internship_keywords)

    def match_candidate(self, candidate: JobCandidate) -> KeywordMatchResult | None:
        """Match the title first, then title + same-card context as a fallback."""
        normalized_title = normalize_text(candidate.title_text)
        title_roles = self._find_matches(normalized_title, self._role_patterns)
        title_internships = self._find_matches(
            normalized_title, self._internship_patterns
        )
        # Require both a role keyword and an internship keyword to appear
        # within the title text itself. Same-card context is no longer used
        # as a fallback for classification.
        if title_roles and title_internships:
            return KeywordMatchResult(
                matched_role_keywords=tuple(title_roles),
                matched_internship_keywords=tuple(title_internships),
                used_context=False,
            )

        return None

    @staticmethod
    def _build_patterns(keywords: tuple[str, ...]) -> tuple[_KeywordPattern, ...]:
        patterns: list[_KeywordPattern] = []
        seen: set[str] = set()
        for keyword in keywords:
            normalized_keyword = normalize_text(keyword)
            if not normalized_keyword or normalized_keyword in seen:
                continue
            seen.add(normalized_keyword)
            patterns.append(
                _KeywordPattern(
                    keyword=keyword,
                    pattern=re.compile(
                        rf"(?<![0-9a-z]){re.escape(normalized_keyword)}(?![0-9a-z])"
                    ),
                )
            )
        return tuple(patterns)

    @staticmethod
    def _find_matches(
        normalized_text: str, patterns: tuple[_KeywordPattern, ...]
    ) -> list[str]:
        matches: list[str] = []
        for keyword_pattern in patterns:
            if keyword_pattern.pattern.search(normalized_text):
                matches.append(keyword_pattern.keyword)
        return matches
