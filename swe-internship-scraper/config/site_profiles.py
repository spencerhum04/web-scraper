"""
Optional per-site scraping profiles.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PaginationProfile:
    type: str | None = None
    selector: str | None = None
    max_clicks: int | None = None


@dataclass(frozen=True)
class SiteProfile:
    content_selector: str | None = None
    wait: str | None = None
    pagination: PaginationProfile = PaginationProfile()
    block_on_headless: bool = False


def load_site_profiles(path: str | Path | None = None) -> dict[str, SiteProfile]:
    profile_path = Path(path) if path else Path(__file__).resolve().parent / "site_profiles.json"
    try:
        raw_profiles = json.loads(profile_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

    if not isinstance(raw_profiles, dict):
        return {}

    profiles: dict[str, SiteProfile] = {}
    for company, raw_profile in raw_profiles.items():
        if not isinstance(company, str) or not isinstance(raw_profile, dict):
            continue
        profiles[company] = _parse_profile(raw_profile)
    return profiles


def _parse_profile(raw_profile: dict[str, Any]) -> SiteProfile:
    raw_pagination = raw_profile.get("pagination")
    pagination = PaginationProfile()
    if isinstance(raw_pagination, dict):
        max_clicks = raw_pagination.get("max_clicks")
        pagination = PaginationProfile(
            type=_optional_string(raw_pagination.get("type")),
            selector=_optional_string(raw_pagination.get("selector")),
            max_clicks=max_clicks if isinstance(max_clicks, int) else None,
        )

    return SiteProfile(
        content_selector=_optional_string(raw_profile.get("content_selector")),
        wait=_optional_string(raw_profile.get("wait")),
        pagination=pagination,
        block_on_headless=bool(raw_profile.get("block_on_headless", False)),
    )


def _optional_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
