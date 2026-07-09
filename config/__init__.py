"""
Configuration module for the SWE internship scraper.
"""
from .loader import AppConfig, CompanyConfig, ConfigError, KeywordConfig, load_app_config
from .settings import settings

__all__ = [
    "AppConfig",
    "CompanyConfig",
    "ConfigError",
    "KeywordConfig",
    "load_app_config",
    "settings",
]
