# file: jobfinder/providers/lever.py
from __future__ import annotations
import datetime as _dt
from typing import Any, Dict, List, Optional

from ._http import get_json

API = "https://api.lever.co/v0/postings/{org}?mode=json"

def _ms_to_iso(ms: Optional[int]) -> Optional[str]:
    if not ms:
        return None
    try:
        return _dt.datetime.utcfromtimestamp(ms / 1000).isoformat() + "Z"
    except Exception:
        return None

def fetch_jobs(org: str, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    data = get_json(API.format(org=org))
    jobs: List[Dict[str, Any]] = []
    for j in data or []:
        loc = (j.get("categories") or {}).get("location")
        jobs.append({
            "id": j.get("id") or j.get("data") or j.get("hostedUrl"),
            "title": j.get("text"),
            "location": loc,
            "url": j.get("hostedUrl"),
            "created_at": _ms_to_iso(j.get("createdAt")) or _ms_to_iso(j.get("updatedAt")),
            "remote": None,
            "description": j.get("lists") or "",
        })
        if limit and len(jobs) >= limit:
            break
    return jobs
