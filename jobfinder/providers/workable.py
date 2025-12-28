# file: jobfinder/providers/workable.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

from ._http import get_json

# Workable exposes multiple API shapes; try the common ones.
API_PATTERNS = [
    "https://apply.workable.com/api/v3/accounts/{org}/jobs",
    "https://apply.workable.com/api/v1/accounts/{org}/jobs",
]

def _loc_str(loc: Any) -> str:
    if isinstance(loc, dict):
        parts = [loc.get("city"), loc.get("region") or loc.get("state"), loc.get("country")]
        return ", ".join([p for p in parts if p])
    return str(loc) if loc else ""

def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Fetch jobs from Workable public API endpoints."""
    jobs: List[Dict[str, Any]] = []
    for pattern in API_PATTERNS:
        try:
            url = pattern.format(org=org)
            data = get_json(url)
            results = data.get("results") if isinstance(data, dict) else data
            if isinstance(data, dict) and not isinstance(results, list):
                results = data.get("jobs") or data.get("data") or []
            if isinstance(results, dict):
                results = results.get("results") or results.get("jobs") or results.get("data") or []
            if not isinstance(results, list):
                continue
            for j in results:
                loc = _loc_str(j.get("location"))
                job_url = j.get("url") or j.get("application_url")
                shortcode = (j.get("shortcode") or "").strip("/")
                if not job_url and shortcode:
                    job_url = f"https://apply.workable.com/{org}/j/{shortcode}/"
                jobs.append(
                    {
                        "id": j.get("id") or shortcode or j.get("slug"),
                        "title": j.get("title"),
                        "location": loc,
                        "url": job_url,
                        "created_at": j.get("published_at") or j.get("updated_at"),
                        "remote": j.get("workplace_type") == "remote" if j.get("workplace_type") else j.get("remote"),
                        "description": j.get("description") or "",
                    }
                )
                if limit and len(jobs) >= limit:
                    break
            if jobs:
                break
        except Exception:
            continue
    return jobs
