# file: jobfinder/providers/smartrecruiters.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

API = "https://api.smartrecruiters.com/v1/companies/{org}/postings"

def fetch_jobs(org: str, *, limit: Optional[int] = 100) -> List[Dict[str, Any]]:
    """
    Fetch jobs from SmartRecruiters public postings API.

    The list endpoint omits postingUrl/applyUrl, but the public page is stable at
    https://jobs.smartrecruiters.com/{org}/{id}. Building URLs locally avoids
    one detail API call per posting, which keeps scans fast on small hosts.
    """
    params = {"limit": limit or 100}
    try:
        data = get_json(API.format(org=org), params=params)
    except Exception:
        return []

    listings: List[Dict[str, Any]] = []
    for j in (data.get("content") or []):
        loc = (j.get("location") or {})
        city = ", ".join([x for x in [loc.get("city"), loc.get("country")] if x])
        pid = j.get("id") or j.get("refNumber") or ""
        listings.append({
            "pid": pid,
            "title": j.get("name"),
            "location": city,
            "created_at": j.get("releasedDate") or j.get("createdOn"),
            "url": f"https://jobs.smartrecruiters.com/{org}/{pid}" if pid else (j.get("ref") or ""),
        })
        if limit and len(listings) >= limit:
            break

    if not listings:
        return []

    jobs: List[Dict[str, Any]] = []
    for listing in listings:
        jobs.append({
            "id": listing["pid"],
            "title": listing["title"],
            "location": listing["location"],
            "url": listing["url"],
            "created_at": listing["created_at"],
            "remote": None,
            "description": "",
        })
    return jobs
