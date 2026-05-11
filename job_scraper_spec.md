# Job Scraper — Production Spec

**Purpose:** Daily automated job discovery for ML/AI roles at startups.
Runs on GitHub Actions at 8am EST on weekdays. Scrapes 3 sources, filters
listings, deduplicates against existing Notion entries, and pushes new rows
to the Notion job discovery database.

Claude is not involved in this pipeline. It is pure API calls and Notion writes.
The Claude generation routine (separate system) reads the Notion database later.

The scraper runs 3 active sources at a time. Source 3 is either Wellfound or
Remotive depending on a config flag. Build both. Test Wellfound first. If it
fails consistently, flip the flag to Remotive. No rebuild needed.

---

## Important Notes Before Building

**Wellfound is the riskiest part.** Their frontend changes frequently and the
Playwright output will need manual verification before trusting it in production.
Build and test sources independently, Wellfound last.

**If Wellfound is consistently blocked, swap to Remotive — do not just drop Source 3.**
Remotive is a public JSON API (same story as RemoteOK), remote-job focused, and
has solid startup coverage. Both sources are built. The active one is controlled
by a single config flag in `scraper.py` (see Source 3 section below).

**RemoteOK is the most reliable source by far.** It is a clean public JSON API
with zero scraping involved. If time is short, shipping RemoteOK + YC Jobs alone
is sufficient until July when applications begin.

**Verify Notion property names before writing any insert code.** Property names
are case-sensitive. Call `GET /v1/databases/{id}` first and confirm the live
schema matches the table in this spec. Silent mismatches are the most common
failure mode.

**Do not use Firecrawl for this scraper.** Firecrawl credits are reserved for
the ERNYG Client Research Routine (separate system). Use Playwright for
JavaScript-rendered sources instead.

**The `workflow_dispatch` key in the GitHub Actions config** allows manual
triggering from the GitHub UI without waiting for the cron. Use this to test
in development instead of waiting until 8am.

**This scraper does not activate until July 2026.** Build and test it in Ann
Arbor. Push to GitHub, confirm the cron fires, then leave it running passively.
Do not triage listings until July when applications begin.

---

## Project Structure

```
job-scraper/
├── .github/
│   └── workflows/
│       └── scraper.yml
├── sources/
│   ├── __init__.py
│   ├── remoteok.py       # Source 1 — always active
│   ├── yc_jobs.py        # Source 2 — always active
│   ├── wellfound.py      # Source 3a — Playwright-based, active if USE_WELLFOUND=True
│   └── remotive.py       # Source 3b — API-based fallback, active if USE_WELLFOUND=False
├── scraper.py            # entrypoint — contains USE_WELLFOUND config flag
├── notion_client.py      # Notion API wrapper
├── filters.py            # filtering and classification logic
├── requirements.txt
├── .env.example
└── README.md
```

---

## Environment Variables

```
NOTION_API_KEY=secret_...
NOTION_DATABASE_ID=429cda96a2654a6a88eae18fedc3fc98
```

The Notion database ID above is the Job Discovery Database.
Do not hardcode secrets anywhere. Use `.env` locally, GitHub Actions secrets in CI.

---

## Notion Database Schema

**Database ID:** `429cda96a2654a6a88eae18fedc3fc98`

The database has these properties. Property names must match exactly (case-sensitive):

| Property Name     | Notion Type | Notes                                                      |
|-------------------|-------------|-------------------------------------------------------------|
| Company Name      | Title       | The company name (this is the page title in Notion)        |
| Role Title        | Rich Text   |                                                             |
| Link to JD        | URL         | Used for deduplication — check this before inserting       |
| Date Found        | Date        | ISO 8601 date string, e.g. "2026-05-11"                   |
| Source            | Select      | Wellfound / YC Jobs / RemoteOK / LinkedIn / Manual         |
| Role Type         | Select      | Startup-MLE / Startup-DS / Research / Growth-Stage-MLE / Other |
| F1 Friendly       | Select      | Yes / No / Unknown                                          |
| Location          | Rich Text   | "Remote" or city name                                      |
| Status            | Select      | Always set to "New" on creation                            |
| Priority          | Select      | Always set to "Medium" on creation (Akhil triages manually)|
| Company Stage     | Select      | Seed / Series A / Series B / Series C+ / Unknown           |
| Tech Stack Match  | Select      | Strong / Partial / Weak (see classification logic below)   |
| Notes             | Rich Text   | Leave blank on creation                                    |

