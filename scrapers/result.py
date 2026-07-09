"""
Scrape result models.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from models.job_posting import JobPosting


class ScrapeStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    BLOCKED = "blocked"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass(frozen=True)
class ScrapeResult:
    """Outcome of one company scrape."""

    company: str
    status: ScrapeStatus
    jobs: list[JobPosting] = field(default_factory=list)
    strategy: str | None = None
    duration_seconds: float = 0.0
    error: str | None = None
    artifact_paths: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        return len(self.jobs)
