import json

import pytest

from config.loader import AppConfig, CompanyConfig, ConfigError, KeywordConfig, load_app_config
from main import JobScrapingOrchestrator
from models.job_posting import JobPosting


class FakeSupabaseService:
    def __init__(self):
        self.initialized = False

    async def initialize(self):
        self.initialized = True

    async def insert_multiple_jobs(self, jobs):
        return jobs

    async def get_job_stats(self):
        return {"total_jobs": 0, "companies": {}, "recent_jobs": 0}

    async def cleanup_old_jobs(self, days_to_keep: int = 30):
        return None


class FakeDiscordService:
    def __init__(self):
        self.closed = False

    async def send_multiple_notifications(self, jobs):
        return len(jobs)

    async def aclose(self):
        self.closed = True


def test_load_app_config_rejects_invalid_json(tmp_path):
    companies_path = tmp_path / "company_urls.json"
    keywords_path = tmp_path / "keywords.json"
    companies_path.write_text("{not valid json", encoding="utf-8")
    keywords_path.write_text(
        json.dumps(
            {
                "role_keywords": ["software"],
                "internship_keywords": ["intern"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError):
        load_app_config(companies_path=companies_path, keywords_path=keywords_path)


def test_load_app_config_allows_empty_company_list(tmp_path):
    companies_path = tmp_path / "company_urls.json"
    keywords_path = tmp_path / "keywords.json"
    companies_path.write_text(json.dumps({"companies": []}), encoding="utf-8")
    keywords_path.write_text(
        json.dumps(
            {
                "role_keywords": [],
                "internship_keywords": [],
            }
        ),
        encoding="utf-8",
    )

    config = load_app_config(companies_path=companies_path, keywords_path=keywords_path)

    assert config.companies == ()
    assert config.keywords.role_keywords == ()
    assert config.keywords.internship_keywords == ()


@pytest.mark.asyncio
async def test_orchestrator_filters_companies_case_insensitively():
    orchestrator = JobScrapingOrchestrator(
        enable_discord=False,
        app_config=AppConfig(
            companies=(
                CompanyConfig(name="Intuit", url="https://example.com/intuit"),
                CompanyConfig(name="Solana", url="https://example.com/solana"),
            ),
            keywords=KeywordConfig(
                role_keywords=("software",),
                internship_keywords=("intern",),
            ),
        ),
        supabase_service=FakeSupabaseService(),
        discord_service=FakeDiscordService(),
    )

    async def fake_scrape_company(company):
        return [
            JobPosting(
                company=company.name,
                title=f"{company.name} Software Intern",
                url=f"https://example.com/{company.name.lower()}",
            )
        ]

    orchestrator.scrape_company = fake_scrape_company

    jobs_by_company = await orchestrator.run_all_scrapers(company_filter="INT")

    assert list(jobs_by_company) == ["Intuit"]
    assert jobs_by_company["Intuit"][0].title == "Intuit Software Intern"
