"""
Browser navigation and page-access helpers.
"""
from __future__ import annotations

import asyncio
import random
import re
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit

from loguru import logger
from playwright.async_api import BrowserContext, Page, Playwright, TimeoutError
from playwright_stealth import stealth_async

from config.site_profiles import SiteProfile, load_site_profiles
from config.settings import settings
from scrapers.matching import normalize_text
from scrapers.result import ScrapeStatus


@dataclass(frozen=True)
class PageLoadResult:
    page: Page | None
    status: ScrapeStatus
    duration_seconds: float
    artifact_paths: tuple[str, ...] = ()
    error: str | None = None


class Navigator:
    """Loads career pages with human-like browser behavior."""

    DEFAULT_CONTENT_SELECTORS = (
        "[data-job-id]",
        "[data-posting-id]",
        "[data-job-posting-id]",
        "[data-testid*='job' i]",
        "[data-qa*='job' i]",
        "script[type='application/ld+json']",
        "article",
        "li",
    )

    LOAD_MORE_SELECTORS = (
        "button:has-text('Load more')",
        "button:has-text('Show more')",
        "a:has-text('Load more')",
        "a:has-text('Next')",
        "button:has-text('Next')",
    )

    def __init__(self, company_name: str, careers_url: str):
        self.company_name = company_name
        self.careers_url = careers_url
        self.logger = logger.bind(company=company_name)
        self._context: BrowserContext | None = None
        self.profile = load_site_profiles().get(company_name, SiteProfile())

    async def __aenter__(self) -> "Navigator":
        return self

    async def __aexit__(self, *_):
        await self.close()

    async def close(self):
        if self._context is not None:
            await self._context.close()
            self._context = None

    async def load(self, playwright: Playwright, *, attempt: int = 1) -> PageLoadResult:
        start_time = monotonic()
        page: Page | None = None
        try:
            context = await self._create_context(playwright, attempt=attempt)
            page = await context.new_page()
            await self._setup_page(page)

            self.logger.info(f"Navigating to {self.careers_url}")
            await self._goto_with_fallback(page)

            status = await self.classify(page)
            if status is not ScrapeStatus.OK:
                artifacts = await self.save_artifacts(page, status.value)
                return PageLoadResult(
                    page=page,
                    status=status,
                    duration_seconds=monotonic() - start_time,
                    artifact_paths=artifacts,
                )

            await self._wait_for_content_signal(page)
            await self._human_interactions(page)
            return PageLoadResult(
                page=page,
                status=ScrapeStatus.OK,
                duration_seconds=monotonic() - start_time,
            )
        except TimeoutError as exc:
            artifacts = await self.save_artifacts(page, "timeout") if page else ()
            return PageLoadResult(
                page=page,
                status=ScrapeStatus.TIMEOUT,
                duration_seconds=monotonic() - start_time,
                artifact_paths=artifacts,
                error=str(exc),
            )
        except Exception as exc:
            status = ScrapeStatus.BLOCKED if self.is_blocked_error(str(exc)) else ScrapeStatus.ERROR
            artifacts = await self.save_artifacts(page, status.value) if page else ()
            return PageLoadResult(
                page=page,
                status=status,
                duration_seconds=monotonic() - start_time,
                artifact_paths=artifacts,
                error=str(exc),
            )

    async def _create_context(self, playwright: Playwright, *, attempt: int) -> BrowserContext:
        await self.close()
        fingerprint = self._fingerprint()
        launch_options = {
            "headless": self._should_run_headless(attempt),
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--window-size=1920,1080",
                "--disable-infobars",
                "--mute-audio",
            ],
        }
        if settings.PROXY_URL:
            launch_options["proxy"] = {"server": settings.PROXY_URL}
        if settings.BROWSER_CHANNEL:
            launch_options["channel"] = settings.BROWSER_CHANNEL

        context_options = {
            "user_agent": fingerprint["user_agent"],
            "locale": fingerprint["locale"],
            "timezone_id": fingerprint["timezone_id"],
            "viewport": {"width": 1920, "height": 1080},
            "extra_http_headers": {
                "Accept-Language": fingerprint["accept_language"],
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,image/apng,*/*;q=0.8"
                ),
                "Upgrade-Insecure-Requests": "1",
            },
        }
        user_data_dir = self._user_data_dir()
        try:
            self._context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                **launch_options,
                **context_options,
            )
        except Exception:
            launch_options.pop("channel", None)
            self._context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                **launch_options,
                **context_options,
            )
        await self._context.add_init_script(
            f"""
            Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
            Object.defineProperty(navigator, 'platform', {{ get: () => '{fingerprint["platform"]}' }});
            Object.defineProperty(navigator, 'languages', {{ get: () => ['en-US', 'en'] }});
            Object.defineProperty(navigator, 'plugins', {{ get: () => [1, 2, 3, 4, 5] }});
            window.chrome = window.chrome || {{ runtime: {{}} }};
            """
        )
        return self._context

    async def _setup_page(self, page: Page):
        await stealth_async(page)
        delay = random.uniform(settings.MIN_DELAY_SECONDS, settings.MAX_DELAY_SECONDS)
        await asyncio.sleep(delay)

    async def _goto_with_fallback(self, page: Page):
        errors: list[Exception] = []
        for wait_until, timeout in (
            ("domcontentloaded", settings.PAGE_LOAD_TIMEOUT),
            ("load", settings.PAGE_LOAD_TIMEOUT + 10000),
        ):
            try:
                await page.goto(self.careers_url, timeout=timeout, wait_until=wait_until)
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                return
            except Exception as exc:
                errors.append(exc)
                self.logger.warning(f"Loading strategy '{wait_until}' failed: {exc}")

        raise errors[-1]

    async def _wait_for_content_signal(self, page: Page):
        selector = ", ".join(self.DEFAULT_CONTENT_SELECTORS)
        if self.profile.content_selector:
            selector = self.profile.content_selector
        try:
            await page.wait_for_selector(selector, timeout=settings.CONTENT_SELECTOR_TIMEOUT)
        except TimeoutError:
            self.logger.warning("No explicit job content selector appeared before timeout")

    async def _human_interactions(self, page: Page):
        await self._move_mouse(page)
        await self._click_load_more(page)
        await self._auto_scroll(page)
        await page.wait_for_timeout(random.randint(700, 1500))

    async def _move_mouse(self, page: Page):
        for _ in range(random.randint(2, 4)):
            await page.mouse.move(random.randint(100, 1600), random.randint(120, 900), steps=8)
            await page.wait_for_timeout(random.randint(120, 360))

    async def _click_load_more(self, page: Page):
        for _ in range(settings.MAX_LOAD_MORE_CLICKS):
            max_clicks = self.profile.pagination.max_clicks or settings.MAX_LOAD_MORE_CLICKS
            if _ >= max_clicks:
                return
            clicked = False
            selectors = self.LOAD_MORE_SELECTORS
            if self.profile.pagination.selector:
                selectors = (self.profile.pagination.selector,)
            for selector in selectors:
                element = page.locator(selector).first
                try:
                    if await element.count() and await element.is_visible(timeout=500):
                        await element.click(timeout=1500)
                        await page.wait_for_timeout(random.randint(900, 1800))
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                return

    async def _auto_scroll(self, page: Page):
        previous_height = 0
        stable_iterations = 0
        for _ in range(settings.MAX_SCROLL_ITERATIONS):
            current_height = await page.evaluate("document.body.scrollHeight || 0")
            if current_height == previous_height:
                stable_iterations += 1
            else:
                stable_iterations = 0
                previous_height = current_height

            if stable_iterations >= 2:
                break

            step = random.randint(420, 900)
            await page.mouse.wheel(0, step)
            await page.wait_for_timeout(random.randint(350, 900))

    async def classify(self, page: Page) -> ScrapeStatus:
        page_snapshot = await page.evaluate(
            """
            () => ({
                title: document.title || "",
                body: (document.body && document.body.innerText) ? document.body.innerText.slice(0, 2500) : "",
            })
            """
        )
        text = normalize_text(
            " ".join([page_snapshot.get("title", ""), page_snapshot.get("body", "")])
        )
        blocked_markers = (
            "access denied",
            "verify you are human",
            "security check",
            "attention required",
            "unusual traffic",
            "captcha",
            "press and hold",
            "bot detection",
            "blocked request",
        )
        if any(marker in text for marker in blocked_markers):
            return ScrapeStatus.BLOCKED
        return ScrapeStatus.OK

    async def save_artifacts(self, page: Page | None, reason: str) -> tuple[str, ...]:
        if page is None:
            return ()

        artifact_dir = Path(settings.ARTIFACT_DIR)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", self.company_name.casefold()).strip("-")
        base_path = artifact_dir / f"{slug}-{reason}"
        paths: list[str] = []
        try:
            screenshot_path = base_path.with_suffix(".png")
            await page.screenshot(path=str(screenshot_path), full_page=True)
            paths.append(str(screenshot_path))
        except Exception as exc:
            self.logger.warning(f"Could not save screenshot artifact: {exc}")
        try:
            html_path = base_path.with_suffix(".html")
            html_path.write_text(await page.content(), encoding="utf-8")
            paths.append(str(html_path))
        except Exception as exc:
            self.logger.warning(f"Could not save HTML artifact: {exc}")
        return tuple(paths)

    def _fingerprint(self) -> dict[str, str]:
        user_agent = random.choice(settings.USER_AGENTS)
        is_macos = "Macintosh" in user_agent
        is_windows = "Windows" in user_agent
        return {
            "user_agent": user_agent,
            "accept_language": "en-US,en;q=0.9",
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "platform": "MacIntel" if is_macos else "Win32" if is_windows else "Linux x86_64",
        }

    def _should_run_headless(self, attempt: int) -> bool:
        if self.profile.block_on_headless and attempt > 1:
            return False
        if self.company_name in settings.KNOWN_DIFFICULT_SITES and attempt > 1:
            return False
        return settings.HEADLESS and attempt == 1

    def _user_data_dir(self) -> Path:
        domain = domain_for_url(self.careers_url).replace(":", "-") or "unknown"
        company = re.sub(r"[^a-z0-9]+", "-", self.company_name.casefold()).strip("-")
        root = Path(settings.USER_DATA_DIR)
        path = root / f"{company}-{domain}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def is_blocked_error(error_message: str) -> bool:
        normalized_error = normalize_text(error_message)
        blocked_markers = (
            "target page context or browser has been closed",
            "access denied",
            "captcha",
            "blocked",
            "challenge",
        )
        return any(marker in normalized_error for marker in blocked_markers)


def domain_for_url(url: str) -> str:
    return urlsplit(url).netloc.casefold()
