# file: jobfinder/providers/workday.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

# Workday public job board API pattern
# Note: Workday typically requires authentication, but some companies expose public endpoints
# This attempts common public endpoint patterns
API_PATTERNS = [
    "https://{org}.myworkdayjobs.com/wday/cxs/inline/{org}/jobpostings",
    "https://{org}.myworkdayjobs.com/{org}/job",
]

def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Attempt to fetch jobs from Workday public endpoints."""
    jobs: List[Dict[str, Any]] = []
    
    # Try common Workday public endpoint patterns
    for pattern in API_PATTERNS:
        try:
            url = pattern.format(org=org)
            # Try JSON endpoint
            data = get_json(url, params={"format": "json"})
            
            # Workday responses vary - try to parse common structures
            if isinstance(data, dict):
                job_list = data.get("jobPostings") or data.get("positions") or data.get("jobs") or []
            elif isinstance(data, list):
                job_list = data
            else:
                continue
            
            for j in job_list:
                if isinstance(j, dict):
                    jobs.append({
                        "id": str(j.get("id") or j.get("jobPostingId") or ""),
                        "title": j.get("title") or j.get("jobTitle") or "",
                        "location": j.get("location") or j.get("locations", [{}])[0].get("name", ""),
                        "url": j.get("externalPath") or j.get("applyUrl") or "",
                        "created_at": j.get("postedOn") or j.get("postedDate") or "",
                        "remote": None,
                        "description": j.get("description") or "",
                    })
                    if limit and len(jobs) >= limit:
                        break
        except Exception:
            # Try next pattern or return empty if none work
            continue
    
    return jobs[:limit] if limit else jobs
