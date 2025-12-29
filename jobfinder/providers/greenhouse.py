# file: jobfinder/providers/greenhouse.py
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional

from ._http import get_json

API = "https://boards-api.greenhouse.io/v1/boards/{org}/jobs"


def fetch_jobs(
    org: str, *, content: bool = True, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Fetch jobs from Greenhouse public board API."""
    url = API.format(org=org)
    params = {"content": "true" if content else "false"}
    data = get_json(url, params=params)
    jobs = []
    for j in data.get("jobs", []):
        jobs.append(
            {
                "id": j.get("id"),
                "title": j.get("title"),
                "location": (j.get("location") or {}).get("name"),
                "url": j.get("absolute_url"),
                "created_at": j.get("updated_at") or j.get("created_at"),
                "remote": None,
                "description": j.get("content") or "",
            }
        )
        if limit and len(jobs) >= limit:
            break
    return jobs
