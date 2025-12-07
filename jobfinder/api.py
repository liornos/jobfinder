from __future__ import annotations
import asyncio, csv, io, os
from typing import Any, Dict, List, Optional
from flask import Flask, jsonify, request
from . import __version__
from .config import load_config
from .models import Company
from .pipeline import fetch_jobs_for_companies, filter_and_rank, enrich_jobs_with_geo
from .search import discover_companies
from .web import web_bp

def _companies_from_csv_text(csv_text: str) -> List[Company]:
    buf = io.StringIO(csv_text); reader = csv.DictReader(buf); items: List[Company] = []
    for row in reader:
        items.append(Company(name=(row.get("name") or row.get("company") or "").strip(),
                             city=(row.get("city") or None), provider=(row.get("provider") or None),
                             org=(row.get("org") or None), careers_url=(row.get("careers_url") or None)))
    return items

def _companies_from_json(objs: List[Dict[str, Any]]) -> List[Company]:
    items: List[Company] = []
    for r in objs:
        items.append(Company(name=str(r.get("name") or r.get("company") or "").strip(),
                             city=r.get("city"), provider=r.get("provider"), org=r.get("org"),
                             careers_url=r.get("careers_url")))
    return items

def _dedupe_companies(items: List[Company]) -> List[Company]:
    seen: set[tuple[str, str]] = set(); out: List[Company] = []
    for c in items:
        key = (str(c.provider or ""), str(c.org or ""))
        if key in seen: continue
        seen.add(key); out.append(c)
    return out

def create_app(config_path: Optional[str] = None) -> Flask:
    app = Flask(__name__)
    app.register_blueprint(web_bp)
    cfg = load_config(config_path)

    @app.get("/health")
    def health() -> Any:
        return jsonify({"status": "ok", "version": __version__})

    @app.post("/discover")
    def api_discover() -> Any:
        data = request.get_json(silent=True) or {}
        cities = data.get("cities") or cfg.defaults.cities or []
        keywords = data.get("keywords") or cfg.defaults.keywords or []
        sources = data.get("sources") or cfg.discovery.sources or ["greenhouse", "lever"]
        limit = int(data.get("limit") or cfg.discovery.limit or 50)
        api_key = cfg.env.get("SERPAPI_API_KEY")
        if not api_key:
            return jsonify({"error": "SERPAPI_API_KEY missing in environment"}), 400
        async def _run():
            res = await discover_companies(cities=list(map(str, cities)),
                                           keywords=list(map(str, keywords)),
                                           sources=[str(s).lower() for s in sources],
                                           limit=limit, api_key=api_key)
            return _dedupe_companies(res.companies)
        comps = asyncio.run(_run())
        return jsonify({"count": len(comps), "companies": [c.to_dict() for c in comps]})

    @app.post("/scan")
    def api_scan() -> Any:
        data = request.get_json(silent=True) or {}
        companies: List[Company] = []
        if "companies" in data and isinstance(data["companies"], list):
            companies = _dedupe_companies(_companies_from_json(data["companies"]))
        elif "companies_csv" in data and isinstance(data["companies_csv"], str):
            companies = _dedupe_companies(_companies_from_csv_text(data["companies_csv"]))
        else:
            return jsonify({"error": "Provide either `companies` (list) or `companies_csv` (CSV string).",
                            "expected_company_fields": ["name","city","provider","org","careers_url"]}), 400
        if not companies:
            return jsonify({"error": "No valid companies parsed"}), 400

        cities = data.get("cities") or cfg.defaults.cities or []
        keywords = data.get("keywords") or cfg.defaults.keywords or []
        geo = data.get("geo") or {}
        radius_km = float(geo.get("radius_km") or 0) or None
        geo_cities = list(map(str, (geo.get("cities") or cities))) if radius_km else []

        server_filters = {
            "provider": data.get("provider"),
            "remote": data.get("remote"),
            "min_score": data.get("min_score"),
            "max_age_days": data.get("max_age_days"),
        }

        async def _run():
            jobs = await fetch_jobs_for_companies(companies)
            centers = None
            if radius_km and geo_cities:
                jobs, centers = await enrich_jobs_with_geo(jobs, geo_cities)
            rows = await filter_and_rank(jobs, cities=list(map(str, cities)),
                                         keywords=list(map(str, keywords)),
                                         geo_centers=centers, radius_km=radius_km,
                                         server_filters=server_filters)
            top = int(data.get("top") or 0)
            if top and top > 0: rows[:] = rows[:top]
            return rows

        rows = asyncio.run(_run())
        return jsonify({"count": len(rows), "results": rows})
    return app

def main() -> None:
    host = os.getenv("HOST", "0.0.0.0"); port = int(os.getenv("PORT", "8000"))
    app = create_app(); app.run(host=host, port=port, debug=bool(os.getenv("DEBUG")))

if __name__ == "__main__": main()
