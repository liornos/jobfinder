from __future__ import annotations
import asyncio, csv
from typing import List, Optional
import typer
from rich import print
from rich.table import Table
from .config import load_config
from .models import Company, Job
from .pipeline import fetch_jobs_for_companies, filter_and_rank
from .storage import export_csv, init_sqlite, upsert_jobs_sqlite
from .search import discover_companies

app = typer.Typer(add_completion=False, help="Find new jobs via public ATS endpoints")

def _load_companies_csv(path: str) -> List[Company]:
    items: List[Company] = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            items.append(Company(name=row.get("name") or row.get("company") or "", city=row.get("city") or None,
                                 provider=row.get("provider") or None, org=row.get("org") or None,
                                 careers_url=row.get("careers_url") or None))
    return items

@app.command()
def discover(cities: str="", keywords: str="", sources: str="greenhouse,lever", limit: int=50,
             out: Optional[str]=None, config: Optional[str]=None):
    cfg = load_config(config)
    cs=[c.strip() for c in (cities or ",".join(cfg.defaults.cities)).split(",") if c.strip()]
    ks=[k.strip() for k in (keywords or ",".join(cfg.defaults.keywords)).split(",") if k.strip()]
    srcs=[s.strip().lower() for s in sources.split(",") if s.strip()]
    async def _run():
        res = await discover_companies(cs, ks, srcs, limit=limit, api_key=cfg.env.get("SERPAPI_API_KEY"))
        rows=[c.to_dict() for c in res.companies]
        if out:
            export_csv(rows, out); print(f"[green]Wrote {len(rows)} companies to {out}[/]")
        else:
            table = Table(title="Discovered Companies"); table.add_column("name"); table.add_column("provider"); table.add_column("org")
            for r in rows: table.add_row(r["name"], r.get("provider") or "", r.get("org") or ""); print(table)
    asyncio.run(_run())

@app.command()
def scan(companies_file: str, cities: str="", keywords: str="", out: Optional[str]=None,
         save_sqlite: Optional[str]=None, top: int=0, config: Optional[str]=None):
    cfg=load_config(config)
    cs=[c.strip() for c in (cities or ",".join(cfg.defaults.cities)).split(",") if c.strip()]
    ks=[k.strip() for k in (keywords or ",".join(cfg.defaults.keywords)).split(",") if k.strip()]
    comps=_load_companies_csv(companies_file)
    async def _run():
        jobs=await fetch_jobs_for_companies(comps)
        rows=filter_and_rank(jobs, cities=cs, keywords=ks)
        if top and top>0: rows[:]=rows[:top]
        if out or cfg.output.csv:
            dst=out or cfg.output.csv; assert dst is not None
            export_csv(rows, dst); print(f"[green]Wrote {len(rows)} rows to {dst}[/]")
        if save_sqlite or cfg.output.sqlite:
            dbp=save_sqlite or cfg.output.sqlite; assert dbp is not None
            conn=init_sqlite(dbp)
            from datetime import datetime
            _jobs: List[Job]=[]
            for r in rows:
                dt=None
                if r.get("created_at"):
                    try: dt=datetime.fromisoformat(str(r["created_at"]))
                    except Exception: dt=None
                _jobs.append(Job(id=str(r["id"]), title=str(r["title"]), company=str(r["company"]),
                                 url=str(r["url"]), location=r.get("location"),
                                 remote=bool(r.get("remote")) if r.get("remote") is not None else None,
                                 created_at=dt, provider=r.get("provider"), extra=r.get("extra")))
            upsert_jobs_sqlite(conn, _jobs)
    asyncio.run(_run())

if __name__ == "__main__": app()
