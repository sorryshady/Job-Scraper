"""RemoteOK source connector."""

from __future__ import annotations

import time
from typing import Any

import requests
from bs4 import BeautifulSoup

ENDPOINTS = [
    "https://remoteok.com/api?tag=machine-learning",
    "https://remoteok.com/api?tag=deep-learning",
    "https://remoteok.com/api?tag=ai",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; job-scraper/1.0; +https://github.com)",
    "Accept": "application/json",
}


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _normalize_job(job: dict[str, Any]) -> dict[str, Any] | None:
    url = (job.get("url") or "").strip()
    title = (job.get("position") or "").strip()
    company = (job.get("company") or "").strip()
    if not url or not title or not company:
        return None

    description_html = job.get("description") or ""
    return {
        "source": "RemoteOK",
        "source_id": str(job.get("id") or ""),
        "company_name": company,
        "role_title": title,
        "url": url,
        "posted_at": job.get("date"),
        "location": (job.get("location") or "").strip(),
        "description_html": description_html,
        "description_text": _strip_html(description_html),
        "tags": [str(tag).strip() for tag in (job.get("tags") or []) if str(tag).strip()],
        "employee_count": None,
        "notes_prefix": "",
    }


def fetch_jobs(timeout_seconds: int = 25) -> list[dict[str, Any]]:
    """Fetch and normalize RemoteOK listings."""
    seen_urls: set[str] = set()
    listings: list[dict[str, Any]] = []

    for index, endpoint in enumerate(ENDPOINTS):
        try:
            response = requests.get(endpoint, headers=HEADERS, timeout=timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            print(f"[RemoteOK] ERROR fetching {endpoint}: {exc}")
            if index < len(ENDPOINTS) - 1:
                time.sleep(2)
            continue

        if not isinstance(payload, list):
            print(f"[RemoteOK] WARNING unexpected response type from {endpoint}")
            if index < len(ENDPOINTS) - 1:
                time.sleep(2)
            continue

        for raw in payload[1:]:
            if not isinstance(raw, dict):
                continue
            normalized = _normalize_job(raw)
            if not normalized:
                continue
            if normalized["url"] in seen_urls:
                continue
            seen_urls.add(normalized["url"])
            listings.append(normalized)

        if index < len(ENDPOINTS) - 1:
            time.sleep(2)

    return listings

