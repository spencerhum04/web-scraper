"""
Discord notification service with individual job notifications.
"""
from __future__ import annotations

import asyncio

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from models.job_posting import JobPosting


class DiscordService:
    """Service for sending Discord notifications via webhook."""

    def __init__(self):
        self.webhook_url = settings.DISCORD_WEBHOOK_URL
        self.rate_limit_delay = settings.NOTIFICATION_DELAY_SECONDS
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def send_job_notification(self, job: JobPosting) -> bool:
        """Send an individual job notification to Discord."""
        if not self.webhook_url:
            logger.warning("Discord webhook URL not configured")
            return False

        payload = {
            "username": "SWE Internship Bot",
            "embeds": [job.to_discord_embed()],
        }

        try:
            client = await self._get_client()
            response = await client.post(self.webhook_url, json=payload)

            if response.status_code == 204:
                logger.success(f"Discord notification sent: {job.company} - {job.title}")
                return True

            if response.status_code == 429:
                retry_after = float(response.headers.get("X-RateLimit-Reset-After", 5))
                logger.warning(f"Discord rate limit hit, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                raise RuntimeError("Rate limited")

            logger.error(
                f"Discord notification failed: {response.status_code} - {response.text}"
            )
            return False
        except httpx.HTTPError as exc:
            logger.error(f"HTTP error sending Discord notification: {exc}")
            raise
        except Exception as exc:
            logger.error(f"Error sending Discord notification: {exc}")
            raise

    async def send_multiple_notifications(self, jobs: list[JobPosting]) -> int:
        """Send notifications for multiple jobs with simple rate limiting."""
        if not jobs:
            logger.info("No jobs to notify about")
            return 0

        successful = 0
        for index, job in enumerate(jobs):
            try:
                if await self.send_job_notification(job):
                    successful += 1

                if index < len(jobs) - 1:
                    await asyncio.sleep(self.rate_limit_delay)
            except Exception as exc:
                logger.error(
                    f"Failed to send notification for {job.company} - {job.title}: {exc}"
                )

        logger.info(f"Sent {successful}/{len(jobs)} Discord notifications")
        return successful

    async def aclose(self):
        """Close the shared async HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