**IMPORTANT:** Before writing any Notion insert code, call `GET /v1/databases/{database_id}`
to retrieve the live schema and confirm property names match exactly. Notion is
case-sensitive. If there is any mismatch, the insert will fail silently or error.

---

## Sources

### Source 1: RemoteOK

RemoteOK has a public, documented JSON API. No auth, no scraping, no browser needed.

**Endpoint:**
```
GET https://remoteok.com/api?tag=machine-learning
GET https://remoteok.com/api?tag=deep-learning
GET https://remoteok.com/api?tag=ai
```

Run all three. Deduplicate by job URL before combining.

**Response format:** JSON array. First element is a metadata object (skip it).
Remaining elements are job objects with fields:
- `id` — unique job ID
- `company` — company name
- `position` — job title
- `url` — direct link to the listing
- `date` — ISO 8601 timestamp
- `location` — location string
- `tags` — array of tag strings (use for tech stack matching)
- `description` — HTML job description (strip tags for text)

**Rate limiting:** Add a 2-second delay between endpoint calls.
Set a descriptive `User-Agent` header (not empty).

---

### Source 2: YC Jobs (workatastartup.com)

YC Jobs has a JSON API backing their search UI. Hit it directly with `requests`
— no browser needed, just mimic the browser request headers.

**Endpoint:**
```
GET https://www.workatastartup.com/jobs/feed?
  query=machine+learning
  &role=eng
  &commitment=fulltime
  &remote=true
  &order_by=created_at
```

Also run with `query=ai+engineer` and `query=inference+engineer`.

**Headers to include:**
```
Accept: application/json
User-Agent: Mozilla/5.0 (compatible; research-bot/1.0)
Referer: https://www.workatastartup.com/jobs
```

**Response format:** JSON object with a `jobs` array. Each job has:
- `id`
- `title` — job title
- `company_name`
- `job_url` — direct link
- `created_at` — timestamp
- `remote` — boolean
- `locations` — array of location strings
- `description` — HTML
- `company` — nested object, may include `num_employees` (string range like "1-10")

**Fallback:** If this endpoint returns non-JSON (the internal URL may change),
fall back to scraping `https://www.workatastartup.com/jobs` with BeautifulSoup.
Log a warning when the fallback fires so it is visible in the GitHub Actions log.

---

### Source 3a: Wellfound (active when USE_WELLFOUND = True)

Wellfound is a React app behind Cloudflare. Plain `requests` will not work.
Use Playwright (headless Chromium) to render the page.

**Do not use Firecrawl here.** Firecrawl credits are reserved for the ERNYG
routine. Playwright is free and runs in GitHub Actions.

**Python setup:**
```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"
    )
    page.goto("https://wellfound.com/jobs?role=machine-learning-engineer&remote=true")
    page.wait_for_timeout(4000)  # wait for JS to render
    content = page.content()
    browser.close()
```

Run for these URLs:
- `https://wellfound.com/jobs?role=machine-learning-engineer&remote=true`
- `https://wellfound.com/jobs?role=artificial-intelligence&remote=true`

Parse the rendered HTML with BeautifulSoup. Job listing cards on Wellfound
follow a repeating structure — find the card container, extract company name,
role title, location, and the link to the job page from each card.

The link pattern is: `https://wellfound.com/jobs/{id}` or
`https://wellfound.com/company/{slug}/jobs/{id}`.

