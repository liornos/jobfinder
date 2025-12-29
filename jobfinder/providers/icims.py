# file: jobfinder/providers/icims.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

API_PATTERNS = [
    "https://careers-{org}.icims.com/jobs/search",
    "https://{org}.icims.com/jobs/search",
]


def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch jobs from iCIMS public API."""
    jobs: List[Dict[str, Any]] = []
    for pattern in API_PATTERNS:
        try:
            url = pattern.format(org=org)
            data = get_json(url)
            # iCIMS API structure varies
            job_list = (
                data.get("searchResults") or data.get("jobs") or data.get("data") or []
            )
            if isinstance(data, list):
                job_list = data
            for j in job_list:
                jobs.append(
                    {
                        "id": j.get("jobId") or j.get("id"),
                        "title": j.get("jobTitle") or j.get("title"),
                        "location": j.get("location") or j.get("jobLocation"),
                        "url": j.get("jobUrl")
                        or j.get("url")
                        or f"https://careers-{org}.icims.com/jobs/{j.get('jobId') or j.get('id')}",
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
