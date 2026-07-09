# SWE Internship Scraper

An automated job scraper that monitors software engineering internship opportunities across multiple company career pages. It now uses a layered raw-scraping flow: load the page with a browser fingerprint that looks like a returning user, extract structured data from the rendered page first, fall back to DOM heuristics when needed, then filter by keywords, store new results in Supabase, and send Discord notifications for new opportunities.

https://discord.gg/CcDDP5Mk9K

## Contributing

Help expand the scraper's reach by adding more companies and improving keyword matching.

### How to Contribute

1. Fork the repository (if you're not already a contributor)
2. Add companies to `config/company_urls.json`
3. Improve keywords in `config/keywords.json` (optional)
4. Create a Pull Request with your changes

## Configuration

### Adding Companies

When adding companies, look for career pages that are already filtered for internships rather than general job boards. These work much better because:

- **Internship-specific portals** (like `company.com/internships`) already show relevant roles
- **Pre-filtered pages** reduce noise and improve job detection accuracy
- **Direct job listings** work better than landing pages that require navigation

Edit `config/company_urls.json` to add more companies to monitor:
```json
{
  "companies": [
    {
      "name": "Company Name",
      "url": "https://company.com/careers",
      "enabled": true
    },
    {
      "name": "Another Company",
      "url": "https://another.com/jobs"
    }
  ]
}
```

**Important URL Requirements:**
- **Public and accessible** - No login/authentication required
- **Pre-filtered for internships** - URL should already show internship positions
- **Direct job listings** - Should display actual job postings, not just a landing page
- **Stable and reliable** - Company's official careers page that loads consistently
- **Optional disable flag** - Set `"enabled": false` to temporarily skip a company without deleting it

**Good URL Examples:**
- `https://www.metacareers.com/jobs?roles[0]=Internship&q=software`
- `https://jobs.apple.com/en-us/search?sort=relevance&location=united-states-USA&key=internship+software+intern`

**Avoid:**
- URLs requiring login or authentication
- Generic landing pages without job listings
- URLs that redirect to external job boards
- Pages that load job content dynamically without proper fallbacks

### Customizing Keywords

Edit `config/keywords.json` to fine-tune job filtering:
```json
{
  "role_keywords": [
    "software",
    "sde", 
    "swe",
    "fullstack",
    "backend",
    "frontend",
    "developer"
  ],
  "internship_keywords": [
    "intern",
    "internship", 
    "co-op",
    "student",
    "university",
    "college"
  ]
}
```

**How it works:** a single posting candidate must match at least one keyword from **both** groups to be included. Matching is title-first, with same-card job metadata used as a fallback when boards split role and internship labels across fields.

### Site Profiles

`config/site_profiles.json` is optional and lets you override a few company-specific scraping behaviors without changing code. If no entry exists for a company, the scraper uses defaults.

Example:
```json
{
  "Intuit": {
    "content_selector": "[data-job-id], .job-card",
    "wait": "selector",
    "pagination": {
      "type": "load_more",
      "selector": "button.load-more",
      "max_clicks": 10
    },
    "block_on_headless": true
  }
}
```

## Local Setup

### 1. Environment Variables
Create a `.env` file with:
```env
# Discord
DISCORD_WEBHOOK_URL=your_discord_webhook_url

# Supabase
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_service_role_key

# Scraper tuning
HEADLESS=true
PAGE_LOAD_TIMEOUT=45000
CONTENT_SELECTOR_TIMEOUT=12000
MIN_DELAY_SECONDS=3.0
MAX_DELAY_SECONDS=6.0
MAX_CONCURRENT_SCRAPERS=2
SCRAPE_RETRY_ATTEMPTS=2
SCRAPE_RETRY_BASE_DELAY_SECONDS=2.0
SCRAPE_RETRY_MAX_DELAY_SECONDS=10.0
USER_DATA_DIR=logs/browser-state
ARTIFACT_DIR=logs/artifacts
MAX_SCROLL_ITERATIONS=8
MAX_LOAD_MORE_CLICKS=5
PROXY_URL=
BROWSER_CHANNEL=chrome
```

### 2. Supabase Database Table
Create or update the required table by running `database/schema.sql` in the Supabase SQL editor. The file is idempotent, so it is safe to run again if the table, indexes, or RLS policies already exist.

The scraper must use a Supabase **service role** key for `SUPABASE_KEY`. An `anon` or `authenticated` JWT will hit RLS errors on insert. The schema enables RLS and grants the `service_role` role access to select existing hashes, insert new jobs, and delete old rows during cleanup.

### 3. Install Dependencies
```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/playwright install chromium
```

### 4. Verify Setup
Run the setup verification script to ensure everything is configured correctly:
```bash
./venv/bin/python test_setup.py
```

This will check:
- Python version compatibility
- Required dependencies are installed
- Environment variables are set
- Configuration files are present and valid
- Project structure is correct
- Optional site profile file is readable

### 5. Run Locally

**Run for all companies:**
```bash
./venv/bin/python main.py
```

**Run for a specific company (in company_urls.json):**
```bash
./venv/bin/python main.py --company intuit
./venv/bin/python main.py --company "1Password"
./venv/bin/python main.py --company solana
```

**Run without Discord notifications: **
```bash
./venv/bin/python main.py --no-discord
./venv/bin/python main.py --company intuit --no-discord
```

The scraper now logs a per-company summary with status, count, strategy, duration, and any saved artifact paths. Non-OK runs save screenshots and HTML under `logs/artifacts/`.

## GitHub Actions

The workflow in this repo currently supports **manual** triggering via GitHub Actions `workflow_dispatch`. It runs under `xvfb-run` so the browser can fall back to a headful session in CI. If you want scheduled runs, add a `schedule` trigger to `.github/workflows/scrape-jobs.yml`.
