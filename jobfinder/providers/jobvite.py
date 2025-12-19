# file: jobfinder/providers/jobvite.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

# Jobvite public API pattern
# Note: Jobvite typically requires authentication, but attempts common public endpoint patterns
API_PATTERNS = [
    "https://{org}.jobvite.com/api/v2/jobs",
    "https://jobs.jobvite.com/{org}/api/v2/jobs",
]

def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Attempt to fetch jobs from Jobvite public endpoints."""
    jobs: List[Dict[str, Any]] = []
    
    for pattern in API_PATTERNS:
        try:
            url = pattern.format(org=org)
            data = get_json(url)
            
            if isinstance(data, dict):
                job_list = data.get("jobs") or data.get("positions") or []
            elif isinstance(data, list):
                job_list = data
            else:
                continue
            
            for j in job_list:
                if isinstance(j, dict):
                    jobs.append({
                        "id": str(j.get("id") or j.get("jobId") or ""),
                        "title": j.get("title") or j.get("jobTitle") or "",
                        "location": j.get("location") or j.get("city", "") + ", " + j.get("state", ""),
                        "url": j.get("applyUrl") or j.get("url") or "",
                        "created_at": j.get("date") or j.get("postedDate") or "",
                        "remote": j.get("remote", False),
                        "description": j.get("description") or "",
                    })
                    if limit and len(jobs) >= limit:
                        break
        except Exception:
            continue
    
    return jobs[:limit] if limit else jobs
