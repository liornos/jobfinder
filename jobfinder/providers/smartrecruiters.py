from __future__ import annotations
from datetime import datetime
from typing import AsyncIterator
import httpx
from ..models import Job, Company

class SmartRecruitersProvider:
    name = "smartrecruiters"
    API = "https://api.smartrecruiters.com/v1/companies/{org}/postings?limit=100"

    async def jobs(self, company: Company) -> AsyncIterator[Job]:
        if not company.org: return
        url = self.API.format(org=company.org)
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url); r.raise_for_status()
            data = r.json() or {}
            for j in data.get("content", []):
                job_id = str(j.get("id"))
                title = j.get("name") or ""
                loc = j.get("location") or {}
                location = ", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")])) or None
                url = j.get("ref") or j.get("applyUrl") or ""
                created_at = j.get("createdOn")
                dt = None
                if created_at:
                    try: dt = datetime.fromisoformat(created_at.replace("Z","+00:00"))
                    except Exception: dt = None
                desc = j.get("jobAd") or ""
                text = f"{title} {location or ''} {str(desc)}".lower()
                if "remote" in text:
                    work_mode = "remote"
                elif "hybrid" in text:
                    work_mode = "hybrid"
                else:
                    work_mode = "onsite"
                remote = "remote" in text  # legacy bool
                yield Job(
                    id=f"smartrecruiters:{company.org}:{job_id}",
                    title=title,
                    company=company.name or company.org or "unknown",
                    url=url,
                    location=location,
                    remote=remote,
                    created_at=dt,
                    provider=self.name,
                    extra={"description": str(desc), "work_mode": work_mode},
                )
