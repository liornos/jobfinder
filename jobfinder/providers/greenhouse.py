from __future__ import annotations
from datetime import datetime
from typing import AsyncIterator
import httpx
from ..models import Job, Company

class GreenhouseProvider:
    name = "greenhouse"
    API = "https://boards-api.greenhouse.io/v1/boards/{org}/jobs?content=true"

    async def jobs(self, company: Company) -> AsyncIterator[Job]:
        if not company.org: return
        url = self.API.format(org=company.org)
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url); r.raise_for_status(); data = r.json() or {}
            for j in data.get("jobs", []):
                job_id = str(j.get("id"))
                title = j.get("title") or ""
                location = (j.get("location") or {}).get("name")
                url = j.get("absolute_url") or ""
                created_at = j.get("updated_at") or j.get("created_at")
                dt = None
                if created_at:
                    try: dt = datetime.fromisoformat(created_at.replace("Z","+00:00"))
                    except Exception: dt = None
                desc = j.get("content") or ""
                text = f"{title} {location or ''} {desc}".lower()
                if "remote" in text:
                    work_mode = "remote"
                elif "hybrid" in text:
                    work_mode = "hybrid"
                else:
                    work_mode = "onsite"
                remote = "remote" in text  # legacy bool
                yield Job(
                    id=f"greenhouse:{company.org}:{job_id}",
                    title=title,
                    company=company.name or company.org or "unknown",
                    url=url,
                    location=location,
                    remote=remote,
                    created_at=dt,
                    provider=self.name,
                    extra={"description": desc, "work_mode": work_mode},
                )
