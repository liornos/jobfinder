from __future__ import annotations
import re
from typing import List, Tuple, Optional, Dict, Any
from .models import Job
from .utils.geo import haversine_km
try:
    from rapidfuzz import fuzz
except Exception:
    fuzz = None

def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())

def _extract_salary(desc: str):
    import re as _re
    nums = _re.findall(r"(\d{2,3}(?:[\s,]?\d{3})?)(?:\s*[kK])?", desc)
    vals = []
    for n in nums[:4]:
        n2 = n.replace(",", "").replace(" ", "")
        try:
            v = float(n2)
            vals.append(v*1000 if _re.search(rf"{n}\s*[kK]", desc) else v)
        except Exception:
            pass
    if not vals: return None, None
    vals.sort()
    return (vals[0], vals[-1] if len(vals)>1 else None)

def score(job: Job, keywords: List[str], cities: List[str],
          center_points=None, radius_km: Optional[float]=None) -> Tuple[int, List[str]]:
    s=0; reasons=[]
    t = normalize(job.title); loc = normalize(job.location or ""); desc = normalize((job.extra or {}).get("description","")[:4000])
    for kw in keywords:
        k=normalize(kw)
        if k in t: s+=20; reasons.append(f"title:{k}")
        if k and fuzz:
            s+=int(0.2*fuzz.partial_ratio(k,t)); s+=int(0.1*fuzz.partial_ratio(k,desc))
            if k in desc: reasons.append(f"desc:{k}")
    if cities and any(normalize(c) in loc for c in cities): s+=15; reasons.append("city")

    wm = ((job.extra or {}).get("work_mode") or "").lower()
    if wm == "remote":
        s += 5; reasons.append("remote")
    elif wm == "hybrid":
        s += 4; reasons.append("hybrid")
    elif job.remote:  # legacy
        s += 5; reasons.append("remote")

    if job.created_at:
        import datetime as _dt
        try:
            days = max(0, (_dt.datetime.utcnow() - job.created_at).days)
            s += max(0, 30 - days); reasons.append(f"fresh-{days}d")
        except Exception:
            pass

    sal_min = (job.extra or {}).get("salary_min"); sal_max = (job.extra or {}).get("salary_max")
    if sal_min or sal_max: s+=5; reasons.append("salary")

    lat=(job.extra or {}).get("lat"); lon=(job.extra or {}).get("lon")
    if center_points and radius_km and lat is not None and lon is not None:
        for clat, clon in center_points:
            d = haversine_km(clat, clon, lat, lon)
            if d <= radius_km:
                s += max(0, int(20 * (1 - (d / radius_km)))); reasons.append(f"geo:{int(d)}km"); break
    return s, reasons

def apply_filters(rows: List[Dict[str, Any]], filters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Server-side filters: provider/remote/min_score/max_age_days + cities."""
    out=[]
    prov = set(map(str.lower, filters.get("provider", []))) if filters.get("provider")            else (set([filters.get("provider")]) if filters.get("provider") else None)
    remote = (filters.get("remote") or "").lower() if filters.get("remote") is not None else None
    min_score = filters.get("min_score")
    max_age_days = filters.get("max_age_days")
    # NEW: city filter (substring match, case-insensitive). Remote jobs are allowed regardless of city.
    cities = [normalize(c) for c in (filters.get("cities") or []) if c]

    for r in rows:
        if prov and str(r.get("provider","")).lower() not in prov: continue

        # Remote/Hybrid/Onsite
        if remote in ("true","false","hybrid"):
            wm = ((r.get("extra") or {}).get("work_mode") or "").lower()
            if remote == "hybrid":
                if wm != "hybrid": continue
            elif remote == "true":
                if wm: 
                    if wm != "remote": continue
                else:
                    if not bool(r.get("remote")): continue
            elif remote == "false":
                if wm:
                    if wm != "onsite": continue
                else:
                    if bool(r.get("remote")): continue

        # City filter
        if cities:
            locn = normalize(str(r.get("location") or ""))
            wm = ((r.get("extra") or {}).get("work_mode") or "").lower()
            if wm != "remote" and not any(c in locn for c in cities):
                continue

        if min_score is not None and (r.get("score") or 0) < int(min_score): continue

        if max_age_days is not None and r.get("created_at"):
            try:
                from datetime import datetime, timezone
                dt = datetime.fromisoformat(str(r["created_at"]))
                age = (datetime.now(timezone.utc) - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))).days
                if age > int(max_age_days): continue
            except Exception: pass

        out.append(r)
    return out
