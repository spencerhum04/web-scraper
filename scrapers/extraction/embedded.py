"""
Embedded SPA state extraction from rendered pages.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable
from urllib.parse import urljoin

from playwright.async_api import Page

from scrapers.types import JobCandidate
from utils.urls import canonicalize_url

_STATE_KEYS = (
    "__NEXT_DATA__",
    "__INITIAL_STATE__",
    "__APOLLO_STATE__",
    "__NUXT__",
)

_TITLE_KEYS = ("title", "jobTitle", "name", "position", "role")
_URL_KEYS = ("url", "absoluteUrl", "applyUrl", "jobUrl", "externalUrl", "hostedUrl")
_LOCATION_KEYS = ("location", "jobLocation", "locations", "office", "offices")
_DATE_KEYS = ("datePosted", "postedAt", "createdAt", "updatedAt")
_JOB_HINT_KEYS = ("job", "posting", "opening", "requisition", "position")


async def extract_from_page(page: Page) -> list[JobCandidate]:
    snapshots = await page.evaluate(
        """
        () => {
            const values = [];
            for (const key of ["__NEXT_DATA__", "__INITIAL_STATE__", "__APOLLO_STATE__", "__NUXT__"]) {
                const script = document.getElementById(key);
                if (script && script.textContent) {
                    values.push(script.textContent);
                }
                if (window[key]) {
                    try {
                        values.push(JSON.stringify(window[key]));
                    } catch (error) {}
                }
            }

            for (const element of document.querySelectorAll("[data-page]")) {
                const value = element.getAttribute("data-page");
                if (value) {
                    values.push(value);
                }
            }

            return values;
        }
        """
    )
    base_url = page.url
    candidates: list[JobCandidate] = []
    seen: set[str] = set()

    for snapshot in snapshots:
        parsed = _parse_embedded_json(snapshot)
        if parsed is None:
            continue

        for raw_job in _walk_job_like_objects(parsed):
            candidate = _candidate_from_object(raw_job, base_url)
            if candidate is None:
                continue

            key = f"{candidate.title_text}|{candidate.url}|{candidate.context_text}"
            if key in seen:
                continue

            seen.add(key)
            candidates.append(candidate)

    return candidates


def _parse_embedded_json(value: str):
    cleaned = value.strip()
    if not cleaned:
        return None

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"=\s*({.*})\s*;?\s*$", cleaned, flags=re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _walk_job_like_objects(value) -> Iterable[dict]:
    if isinstance(value, dict):
        if _looks_like_job(value):
            yield value
        for nested in value.values():
            yield from _walk_job_like_objects(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_job_like_objects(item)


def _looks_like_job(value: dict) -> bool:
    keys = {str(key).casefold() for key in value}
    has_title = any(key.casefold() in keys for key in _TITLE_KEYS)
    has_job_hint = any(any(hint in key for hint in _JOB_HINT_KEYS) for key in keys)
    has_url = any(key.casefold() in keys for key in _URL_KEYS)
    return has_title and (has_job_hint or has_url)


def _candidate_from_object(value: dict, base_url: str) -> JobCandidate | None:
    title = _clean_text(_first_string(value, _TITLE_KEYS))
    if not title:
        return None

    url = _extract_url(value, base_url)
    location = _clean_text(_flatten(value.get(key)) for key in _LOCATION_KEYS if key in value)
    posted_at = _clean_text(_first_string(value, _DATE_KEYS))
    context = _clean_text(" ".join(part for part in (title, location, posted_at) if part))
    return JobCandidate(
        title_text=title,
        context_text=context,
        url=url or None,
        location=location or None,
        posted_at=posted_at or None,
        source="embedded",
    )


def _first_string(value: dict, keys: tuple[str, ...]) -> str:
    folded_keys = {str(key).casefold(): key for key in value}
    for key in keys:
        original_key = folded_keys.get(key.casefold())
        if original_key is None:
            continue
        flattened = _flatten(value.get(original_key))
        if flattened:
            return flattened
    return ""


def _extract_url(value: dict, base_url: str) -> str:
    raw_url = _first_string(value, _URL_KEYS)
    if not raw_url:
        raw_url = _first_string(value, ("id", "slug"))
    if not raw_url:
        return ""
    return canonicalize_url(urljoin(base_url, raw_url))


def _flatten(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return " ".join(_flatten(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_flatten(item) for item in value.values())
    return ""


def _clean_text(value) -> str:
    if not isinstance(value, str):
        value = " ".join(str(part) for part in value)
    return " ".join(value.split())
