from __future__ import annotations
from typing import Iterable, List, Dict, Any
from .models import Company, Job
from .providers import PROVIDERS
from .filtering import score

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

def filter_and_rank(jobs: Iterable[Job], cities: List[str], keywords: List[str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for j in jobs:
        s, reasons = score(j, keywords=keywords, cities=cities)
        row = j.to_row(); row["score"]=s; row["reasons"]=",".join(reasons); out.append(row)
    out.sort(key=lambda r: r.get("score",0), reverse=True); return out
