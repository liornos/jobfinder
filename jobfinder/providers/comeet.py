# file: jobfinder/providers/comeet.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

API = "https://www.comeet.co/careers-api/2.0/company/{org}/positions"

def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch jobs from Comeet public API."""
    try:
        url = API.format(org=org)
        data = get_json(url)
        jobs: List[Dict[str, Any]] = []
        for j in data.get("positions", []):
            location = j.get("location", {})
            loc_name = location.get("name") if isinstance(location, dict) else str(location) if location else ""
            jobs.append({
                "id": j.get("uid") or j.get("id"),
                "title": j.get("name"),
                "location": loc_name,
                "url": j.get("url") or j.get("apply_url"),
                "created_at": j.get("created_at") or j.get("updated_at"),
                "remote": j.get("remote"),
                "description": j.get("description") or "",
            })
            if limit and len(jobs) >= limit:
                break
        return jobs
    except Exception:
        return []
