"""
Configuration loading and validation helpers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class ConfigError(ValueError):
    """Raised when a configuration file is missing or invalid."""


@dataclass(frozen=True)
class CompanyConfig:
    """Validated company scraping target."""

    name: str
    url: str
    enabled: bool = True


@dataclass(frozen=True)
class KeywordConfig:
    """Validated keyword configuration."""

    role_keywords: tuple[str, ...]
    internship_keywords: tuple[str, ...]

    def as_dict(self) -> dict[str, list[str]]:
        """Return the keyword lists in the existing scraper shape."""
        return {
            "role_keywords": list(self.role_keywords),
            "internship_keywords": list(self.internship_keywords),
        }


@dataclass(frozen=True)
class AppConfig:
    """Validated application config."""

    companies: tuple[CompanyConfig, ...]
    keywords: KeywordConfig


def load_app_config(
    companies_path: str | Path | None = None,
    keywords_path: str | Path | None = None,
) -> AppConfig:
    """Load and validate the full application configuration."""
    base_dir = Path(__file__).resolve().parent
    company_data = _load_json(companies_path or base_dir / "company_urls.json")
    keyword_data = _load_json(keywords_path or base_dir / "keywords.json")

    companies = _parse_companies(company_data)
    keywords = _parse_keywords(keyword_data)
    return AppConfig(companies=companies, keywords=keywords)


def _load_json(path: str | Path) -> Any:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Configuration file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {config_path}: {exc}") from exc


def _parse_companies(data: Any) -> tuple[CompanyConfig, ...]:
    if not isinstance(data, dict):
        raise ConfigError("Company config must be a JSON object")

    companies = data.get("companies", [])
    if not isinstance(companies, list):
        raise ConfigError("Company config field 'companies' must be a list")

    parsed: list[CompanyConfig] = []
    for index, raw_company in enumerate(companies):
        if not isinstance(raw_company, dict):
            raise ConfigError(f"Company entry #{index + 1} must be an object")

        name = _clean_string(raw_company.get("name"))
        url = _clean_string(raw_company.get("url"))
        enabled = raw_company.get("enabled", True)
        if not name:
            raise ConfigError(f"Company entry #{index + 1} is missing a valid name")
        if not _is_http_url(url):
            raise ConfigError(
                f"Company '{name}' must define a valid http/https url, got: {url!r}"
            )
        if not isinstance(enabled, bool):
            raise ConfigError(f"Company '{name}' field 'enabled' must be a boolean")

        if enabled:
            parsed.append(CompanyConfig(name=name, url=url, enabled=enabled))

    return tuple(parsed)


def _parse_keywords(data: Any) -> KeywordConfig:
    if not isinstance(data, dict):
        raise ConfigError("Keyword config must be a JSON object")

    role_keywords = _parse_keyword_list(data.get("role_keywords"), "role_keywords")
    internship_keywords = _parse_keyword_list(
        data.get("internship_keywords"), "internship_keywords"
    )
    return KeywordConfig(
        role_keywords=role_keywords,
        internship_keywords=internship_keywords,
    )


def _parse_keyword_list(raw_value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(raw_value, list):
        raise ConfigError(f"Keyword config field '{field_name}' must be a list")

    values: list[str] = []
    for index, raw_keyword in enumerate(raw_value):
        keyword = _clean_string(raw_keyword)
        if not keyword:
            raise ConfigError(
                f"Keyword entry #{index + 1} in '{field_name}' must be a non-empty string"
            )
        values.append(keyword)

    return tuple(values)


def _clean_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_http_url(value: str) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
