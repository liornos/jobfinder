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

from . import filtering, pipeline
from .logging_utils import setup_logging

api = Blueprint("api", __name__)
log = logging.getLogger(__name__)

def _parse_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
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
