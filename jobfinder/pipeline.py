from __future__ import annotations
from typing import Iterable, List, Dict, Any, Tuple, Optional
from .models import Company, Job
from .providers import PROVIDERS
from .filtering import score, apply_filters, _extract_salary
from .utils.geo import geocode_place

async def fetch_jobs_for_companies(companies: Iterable[Company]) -> List[Job]:
    jobs: List[Job] = []
    async def _fetch_one(provider_name: str, company: Company) -> List[Job]:
        provider = PROVIDERS[provider_name]; js: List[Job] = []
        async for j in provider.jobs(company): js.append(j)
        return js
    import asyncio
    tasks = [_fetch_one(c.provider, c) for c in companies if c.provider and c.provider in PROVIDERS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, Exception): continue
        jobs.extend(r)
    return jobs

async def enrich_jobs_with_geo(jobs: List[Job], center_cities: List[str]) -> Tuple[List[Job], List[Tuple[float,float]]]:
    centers: List[Tuple[float,float]] = []
    for c in center_cities:
        gp = await geocode_place(c)
        if gp: centers.append(gp)
    if not centers:
        return jobs, centers
    for j in jobs:
        loc = j.location or ""
        if not loc: continue
        try:
            gp = await geocode_place(loc)
            if not j.extra: j.extra = {}
            if gp:
                j.extra["lat"], j.extra["lon"] = gp[0], gp[1]
        except Exception:
            pass
    return jobs, centers

async def filter_and_rank(jobs: Iterable[Job], *, cities: List[str], keywords: List[str], geo_centers: List[Tuple[float,float]] | None = None, radius_km: Optional[float] = None, server_filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for j in jobs:
        if j.extra is None: j.extra = {}
        if "salary_min" not in j.extra and "salary_max" not in j.extra:
            smin, smax = _extract_salary((j.extra or {}).get("description","") or "")
            if smin: j.extra["salary_min"] = smin
            if smax: j.extra["salary_max"] = smax
        s, reasons = score(j, keywords=keywords, cities=cities, center_points=geo_centers, radius_km=radius_km)
        row = j.to_row(); row["score"]=s; row["reasons"]=",".join(reasons); rows.append(row)
    rows.sort(key=lambda r: r.get("score",0), reverse=True)
    if server_filters: rows = apply_filters(rows, server_filters)
    return rows
