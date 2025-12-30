# file: jobfinder/providers/comeet.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

API_PATTERNS = [
    "https://www.comeet.com/careers-api/2.0/company/{org}/positions",
    "https://www.comeet.co/careers-api/2.0/company/{org}/positions",
]


def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch jobs from Comeet public API."""
    jobs: List[Dict[str, Any]] = []
    for pattern in API_PATTERNS:
        try:
            url = pattern.format(org=org)
            data = get_json(url)
            positions = data.get("positions", []) if isinstance(data, dict) else []
            for j in positions:
                location = j.get("location", {})
                loc_name = (
                    location.get("name")
                    if isinstance(location, dict)
                    else str(location)
                    if location
                    else ""
                )
                jobs.append(
                    {
                        "id": j.get("uid") or j.get("id"),
                        "title": j.get("name"),
                        "location": loc_name,
                        "url": j.get("url") or j.get("apply_url"),
                        "created_at": j.get("created_at") or j.get("updated_at"),
                        "remote": j.get("remote"),
                        "description": j.get("description") or "",
                    }
                )
                if limit and len(jobs) >= limit:
                    break
            if jobs:
                break
        except Exception:
            continue
    return jobs
