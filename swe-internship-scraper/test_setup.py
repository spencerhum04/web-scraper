#!/usr/bin/env python3
"""
Quick setup verification script.
"""
from __future__ import annotations

import importlib.util
import base64
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def check_setup():
    """Verify the local setup is correct."""
    print("Checking SWE Internship Scraper setup...\n")

    issues: list[str] = []

    if sys.version_info < (3, 9):
        issues.append(
            f"Python {sys.version_info.major}.{sys.version_info.minor} detected. Need Python 3.9+"
        )
    else:
        print(f"OK  Python {sys.version_info.major}.{sys.version_info.minor}")

    if hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    ):
        print("OK  Virtual environment active")
    else:
        print("WARN Virtual environment not detected (recommended)")

    env_path = Path(".env")
    if env_path.exists():
        print("OK  .env file found")
        for variable_name in ("DISCORD_WEBHOOK_URL", "SUPABASE_URL", "SUPABASE_KEY"):
            if os.getenv(variable_name):
                print(f"OK  {variable_name} set")
            else:
                issues.append(f"{variable_name} missing from .env")

        supabase_key = os.getenv("SUPABASE_KEY")
        if supabase_key:
            key_role = _extract_supabase_key_role(supabase_key)
            if key_role and key_role != "service_role":
                issues.append(
                    f"SUPABASE_KEY is a {key_role} JWT; use a service_role key for inserts"
                )
    else:
        issues.append(".env file not found")

    for package_name in ("playwright", "pydantic", "httpx", "supabase"):
        if importlib.util.find_spec(package_name) is not None:
            print(f"OK  {package_name} installed")
        else:
            issues.append(f"{package_name} is not installed")

    required_files = [
        "main.py",
        "config/settings.py",
        "config/loader.py",
        "config/company_urls.json",
        "config/keywords.json",
        "models/job_posting.py",
        "scrapers/scraper.py",
        "scrapers/matching.py",
        "services/discord_service.py",
        "services/supabase_service.py",
    ]
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"OK  {file_path} found")
        else:
            issues.append(f"{file_path} is missing")

    _check_json_config("config/company_urls.json", issues)
    _check_json_config("config/keywords.json", issues)

    print("\n" + "=" * 50)
    if issues:
        print("Issues found:")
        for issue in issues:
            print(f" - {issue}")
        print("\nFix these issues before running the scraper.")
    else:
        print("Setup looks good. Suggested verification:")
        print("  ./venv/bin/python test_setup.py")
        print("  ./venv/bin/ruff check .")
        print("  ./venv/bin/pytest -q")
    print("=" * 50)


def _check_json_config(path_str: str, issues: list[str]):
    config_path = Path(path_str)
    if not config_path.exists():
        return

    try:
        import json

        with config_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        issues.append(f"Error reading {path_str}: {exc}")
        return

    if path_str.endswith("company_urls.json"):
        company_count = len(data.get("companies", []))
        print(f"OK  Company URLs configured: {company_count}")
    elif path_str.endswith("keywords.json"):
        role_count = len(data.get("role_keywords", []))
        internship_count = len(data.get("internship_keywords", []))
        print(f"OK  Keywords configured: {role_count} role, {internship_count} internship")


def _extract_supabase_key_role(supabase_key: str):
    parts = supabase_key.split(".")
    if len(parts) != 3:
        return None

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding).decode("utf-8")
        claims = json.loads(decoded)
    except Exception:
        return None

    role = claims.get("role")
    return role if isinstance(role, str) else None


if __name__ == "__main__":
    check_setup()
