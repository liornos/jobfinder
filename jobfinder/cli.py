# file: jobfinder/cli.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, List
import typer

from . import filtering, pipeline
from .alerts.companies import load_companies
from .config import load_config
from .logging_utils import setup_logging

app = typer.Typer(add_completion=False, help="Find new jobs via public ATS endpoints")


def _csv_list(val: Optional[str]) -> List[str]:
    if not val:
        return []
    return [s.strip() for s in val.split(",") if s.strip()]


@app.command("scan")
def scan(
    companies_json: str = typer.Option(
        ..., help="JSON array of companies from discover"
    ),
    cities: Optional[str] = typer.Option(None, help="Comma list of cities"),
    keywords: Optional[str] = typer.Option(None, help="Comma list of content keywords"),
    provider: Optional[str] = typer.Option(None, help="Restrict to provider"),
    remote: str = typer.Option("any", help="any|true|false|hybrid"),
    min_score: int = typer.Option(0, help="Minimum score"),
    max_age_days: Optional[int] = typer.Option(None, help="Max age in days"),
    geo_radius_km: Optional[float] = typer.Option(None, help="Geofence radius in km"),
    title_contains: Optional[str] = typer.Option(
        None, help='Title contains (comma). e.g. "automation, software"'
    ),
):
    setup_logging()
    companies = json.loads(companies_json)
    city_list = _csv_list(cities)
    keyword_list = _csv_list(keywords)
    title_list = _csv_list(title_contains)

    geo = {"cities": city_list, "radius_km": geo_radius_km} if geo_radius_km else None

    results = pipeline.scan(
        companies=companies,
        cities=city_list,
        keywords=keyword_list,
        provider=provider,
        remote=remote,
        min_score=min_score,
        max_age_days=max_age_days,
        geo=geo,
    )
    if title_list:
        results = filtering.filter_by_title_keywords(results, title_list)

    typer.echo(json.dumps({"results": results}, ensure_ascii=False))


@app.command("refresh")
def refresh(
    companies_path: Optional[str] = typer.Option(
        None,
        "--companies-path",
        help="Path to companies.json (defaults to static/companies.json)",
    ),
    cities: Optional[str] = typer.Option(None, help="Comma list of cities"),
    keywords: Optional[str] = typer.Option(None, help="Comma list of keywords"),
    provider: Optional[str] = typer.Option(None, help="Restrict to provider"),
    db_url: Optional[str] = typer.Option(None, help="Override database URL"),
):
    setup_logging()
    cfg = load_config()
    companies = load_companies(Path(companies_path) if companies_path else None)
    city_list = _csv_list(cities) or cfg.defaults.cities
    keyword_list = _csv_list(keywords) or cfg.defaults.keywords

    summary = pipeline.refresh(
        companies=companies,
        cities=city_list,
        keywords=keyword_list,
        provider=provider,
        db_url=db_url,
    )
    typer.echo(json.dumps({"summary": summary}, ensure_ascii=False))


# NEW: provider diagnostics from CLI
@app.command("debug-providers")
def debug_providers():
    """
    Print provider import diagnostics (module paths, errors, sys.path head, cwd).
    """
    setup_logging("DEBUG")
    import json as _json

    report = pipeline.diagnose_providers()
    typer.echo(_json.dumps(report, indent=2))
