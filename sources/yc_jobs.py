"""YC Jobs source connector with JSON-first and HTML fallback behavior."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

FEED_URL = "https://www.workatastartup.com/jobs/feed"
JOBS_URL = "https://www.workatastartup.com/jobs"
QUERIES = ["machine learning", "ai engineer", "inference engineer"]

HEADERS = {
    "Accept": "*/*",
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Referer": JOBS_URL,
}

HTML_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)",
    "Referer": JOBS_URL,
}


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _safe_int_from_range(value: str | None) -> int | None:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if "-" in cleaned:
        left = cleaned.split("-", maxsplit=1)[0].strip()
        return int(left) if left.isdigit() else None
    return int(cleaned) if cleaned.isdigit() else None


def _normalize_json_job(job: dict[str, Any]) -> dict[str, Any] | None:
    url = (job.get("job_url") or "").strip()
    title = (job.get("title") or "").strip()
    company_name = (job.get("company_name") or "").strip()
    if not url or not title or not company_name:
        return None

    company_obj = job.get("company") or {}
    if not isinstance(company_obj, dict):
        company_obj = {}

    description_html = job.get("description") or ""
    locations = job.get("locations") or []
    location = ", ".join(x for x in locations if isinstance(x, str) and x.strip())
    if not location and job.get("remote"):
        location = "Remote"

    return {
        "source": "YC Jobs",
        "source_id": str(job.get("id") or ""),
        "company_name": company_name,
        "role_title": title,
        "url": url,
        "posted_at": job.get("created_at"),
        "location": location,
        "description_html": description_html,
        "description_text": _strip_html(description_html),
        "tags": [],
        "employee_count": _safe_int_from_range(company_obj.get("num_employees")),
        "notes_prefix": "",
    }


def _fallback_scrape(timeout_seconds: int) -> list[dict[str, Any]]:
    print("[YC Jobs] WARNING JSON feed failed; falling back to HTML scraping.")
    response = requests.get(JOBS_URL, headers=HTML_HEADERS, timeout=timeout_seconds)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    data_page_node = soup.select_one("[data-page]")
    if data_page_node:
        raw_payload = data_page_node.get("data-page")
        if raw_payload:
            try:
                payload = json.loads(raw_payload)
                jobs = payload.get("props", {}).get("jobs", [])
                if isinstance(jobs, list):
                    parsed: list[dict[str, Any]] = []
                    for job in jobs:
                        if not isinstance(job, dict):
                            continue
                        job_id = str(job.get("id") or "").strip()
                        title = str(job.get("title") or "").strip()
                        company_name = str(job.get("companyName") or "").strip()
                        company_slug = str(job.get("companySlug") or "").strip()
                        if not job_id or not title or not company_name:
                            continue
                        url = f"https://www.workatastartup.com/companies/{company_slug}/jobs/{job_id}"
                        parsed.append(
                            {
                                "source": "YC Jobs",
                                "source_id": job_id,
                                "company_name": company_name,
                                "role_title": title,
                                "url": url,
                                "posted_at": None,
                                "location": str(job.get("location") or ""),
                                "description_html": "",
                                "description_text": "",
                                "tags": [],
                                "employee_count": None,
                                "notes_prefix": "",
                            }
                        )
                    if parsed:
                        return parsed
            except Exception:  # noqa: BLE001
                pass

    listings: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for anchor in soup.select("a[href*='/jobs/']"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        url = urljoin(JOBS_URL, href)
        if url in seen_urls:
            continue
        title = anchor.get_text(" ", strip=True)
        if not title:
            continue
        seen_urls.add(url)
        listings.append(
            {
                "source": "YC Jobs",
                "source_id": "",
                "company_name": "Unknown",
                "role_title": title,
                "url": url,
                "posted_at": None,
                "location": "",
                "description_html": "",
                "description_text": "",
                "tags": [],
                "employee_count": None,
                "notes_prefix": "",
            }
        )
    return listings


def fetch_jobs(timeout_seconds: int = 25) -> list[dict[str, Any]]:
    """Fetch and normalize YC Jobs listings from JSON feed or fallback HTML."""
    seen_urls: set[str] = set()
    listings: list[dict[str, Any]] = []

    for query in QUERIES:
        params = {
            "query": query,
            "role": "eng",
            "commitment": "fulltime",
            "remote": "true",
            "order_by": "created_at",
        }
        try:
            response = requests.get(FEED_URL, params=params, headers=HEADERS, timeout=timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            jobs = payload.get("jobs") if isinstance(payload, dict) else None
            if not isinstance(jobs, list):
                raise ValueError("missing jobs list in JSON payload")
        except Exception as exc:  # noqa: BLE001
            print(f"[YC Jobs] WARNING query='{query}' feed unavailable: {exc}")
            try:
                fallback = _fallback_scrape(timeout_seconds=timeout_seconds)
            except Exception as fallback_exc:  # noqa: BLE001
                print(f"[YC Jobs] ERROR HTML fallback failed: {fallback_exc}")
                continue
            for item in fallback:
                if item["url"] in seen_urls:
                    continue
                seen_urls.add(item["url"])
                listings.append(item)
            continue

        for raw in jobs:
            if not isinstance(raw, dict):
                continue
            normalized = _normalize_json_job(raw)
            if not normalized:
                continue
            if normalized["url"] in seen_urls:
                continue
            seen_urls.add(normalized["url"])
            listings.append(normalized)

    return listings

