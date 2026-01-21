from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any, Dict, List, Optional, Tuple

try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None


@dataclass(frozen=True, slots=True)
class Job:
    id: str
    title: str
    company: str
    url: str
    location: Optional[str] = None
    remote: Optional[bool] = None
    created_at: Optional[datetime] = None
    provider: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    c = 2 * asin(sqrt(a))
    return R * c


def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


REMOTE_ONLY_TOKENS = {
    "remote",
    "remotely",
    "anywhere",
    "wfh",
    "work",
    "from",
    "home",
    "homebased",
    "based",
    "global",
    "worldwide",
    "international",
    "only",
    "telecommute",
    "telecommuting",
}


def _parse_created_at(val: Any) -> Optional[datetime]:
    """
    Best-effort parser for provider created_at values (ISO string, Z suffix, or epoch ms).
    Returns timezone-aware datetime in UTC or None on failure.
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)

    if isinstance(val, (int, float)):
        try:
            ts = float(val)
            if ts > 1e12:
                ts /= 1000.0  # likely milliseconds
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None

    s = str(val).strip()
    if not s:
        return None

    if s.isdigit():
        try:
            ts = float(s)
            if len(s) >= 13:
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            pass

    cleaned = s[:-1] + "+00:00" if s.endswith("Z") else s
    cleaned = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", cleaned)

    for cand in (cleaned, s):
        try:
            dt = datetime.fromisoformat(cand)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

    try:
        dt = datetime.strptime(s[:10], "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _extract_salary(desc: str):
    import re as _re

    nums = _re.findall(r"(\d{2,3}(?:[\s,]?\d{3})?)(?:\s*[kK])?", desc)
    vals = []
    for n in nums[:4]:
        n2 = n.replace(",", "").replace(" ", "")
        try:
            v = float(n2)
            vals.append(v * 1000 if _re.search(rf"{n}\s*[kK]", desc) else v)
        except Exception:
            pass
    if not vals:
        return None, None
    vals.sort()
    return (vals[0], vals[-1] if len(vals) > 1 else None)


def score(
    job: Job,
    keywords: List[str],
    cities: List[str],
    center_points=None,
    radius_km: Optional[float] = None,
) -> Tuple[int, List[str]]:
    s = 0
    reasons = []
    t = normalize(job.title)
    loc = normalize(job.location or "")
    desc = normalize((job.extra or {}).get("description", "")[:4000])
    for kw in keywords:
        k = normalize(kw)
        if k in t:
            s += 20
            reasons.append(f"title:{k}")
        if k and fuzz:
            s += int(0.2 * fuzz.partial_ratio(k, t))
            s += int(0.1 * fuzz.partial_ratio(k, desc))
            if k in desc:
                reasons.append(f"desc:{k}")
    if cities and any(normalize(c) in loc for c in cities):
        s += 15
        reasons.append("city")

    wm = ((job.extra or {}).get("work_mode") or "").lower()
    if wm == "remote":
        s += 5
        reasons.append("remote")
    elif wm == "hybrid":
        s += 4
        reasons.append("hybrid")
    elif job.remote:  # legacy
        s += 5
        reasons.append("remote")

    if job.created_at:
        import datetime as _dt

        try:
            now = _dt.datetime.now(job.created_at.tzinfo or _dt.timezone.utc)
            days = max(0, (now - job.created_at).days)
            s += max(0, 30 - days)
            reasons.append(f"fresh-{days}d")
        except Exception:
            pass

    sal_min = (job.extra or {}).get("salary_min")
    sal_max = (job.extra or {}).get("salary_max")
    if sal_min or sal_max:
        s += 5
        reasons.append("salary")

    lat = (job.extra or {}).get("lat")
    lon = (job.extra or {}).get("lon")
    if center_points and radius_km and lat is not None and lon is not None:
        for clat, clon in center_points:
            d = haversine_km(clat, clon, lat, lon)
            if d <= radius_km:
                s += max(0, int(20 * (1 - (d / radius_km))))
                reasons.append(f"geo:{int(d)}km")
                break
    return s, reasons


def apply_filters(
    rows: List[Dict[str, Any]], filters: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Server-side filters: provider/remote/min_score/max_age_days + cities."""
    out = []
    raw_provider = filters.get("provider")
    if raw_provider:
        if isinstance(raw_provider, (list, tuple, set)):
            prov = {str(p).lower() for p in raw_provider if p}
        else:
            prov = {str(raw_provider).lower()}
    else:
        prov = None
    remote = (
        (filters.get("remote") or "").lower()
        if filters.get("remote") is not None
        else None
    )
    min_score = filters.get("min_score")
    max_age_days = filters.get("max_age_days")
    # City filter (substring match, case-insensitive). Match job location or company city.
    cities = [normalize(c) for c in (filters.get("cities") or []) if c]

    for r in rows:
        if prov and str(r.get("provider", "")).lower() not in prov:
            continue

        # Remote/Hybrid/Onsite
        if remote in ("true", "false", "hybrid"):
            wm = ((r.get("extra") or {}).get("work_mode") or "").lower()
            if remote == "hybrid":
                if wm != "hybrid":
                    continue
            elif remote == "true":
                if wm:
                    if wm != "remote":
                        continue
                else:
                    if not bool(r.get("remote")):
                        continue
            elif remote == "false":
                if wm:
                    if wm != "onsite":
                        continue
                else:
                    if bool(r.get("remote")):
                        continue

        # City filter: match explicit locations; only fallback to company city for remote/blank.
        if cities:
            locn = normalize(str(r.get("location") or ""))
            company_city = normalize(str(r.get("company_city") or ""))
            locn_tokens = [t for t in re.split(r"[^a-z0-9]+", locn) if t]
            remote_only = not locn_tokens or all(
                t in REMOTE_ONLY_TOKENS for t in locn_tokens
            )

            if any(c in locn for c in cities):
                pass
            elif locn and not remote_only:
                continue
            else:
                wm = ((r.get("extra") or {}).get("work_mode") or "").lower()
                remote_flag = bool(r.get("remote"))
                is_remoteish = remote_only or not locn or wm == "remote" or remote_flag
                if not (is_remoteish and any(c in company_city for c in cities)):
                    continue

        if min_score is not None and (r.get("score") or 0) < int(min_score):
            continue

        if max_age_days is not None and r.get("created_at"):
            dt = _parse_created_at(r.get("created_at"))
            if dt:
                age = (datetime.now(timezone.utc) - dt).days
                if age > int(max_age_days):
                    continue

        out.append(r)
    return out


def filter_by_title_keywords(
    rows: List[Dict[str, Any]], keywords: List[str]
) -> List[Dict[str, Any]]:
    """
    Lightweight title filter used by the API/UI to avoid client-side filtering loops.
    Matches if any keyword substring is present (case-insensitive).
    """
    needles = [normalize(k) for k in (keywords or []) if k]
    if not needles:
        return rows
    out = []
    for r in rows:
        title = normalize(str(r.get("title") or ""))
        if any(n in title for n in needles):
            out.append(r)
    return out
