import pytest

from config.loader import KeywordConfig
from models.job_posting import JobPosting
from scrapers.extraction import jsonld
from scrapers.scraper import Scraper, extract_candidates_from_html


class FakePage:
    def __init__(self, url, payloads):
        self.url = url
        self.payloads = payloads

    async def evaluate(self, script):
        return self.payloads


def test_scraper_extracts_title_match_from_local_html():
    scraper = Scraper("Example", "https://example.com/careers")
    keywords = KeywordConfig(
        role_keywords=("software",),
        internship_keywords=("intern",),
    )
    html = """
    <main>
      <article class="job-card">
        <a href="/jobs/123">Software Engineer Intern</a>
      </article>
    </main>
    """

    candidates = extract_candidates_from_html(html, "https://example.com/careers")
    jobs = scraper._build_job_postings(candidates, keywords)

    assert len(jobs) == 1
    assert jobs[0].title == "Software Engineer Intern"
    assert str(jobs[0].url) == "https://example.com/jobs/123"


def test_scraper_uses_same_card_context_for_matching():
    scraper = Scraper("Example", "https://example.com/careers")
    keywords = KeywordConfig(
        role_keywords=("developer",),
        internship_keywords=("intern",),
    )
    html = """
    <main>
      <article class="job-card">
        <h2><a href="/jobs/456">Developer</a></h2>
        <p>Winter 2026 Intern</p>
      </article>
    </main>
    """

    candidates = extract_candidates_from_html(html, "https://example.com/careers")
    jobs = scraper._build_job_postings(candidates, keywords)

    assert len(jobs) == 1
    assert jobs[0].title == "Developer"


def test_scraper_ignores_unrelated_page_copy():
    scraper = Scraper("Example", "https://example.com/careers")
    keywords = KeywordConfig(
        role_keywords=("software",),
        internship_keywords=("intern",),
    )
    html = """
    <main>
      <section>
        <p>Our software intern program is amazing.</p>
      </section>
      <article class="job-card">
        <a href="/jobs/789">Product Manager</a>
      </article>
    </main>
    """

    candidates = extract_candidates_from_html(html, "https://example.com/careers")
    jobs = scraper._build_job_postings(candidates, keywords)

    assert len(jobs) == 0


@pytest.mark.asyncio
async def test_jsonld_extractor_reads_job_posting_objects():
    page = FakePage(
        "https://example.com/careers",
        [
            """
            {
              "@context": "https://schema.org",
              "@type": "JobPosting",
              "title": "Software Engineering Intern",
              "url": "/jobs/123",
              "jobLocation": {
                "address": {
                  "addressLocality": "New York",
                  "addressRegion": "NY"
                }
              },
              "datePosted": "2026-01-15"
            }
            """
        ],
    )

    candidates = await jsonld.extract_from_page(page)

    assert len(candidates) == 1
    assert candidates[0].title_text == "Software Engineering Intern"
    assert candidates[0].url == "https://example.com/jobs/123"
    assert candidates[0].source == "jsonld"


def test_job_posting_hash_prefers_canonical_url():
    first = JobPosting(
        company="Example",
        title="Software Intern",
        url="https://example.com/jobs/123?b=2&a=1#details",
    )
    second = JobPosting(
        company="Example",
        title="Retitled Internship",
        url="https://example.com/jobs/123?a=1&b=2",
    )

    assert first.hash == second.hash
    assert first.hash == "example#https://example.com/jobs/123?a=1&b=2"
