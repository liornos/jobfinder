# file: jobfinder/api.py
from __future__ import annotations
import argparse, json, logging, os
from typing import Any, Dict, List

from flask import Blueprint, Flask, jsonify, render_template, request

# CORS optional (safe if not installed)
try:
    from flask_cors import CORS
except Exception:
    def CORS(*args, **kwargs):  # no-op
        return None

from . import db, filtering, pipeline
from .logging_utils import setup_logging

api = Blueprint("api", __name__)
log = logging.getLogger(__name__)

def _parse_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items: List[str] = []
        for x in value:
            for part in str(x).split(","):
                part = part.strip()
                if part:
                    items.append(part)
        return items
    return [s.strip() for s in str(value).split(",") if s.strip()]

@api.route("/discover", methods=["POST"])
def discover() -> Any:
    body: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
    cities = _parse_list(body.get("cities"))
    keywords = _parse_list(body.get("keywords"))
    sources = _parse_list(body.get("sources"))
    limit = int(body.get("limit") or 50)

    log.info("API /discover called | cities=%s | keywords=%s | sources=%s | limit=%s",
             cities, keywords, sources, limit)

    # If you have a pipeline.discover, use it; else just echo back companies via UI discover flow.
    discover_fn = getattr(pipeline, "discover", None)
    if callable(discover_fn):
        try:
            companies = discover_fn(cities=cities, keywords=keywords, sources=sources or None, limit=limit)
            safe_companies = companies or []
            log.info("API /discover result count=%d | companies=%s",
                     len(safe_companies), json.dumps(safe_companies))
            return jsonify({"companies": companies})
        except Exception as e:
            log.exception("API /discover failed: %s", e)
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "discover() not implemented in pipeline"}), 501

@api.route("/refresh", methods=["POST"])
def refresh() -> Any:
    body: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
    companies = body.get("companies") or []
    cities = _parse_list(body.get("cities"))
    keywords = _parse_list(body.get("keywords"))
    provider = body.get("provider") or None

    log.info(
        "API /refresh called | companies=%d | provider=%s | cities=%s | keywords=%s",
        len(companies or []),
        provider,
        cities,
        keywords,
    )

    try:
        summary = pipeline.refresh(companies=companies, cities=cities, keywords=keywords, provider=provider)
    except Exception as e:
        log.exception("API /refresh failed: %s", e)
        return jsonify({"error": str(e)}), 500

    log.info("API /refresh summary=%s", summary)
    return jsonify({"summary": summary})

@api.route("/jobs", methods=["GET"])
def jobs() -> Any:
    args = request.args
    provider = args.get("provider") or None
    remote = args.get("remote") or "any"
    min_score = int(args.get("min_score") or 0)
    max_age_days_raw = args.get("max_age_days")
    max_age_days = int(max_age_days_raw) if max_age_days_raw is not None and max_age_days_raw != "" else None
    cities = _parse_list(args.getlist("cities") or args.get("cities"))
    keywords = _parse_list(args.getlist("keywords") or args.get("keywords"))
    title_keywords = _parse_list(args.getlist("title_keywords") or args.get("title") or args.get("fltTitle"))
    orgs = _parse_list(args.getlist("orgs") or args.get("orgs") or args.get("companies"))
    company_names = _parse_list(args.getlist("company_names") or args.get("company_names"))
    only_active = str(args.get("active") or "true").lower() not in {"0", "false", "no"}
    limit_raw = int(args.get("limit") or 500)
    limit = max(1, min(limit_raw, 2000))
    offset = int(args.get("offset") or 0)

    log.info(
        "API /jobs called | provider=%s | remote=%s | min_score=%s | max_age_days=%s | cities=%s | keywords=%s | title_keywords=%s | orgs=%s | company_names=%s | active=%s | limit=%s offset=%s",
        provider,
        remote,
        min_score,
        max_age_days,
        cities,
        keywords,
        title_keywords,
        orgs,
        company_names,
        only_active,
        limit,
        offset,
    )

    try:
        results = pipeline.query_jobs(
            provider=provider,
            remote=remote,
            min_score=min_score,
            max_age_days=max_age_days,
            cities=cities,
            keywords=keywords,
            title_keywords=title_keywords,
            orgs=orgs,
            company_names=company_names,
            only_active=only_active,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        log.exception("API /jobs failed: %s", e)
        return jsonify({"error": str(e)}), 500

    preview = [{"company": r.get("company"), "title": r.get("title"), "id": r.get("id")} for r in (results or [])[:10]]
    log.info("API /jobs result count=%d | preview=%s", len(results or []), json.dumps(preview))
    return jsonify({"results": results, "count": len(results or [])})

@api.route("/scan", methods=["POST"])
def scan() -> Any:
    body: Dict[str, Any] = request.get_json(force=True, silent=True) or {}

    companies = body.get("companies") or []
    cities = _parse_list(body.get("cities"))
    keywords = _parse_list(body.get("keywords"))
    provider = body.get("provider") or None
    remote = body.get("remote") or "any"
    min_score = body.get("min_score") or 0
    max_age_days = body.get("max_age_days")
    geo = body.get("geo")
    title_keywords = _parse_list(body.get("title_keywords") or body.get("title") or body.get("fltTitle"))

    log.info("API /scan called | provider=%s | cities=%s | companies=%d | remote=%s | keywords=%s | title_keywords=%s",
             provider, cities, len(companies or []), remote, keywords, title_keywords)

    try:
        results: List[Dict[str, Any]] = pipeline.scan(
            companies=companies,
            cities=cities,
            keywords=keywords,
            provider=provider,
            remote=remote,
            min_score=min_score,
            max_age_days=max_age_days,
            geo=geo,
        )
    except Exception as e:
        log.exception("API /scan failed: %s", e)
        return jsonify({"error": str(e)}), 500

    if title_keywords:
        results = filtering.filter_by_title_keywords(results, title_keywords)

    safe_results = results or []
    preview = [{"company": r.get("company"), "title": r.get("title"), "id": r.get("id")} for r in safe_results[:10]]
    log.info("API /scan result count=%d | jobs_preview=%s", len(safe_results), json.dumps(preview))

    return jsonify({"results": results})

# NEW: provider diagnostics endpoint
@api.route("/debug/providers", methods=["GET"])
def debug_providers() -> Any:
    return jsonify(pipeline.diagnose_providers())

def create_app() -> Flask:
    setup_logging()  # respect LOG_LEVEL
    app = Flask(__name__, static_folder="static", template_folder="templates")
    CORS(app)
    app.register_blueprint(api)
    try:
        db.init_db()
    except Exception as e:
        log.warning("DB init skipped (non-fatal): %s", e)

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/healthz")
    def healthz() -> Any:
        return jsonify({"ok": True})
    return app

app = create_app()

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jobfinder-api", description="Run jobfinder Flask API")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--debug", action="store_true", default=os.getenv("DEBUG", "").lower() in {"1","true","yes"})
    args = parser.parse_args(argv)
    application = create_app()
    application.run(host=args.host, port=args.port, debug=args.debug)

if __name__ == "__main__":
    main()
