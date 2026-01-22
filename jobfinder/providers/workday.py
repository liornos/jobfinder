# file: jobfinder/providers/workday.py
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Optional, Tuple
import json
import re
import ssl
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

from ._http import get_json as _legacy_get_json

API_PATH = "/wday/cxs/{tenant}/{site_id}/jobs"
DEFAULT_PAGE_SIZE = 20
_LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[A-Za-z]{2})?$")

# Back-compat for unit tests that monkeypatch workday.get_json
get_json = _legacy_get_json

API_PATTERNS = [
    "https://{host}/wday/cxs/inline/{org}/jobpostings",
    "https://{host}/{org}/job",
]


def _norm_text(val: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (val or "").lower()).strip()


def _ensure_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return "https://" + url.lstrip("/")


def _fetch_html(url: str) -> Tuple[str, str]:
    req = Request(
        url,
        headers={
            "User-Agent": "jobfinder/0.3",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    ctx = ssl.create_default_context()
    with urlopen(req, timeout=20, context=ctx) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
        return html, resp.geturl()


def _extract_config_value(html: str, key: str) -> Optional[str]:
    # matches: key: "value" or key: 'value'
    pat = rf"{re.escape(key)}\s*:\s*['\"]([^'\"]+)['\"]"
    m = re.search(pat, html)
    return m.group(1) if m else None


def _extract_locale_and_site(url: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        p = urlparse(url)
    except Exception:
        return None, None
    segs = [s for s in (p.path or "").split("/") if s]
    if not segs:
        return None, None
    first = segs[0]
    if _LOCALE_RE.match(first):
        locale = first
        site = segs[1] if len(segs) > 1 else None
        return locale, site
    return None, first


def _extract_location_ids_from_url(url: str) -> List[str]:
    try:
        q = parse_qs(urlparse(url).query)
    except Exception:
        return []
    raw = q.get("locations") or []
    out: List[str] = []
    for val in raw:
        for part in str(val).split(","):
            part = part.strip()
            if part:
                out.append(part)
    return out


def _post_jobs(
    *,
    host: str,
    tenant: str,
    site_id: str,
    applied_facets: Dict[str, List[str]],
    offset: int,
    limit: int,
    token: Optional[str],
) -> Dict[str, Any]:
    url = f"https://{host}" + API_PATH.format(tenant=tenant, site_id=site_id)
    payload = {
        "appliedFacets": applied_facets or {},
        "limit": int(limit),
        "offset": int(offset),
        "searchText": "",
    }
    headers = {
        "User-Agent": "jobfinder/0.3",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if token:
        headers["X-CALYPSO-CSRF-TOKEN"] = token
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    ctx = ssl.create_default_context()
    try:
        with urlopen(req, timeout=25, context=ctx) as resp:
            data = resp.read()
            return json.loads(data.decode("utf-8", errors="ignore"))
    except HTTPError as exc:
        if exc.code == 404:
            return {}
        raise


def _extract_location_facets(
    facets: Iterable[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    locations: List[Dict[str, Any]] = []
    countries: List[Dict[str, Any]] = []
    for f in facets or []:
        if f.get("facetParameter") != "locationMainGroup":
            continue
        for group in f.get("values") or []:
            if group.get("facetParameter") == "locations":
                locations = list(group.get("values") or [])
            elif group.get("facetParameter") == "locationHierarchy1":
                countries = list(group.get("values") or [])
    return locations, countries


def _match_location_facets(
    facets: Iterable[Dict[str, Any]], cities: List[str]
) -> Tuple[Dict[str, List[str]], List[str]]:
    if not cities:
        return {}, []
    locations, countries = _extract_location_facets(facets)
    if not locations and not countries:
        return {}, []

    city_norms = [_norm_text(c) for c in cities if c]
    city_norms = [c for c in city_norms if c]
    if not city_norms:
        return {}, []

    loc_ids: List[str] = []
    loc_labels: List[str] = []
    country_ids: List[str] = []
    country_labels: List[str] = []

    for cn in city_norms:
        if cn == "israel":
            for v in countries:
                if _norm_text(v.get("descriptor") or "") == "israel":
                    vid = v.get("id")
                    if vid and vid not in country_ids:
                        country_ids.append(vid)
                        country_labels.append(v.get("descriptor") or "Israel")
        else:
            for v in locations:
                desc = v.get("descriptor") or ""
                if cn and cn in _norm_text(desc):
                    vid = v.get("id")
                    if vid and vid not in loc_ids:
                        loc_ids.append(vid)
                        loc_labels.append(desc)

    if loc_ids:
        return {"locations": loc_ids}, loc_labels
    if country_ids:
        return {"locationHierarchy1": country_ids}, country_labels
    return {}, []


def _location_from_external_path(external_path: str) -> Optional[str]:
    if not external_path:
        return None
    path = unquote(external_path)
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    # expected: /job/Israel-Raanana/...
    if parts[0].lower() == "job" and len(parts) > 1:
        loc = parts[1]
    elif _LOCALE_RE.match(parts[0]) and len(parts) > 2 and parts[1].lower() == "job":
        loc = parts[2]
    else:
        return None
    loc = loc.replace("-", " ").strip()
    return loc or None


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


def _fetch_legacy_jobs(
    org: str, *, host: str, limit: Optional[int]
) -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    for pattern in API_PATTERNS:
        try:
            url = pattern.format(host=host, org=org)
            data = get_json(url)
        except Exception:
            continue

        job_list = data.get("jobPostings") or data.get("jobs") or data.get("data") or []
        if isinstance(data, list):
            job_list = data

        for j in job_list:
            jobs.append(
                {
                    "id": j.get("jobPostingId") or j.get("id") or j.get("externalPath"),
                    "title": j.get("title") or j.get("jobTitle"),
                    "location": j.get("location")
                    or (j.get("locations", [{}])[0] if j.get("locations") else {}).get(
                        "name"
                    ),
                    "url": j.get("externalPath") or j.get("url"),
                    "created_at": j.get("postedOn") or j.get("createdAt"),
                    "remote": j.get("remote"),
                    "description": j.get("description")
                    or j.get("jobDescription")
                    or "",
                }
            )
            if limit and len(jobs) >= limit:
                return jobs
        if jobs:
            return jobs
    return jobs


def fetch_jobs(
    org: str,
    *,
    limit: Optional[int] = None,
    company: Optional[Dict[str, Any]] = None,
    careers_url: Optional[str] = None,
    cities: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Fetch jobs from Workday public API."""
    jobs: List[Dict[str, Any]] = []
    base_url = _ensure_url(careers_url or (company or {}).get("careers_url") or "")
    if not base_url:
        base_url = f"https://{_resolve_host(org)}"

    # Back-compat: try legacy JSON endpoints first (used in tests).
    legacy_host = _resolve_host(org, company=company, careers_url=base_url)
    legacy_jobs = _fetch_legacy_jobs(org, host=legacy_host, limit=limit)
    if legacy_jobs:
        return legacy_jobs

    try:
        html, final_url = _fetch_html(base_url)
    except Exception:
        return jobs

    tenant = _extract_config_value(html, "tenant") or org
    site_id = _extract_config_value(html, "siteId")
    token = _extract_config_value(html, "token")
    request_locale = _extract_config_value(html, "requestLocale") or ""

    if not site_id:
        _, site_id = _extract_locale_and_site(final_url or base_url)
    locale, site_from_url = _extract_locale_and_site(final_url or base_url)
    if not site_id:
        site_id = site_from_url or org

    host = (urlparse(final_url or base_url).netloc or "").lower()
    if not host:
        host = _resolve_host(org, company=company, careers_url=careers_url)

    location_ids = _extract_location_ids_from_url(final_url or base_url)

    applied_facets: Dict[str, List[str]] = {}
    selected_labels: List[str] = []
    if cities:
        # Fetch facets to map city -> location IDs.
        try:
            seed = _post_jobs(
                host=host,
                tenant=tenant,
                site_id=site_id,
                applied_facets={},
                offset=0,
                limit=1,
                token=token,
            )
            applied_facets, selected_labels = _match_location_facets(
                seed.get("facets") or [], list(cities or [])
            )
        except Exception:
            applied_facets = {}
            selected_labels = []
    elif location_ids:
        applied_facets = {"locations": location_ids}

    page_size = int(limit or DEFAULT_PAGE_SIZE)
    page_size = max(1, min(page_size, DEFAULT_PAGE_SIZE))

    offset = 0
    total: Optional[int] = None
    while True:
        try:
            data = _post_jobs(
                host=host,
                tenant=tenant,
                site_id=site_id,
                applied_facets=applied_facets,
                offset=offset,
                limit=page_size,
                token=token,
            )
        except Exception:
            break

        if total is None:
            total = data.get("total") if isinstance(data.get("total"), int) else None

        job_list = data.get("jobPostings") or []
        if not job_list:
            break

        for j in job_list:
            external_path = j.get("externalPath") or ""
            raw_location = j.get("locationsText") or j.get("location") or ""
            location = raw_location
            if not location or re.match(r"^\d+\s+Locations$", str(location).strip()):
                if selected_labels:
                    location = ", ".join(selected_labels)
                else:
                    location = (
                        _location_from_external_path(external_path) or raw_location
                    )

            job_url = ""
            if external_path:
                if str(external_path).startswith("http"):
                    job_url = str(external_path)
                else:
                    use_locale = request_locale or locale or ""
                    prefix = f"/{use_locale}" if use_locale else ""
                    if site_id and f"/{site_id}/" in str(external_path):
                        base_path = ""
                    else:
                        base_path = f"{prefix}/{site_id}" if site_id else prefix
                    ext = (
                        external_path
                        if str(external_path).startswith("/")
                        else f"/{external_path}"
                    )
                    job_url = f"https://{host}{base_path}{ext}"

            jobs.append(
                {
                    "id": (j.get("bulletFields") or [None])[0]
                    or j.get("jobPostingId")
                    or j.get("id")
                    or external_path,
                    "title": j.get("title") or j.get("jobTitle"),
                    "location": location,
                    "url": job_url,
                    "created_at": j.get("postedOn") or j.get("createdAt"),
                    "remote": j.get("remote"),
                    "description": j.get("description") or "",
                }
            )
            if limit and len(jobs) >= limit:
                return jobs

        offset += len(job_list)
        if total is not None and offset >= total:
            break
        if len(job_list) < page_size:
            break

    return jobs
