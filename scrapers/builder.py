"""
Build persisted job postings from extracted candidates.
"""
from __future__ import annotations

from config.loader import KeywordConfig
from config.settings import settings
from models.job_posting import JobPosting
from scrapers.matching import KeywordMatcher, normalize_text
from scrapers.types import JobCandidate
from utils.urls import canonicalize_url


class JobPostingBuilder:
    """Filter candidates and convert them into job postings."""

    def __init__(self, company_name: str, careers_url: str):
        self.company_name = company_name
        self.careers_url = careers_url

    def build(self, candidates: list[JobCandidate], keywords: KeywordConfig) -> list[JobPosting]:
        matcher = KeywordMatcher(keywords)
        seen: set[str] = set()
        jobs: list[JobPosting] = []

        for candidate in candidates:
            match = matcher.match_candidate(candidate)
            if match is None:
                continue

            job_url = self.resolve_job_url(candidate.url)
            if not job_url:
                continue

            dedup_key = self.build_dedup_key(candidate, job_url)
            if dedup_key in seen:
                continue

            seen.add(dedup_key)
            title = candidate.title_text or candidate.context_text
            jobs.append(
                JobPosting(
                    title=title,
                    company=self.company_name,
                    url=job_url,
                    location=candidate.location,
                )
            )

        return jobs

    def resolve_job_url(self, candidate_url: str | None) -> str | None:
        canonical_candidate_url = canonicalize_url(candidate_url or "")
        if canonical_candidate_url:
            return canonical_candidate_url

        if self.company_name in settings.COMPANIES_USE_MAIN_URL:
            return canonicalize_url(self.careers_url)

        return None

    @staticmethod
    def build_dedup_key(candidate: JobCandidate, job_url: str) -> str:
        normalized_title = normalize_text(candidate.title_text or candidate.context_text)
        return f"{normalized_title}|{canonicalize_url(job_url)}"
