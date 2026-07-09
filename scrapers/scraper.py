"""
Unified scraper for SWE internship job postings.
"""
from __future__ import annotations

import asyncio
from time import monotonic

from loguru import logger
from playwright.async_api import async_playwright

from config.loader import KeywordConfig
from config.settings import settings
from models.job_posting import JobPosting
from scrapers.builder import JobPostingBuilder
from scrapers.extraction import Extractor
from scrapers.extraction.dom import extract_candidates_from_html
from scrapers.navigator import Navigator
from scrapers.result import ScrapeResult, ScrapeStatus
from scrapers.types import JobCandidate
from utils.urls import canonicalize_url

__all__ = ["Scraper", "extract_candidates_from_html"]


class Scraper:
    """Scraper for SWE internship job postings using layered raw-page extraction."""

    def __init__(self, company_name: str, careers_url: str):
        self.company_name = company_name
        self.careers_url = careers_url
        self.logger = logger.bind(company=company_name)
        self.builder = JobPostingBuilder(company_name, careers_url)
        self.extractor = Extractor()

    async def scrape(self, keywords: KeywordConfig) -> list[JobPosting]:
        """Scrape job postings from the company's careers page."""
        return (await self.scrape_with_result(keywords)).jobs

    async def scrape_with_result(self, keywords: KeywordConfig) -> ScrapeResult:
        """Scrape a company and return observable status metadata."""
        start_time = monotonic()
        last_result: ScrapeResult | None = None

        async with async_playwright() as playwright:
            for attempt in range(1, settings.SCRAPE_RETRY_ATTEMPTS + 1):
                async with Navigator(self.company_name, self.careers_url) as navigator:
                    load_result = await navigator.load(playwright, attempt=attempt)
                    if load_result.status is ScrapeStatus.OK and load_result.page is not None:
                        extraction = await self.extractor.extract(load_result.page)
                        jobs = self._build_job_postings(extraction.candidates, keywords)
                        status = ScrapeStatus.OK if jobs else ScrapeStatus.EMPTY
                        self.logger.info(
                            f"Found {len(jobs)} unique job postings"
                            + (f" via {extraction.strategy}" if extraction.strategy else "")
                        )
                        return ScrapeResult(
                            company=self.company_name,
                            status=status,
                            jobs=jobs,
                            strategy=extraction.strategy,
                            duration_seconds=monotonic() - start_time,
                        )

                    last_result = ScrapeResult(
                        company=self.company_name,
                        status=load_result.status,
                        duration_seconds=monotonic() - start_time,
                        error=load_result.error,
                        artifact_paths=load_result.artifact_paths,
                    )

                if attempt < settings.SCRAPE_RETRY_ATTEMPTS:
                    delay_seconds = min(
                        settings.SCRAPE_RETRY_BASE_DELAY_SECONDS * attempt,
                        settings.SCRAPE_RETRY_MAX_DELAY_SECONDS,
                    )
                    self.logger.warning(
                        f"Attempt {attempt} ended with {last_result.status}; "
                        f"retrying in {delay_seconds:.1f}s"
                    )
                    await asyncio.sleep(delay_seconds)

        if last_result is not None:
            self.logger.error(
                f"Scraping ended with {last_result.status}"
                + (f": {last_result.error}" if last_result.error else "")
            )
            return last_result

        return ScrapeResult(
            company=self.company_name,
            status=ScrapeStatus.ERROR,
            duration_seconds=monotonic() - start_time,
            error="Scraper exited before any attempt ran",
        )

    async def _extract_candidates(self, page) -> list[JobCandidate]:
        """Extract structured job candidates from the page."""
        return (await self.extractor.extract(page)).candidates

    def _build_job_postings(
        self, candidates: list[JobCandidate], keywords: KeywordConfig
    ) -> list[JobPosting]:
        """Filter candidates and convert them into job postings."""
        return self.builder.build(candidates, keywords)

    def _resolve_job_url(self, candidate_url: str | None) -> str | None:
        """Resolve the URL to persist for a matched candidate."""
        return self.builder.resolve_job_url(candidate_url)

    def _build_dedup_key(self, candidate: JobCandidate, job_url: str) -> str:
        """Build a stable per-run dedup key."""
        return self.builder.build_dedup_key(candidate, job_url)

    @staticmethod
    def _canonicalize_url(value: str) -> str:
        """Canonicalize a URL for matching and deduplication."""
        return canonicalize_url(value)
