# file: jobfinder/providers/smartrecruiters.py
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
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

    listings: List[Dict[str, Any]] = []
    for j in (data.get("content") or []):
        loc = (j.get("location") or {})
        city = ", ".join([x for x in [loc.get("city"), loc.get("country")] if x])
        pid = j.get("id") or j.get("refNumber") or ""
        listings.append({
            "pid": pid,
            "fallback": j.get("ref") or "",
            "title": j.get("name"),
            "location": city,
            "created_at": j.get("releasedDate") or j.get("createdOn"),
        })
        if limit and len(listings) >= limit:
            break

    if not listings:
        return []

    # Resolve posting URLs concurrently; the detail endpoint is slow when called serially.
    def _fetch_url(item: Dict[str, Any]) -> str:
        pid = item["pid"]
        if not pid:
            return item["fallback"]
        return _resolve_posting_url(org, pid, item["fallback"])

    max_workers = min(12, max(1, len(listings)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        urls = list(pool.map(_fetch_url, listings))

    jobs: List[Dict[str, Any]] = []
    for listing, url in zip(listings, urls):
        jobs.append({
            "id": listing["pid"],
            "title": listing["title"],
            "location": listing["location"],
            "url": url,
            "created_at": listing["created_at"],
            "remote": None,
            "description": "",
        })
    return jobs
