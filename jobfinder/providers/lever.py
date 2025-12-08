from __future__ import annotations
from datetime import datetime
from typing import AsyncIterator
import httpx
from ..models import Job, Company

class LeverProvider:
    name = "lever"
    API = "https://api.lever.co/v0/postings/{org}?mode=json"

    async def jobs(self, company: Company) -> AsyncIterator[Job]:
        if not company.org: return
        url = self.API.format(org=company.org)
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url); r.raise_for_status(); data = r.json() or []
            for j in data:
                job_id = str(j.get("id"))
                title = j.get("text") or j.get("title") or ""
                location = (j.get("categories") or {}).get("location")
                url = j.get("hostedUrl") or j.get("applyUrl") or ""
                created_at = j.get("createdAt"); dt=None
                if created_at:
                    try: dt = datetime.utcfromtimestamp(int(created_at)/1000.0)
                    except Exception: dt=None
                desc = j.get("descriptionPlain") or j.get("description") or ""
                text = f"{title} {location or ''} {desc}".lower()
                if "remote" in text:
                    work_mode = "remote"
                elif "hybrid" in text:
                    work_mode = "hybrid"
                else:
                    work_mode = "onsite"
                remote = "remote" in text  # legacy bool
                yield Job(
                    id=f"lever:{company.org}:{job_id}",
                    title=title,
                    company=company.name or company.org or "unknown",
                    url=url,
                    location=location,
                    remote=remote,
                    created_at=dt,
                    provider=self.name,
                    extra={"description": desc, "work_mode": work_mode},
                )
