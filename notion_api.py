"""Notion SDK wrapper for schema validation, dedupe query, and inserts."""

from __future__ import annotations

import time
from datetime import date
from typing import Any

from notion_client import Client
from notion_client.errors import APIResponseError

REQUIRED_PROPERTIES = {
    "Company Name",
    "Role Title",
    "Link to JD",
    "Date Found",
    "Source",
    "Role Type",
    "F1 Friendly",
    "Location",
    "Status",
    "Priority",
    "Company Stage",
    "Tech Stack Match",
    "Notes",
}


class NotionJobClient:
    """Small adapter around the official Notion client."""

    def __init__(self, api_key: str, database_id: str) -> None:
        self.database_id = database_id
        self.client = Client(auth=api_key)

    def validate_schema(self) -> None:
        database = self.client.databases.retrieve(database_id=self.database_id)
        properties = database.get("properties", {})
        if not isinstance(properties, dict):
            raise RuntimeError("Notion schema fetch returned malformed properties payload.")
        missing = sorted(REQUIRED_PROPERTIES - set(properties.keys()))
        if missing:
            raise RuntimeError(f"Notion schema mismatch. Missing properties: {missing}")

    def fetch_existing_job_urls(self) -> set[str]:
        urls: set[str] = set()
        cursor: str | None = None
        while True:
            payload: dict[str, Any] = {
                "database_id": self.database_id,
                "page_size": 100,
                "filter": {"property": "Link to JD", "url": {"is_not_empty": True}},
            }
            if cursor:
                payload["start_cursor"] = cursor

            response = self.client.databases.query(**payload)
            for result in response.get("results", []):
                props = result.get("properties", {})
                if not isinstance(props, dict):
                    continue
                link_prop = props.get("Link to JD", {})
                if not isinstance(link_prop, dict):
                    continue
                url = link_prop.get("url")
                if isinstance(url, str) and url.strip():
                    urls.add(url.strip())

            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
            if not cursor:
                break
        return urls

    def insert_listing(self, listing: dict[str, Any], date_found: str | None = None) -> bool:
        today = date_found or date.today().isoformat()
        notes_value = str(listing.get("notes_prefix") or "")
        try:
            self.client.pages.create(
                parent={"database_id": self.database_id},
                properties={
                    "Company Name": {"title": [{"text": {"content": str(listing["company_name"])[:2000]}}]},
                    "Role Title": {"rich_text": [{"text": {"content": str(listing["role_title"])[:2000]}}]},
                    "Link to JD": {"url": str(listing["url"])},
                    "Date Found": {"date": {"start": today}},
                    "Source": {"select": {"name": str(listing["source"])}},
                    "Role Type": {"select": {"name": str(listing["role_type"])}},
                    "F1 Friendly": {"select": {"name": str(listing["f1_friendly"])}},
                    "Location": {"rich_text": [{"text": {"content": str(listing.get("location") or "")[:2000]}}]},
                    "Status": {"select": {"name": "New"}},
                    "Priority": {"select": {"name": "Medium"}},
                    "Company Stage": {"select": {"name": str(listing["company_stage"])}},
                    "Tech Stack Match": {"select": {"name": str(listing["tech_stack_match"])}},
                    "Notes": {"rich_text": [{"text": {"content": notes_value[:2000]}}]},
                },
            )
            return True
        except APIResponseError as exc:
            print(f"[Notion] ERROR inserting '{listing.get('role_title')}' ({listing.get('url')}): {exc}")
            return False
        except Exception as exc:  # noqa: BLE001
            print(f"[Notion] ERROR unexpected insert failure '{listing.get('url')}': {exc}")
            return False

    @staticmethod
    def throttle_insert() -> None:
        """Throttle inserts to stay below Notion rate limits."""
        time.sleep(0.4)

