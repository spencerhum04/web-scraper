"""
Layered candidate extraction.
"""
from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Page

from scrapers.types import JobCandidate

from . import dom, embedded, jsonld


@dataclass(frozen=True)
class ExtractionResult:
    candidates: list[JobCandidate]
    strategy: str | None


class Extractor:
    """Extract candidates from structured data before falling back to DOM heuristics."""

    async def extract(self, page: Page) -> ExtractionResult:
        merged: list[JobCandidate] = []
        seen: set[str] = set()
        primary_strategy: str | None = None

        for strategy, extractor in (
            ("jsonld", jsonld.extract_from_page),
            ("embedded", embedded.extract_from_page),
            ("dom", dom.extract_from_page),
        ):
            candidates = await extractor(page)
            new_candidates = [
                candidate
                for candidate in candidates
                if self._dedup_key(candidate) not in seen
            ]
            for candidate in new_candidates:
                seen.add(self._dedup_key(candidate))
                merged.append(candidate)

            if new_candidates and primary_strategy is None:
                primary_strategy = strategy
                if strategy in {"jsonld", "embedded"}:
                    break

        return ExtractionResult(candidates=merged, strategy=primary_strategy)

    @staticmethod
    def _dedup_key(candidate: JobCandidate) -> str:
        return "|".join(
            (
                candidate.title_text.casefold(),
                candidate.url or "",
                candidate.context_text[:160].casefold(),
            )
        )
