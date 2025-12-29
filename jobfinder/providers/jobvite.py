# file: jobfinder/providers/jobvite.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

API_PATTERNS = [
    "https://{org}.jobvite.com/api/v2/jobs",
    "https://jobs.jobvite.com/{org}/api/v2/jobs",
]


def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch jobs from Jobvite public API."""
    jobs: List[Dict[str, Any]] = []
    for pattern in API_PATTERNS:
        try:
            url = pattern.format(org=org)
            data = get_json(url)
            job_list = data.get("jobs") or data.get("data") or []
            if isinstance(data, list):
                job_list = data
            for j in job_list:
                jobs.append(
                    {
                        "id": j.get("jobId") or j.get("id"),
                        "title": j.get("title") or j.get("jobTitle"),
                        "location": j.get("location") or j.get("city"),
                        "url": j.get("applyUrl")
                        or j.get("url")
                        or f"https://{org}.jobvite.com/j/{j.get('jobId') or j.get('id')}",
                        "created_at": j.get("datePosted") or j.get("createdAt"),
                        "remote": j.get("remote"),
                        "description": j.get("description")
                        or j.get("jobDescription")
                        or "",
                    }
                )
                if limit and len(jobs) >= limit:
                    break
            if jobs:
                break
        except Exception:
            continue
    return jobs
