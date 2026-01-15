# file: jobfinder/api.py
from __future__ import annotations

import argparse
import inspect
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, Flask, jsonify, render_template, request

# CORS optional (safe if not installed)
try:
    from flask_cors import CORS
except Exception:

    def CORS(*args, **kwargs):  # no-op
        return None


from . import db, filtering, pipeline
from .alerts.companies import load_companies
from .config import load_config
from .logging_utils import setup_logging

api = Blueprint("api", __name__)
log = logging.getLogger(__name__)
_STARTUP_REFRESH_DONE = False
_STARTUP_REFRESH_LOCK = threading.Lock()


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


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _run_startup_refresh(*, cities: List[str], keywords: List[str]) -> None:
    try:
        companies = load_companies()
    except Exception as exc:
        log.warning("Auto refresh skipped: %s", exc)
        return

    if not companies:
        log.info("Auto refresh skipped: no companies found")
        return

    log.info("Auto refresh starting | companies=%d", len(companies))
    summary = pipeline.refresh(
        companies=companies, cities=cities or None, keywords=keywords or None
    )
    log.info("Auto refresh finished | summary=%s", summary)


def _maybe_startup_refresh(*, cities: List[str], keywords: List[str]) -> None:
    global _STARTUP_REFRESH_DONE
    if not _env_bool("AUTO_REFRESH_ON_START", True):
        return

    with _STARTUP_REFRESH_LOCK:
        if _STARTUP_REFRESH_DONE:
            return
        _STARTUP_REFRESH_DONE = True

    if _env_bool("AUTO_REFRESH_ASYNC", True):
        t = threading.Thread(
            target=_run_startup_refresh,
            kwargs={"cities": cities, "keywords": keywords},
            name="jobfinder-startup-refresh",
            daemon=True,
        )
        t.start()
    else:
        _run_startup_refresh(cities=cities, keywords=keywords)


@api.route("/discover", methods=["POST"])
def discover() -> Any:
    body: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
    cities = _parse_list(body.get("cities"))
    keywords = _parse_list(body.get("keywords"))
    sources = _parse_list(body.get("sources"))
    limit = int(body.get("limit") or 50)

    log.info(
        "API /discover called | cities=%s | keywords=%s | sources=%s | limit=%s",
        cities,
        keywords,
        sources,
        limit,
    )

    # If you have a pipeline.discover, use it; else just echo back companies via UI discover flow.
    discover_fn = getattr(pipeline, "discover", None)
    if callable(discover_fn):
        try:
            companies = discover_fn(
                cities=cities, keywords=keywords, sources=sources or None, limit=limit
            )
            safe_companies = companies or []
            log.info(
                "API /discover result count=%d | companies=%s",
                len(safe_companies),
                json.dumps(safe_companies),
            )
            return jsonify({"companies": companies})
        except Exception as e:
            log.exception("API /discover failed: %s", e)
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "discover() not implemented in pipeline"}), 501


