# file: jobfinder/providers/smartrecruiters.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

API = "https://api.smartrecruiters.com/v1/companies/{org}/postings"
DETAIL_API = "https://api.smartrecruiters.com/v1/companies/{org}/postings/{posting_id}"

def _resolve_posting_url(org: str, posting_id: str, fallback: str) -> str:
    """
    SmartRecruiters list API does not include postingUrl/applyUrl; fetch details to get the human URL.
    If detail fetch fails, return the fallback (typically the API ref link).
    """
    try:
        data = get_json(DETAIL_API.format(org=org, posting_id=posting_id))
        return data.get("postingUrl") or data.get("applyUrl") or fallback
    except Exception:
        return fallback

def fetch_jobs(org: str, *, limit: Optional[int] = 100) -> List[Dict[str, Any]]:
    """Fetch jobs from SmartRecruiters public postings API."""
    params = {"limit": limit or 100}
    try:
        data = get_json(API.format(org=org), params=params)
    except Exception:
        return []
    jobs: List[Dict[str, Any]] = []
    for j in (data.get("content") or []):
        loc = (j.get("location") or {})
        city = ", ".join([x for x in [loc.get("city"), loc.get("country")] if x])
        pid = j.get("id") or j.get("refNumber") or ""
        # Always resolve the human-facing posting URL using a detail call.
        url = _resolve_posting_url(org, pid, j.get("ref") or "")
        jobs.append({
            "id": pid,
            "title": j.get("name"),
            "location": city,
            "url": url,
            "created_at": j.get("releasedDate") or j.get("createdOn"),
            "remote": None,
            "description": "",
        })
        if limit and len(jobs) >= limit:
            break
    return jobs