**If Cloudflare blocks the request** (HTTP 403, CAPTCHA page, or near-empty
content after waiting): log a warning, return an empty list, and continue.
The other two sources run normally.

**If Wellfound blocking is consistent across multiple test runs:** flip
`USE_WELLFOUND = False` in `scraper.py`. Remotive activates automatically.
Do not delete the Wellfound source file — keep it in case it becomes viable later.

---

### Source 3b: Remotive (active when USE_WELLFOUND = False)

Remotive has a public, documented JSON API. No auth, no scraping, no browser.
Same story as RemoteOK.

**Endpoint:**
```
GET https://remotive.com/api/remote-jobs?category=machine-learning
GET https://remotive.com/api/remote-jobs?category=software-dev&limit=100
```

Run both. Deduplicate by job URL before combining.

**Response format:** JSON object with a `jobs` array. Each job has:
- `id`
- `company_name`
- `title` — job title
- `url` — direct link to the listing (canonical, stable)
- `publication_date` — ISO 8601 timestamp
- `candidate_required_location` — location string (usually "Worldwide" or "USA")
- `description` — HTML job description (strip tags for text)
- `tags` — array of tag strings
- `company_logo_url` — ignore
- `salary` — string, may be empty

Note: Remotive leans toward fully remote global roles. The location filter in
Filter 5 still applies — flag anything clearly onsite but do not drop it.

**Rate limiting:** Add a 1-second delay between the two endpoint calls.

---

## Filtering Logic

Implement in `filters.py`. Apply these in order. A listing that fails any
filter is dropped and not inserted into Notion.

### Filter 1: Title keyword match

Keep the listing only if the job title contains at least one of:
```python
TITLE_KEYWORDS = [
    "machine learning",
    "ml engineer",
    "ai engineer",
    "applied ml",
    "applied machine learning",
    "inference engineer",
    "mlops",
    "research engineer",
    "computer vision engineer",
    "nlp engineer",
    "deep learning",
]
```
Match case-insensitively against the full title string.

### Filter 2: Exclude senior/lead titles

Drop the listing if the title contains any of:
```python
EXCLUDE_TITLE_TERMS = [
    "senior", "sr.", "staff", "lead", "principal",
    "head of", "director", "vp ", "vice president",
    "manager", "architect",
]
```
Match case-insensitively.

Also drop if the description contains any of:
`"5+ years"`, `"6+ years"`, `"7+ years"`, `"8+ years"`, `"10+ years"`
Do not drop for "3+ years" — within range for a new grad with strong projects.

### Filter 3: Company size (where available)

If `num_employees` or similar is available, keep only if size is under 200.
If the field is absent or unparseable, keep the listing (do not drop on missing data).

### Filter 4: Posted within 48 hours

Drop listings posted more than 48 hours ago. Use 48 hours instead of 24 to
account for scraper delays and timezone drift.
If `date` or `created_at` is absent, keep the listing.

### Filter 5: Remote (soft filter — do not drop)

If location clearly indicates onsite-only (no "remote" in location or description,
specific non-remote city listed): keep the listing but set the Location field to
the city name and prepend "ONSITE — " to the Notes field.
Do not drop — Akhil may still want to review these.

---

## Classification Logic

For each listing that passes filters, classify these fields before inserting.

### F1 Friendly

Scan the full job description (lowercased) for these signals:

```python
F1_NO_SIGNALS = [
    "no sponsorship",
    "sponsorship not available",
    "sponsorship is not available",
    "unable to sponsor",
    "cannot sponsor",
    "does not sponsor",
    "authorized to work without sponsorship",
    "must be authorized to work in the u.s.",
    "us citizen",
    "u.s. citizen",
    "security clearance",
    "secret clearance",
]

F1_YES_SIGNALS = [
    "visa sponsorship",
    "will sponsor",
    "sponsorship available",
    "opt eligible",
    "cpt eligible",
    "f-1",
    "f1 visa",
]
```

