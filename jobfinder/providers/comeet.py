# file: jobfinder/providers/comeet.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

# Comeet public career page API
# Note: Comeet typically requires authentication, but some companies expose public endpoints
API = "https://www.comeet.co/careers-api/2.0/company/{org}/positions"

def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Attempt to fetch jobs from Comeet public endpoints."""
    jobs: List[Dict[str, Any]] = []
    
    try:
        # Try public endpoint (may require token for some companies)
        url = API.format(org=org)
        data = get_json(url, params={"details": "false"})
        
        if isinstance(data, list):
            for j in data:
                if isinstance(j, dict):
                    loc = j.get("location", {})
                    location_str = loc.get("name") or f"{loc.get('city', '')}, {loc.get('country', '')}".strip(", ")
                    
                    jobs.append({
                        "id": str(j.get("uid") or ""),
                        "title": j.get("name") or "",
                        "location": location_str,
                        "url": j.get("url_active_page") or j.get("url_comeet_hosted_page") or "",
                        "created_at": j.get("time_updated") or "",
                        "remote": j.get("workplace_type", "").lower() == "remote",
                        "description": "",
                    })
                    if limit and len(jobs) >= limit:
                        break
    except Exception:
        # Comeet requires authentication for most endpoints
        return []
    
    return jobs[:limit] if limit else jobs
