#!/usr/bin/env python3
"""
Main orchestrator for the SWE internship job scraping system.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime

from loguru import logger

from config.loader import AppConfig, CompanyConfig, ConfigError, load_app_config
from config.settings import settings
from models.job_posting import JobPosting
from scrapers.result import ScrapeResult, ScrapeStatus
from scrapers.scraper import Scraper
from services.discord_service import DiscordService
from services.supabase_service import SupabaseService
from utils.logger import setup_logger


class JobScrapingOrchestrator:
    """Main orchestrator for the job scraping system."""

    def __init__(
        self,
        enable_discord: bool = True,
        app_config: AppConfig | None = None,
        supabase_service: SupabaseService | None = None,
        discord_service: DiscordService | None = None,
    ):
        setup_logger(settings)
        self.logger = logger.bind(company="System")
        self.enable_discord = enable_discord

        try:
            self.app_config = app_config or load_app_config()
        except ConfigError as exc:
            self.logger.error(f"Failed to load application config: {exc}")
            raise

        self.companies = self.app_config.companies
        self.keywords = self.app_config.keywords
        self.supabase = supabase_service or SupabaseService()
        self.discord = discord_service or DiscordService()
        self.last_scrape_results: list[ScrapeResult] = []

        if not enable_discord:
            self.logger.info("Discord notifications disabled (debug mode)")

    async def initialize(self):
        """Initialize all services."""
        await self.supabase.initialize()

    async def scrape_company(self, company: CompanyConfig) -> list[JobPosting]:
        """Scrape jobs from a single company."""
        scraper = Scraper(company.name, company.url)

        try:
            return await scraper.scrape(self.keywords)
        except Exception as exc:
            self.logger.error(f"Error scraping {company.name}: {exc}")
            return []

    async def scrape_company_with_result(self, company: CompanyConfig) -> ScrapeResult:
        """Scrape jobs from a single company with status metadata."""
        if "scrape_company" in self.__dict__:
            jobs = await self.scrape_company(company)
            return ScrapeResult(
                company=company.name,
                status=ScrapeStatus.OK if jobs else ScrapeStatus.EMPTY,
                jobs=jobs,
            )

        scraper = Scraper(company.name, company.url)

        try:
            return await scraper.scrape_with_result(self.keywords)
        except Exception as exc:
            self.logger.error(f"Error scraping {company.name}: {exc}")
            return ScrapeResult(
                company=company.name,
                status=ScrapeStatus.ERROR,
                error=str(exc),
            )

    async def run_all_scrapers(
        self, company_filter: str | None = None
    ) -> dict[str, list[JobPosting]]:
        """Run scrapers for all companies concurrently, optionally filtered."""
        companies_to_scrape = list(self.companies)

        if company_filter:
            companies_to_scrape = [
                company
                for company in self.companies
                if company_filter.casefold() in company.name.casefold()
            ]
            if not companies_to_scrape:
                self.logger.error(f"No companies found matching '{company_filter}'")
                return {}

            self.logger.info(
                f"Scraping {len(companies_to_scrape)} companies matching '{company_filter}'..."
            )
        else:
            self.logger.info(f"Scraping {len(companies_to_scrape)} companies...")

        semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_SCRAPERS)

        async def scrape_with_limit(company: CompanyConfig) -> ScrapeResult:
            async with semaphore:
                return await self.scrape_company_with_result(company)

        results = await asyncio.gather(
            *(scrape_with_limit(company) for company in companies_to_scrape),
            return_exceptions=True,
        )

        jobs_by_company: dict[str, list[JobPosting]] = {}
        total_jobs = 0
        scrape_results: list[ScrapeResult] = []
        for company, result in zip(companies_to_scrape, results):
            if isinstance(result, Exception):
                self.logger.error(f"Failed to scrape {company.name}: {result}")
                jobs_by_company[company.name] = []
                scrape_results.append(
                    ScrapeResult(
                        company=company.name,
                        status=ScrapeStatus.ERROR,
                        error=str(result),
                    )
                )
                continue

            scrape_results.append(result)
            jobs_by_company[company.name] = result.jobs
            total_jobs += len(result.jobs)

        self.last_scrape_results = scrape_results
        self._log_scrape_summary(scrape_results)
        self.logger.info(f"Found {total_jobs} total job postings")
        return jobs_by_company

    def _log_scrape_summary(self, scrape_results: list[ScrapeResult]):
        if not scrape_results:
            return

        self.logger.info("=" * 80)
        self.logger.info("Scrape Summary")
        self.logger.info("=" * 80)
        for result in scrape_results:
            strategy = result.strategy or "-"
            artifacts = ", ".join(result.artifact_paths) if result.artifact_paths else "-"
            self.logger.info(
                f"{result.company}: status={result.status} "
                f"count={result.count} strategy={strategy} "
                f"duration={result.duration_seconds:.1f}s artifacts={artifacts}"
            )
        self.logger.info("=" * 80)

    async def process_and_store_jobs(
        self, jobs_by_company: dict[str, list[JobPosting]]
    ) -> list[JobPosting]:
        """Process scraped jobs and store new ones in the database."""
        all_jobs = [
            job for company_jobs in jobs_by_company.values() for job in company_jobs
        ]
        if not all_jobs:
            return []

        new_jobs = await self.supabase.insert_multiple_jobs(all_jobs)
        self.logger.info(f"Added {len(new_jobs)} new jobs to database")
        return new_jobs

    async def send_notifications(self, new_jobs: list[JobPosting]):
        """Send Discord notifications for new jobs."""
        if not new_jobs:
            self.logger.info("No new jobs found - skipping Discord notifications")
            return

        if not self.enable_discord:
            self.logger.info(
                f"Discord disabled - would have sent {len(new_jobs)} notifications"
            )
            for job in new_jobs:
                self.logger.info(f"  - {job.company}: {job.title}")
            return

        new_jobs.sort(key=lambda job: (job.company, job.title))
        self.logger.info(f"Sending notifications for {len(new_jobs)} new jobs")

        successful = await self.discord.send_multiple_notifications(new_jobs)
        if successful < len(new_jobs):
            self.logger.warning(
                f"Only {successful}/{len(new_jobs)} notifications were sent successfully"
            )

    async def print_stats(self):
        """Print job statistics."""
        stats = await self.supabase.get_job_stats()

        self.logger.info("=" * 50)
        self.logger.info("Job Statistics")
        self.logger.info("=" * 50)
        self.logger.info(f"Total jobs in database: {stats['total_jobs']}")
        self.logger.info(f"Jobs in last 7 days: {stats['recent_jobs']}")

        companies = stats.get("companies", {})
        if companies:
            self.logger.info("Top companies:")
            for company, count in list(companies.items())[:10]:
                self.logger.info(f"  - {company}: {count} jobs")

        self.logger.info("=" * 50)

    async def cleanup_old_data(self):
        """Cleanup old job postings."""
        if settings.IS_GITHUB_ACTIONS:
            self.logger.info("Running cleanup of old jobs...")
            await self.supabase.cleanup_old_jobs(days_to_keep=30)

    async def run(self, company_filter: str | None = None):
        """Main execution method."""
        start_time = datetime.now()
        self.logger.info("Starting SWE Internship Job Scraper")

        if company_filter:
            self.logger.info(f"Company filter: '{company_filter}'")

        try:
            await self.initialize()
            jobs_by_company = await self.run_all_scrapers(company_filter)
            new_jobs = await self.process_and_store_jobs(jobs_by_company)
            await self.send_notifications(new_jobs)
            await self.cleanup_old_data()

            execution_time = (datetime.now() - start_time).total_seconds()
            self.logger.success(f"Job scraping completed in {execution_time:.1f}s")
        except Exception as exc:
            self.logger.error(f"Fatal error in orchestrator: {exc}", exc_info=True)
            sys.exit(1)
        finally:
            await self.discord.aclose()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="SWE Internship Job Scraper")
    parser.add_argument(
        "--no-discord",
        action="store_true",
        help="Disable Discord notifications (debug mode)",
    )
    parser.add_argument(
        "--company",
        type=str,
        help="Run scraper for only the specified company (case-insensitive)",
    )
    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()
    orchestrator = JobScrapingOrchestrator(enable_discord=not args.no_discord)
    await orchestrator.run(company_filter=args.company)


if __name__ == "__main__":
    asyncio.run(main())
