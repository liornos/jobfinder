# file: jobfinder/providers/breezy.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

API = "https://{org}.breezy.hr/api/v3/positions"

def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch jobs from Breezy HR public API."""
    try:
        url = API.format(org=org)
        data = get_json(url)
        jobs: List[Dict[str, Any]] = []
        for j in data.get("positions", []):
            jobs.append({
                "id": j.get("id") or j.get("_id"),
                "title": j.get("name"),
                "location": j.get("location", {}).get("name") if isinstance(j.get("location"), dict) else j.get("location"),
                "url": j.get("url") or f"https://{org}.breezy.hr/position/{j.get('id') or j.get('_id')}",
                "created_at": j.get("created_at") or j.get("created"),
                "remote": j.get("remote"),
                "description": j.get("description") or "",
            })
            if limit and len(jobs) >= limit:
                break
        return jobs
    except Exception:
        return []