- If any F1_NO_SIGNALS match: set "No"
- Else if any F1_YES_SIGNALS match: set "Yes"
- Otherwise: set "Unknown"

This is heuristic, not authoritative. Akhil still reviews before applying.
The goal is to surface obvious No listings so he can skip them immediately,
and flag Yes listings so he prioritizes them. Unknown is the default.

### Role Type

```python
def classify_role_type(title: str) -> str:
    title = title.lower()
    if any(x in title for x in ["research", "scientist"]):
        return "Research"
    if any(x in title for x in ["ml engineer", "machine learning engineer",
                                  "mlops", "inference"]):
        return "Startup-MLE"
    if any(x in title for x in ["data scientist", "applied scientist"]):
        return "Startup-DS"
    return "Other"
```

### Tech Stack Match

Check if the job description (lowercased) contains any of:
```python
STRONG_MATCH = ["pytorch", "python", "core ml", "tflite", "onnx",
                "transformers", "hugging face", "computer vision", "nlp"]
PARTIAL_MATCH = ["tensorflow", "sklearn", "scikit-learn", "pandas",
                 "sql", "spark", "aws", "gcp"]
```
If 2+ STRONG_MATCH terms: "Strong"
If 1 STRONG_MATCH or 2+ PARTIAL_MATCH: "Partial"
Otherwise: "Weak"

### Company Stage

Map from employee count if available:
- 1-10: Seed
- 11-50: Seed
- 51-150: Series A
- 151-200: Series B
If employee count unavailable: "Unknown"

---

## Deduplication

Before inserting any listing, check if a row with the same `Link to JD` already
exists in the Notion database.

**Approach:**
1. At script start, fetch all existing `Link to JD` values from the database.
   Use `POST /v1/databases/{id}/query` with a filter on Link to JD not empty.
   Paginate through all results (Notion returns max 100 per page, use `start_cursor`).
   Build a Python set of existing URLs.

2. For each new listing, check if its URL is in the set.
   If yes: skip.
   If no: insert and add the URL to the set (handles within-run deduplication too).

**Do not rely on job IDs for deduplication.** URLs are more stable across sources.

---

## Notion Insert

Use the `notion-client` Python SDK (official). Do not roll a raw requests wrapper.

```
POST https://api.notion.com/v1/pages
```

Set all fields per the schema table above.
Status must always be "New". Priority must always be "Medium". Notes empty string.

**Rate limiting:** Notion allows 3 requests/second. Add a 0.4-second delay
between inserts to stay safely under the limit.

**Error handling:** If an insert fails (non-2xx response), log the error with
the job title and URL. Do not crash. Continue with remaining listings.

---

## Script Entrypoint (`scraper.py`)

The config flag lives at the top of this file:

```python
# SOURCE 3 CONFIG
# Set to True to use Wellfound (Playwright, may be blocked by Cloudflare)
# Set to False to use Remotive (public JSON API, always reliable)
USE_WELLFOUND = True
```

Flip this flag and redeploy if Wellfound testing fails. No other changes needed.

```
1. Load env vars (python-dotenv locally, Actions secrets in CI)
2. Log which Source 3 is active (Wellfound or Remotive)
3. Fetch all existing Notion URLs for deduplication (abort if this fails)
4. Run Source 1 (RemoteOK), Source 2 (YC Jobs), Source 3 (Wellfound or Remotive)
   independently — failure in one source does not stop the others
5. Apply filters to all collected listings
6. Classify each passing listing (role type, F1 friendly, tech stack, stage)
7. Deduplicate against existing Notion URLs
8. Insert new listings to Notion with rate limiting
9. Log final summary line: "SCRAPER COMPLETE: {n} new listings inserted"
```

Log everything to stdout. GitHub Actions captures this in the run log.

---

## GitHub Actions Workflow (`.github/workflows/scraper.yml`)

