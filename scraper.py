"""Entrypoint for the daily job discovery scraper."""

from __future__ import annotations

import os
from datetime import date
from typing import Any, Callable

from dotenv import load_dotenv

from filters import apply_filters, classify_listing
from notion_api import NotionJobClient
from sources.remoteok import fetch_jobs as fetch_remoteok_jobs
from sources.remotive import fetch_jobs as fetch_remotive_jobs
from sources.wellfound import fetch_jobs as fetch_wellfound_jobs
from sources.yc_jobs import fetch_jobs as fetch_yc_jobs

# SOURCE 3 CONFIG
# Set to True to use Wellfound (Playwright, may be blocked by Cloudflare)
# Set to False to use Remotive (public JSON API, always reliable)
USE_WELLFOUND = False


def _run_source(
    name: str, fetch_fn: Callable[[], list[dict[str, Any]]]
) -> tuple[list[dict[str, Any]], bool]:
    try:
        jobs = fetch_fn()
    except Exception as exc:  # noqa: BLE001
        print(f"[{name}] ERROR source failed: {exc}")
        return [], False
    print(f"[{name}] fetched {len(jobs)} jobs")
    return jobs, True


def main() -> int:
    inserted_count = 0
    load_dotenv()

    notion_api_key = os.getenv("NOTION_API_KEY")
    notion_database_id = os.getenv("NOTION_DATABASE_ID")
    if not notion_api_key or not notion_database_id:
        print("ERROR: Missing NOTION_API_KEY or NOTION_DATABASE_ID.")
        print(f"SCRAPER COMPLETE: {inserted_count} new listings inserted")
        return 1

    source3_name = "Wellfound" if USE_WELLFOUND else "Remotive"
    print(f"[Config] Source 3 active: {source3_name}")

    notion = NotionJobClient(api_key=notion_api_key, database_id=notion_database_id)
    try:
        notion.validate_schema()
        existing_urls = notion.fetch_existing_job_urls()
        print(f"[Notion] loaded {len(existing_urls)} existing URLs for dedupe")
    except Exception as exc:  # noqa: BLE001
        print(f"[Notion] ERROR dedupe preload failed; aborting run: {exc}")
        print(f"SCRAPER COMPLETE: {inserted_count} new listings inserted")
        return 1

    source_fetchers: list[tuple[str, Callable[[], list[dict[str, Any]]]]] = [
        ("RemoteOK", fetch_remoteok_jobs),
        ("YC Jobs", fetch_yc_jobs),
        (
            "Wellfound" if USE_WELLFOUND else "Remotive",
            fetch_wellfound_jobs if USE_WELLFOUND else fetch_remotive_jobs,
        ),
    ]

    all_jobs: list[dict[str, Any]] = []
    successful_sources = 0
    for source_name, fetch_fn in source_fetchers:
        jobs, ok = _run_source(source_name, fetch_fn)
        if ok:
            successful_sources += 1
        all_jobs.extend(jobs)

    if successful_sources == 0:
        print("[Run] WARNING all three sources failed; exiting without error.")
        print(f"SCRAPER COMPLETE: {inserted_count} new listings inserted")
        return 0

    filtered_jobs: list[dict[str, Any]] = []
    for job in all_jobs:
        passes, filtered = apply_filters(job)
        if not passes:
            continue
        filtered_jobs.append(classify_listing(filtered))

    print(f"[Pipeline] {len(all_jobs)} collected, {len(filtered_jobs)} after filtering")

    today = date.today().isoformat()
    for listing in filtered_jobs:
        url = listing.get("url")
        if not url:
            continue
        if url in existing_urls:
            continue
        inserted = notion.insert_listing(listing, date_found=today)
        if inserted:
            inserted_count += 1
            existing_urls.add(str(url))
        notion.throttle_insert()

    print(f"SCRAPER COMPLETE: {inserted_count} new listings inserted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
