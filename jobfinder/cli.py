# file: jobfinder/cli.py
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

import yaml
from dotenv import load_dotenv

from jobfinder import filtering, pipeline
from jobfinder.alerts.companies import load_companies
from jobfinder.alerts.saved_search_worker import run_due_alerts_once, run_forever


def _csv_list(val: Optional[str]) -> List[str]:
    if not val:
        return []
    return [s.strip() for s in val.split(",") if s.strip()]


def _setup_logging(level_name: str | None = None) -> None:
    level = getattr(
        logging, (level_name or os.getenv("LOG_LEVEL") or "INFO").upper(), logging.INFO
    )
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _load_defaults(config_path: Optional[str] = None) -> tuple[List[str], List[str]]:
    load_dotenv()
    cfg_path = Path(config_path) if config_path else (Path.cwd() / "config.yaml")
    data: dict = {}
    if cfg_path.exists():
        try:
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
    defaults = data.get("defaults", {}) if isinstance(data, dict) else {}
    cities_raw = defaults.get("cities") if isinstance(defaults, dict) else None
    keywords_raw = defaults.get("keywords") if isinstance(defaults, dict) else None

    cities = [str(c).strip() for c in (cities_raw or []) if str(c).strip()]
    keywords = [str(k).strip() for k in (keywords_raw or []) if str(k).strip()]

    if not cities:
        cities = ["Tel Aviv", "herzliya"]
    if not keywords:
        keywords = ["software"]
    return cities, keywords


def _run_scan(args: argparse.Namespace) -> int:
    companies = json.loads(args.companies_json)
    city_list = _csv_list(args.cities)
    keyword_list = _csv_list(args.keywords)
    title_list = _csv_list(args.title_contains)

    geo = (
        {"cities": city_list, "radius_km": args.geo_radius_km}
        if args.geo_radius_km
        else None
    )

    results = pipeline.scan(
        companies=companies,
        cities=city_list,
        keywords=keyword_list,
        provider=args.provider,
        remote=args.remote,
        min_score=args.min_score,
        max_age_days=args.max_age_days,
        geo=geo,
    )

    if title_list and hasattr(filtering, "filter_by_title_keywords"):
        try:
            results = filtering.filter_by_title_keywords(results, title_list)
        except Exception:
            pass

    print(json.dumps({"results": results}, ensure_ascii=False))
    return 0


def _run_refresh(args: argparse.Namespace) -> int:
    companies = load_companies(
        Path(args.companies_path) if args.companies_path else None
    )
    default_cities, default_keywords = _load_defaults(args.config)
    city_list = _csv_list(args.cities) or default_cities
    keyword_list = _csv_list(args.keywords) or default_keywords

    summary = pipeline.refresh(
        companies=companies,
        cities=city_list,
        keywords=keyword_list,
        provider=args.provider,
        db_url=args.db_url,
    )
    print(json.dumps({"summary": summary}, ensure_ascii=False))
    return 0


def _run_debug_providers() -> int:
    report = pipeline.diagnose_providers()
    print(json.dumps(report, indent=2))
    return 0


def _run_alerts_once(args: argparse.Namespace) -> int:
    summary = run_due_alerts_once(batch_limit=int(args.batch_limit or 200))
    print(json.dumps({"summary": summary}, ensure_ascii=False))
    return 0


def _run_alerts_worker(args: argparse.Namespace) -> int:
    run_forever(
        interval_seconds=int(args.interval_seconds or 900),
        batch_limit=int(args.batch_limit or 200),
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobfinder",
        description="Jobfinder CLI helpers (refresh/scan/debug-providers)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="Scan companies without DB persistence")
    scan_p.add_argument(
        "--companies-json", required=True, help="JSON array of companies"
    )
    scan_p.add_argument("--cities", help="Comma list of cities")
    scan_p.add_argument("--keywords", help="Comma list of content keywords")
    scan_p.add_argument("--provider", help="Restrict to provider")
    scan_p.add_argument("--remote", default="any", help="any|true|false|hybrid")
    scan_p.add_argument("--min-score", type=int, default=0, help="Minimum score")
    scan_p.add_argument("--max-age-days", type=int, help="Max age in days")
    scan_p.add_argument("--geo-radius-km", type=float, help="Geofence radius in km")
    scan_p.add_argument("--title-contains", help="Title contains (comma list)")

    refresh_p = sub.add_parser("refresh", help="Fetch jobs and persist to DB")
    refresh_p.add_argument(
        "--companies-path",
        help="Path to companies.json (defaults to static/companies.json)",
    )
    refresh_p.add_argument("--cities", help="Comma list of cities")
    refresh_p.add_argument("--keywords", help="Comma list of keywords")
    refresh_p.add_argument("--provider", help="Restrict to provider")
    refresh_p.add_argument("--db-url", help="Override database URL")
    refresh_p.add_argument(
        "--config",
        help="Path to config.yaml (defaults to ./config.yaml if present)",
    )

    sub.add_parser("debug-providers", help="Print provider import diagnostics")

    alerts_once_p = sub.add_parser(
        "alerts-run-once", help="Run due saved-search alerts one time"
    )
    alerts_once_p.add_argument(
        "--batch-limit", type=int, default=200, help="Max alerts to process"
    )

    alerts_worker_p = sub.add_parser(
        "alerts-worker", help="Run saved-search alert worker loop"
    )
    alerts_worker_p.add_argument(
        "--interval-seconds",
        type=int,
        default=900,
        help="Worker poll interval in seconds",
    )
    alerts_worker_p.add_argument(
        "--batch-limit", type=int, default=200, help="Max alerts to process per loop"
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _setup_logging()
    try:
        if args.command == "scan":
            return _run_scan(args)
        if args.command == "refresh":
            return _run_refresh(args)
        if args.command == "debug-providers":
            return _run_debug_providers()
        if args.command == "alerts-run-once":
            return _run_alerts_once(args)
        if args.command == "alerts-worker":
            return _run_alerts_worker(args)
    except Exception as exc:
        logging.exception("jobfinder %s failed: %s", args.command, exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
