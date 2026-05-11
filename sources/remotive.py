"""Remotive source connector."""

from __future__ import annotations

import time
from typing import Any

import requests
from bs4 import BeautifulSoup

ENDPOINTS = [
    "https://remotive.com/api/remote-jobs?category=machine-learning",
    "https://remotive.com/api/remote-jobs?category=software-dev&limit=100",
]


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    return BeautifulSoup(value, "html.parser").get_text(" ", strip=True)


def _normalize_job(job: dict[str, Any]) -> dict[str, Any] | None:
    url = (job.get("url") or "").strip()
    title = (job.get("title") or "").strip()
    company_name = (job.get("company_name") or "").strip()
    if not url or not title or not company_name:
        return None

    description_html = job.get("description") or ""
    return {
        "source": "Remotive",
        "source_id": str(job.get("id") or ""),
        "company_name": company_name,
        "role_title": title,
        "url": url,
        "posted_at": job.get("publication_date"),
        "location": (job.get("candidate_required_location") or "").strip(),
        "description_html": description_html,
        "description_text": _strip_html(description_html),
        "tags": [str(tag).strip() for tag in (job.get("tags") or []) if str(tag).strip()],
        "employee_count": None,
        "notes_prefix": "",
    }


def fetch_jobs(timeout_seconds: int = 25) -> list[dict[str, Any]]:
    """Fetch and normalize Remotive listings."""
    seen_urls: set[str] = set()
    listings: list[dict[str, Any]] = []
    for index, endpoint in enumerate(ENDPOINTS):
        try:
            response = requests.get(endpoint, timeout=timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            jobs = payload.get("jobs") if isinstance(payload, dict) else None
            if not isinstance(jobs, list):
                raise ValueError("missing jobs list")
        except Exception as exc:  # noqa: BLE001
            print(f"[Remotive] ERROR fetching {endpoint}: {exc}")
            if index < len(ENDPOINTS) - 1:
                time.sleep(1)
            continue

        for raw in jobs:
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
            time.sleep(1)
    return listings

