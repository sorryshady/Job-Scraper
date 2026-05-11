# Job Scraper

Daily automated job discovery pipeline for startup ML/AI roles, writing new listings into Notion.

## What It Does

- Runs 3 sources per execution:
  - RemoteOK (always on)
  - YC Jobs (always on)
  - Source 3 toggle in `scraper.py`: Wellfound (`USE_WELLFOUND = True`) or Remotive (`False`)
- Filters and classifies listings before insert.
- Deduplicates against existing Notion rows using `Link to JD`.
- Inserts only net-new jobs into Notion.

## Setup

1. Create and activate a Python 3.11 virtualenv.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Copy env file:
   - `cp .env.example .env`
4. Fill `.env` values:
   - `NOTION_API_KEY`
   - `NOTION_DATABASE_ID`

## Run Locally

- Run scraper:
  - `python scraper.py`

Expected final log line:

- `SCRAPER COMPLETE: {n} new listings inserted`

## Source 3 Toggle

At the top of `scraper.py`:

- `USE_WELLFOUND = True` -> uses Wellfound via Playwright
- `USE_WELLFOUND = False` -> uses Remotive JSON API fallback source

If Wellfound is blocked consistently, set `USE_WELLFOUND = False`.

## GitHub Actions

Workflow file: `.github/workflows/scraper.yml`

- Weekday cron at `0 12 * * 1-5` (8am EST / 12pm UTC)
- Includes `workflow_dispatch` for manual test runs
- Installs Playwright Chromium before executing the scraper

