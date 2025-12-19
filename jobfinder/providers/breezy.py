# file: jobfinder/providers/breezy.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

# Breezy HR public API
# Note: Breezy typically requires authentication, but some companies expose public endpoints
API = "https://{org}.breezy.hr/api/v3/positions"

def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Attempt to fetch jobs from Breezy HR public endpoints."""
    jobs: List[Dict[str, Any]] = []
    
    try:
        url = API.format(org=org)
        data = get_json(url)
        
        if isinstance(data, list):
            for j in data:
                if isinstance(j, dict):
                    jobs.append({
                        "id": str(j.get("id") or ""),
                        "title": j.get("name") or "",
                        "location": j.get("location", {}).get("name", "") if isinstance(j.get("location"), dict) else str(j.get("location", "")),
                        "url": j.get("url") or j.get("public_url") or "",
                        "created_at": j.get("created_at") or j.get("published_at") or "",
                        "remote": j.get("remote", False),
                        "description": j.get("description") or "",
                    })
                    if limit and len(jobs) >= limit:
                        break
    except Exception:
        # Breezy requires authentication for most endpoints
        return []
    
    return jobs[:limit] if limit else jobs
