"""
schema.org JobPosting extraction from rendered pages.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from urllib.parse import urljoin

from playwright.async_api import Page

from scrapers.types import JobCandidate
from utils.urls import canonicalize_url


async def extract_from_page(page: Page) -> list[JobCandidate]:
    payloads = await page.evaluate(
        """
        () => Array.from(document.querySelectorAll("script[type='application/ld+json']"))
            .map(script => script.textContent || "")
            .filter(Boolean)
        """
    )
    base_url = page.url
    candidates: list[JobCandidate] = []
    seen: set[str] = set()

    for payload in payloads:
        for node in _iter_jsonld_nodes(payload):
            if not _is_job_posting(node):
                continue

            title = _clean_text(str(node.get("title") or node.get("name") or ""))
            url = _extract_url(node, base_url)
            location = _extract_location(node)
            posted_at = _clean_text(str(node.get("datePosted") or ""))
            context = _clean_text(" ".join(part for part in (title, location, posted_at) if part))
            key = f"{title}|{url}|{context}"
            if not title or key in seen:
                continue

            seen.add(key)
            candidates.append(
                JobCandidate(
                    title_text=title,
                    context_text=context,
                    url=url or None,
                    location=location or None,
                    posted_at=posted_at or None,
                    source="jsonld",
                )
            )

    return candidates


def _iter_jsonld_nodes(payload: str) -> Iterable[dict]:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return ()

    return _walk_nodes(parsed)


def _walk_nodes(value) -> Iterable[dict]:
    if isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _walk_nodes(item)
        for key in ("itemListElement", "mainEntity", "hasPart"):
            nested = value.get(key)
            if isinstance(nested, (list, dict)):
                yield from _walk_nodes(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_nodes(item)


def _is_job_posting(node: dict) -> bool:
    raw_type = node.get("@type")
    if isinstance(raw_type, str):
        return raw_type.casefold() == "jobposting"
    if isinstance(raw_type, list):
        return any(str(item).casefold() == "jobposting" for item in raw_type)
    return False


def _extract_url(node: dict, base_url: str) -> str:
    raw_url = node.get("url") or node.get("sameAs") or node.get("@id") or ""
    if isinstance(raw_url, dict):
        raw_url = raw_url.get("@id") or raw_url.get("url") or ""
    if isinstance(raw_url, list):
        raw_url = raw_url[0] if raw_url else ""
    if not isinstance(raw_url, str):
        return ""
    return canonicalize_url(urljoin(base_url, raw_url))


def _extract_location(node: dict) -> str:
    raw_location = node.get("jobLocation") or node.get("applicantLocationRequirements")
    return _clean_text(_flatten_location(raw_location))


def _flatten_location(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_flatten_location(item) for item in value)
    if not isinstance(value, dict):
        return ""

    address = value.get("address")
    if address:
        return _flatten_location(address)

    return " ".join(
        str(value.get(key) or "")
        for key in ("addressLocality", "addressRegion", "addressCountry", "name")
    )


def _clean_text(value: str) -> str:
    return " ".join(value.split())
