"""
Simplified job posting model with essential fields only.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl, field_serializer, field_validator, model_validator

from utils.urls import canonicalize_url


class JobPosting(BaseModel):
    """Simplified model for job posting data."""

    company: str = Field(..., description="Company name")
    title: str = Field(..., description="Job title")
    url: HttpUrl = Field(..., description="Job posting URL")
    location: Optional[str] = Field(None, description="Job location")
    scraped_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the job was scraped",
    )
    hash: Optional[str] = Field(None, description="Hash for deduplication")

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        """Clean and normalize the job title."""
        return " ".join(value.split())

    @model_validator(mode="after")
    def ensure_hash(self) -> "JobPosting":
        """Generate the stable persisted hash when one is not provided."""
        if self.hash:
            return self

        company = self.company.lower().strip()
        canonical_url = canonicalize_url(str(self.url))
        if canonical_url:
            self.hash = f"{company}#{canonical_url}"
            return self

        title = self.title.lower().strip()
        self.hash = f"{company}#{title}"
        return self

    @field_serializer("scraped_at")
    def serialize_scraped_at(self, value: datetime) -> str:
        """Serialize timestamps consistently."""
        return value.isoformat()

    @field_serializer("url")
    def serialize_url(self, value: HttpUrl) -> str:
        """Serialize URLs consistently."""
        return str(value)

    def to_discord_embed(self) -> dict:
        """Convert to Discord embed format."""
        return {
            "title": self.title,
            "url": str(self.url),
            "color": 0x00B4D8,
            "fields": [
                {"name": "Company", "value": self.company, "inline": True},
            ],
            "timestamp": self.scraped_at.isoformat(),
        }

    def to_supabase_record(self) -> dict:
        """Convert to Supabase record format."""
        return {
            "hash": self.hash,
            "company": self.company,
            "role": self.title,
            "location": self.location,
            "link_to_posting": str(self.url),
            "scraped_at": self.scraped_at.isoformat(),
        }