def _refresh_with_report(
    *,
    companies: List[Dict[str, Any]],
    cities: List[str],
    keywords: List[str],
    provider: Optional[str],
    top: Optional[Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    companies = companies or []
    limit: Optional[int] = None
    if top is not None and str(top).strip():
        try:
            limit = max(1, int(top))
        except (TypeError, ValueError):
            limit = None

    def _supports_limit(fetch_fn) -> bool:
        try:
            sig = inspect.signature(fetch_fn)
        except (TypeError, ValueError):
            return False
        if "limit" in sig.parameters:
            return True
        return any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )

    def _fetch_jobs_with_error(
        fetch_fn,
        org: str,
        company: Dict[str, Any],
        *,
        limit_val: Optional[int],
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        attempts: List[Dict[str, Any]] = []
        if company:
            attempts.append({"org": org, "company": company})
            careers_url = (company.get("careers_url") or "").strip()
            if careers_url:
                attempts.append({"org": org, "careers_url": careers_url})
        attempts.extend(({"org": org}, {"slug": org}, {"company": org}, {}))

        limit_ok = limit_val if (limit_val and _supports_limit(fetch_fn)) else None
        last_exc: Optional[BaseException] = None
        for kwargs in attempts:
            try:
                call_kwargs = dict(kwargs)
                if limit_ok is not None:
                    call_kwargs["limit"] = limit_ok
                if call_kwargs:
                    return list(fetch_fn(**call_kwargs)), None
                return list(fetch_fn(org)), None
            except TypeError:
                continue
            except Exception as exc:
                last_exc = exc
                break
        if last_exc:
            return [], str(last_exc)
        return [], "no_compatible_signature"

    def _write_company_jobs(
        *,
        company_payload: Dict[str, Any],
        jobs: List[Dict[str, Any]],
        seen_at: datetime,
        keywords_list: List[str],
        cities_list: List[str],
    ) -> int:
        with db.session_scope() as session:
            company_row = db.upsert_company(session, company_payload)
            seen_keys: List[str] = []
            written = 0
            for job in jobs:
                row = db.upsert_job(
                    session,
                    company=company_row,
                    job_dict=job,
                    seen_at=seen_at,
                    keywords=keywords_list,
                    cities=cities_list,
                )
                seen_keys.append(row.job_key)
                written += 1
            db.mark_inactive(
                session,
                provider=company_row.provider,
                org=company_row.org,
                seen_keys=seen_keys,
                seen_at=seen_at,
            )
        return written

    db.init_db()
    cities_list = pipeline._expand_city_aliases(pipeline._as_str_list(cities))
    keywords_list = pipeline._as_str_list(keywords)
    prov_filter = (str(provider).strip().lower()) if provider else None
    t0 = time.perf_counter()

    report_by_index: List[Optional[Dict[str, Any]]] = [None] * len(companies)
    companies_ok = 0
    companies_failed = 0
    jobs_fetched_total = 0
    jobs_written_total = 0

    def _fetch_company(idx: int, company: Dict[str, Any]) -> Dict[str, Any]:
        t1 = time.perf_counter()
        name = (company.get("name") or "").strip()
        provider_val = (company.get("provider") or "").strip().lower()
        org = (
            company.get("org")
            or company.get("slug")
            or company.get("company")
            or company.get("name")
            or ""
        )
        org = str(org).strip()

        result: Dict[str, Any] = {
            "index": idx,
            "name": name or org or "unknown",
            "provider": provider_val or None,
            "org": org or None,
            "status": "error",
            "error": None,
            "jobs": [],
            "jobs_fetched": 0,
            "company_payload": None,
            "elapsed_fetch_ms": 0,
            "skip_write": False,
        }
        try:
            if not provider_val or not org:
                raise ValueError("Company requires provider and org")

            company_payload = {**company, "provider": provider_val, "org": org}
            result["company_payload"] = company_payload
            if prov_filter and provider_val != prov_filter:
                result["skip_write"] = True
                result["status"] = "ok"
                return result

            mod = pipeline._import_provider(provider_val)
            if mod is None:
                raise RuntimeError(f"Provider '{provider_val}' not found")
            fetch_fn = getattr(mod, "fetch_jobs", None)
            if not callable(fetch_fn):
                raise RuntimeError(f"Provider '{provider_val}' has no fetch_jobs()")

            raw_jobs, fetch_error = _fetch_jobs_with_error(
                fetch_fn, org, company_payload, limit_val=limit
            )
            if fetch_error:
                raise RuntimeError(fetch_error)

            jobs = [
                pipeline._normalize_job(company_payload, provider_val, rj)
                for rj in raw_jobs
            ]
            for job in jobs:
                score_val, reasons = pipeline._compute_score(
                    job, keywords_list, cities_list
                )
                job["score"] = score_val
                if reasons:
                    job["reasons"] = reasons

            result["jobs_fetched"] = len(raw_jobs)
            result["jobs"] = pipeline._dedupe(jobs)
            result["status"] = "ok"
        except Exception as exc:
            result["error"] = str(exc)
        finally:
            result["elapsed_fetch_ms"] = int((time.perf_counter() - t1) * 1000)
        return result

    fetch_results: List[Dict[str, Any]] = []
    if companies:
        max_workers = min(8, len(companies))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                pool.submit(_fetch_company, idx, c) for idx, c in enumerate(companies)
            ]
            for future in as_completed(futures):
                fetch_results.append(future.result())

    for res in fetch_results:
        idx = int(res.get("index") or 0)
        item = {
            "name": res.get("name") or "unknown",
            "provider": res.get("provider"),
            "org": res.get("org"),
            "status": res.get("status") or "error",
            "jobs_fetched": int(res.get("jobs_fetched") or 0),
            "jobs_written": 0,
            "elapsed_ms": int(res.get("elapsed_fetch_ms") or 0),
        }

        if item["status"] != "ok":
            companies_failed += 1
            err_val = res.get("error")
            if err_val:
                item["error"] = str(err_val)
            report_by_index[idx] = item
            continue

        if res.get("skip_write"):
            item["status"] = "ok"
            companies_ok += 1
            report_by_index[idx] = item
            continue

        jobs_fetched_total += item["jobs_fetched"]
        company_payload = res.get("company_payload")
        if not isinstance(company_payload, dict):
            companies_failed += 1
            item["status"] = "error"
            item["error"] = "Missing company payload"
            report_by_index[idx] = item
            continue

        t_write = time.perf_counter()
        try:
            seen_at = datetime.now(timezone.utc)
            written = _write_company_jobs(
                company_payload=company_payload,
                jobs=res.get("jobs") or [],
                seen_at=seen_at,
                keywords_list=keywords_list,
                cities_list=cities_list,
            )
            item["jobs_written"] = written
            jobs_written_total += written
            item["status"] = "ok"
            companies_ok += 1
        except Exception as exc:
            companies_failed += 1
            item["status"] = "error"
            item["error"] = str(exc)
        item["elapsed_ms"] = item["elapsed_ms"] + int(
            (time.perf_counter() - t_write) * 1000
        )
        report_by_index[idx] = item

    report = [r for r in report_by_index if r is not None]

    summary = {
        "companies_total": len(companies),
        "companies_ok": companies_ok,
        "companies_failed": companies_failed,
        "jobs_fetched": jobs_fetched_total,
        "jobs_written": jobs_written_total,
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
    }
    return summary, report


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
        summary = pipeline.refresh(
            companies=companies, cities=cities, keywords=keywords, provider=provider
        )
    except Exception as e:
        log.exception("API /refresh failed: %s", e)
        return jsonify({"error": str(e)}), 500

    log.info("API /refresh summary=%s", summary)
    return jsonify({"summary": summary})


@api.route("/debug/refresh", methods=["POST"])
def debug_refresh() -> Any:
    body: Dict[str, Any] = request.get_json(force=True, silent=True) or {}
    companies = body.get("companies") or []
    cities = _parse_list(body.get("cities"))
    keywords = _parse_list(body.get("keywords"))
    provider = body.get("provider") or None
    top_raw = body.get("top")

    log.info("API /debug/refresh called | companies=%d", len(companies or []))

    try:
        summary, report = _refresh_with_report(
            companies=companies,
            cities=cities,
            keywords=keywords,
            provider=provider,
            top=top_raw,
        )
    except Exception as e:
        log.exception("API /debug/refresh failed: %s", e)
        return jsonify({"error": str(e)}), 500

    log.info("API /debug/refresh summary=%s", summary)
    return jsonify({"summary": summary, "companies": report})


@api.route("/jobs", methods=["GET"])
def jobs() -> Any:
    args = request.args
    provider = args.get("provider") or None
    remote = args.get("remote") or "any"
    min_score = int(args.get("min_score") or 0)
    max_age_days_raw = args.get("max_age_days")
    max_age_days = (
        int(max_age_days_raw)
        if max_age_days_raw is not None and max_age_days_raw != ""
        else None
    )
    cities = _parse_list(args.getlist("cities") or args.get("cities"))
    keywords = _parse_list(args.getlist("keywords") or args.get("keywords"))
    title_keywords = _parse_list(
        args.getlist("title_keywords") or args.get("title") or args.get("fltTitle")
    )
    orgs = _parse_list(
        args.getlist("orgs") or args.get("orgs") or args.get("companies")
    )
    company_names = _parse_list(
        args.getlist("company_names") or args.get("company_names")
    )
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

    preview = [
        {"company": r.get("company"), "title": r.get("title"), "id": r.get("id")}
        for r in (results or [])[:10]
    ]
    log.info(
        "API /jobs result count=%d | preview=%s",
        len(results or []),
        json.dumps(preview),
    )
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
    title_keywords = _parse_list(
        body.get("title_keywords") or body.get("title") or body.get("fltTitle")
    )

    log.info(
        "API /scan called | provider=%s | cities=%s | companies=%d | remote=%s | keywords=%s | title_keywords=%s",
        provider,
        cities,
        len(companies or []),
        remote,
        keywords,
        title_keywords,
    )

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
    preview = [
        {"company": r.get("company"), "title": r.get("title"), "id": r.get("id")}
        for r in safe_results[:10]
    ]
    log.info(
        "API /scan result count=%d | jobs_preview=%s",
        len(safe_results),
        json.dumps(preview),
    )

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
    auto_refresh_on_start = _env_bool("AUTO_REFRESH_ON_START", True)
    cfg = load_config()
    try:
        db.init_db()
    except Exception as e:
        log.warning("DB init skipped (non-fatal): %s", e)
    _maybe_startup_refresh(cities=cfg.defaults.cities, keywords=cfg.defaults.keywords)

    @app.get("/")
    def index() -> str:
        return render_template(
            "index.html",
            auto_refresh_on_start=auto_refresh_on_start,
            show_refresh_report=False,
        )

    @app.get("/debug/refresh-report")
    def debug_refresh_report() -> str:
        return render_template(
            "index.html",
            auto_refresh_on_start=auto_refresh_on_start,
            show_refresh_report=True,
        )

    @app.get("/search")
    def search() -> str:
        return render_template("search.html")

    @app.get("/healthz")
    def healthz() -> Any:
        return jsonify({"ok": True})

    return app


app = create_app()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="jobfinder-api", description="Run jobfinder Flask API"
    )
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.getenv("DEBUG", "").lower() in {"1", "true", "yes"},
    )
    args = parser.parse_args(argv)
    application = create_app()
    application.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
