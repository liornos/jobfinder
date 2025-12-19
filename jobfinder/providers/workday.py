# file: jobfinder/providers/workday.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

API_PATTERNS = [
    "https://{org}.myworkdayjobs.com/wday/cxs/inline/{org}/jobpostings",
    "https://{org}.myworkdayjobs.com/{org}/job",
]

def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch jobs from Workday public API."""
    jobs: List[Dict[str, Any]] = []
    for pattern in API_PATTERNS:
        try:
            url = pattern.format(org=org)
            data = get_json(url)
            # Workday API structure varies, try common patterns
            job_list = data.get("jobPostings") or data.get("jobs") or data.get("data") or []
            if isinstance(data, list):
                job_list = data
            for j in job_list:
                jobs.append({
                    "id": j.get("jobPostingId") or j.get("id") or j.get("externalPath"),
                    "title": j.get("title") or j.get("jobTitle"),
                    "location": j.get("location") or (j.get("locations", [{}])[0] if j.get("locations") else {}).get("name"),
                    "url": j.get("externalPath") or j.get("url") or f"https://{org}.myworkdayjobs.com/en-US/job/{j.get('jobPostingId') or j.get('id')}",
                    "created_at": j.get("postedOn") or j.get("createdAt"),
                    "remote": j.get("remote"),
                    "description": j.get("description") or j.get("jobDescription") or "",
                })
                if limit and len(jobs) >= limit:
                    break
            if jobs:
                break
        except Exception:
            continue
    return jobs
