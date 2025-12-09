# file: jobfinder/providers/smartrecruiters.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

API = "https://api.smartrecruiters.com/v1/companies/{org}/postings"

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
        jobs.append({
            "id": j.get("id") or j.get("refNumber"),
            "title": j.get("name"),
            "location": city,
            "url": (j.get("applyUrl") or j.get("ref") or ""),
            "created_at": j.get("releasedDate") or j.get("createdOn"),
            "remote": None,
            "description": "",
        })
        if limit and len(jobs) >= limit:
            break
    return jobs