```yaml
name: Job Scraper

on:
  schedule:
    - cron: '0 12 * * 1-5'   # 8am EST (12pm UTC), weekdays only
  workflow_dispatch:           # manual trigger from GitHub UI for testing

jobs:
  scrape:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Install Playwright browser
        run: playwright install chromium --with-deps

      - name: Run scraper
        env:
          NOTION_API_KEY: ${{ secrets.NOTION_API_KEY }}
          NOTION_DATABASE_ID: ${{ secrets.NOTION_DATABASE_ID }}
        run: python scraper.py
```

Weekdays only. Playwright browser install adds roughly 1-2 minutes to the
action run time, which is acceptable. GitHub Actions free tier gives 2,000
minutes/month on private repos — this script runs in under 5 minutes per day,
so monthly usage is well within the free limit.

---

## Requirements

```
requests==2.32.3
python-dotenv==1.0.1
notion-client==2.2.1
beautifulsoup4==4.12.3
playwright==1.44.0
```

No Firecrawl dependency. Playwright handles JS-rendered pages.
Remotive requires only `requests` — no additional dependency needed.

---

## `.env.example`

```
NOTION_API_KEY=secret_your_key_here
NOTION_DATABASE_ID=429cda96a2654a6a88eae18fedc3fc98
```

---

## Error Handling Rules

- If a single source fails entirely: log error, skip that source, continue
- If Notion deduplication fetch fails: abort the run entirely (safer than inserting duplicates)
- If an individual Notion insert fails: log and continue
- If all three sources fail: exit 0 (do not fail the Actions run — failed runs
  send GitHub notifications, which would become noise)
- Final log line must always be: `SCRAPER COMPLETE: {n} new listings inserted`

---

## Testing Checklist

Before pushing to GitHub, test locally:

1. Copy `.env.example` to `.env` and fill in real keys
2. Run `python scraper.py`
3. Check Notion database — confirm new rows appeared with Status "New"
4. Run again immediately — confirm no duplicate rows were inserted
5. Verify F1 Friendly classification on a listing that has "no sponsorship" in its description
6. Check the final log line for the summary

**Test Source 3 options:**

Test Wellfound first:
```
python -c "from sources.wellfound import fetch_jobs; jobs = fetch_jobs(); print(len(jobs), jobs[:1])"
```
If it returns 0 jobs or raises an error, check the HTML content for a Cloudflare
challenge page. If blocked consistently across 2-3 runs on different days, flip
`USE_WELLFOUND = False` in `scraper.py` and test Remotive instead:
```
python -c "from sources.remotive import fetch_jobs; jobs = fetch_jobs(); print(len(jobs), jobs[:1])"
```
Remotive should always return results. If it does not, the API may have changed —
check https://remotive.com/api/remote-jobs for the current response format.

---

## GitHub Secrets to Add

Go to repo Settings > Secrets and variables > Actions > New repository secret.
Add:
- `NOTION_API_KEY`
- `NOTION_DATABASE_ID`

---

## Known Constraints and Gotchas

- **Notion property names are case-sensitive.** Fetch the live schema first.
  Silent empty inserts are almost always a casing mismatch.

- **Wellfound changes their frontend frequently.** The Playwright + BeautifulSoup
  parsing logic will need updates if the card structure changes. Keep the
  Wellfound source isolated in `sources/wellfound.py` so updates don't touch
  the rest of the script.

- **Wellfound may be consistently blocked by Cloudflare.** If this happens, flip
  `USE_WELLFOUND = False` in `scraper.py`. Remotive activates as Source 3 with
  no other changes. Keep the Wellfound file in case it becomes viable later.

- **YC Jobs internal endpoint may change.** If the JSON feed URL stops returning
  JSON, fall back to BeautifulSoup on the HTML page. The HTML structure is more
  stable than the internal XHR endpoint.

- **F1 Friendly classification is heuristic.** It will miss edge cases. Its value
  is flagging obvious No listings quickly, not replacing manual review. Always
  check before applying.

- **Company Stage inference from employee count is approximate.** Many Series B
  companies have 50 employees. Use it as a rough signal only.
