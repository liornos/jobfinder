# file: jobfinder/providers/workday.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from ._http import get_json

API_PATTERNS = [
    "https://{host}/wday/cxs/inline/{org}/jobpostings",
    "https://{host}/{org}/job",
]


def _resolve_host(
    org: str,
    *,
    company: Optional[Dict[str, Any]] = None,
    careers_url: Optional[str] = None,
) -> str:
    url = careers_url or (company or {}).get("careers_url") or ""
    if url:
        try:
            host = (urlparse(url).netloc or "").lower()
            if host and host.endswith("myworkdayjobs.com"):
                return host
        except Exception:
            pass
    return f"{org}.myworkdayjobs.com"


def fetch_jobs(
    org: str,
    *,
    limit: Optional[int] = None,
    company: Optional[Dict[str, Any]] = None,
    careers_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch jobs from Workday public API."""
    jobs: List[Dict[str, Any]] = []
    host = _resolve_host(org, company=company, careers_url=careers_url)
    for pattern in API_PATTERNS:
        try:
            url = pattern.format(host=host, org=org)
            data = get_json(url)
            # Workday API structure varies, try common patterns
            job_list = (
                data.get("jobPostings") or data.get("jobs") or data.get("data") or []
            )
            if isinstance(data, list):
                job_list = data
            for j in job_list:
                jobs.append(
                    {
                        "id": j.get("jobPostingId")
                        or j.get("id")
                        or j.get("externalPath"),
                        "title": j.get("title") or j.get("jobTitle"),
                        "location": j.get("location")
                        or (
                            j.get("locations", [{}])[0] if j.get("locations") else {}
                        ).get("name"),
                        "url": j.get("externalPath")
                        or j.get("url")
                        or f"https://{org}.myworkdayjobs.com/en-US/job/{j.get('jobPostingId') or j.get('id')}",
                        "created_at": j.get("postedOn") or j.get("createdAt"),
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
