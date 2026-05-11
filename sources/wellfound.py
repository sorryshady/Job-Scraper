"""Wellfound source connector using Playwright-rendered HTML."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

WELLFOUND_URLS = [
    "https://wellfound.com/jobs?role=machine-learning-engineer&remote=true",
    "https://wellfound.com/jobs?role=artificial-intelligence&remote=true",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _is_blocked(content: str) -> bool:
    lowered = content.lower()
    return (
        len(content.strip()) < 1500
        or "captcha" in lowered
        or "attention required" in lowered
        or "cloudflare" in lowered
    )


def _extract_cards(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("a[href*='/jobs/']")
    listings: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for anchor in cards:
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        if "/jobs/" not in href:
            continue
        url = urljoin("https://wellfound.com", href)
        if url in seen_urls:
            continue

        title = anchor.get_text(" ", strip=True)
        if not title:
            title_node = anchor.select_one("h2, h3, [class*='title']")
            title = title_node.get_text(" ", strip=True) if title_node else ""
        if not title:
            continue

        parent = anchor.parent
        company_name = ""
        location = ""
        if parent is not None:
            company_node = parent.select_one("[class*='company'], [data-test*='company']")
            location_node = parent.select_one("[class*='location'], [data-test*='location']")
            if company_node:
                company_name = company_node.get_text(" ", strip=True)
            if location_node:
                location = location_node.get_text(" ", strip=True)
        if not company_name:
            company_name = "Unknown"

        seen_urls.add(url)
        listings.append(
            {
                "source": "Wellfound",
                "source_id": "",
                "company_name": company_name,
                "role_title": title,
                "url": url,
                "posted_at": None,
                "location": location,
                "description_html": "",
                "description_text": "",
                "tags": [],
                "employee_count": None,
                "notes_prefix": "",
            }
        )
    return listings


def fetch_jobs() -> list[dict[str, Any]]:
    """Fetch Wellfound jobs; return empty list on block or failure."""
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            for url in WELLFOUND_URLS:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(4000)
                    html = page.content()
                    if _is_blocked(html):
                        print(f"[Wellfound] WARNING possible Cloudflare block for {url}; skipping source.")
                        browser.close()
                        return []
                    page_listings = _extract_cards(html)
                    for listing in page_listings:
                        if listing["url"] in seen_urls:
                            continue
                        seen_urls.add(listing["url"])
                        results.append(listing)
                except Exception as exc:  # noqa: BLE001
                    print(f"[Wellfound] ERROR while processing {url}: {exc}")
                    continue
            browser.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[Wellfound] ERROR Playwright startup failed: {exc}")
        return []
    return results

