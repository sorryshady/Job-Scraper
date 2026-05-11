"""Filtering and classification logic for normalized job listings."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

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
    "python",
    "data scientist",
    "applied scientist",
    "ml platform",
    "ai/ml",
]

EXCLUDE_TITLE_TERMS = [
    "senior",
    "sr.",
    "staff",
    "lead",
    "principal",
    "head of",
    "director",
    "vp ",
    "vice president",
    "manager",
    "architect",
]

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

STRONG_MATCH = [
    "pytorch",
    "python",
    "core ml",
    "tflite",
    "onnx",
    "transformers",
    "hugging face",
    "computer vision",
    "nlp",
]

PARTIAL_MATCH = ["tensorflow", "sklearn", "scikit-learn", "pandas", "sql", "spark", "aws", "gcp"]


def _contains_any(value: str, terms: list[str]) -> bool:
    return any(term in value for term in terms)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_employee_count(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if "-" in cleaned:
        left = cleaned.split("-", maxsplit=1)[0].strip()
        return int(left) if left.isdigit() else None
    return int(cleaned) if cleaned.isdigit() else None


def classify_f1_friendly(description_text: str) -> str:
    content = (description_text or "").lower()
    if _contains_any(content, F1_NO_SIGNALS):
        return "No"
    if _contains_any(content, F1_YES_SIGNALS):
        return "Yes"
    return "Unknown"


def classify_role_type(title: str) -> str:
    lowered = (title or "").lower()
    if any(x in lowered for x in ["research", "scientist"]):
        return "Research"
    if any(x in lowered for x in ["ml engineer", "machine learning engineer", "mlops", "inference"]):
        return "Startup-MLE"
    if any(x in lowered for x in ["data scientist", "applied scientist"]):
        return "Startup-DS"
    return "Other"


def classify_tech_stack_match(description_text: str) -> str:
    content = (description_text or "").lower()
    strong_hits = sum(1 for term in STRONG_MATCH if term in content)
    partial_hits = sum(1 for term in PARTIAL_MATCH if term in content)
    if strong_hits >= 2:
        return "Strong"
    if strong_hits == 1 or partial_hits >= 2:
        return "Partial"
    return "Weak"


def classify_company_stage(employee_count: int | None) -> str:
    if employee_count is None:
        return "Unknown"
    if employee_count <= 50:
        return "Seed"
    if employee_count <= 150:
        return "Series A"
    if employee_count <= 200:
        return "Series B"
    return "Unknown"


def apply_filters(listing: dict[str, Any], now_utc: datetime | None = None) -> tuple[bool, dict[str, Any]]:
    """Return (passes, updated_listing)."""
    updated = dict(listing)
    title = str(updated.get("role_title") or "")
    lowered_title = title.lower()
    description_text = str(updated.get("description_text") or "")
    lowered_description = description_text.lower()

    if not _contains_any(lowered_title, TITLE_KEYWORDS):
        return False, updated

    if _contains_any(lowered_title, EXCLUDE_TITLE_TERMS):
        return False, updated

    employee_count = _normalize_employee_count(updated.get("employee_count"))
    updated["employee_count"] = employee_count
    if employee_count is not None and employee_count >= 200:
        return False, updated

    posted_at = _parse_datetime(updated.get("posted_at"))
    if posted_at is not None:
        clock = now_utc or datetime.now(timezone.utc)
        if posted_at < (clock - timedelta(days=14)):  # CHANGE BACK TO 48 HOURS before pushing to GitHub.
            return False, updated

    location = str(updated.get("location") or "").strip()
    remote_signals = "remote" in f"{location} {lowered_description}".lower()
    if not remote_signals and location:
        current_notes = str(updated.get("notes_prefix") or "")
        updated["notes_prefix"] = f"{current_notes}ONSITE — ".strip()

    return True, updated


def classify_listing(listing: dict[str, Any]) -> dict[str, Any]:
    updated = dict(listing)
    updated["f1_friendly"] = classify_f1_friendly(str(updated.get("description_text") or ""))
    updated["role_type"] = classify_role_type(str(updated.get("role_title") or ""))
    updated["tech_stack_match"] = classify_tech_stack_match(str(updated.get("description_text") or ""))
    updated["company_stage"] = classify_company_stage(updated.get("employee_count"))
    return updated

