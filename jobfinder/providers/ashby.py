from __future__ import annotations
from datetime import datetime
from typing import AsyncIterator
import httpx, re
from ..models import Job, Company
class AshbyProvider:
    name = "ashby"
    API = "https://jobs.ashbyhq.com/api/postings/{org}?limit=100&offset=0"
    async def jobs(self, company: Company) -> AsyncIterator[Job]:
        if not company.org: return
        url = self.API.format(org=company.org)
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(url); r.raise_for_status()
            data = r.json() or {}
            postings = data.get("jobs") or data.get("postings") or data.get("data") or []
            for j in postings:
                job_id = str(j.get("id") or j.get("_id") or j.get("slug") or j.get("jobId") or "")
                title = j.get("title") or j.get("jobTitle") or ""
                location = j.get("locationName") or j.get("location") or (j.get("jobLocation") or {}).get("name")
                url = j.get("jobUrl") or j.get("applyUrl") or j.get("url") or ""
                remote = False
                for fld in (title, location, str(j)):
                    if fld and re.search(r"\bremote|hybrid\b", str(fld), re.I):
                        remote = True; break
                created_at = j.get("createdAt") or j.get("updatedAt")
                dt = None
                if created_at:
                    try:
                        if isinstance(created_at, str):
                            dt = datetime.fromisoformat(created_at.replace("Z","+00:00"))
                        else:
                            dt = datetime.utcfromtimestamp(int(created_at)/1000.0)
                    except Exception:
                        dt = None
                desc = j.get("descriptionHtml") or j.get("description") or j.get("sectionsText") or ""
                yield Job(id=f"ashby:{company.org}:{job_id}", title=title, company=company.name or company.org or "unknown",
                          url=url, location=location, remote=remote, created_at=dt, provider=self.name,
                          extra={"description": desc})
