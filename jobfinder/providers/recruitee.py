# file: jobfinder/providers/recruitee.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

# Recruitee public careers API
API = "https://api.recruitee.com/c/{org}/offers"

def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Attempt to fetch jobs from Recruitee public API."""
    jobs: List[Dict[str, Any]] = []
    
    try:
        data = get_json(API.format(org=org))
        
        if isinstance(data, dict):
            offers = data.get("offers") or []
        elif isinstance(data, list):
            offers = data
        else:
            return []
        
        for j in offers:
            if isinstance(j, dict):
                location_parts = []
                if j.get("city"):
                    location_parts.append(j["city"])
                if j.get("country"):
                    location_parts.append(j["country"])
                location_str = ", ".join(location_parts) if location_parts else ""
                
                jobs.append({
                    "id": str(j.get("id") or ""),
                    "title": j.get("title") or "",
                    "location": location_str,
                    "url": j.get("careers_url") or j.get("url") or "",
                    "created_at": j.get("created_at") or j.get("published_at") or "",
                    "remote": j.get("remote", False),
                    "description": j.get("description") or "",
                })
                if limit and len(jobs) >= limit:
                    break
    except Exception:
        # Recruitee may require authentication
        return []
    
    return jobs[:limit] if limit else jobs
