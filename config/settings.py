import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


class Settings:
    """Simple application settings using environment variables"""
    
    # Discord
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
    
    # Supabase
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    TABLE_NAME = "swe_internship_postings"
    
    # Scraper settings
    HEADLESS = _env_bool("HEADLESS", True)
    PAGE_LOAD_TIMEOUT = _env_int("PAGE_LOAD_TIMEOUT", 45000)
    CONTENT_SELECTOR_TIMEOUT = _env_int("CONTENT_SELECTOR_TIMEOUT", 12000)
    MIN_DELAY_SECONDS = _env_float("MIN_DELAY_SECONDS", 3.0)
    MAX_DELAY_SECONDS = _env_float("MAX_DELAY_SECONDS", 6.0)
    MAX_CONCURRENT_SCRAPERS = _env_int("MAX_CONCURRENT_SCRAPERS", 2)
    SCRAPE_RETRY_ATTEMPTS = _env_int("SCRAPE_RETRY_ATTEMPTS", 2)
    SCRAPE_RETRY_BASE_DELAY_SECONDS = _env_float("SCRAPE_RETRY_BASE_DELAY_SECONDS", 2.0)
    SCRAPE_RETRY_MAX_DELAY_SECONDS = _env_float("SCRAPE_RETRY_MAX_DELAY_SECONDS", 10.0)
    USER_DATA_DIR = os.getenv("USER_DATA_DIR", "logs/browser-state")
    PROXY_URL = os.getenv("PROXY_URL")
    ARTIFACT_DIR = os.getenv("ARTIFACT_DIR", "logs/artifacts")
    MAX_SCROLL_ITERATIONS = _env_int("MAX_SCROLL_ITERATIONS", 8)
    MAX_LOAD_MORE_CLICKS = _env_int("MAX_LOAD_MORE_CLICKS", 5)
    BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "chrome")
    USER_AGENTS = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]
    
    # Notifications
    NOTIFICATION_DELAY_SECONDS = 1.0
    
    # Logging
    LOG_LEVEL = "INFO"
    LOG_FILE_PATH = "logs/scraper.log"
    LOG_ROTATION = "10 MB"
    LOG_RETENTION = "7 days"
    
    # GitHub Actions detection
    IS_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS", "").lower() == "true"
    
    # Companies that should use their main careers page URL when no specific job link is found
    COMPANIES_USE_MAIN_URL = [
        "Netflix",
    ]
    
    # Companies with aggressive anti-bot protection - these may fail frequently
    # They use Cloudflare Turnstile or similar that blocks automated browsers
    KNOWN_DIFFICULT_SITES = [
        "X",
        "xAI", 
        "HubSpot",
    ]


# Global settings instance
settings = Settings()
