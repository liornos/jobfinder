# file: jobfinder/providers/recruitee.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

API = "https://api.recruitee.com/c/{org}/offers"


def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch jobs from Recruitee public API."""
    try:
        url = API.format(org=org)
        data = get_json(url)
        jobs: List[Dict[str, Any]] = []
        offers = data.get("offers", [])
        if isinstance(data, list):
            offers = data
        for j in offers:
            jobs.append(
                {
                    "id": j.get("id"),
                    "title": j.get("title"),
                    "location": j.get("location")
                    or (j.get("locations", [{}])[0] if j.get("locations") else {}).get(
                        "name"
                    ),
                    "url": j.get("careers_url")
                    or j.get("url")
                    or f"https://{org}.recruitee.com/o/{j.get('slug') or j.get('id')}",
                    "created_at": j.get("created_at") or j.get("published_at"),
                    "remote": j.get("remote"),
                    "description": j.get("description") or "",
                }
            )
            if limit and len(jobs) >= limit:
                break
        return jobs
    except Exception:
        return []
