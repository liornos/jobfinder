# file: jobfinder/providers/comeet.py
from __future__ import annotations
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ._http import get_json

API_BASE = "https://www.comeet.co/careers-api/2.0/company/{company_uid}/positions"
_COMPANY_RE = re.compile(r"COMPANY_DATA\s*=\s*(\{.*?\});", re.DOTALL)


def _fetch_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": "jobfinder/0.3"})
    with urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _parse_company_meta(html: str) -> Dict[str, Any]:
    match = _COMPANY_RE.search(html or "")
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except Exception:
        return {}


def _parse_comeet_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        p = urlparse(url)
        segs = [s for s in (p.path or "").split("/") if s]
        if "jobs" in segs:
            idx = segs.index("jobs")
            slug = segs[idx + 1] if len(segs) > idx + 1 else None
            company_uid = segs[idx + 2] if len(segs) > idx + 2 else None
            return slug, company_uid
        slug = segs[0] if segs else None
        company_uid = segs[1] if len(segs) > 1 else None
        return slug, company_uid
    except Exception:
        return None, None


def _resolve_company_meta(
    org: str,
    careers_url: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    slug = None
    company_uid = None
    token = None

    if careers_url:
        slug, company_uid = _parse_comeet_url(careers_url)
        try:
            html = _fetch_html(careers_url)
            meta = _parse_company_meta(html)
            token = meta.get("token") or token
            company_uid = company_uid or meta.get("company_uid")
            slug = slug or meta.get("slug")
        except Exception:
            pass

    if not slug:
        slug = (org or "").strip() or None
    if not company_uid and org and "." in org:
        company_uid = org

    return slug, company_uid, token


def fetch_jobs(
    org: str,
    *,
    limit: Optional[int] = None,
    company: Optional[Dict[str, Any]] = None,
    careers_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch jobs from Comeet public API.
    Requires company_uid + token (parsed from a valid Comeet job URL).
    """
    url = careers_url or (company or {}).get("careers_url")
    _, company_uid, token = _resolve_company_meta(org, url)
    if not company_uid or not token:
        return []

    try:
        data = get_json(
            API_BASE.format(company_uid=company_uid), params={"token": token}
        )
    except Exception:
        return []

    positions: List[Dict[str, Any]] = []
    raw_positions: Any = []
    if isinstance(data, list):
        raw_positions = data
    elif isinstance(data, dict):
        raw_positions = data.get("positions") or data.get("data") or []
        if isinstance(raw_positions, dict):
            raw_positions = (
                raw_positions.get("positions") or raw_positions.get("data") or []
            )

    if isinstance(raw_positions, list):
        positions = [p for p in raw_positions if isinstance(p, dict)]
    elif isinstance(raw_positions, dict):
        positions = [p for p in raw_positions.values() if isinstance(p, dict)]

    jobs: List[Dict[str, Any]] = []
    for j in positions or []:
        location = j.get("location", {})
        loc_name = (
            location.get("name")
            if isinstance(location, dict)
            else str(location)
            if location
            else ""
        )
        remote_flag = None
        if isinstance(location, dict):
            remote_flag = location.get("is_remote")
        workplace = str(j.get("workplace_type") or "").lower()
        if remote_flag is None and workplace:
            remote_flag = "remote" in workplace
        if remote_flag is None:
            remote_val = j.get("remote")
            if isinstance(remote_val, bool):
                remote_flag = remote_val

        jobs.append(
            {
                "id": j.get("uid") or j.get("internal_use_custom_id"),
                "title": j.get("name"),
                "location": loc_name,
                "url": j.get("url_comeet_hosted_page")
                or j.get("url_recruit_hosted_page")
                or j.get("url_active_page")
                or j.get("position_url")
                or j.get("url")
                or j.get("apply_url"),
                "created_at": j.get("time_updated")
                or j.get("created_at")
                or j.get("updated_at"),
                "remote": remote_flag,
                "description": j.get("description") or "",
            }
        )
        if limit and len(jobs) >= limit:
            break
    return jobs
