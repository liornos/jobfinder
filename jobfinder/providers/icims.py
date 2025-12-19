# file: jobfinder/providers/icims.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

# iCIMS public API pattern
# Note: iCIMS typically requires authentication, but attempts common public endpoint patterns
API_PATTERNS = [
    "https://careers-{org}.icims.com/jobs/search",
    "https://{org}.icims.com/jobs/search",
]

def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Attempt to fetch jobs from iCIMS public endpoints."""
    jobs: List[Dict[str, Any]] = []
    
    for pattern in API_PATTERNS:
        try:
            url = pattern.format(org=org)
            data = get_json(url, params={"pr": "0", "format": "json"})
            
            if isinstance(data, dict):
                job_list = data.get("searchResults") or data.get("jobs") or []
            elif isinstance(data, list):
                job_list = data
            else:
                continue
            
            for j in job_list:
                if isinstance(j, dict):
                    jobs.append({
                        "id": str(j.get("jobId") or j.get("id") or ""),
                        "title": j.get("jobTitle") or j.get("title") or "",
                        "location": j.get("jobLocation") or j.get("location") or "",
                        "url": j.get("jobUrl") or j.get("url") or "",
                        "created_at": j.get("postedDate") or j.get("datePosted") or "",
                        "remote": None,
                        "description": j.get("jobDescription") or "",
                    })
                    if limit and len(jobs) >= limit:
                        break
        except Exception:
            continue
    
    return jobs[:limit] if limit else jobs
