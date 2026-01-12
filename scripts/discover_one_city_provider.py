from __future__ import annotations

import argparse
import json
import os
import time
from urllib.parse import urlparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from jobfinder import pipeline
from jobfinder.logging_utils import setup_logging


def _sanitize_city(city: str) -> str:
    return (city or "").replace('"', "").strip()


def _parse_args() -> argparse.Namespace:
    providers = ", ".join(sorted(pipeline._PROVIDER_HOST.keys()))
    parser = argparse.ArgumentParser(
        description="Discover companies for one city and one provider via SerpAPI."
    )
    parser.add_argument("--city", required=True, help="Single city (exact string).")
    parser.add_argument(
        "--provider",
        required=True,
        help=f"Provider name. Options: {providers}",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max companies to keep (default: 50).",
    )
    parser.add_argument(
        "--out",
        default="jobfinder/static",
        help="Output directory or file path (default: jobfinder/static).",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="SerpAPI key (defaults to SERPAPI_API_KEY env var).",
    )
    parser.add_argument(
        "--origin",
        default="jobfinder/static/companies.json",
        help="Origin companies.json to update with verified companies.",
    )
    return parser.parse_args()


def _is_workable_job_link(url: str, org: str) -> bool:
    try:
        parts = [s for s in urlparse(url).path.split("/") if s]
    except Exception:
        return False
    if len(parts) < 3:
        return False
    return parts[0].lower() == org.lower() and parts[1].lower() == "j"


def _build_companies(
    data: Dict[str, Any], *, provider: str, city: str, limit: int
) -> Tuple[List[Dict[str, Any]], set[str]]:
    host = pipeline._PROVIDER_HOST[provider]
    companies: List[Dict[str, Any]] = []
    seen_orgs = set()
    job_link_orgs: set[str] = set()

    for item in data.get("organic_results") or []:
        link = item.get("link") or ""
        if not link or host not in link:
            continue
        org = pipeline._extract_org_from_url(provider, link)
        if org and provider == "workable" and _is_workable_job_link(link, org):
            job_link_orgs.add(org.lower())
        if not org or org in seen_orgs:
            continue
        seen_orgs.add(org)

        if provider == "comeet":
            careers_url = pipeline._normalize_comeet_careers_url(link) or link
        elif provider == "workday":
            careers_url = link
        else:
            careers_url = f"https://{host}/{org}"

        companies.append(
            {
                "name": org,
                "org": org,
                "provider": provider,
                "careers_url": careers_url,
                "city": city,
            }
        )
        if len(companies) >= limit:
            break

    return companies, job_link_orgs


def _slugify(value: str) -> str:
    out = []
    last_was_sep = False
    for ch in (value or "").strip().lower():
        if "a" <= ch <= "z" or "0" <= ch <= "9":
            out.append(ch)
            last_was_sep = False
            continue
        if not last_was_sep:
            out.append("_")
            last_was_sep = True
    slug = "".join(out).strip("_")
    return slug or "city"


def _company_key(company: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    provider = str(company.get("provider") or "").strip().lower()
    org = str(company.get("org") or company.get("name") or "").strip().lower()
    if not provider or not org:
        return None
    return provider, org


def _load_company_list(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(raw, dict):
        items = raw.get("companies")
    else:
        items = raw
    if not isinstance(items, list):
        return []
    return [c for c in items if isinstance(c, dict)]


def _update_origin_companies(verified: List[Dict[str, Any]], origin_path: Path) -> int:
    existing = _load_company_list(origin_path)
    existing_keys = set()
    for company in existing:
        key = _company_key(company)
        if key:
            existing_keys.add(key)
    added = 0
    for company in verified:
        key = _company_key(company)
        if not key or key in existing_keys:
            continue
        existing_keys.add(key)
        existing.append(company)
        added += 1
    if added:
        origin_path.parent.mkdir(parents=True, exist_ok=True)
        origin_path.write_text(
            json.dumps({"companies": existing}, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    return added


def _verify_companies_with_jobs(
    companies: List[Dict[str, Any]],
    provider: str,
    job_link_orgs: set[str] | None = None,
) -> List[Dict[str, Any]]:
    if not companies:
        return []
    mod = pipeline._import_provider(provider)
    fetch = getattr(mod, "fetch_jobs", None) if mod else None
    if not callable(fetch):
        raise SystemExit(f"Provider '{provider}' has no fetch_jobs function.")
    verified: List[Dict[str, Any]] = []
    for company in companies:
        org = str(company.get("org") or company.get("name") or "").strip()
        if not org:
            continue
        jobs = pipeline._call_fetch(fetch, org, company=company, provider=provider)
        if jobs:
            verified.append(company)
            continue
        if provider == "workable" and job_link_orgs and org.lower() in job_link_orgs:
            verified.append(company)
    return verified


def main() -> None:
    args = _parse_args()
    setup_logging()

    city = _sanitize_city(args.city)
    if not city:
        raise SystemExit("City is required.")

    provider = (args.provider or "").strip().lower()
    if provider not in pipeline._PROVIDER_HOST:
        options = ", ".join(sorted(pipeline._PROVIDER_HOST.keys()))
        raise SystemExit(f"Unknown provider '{provider}'. Options: {options}")

    api_key = (args.api_key or os.getenv("SERPAPI_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("SERPAPI_API_KEY missing. Set it or pass --api-key.")

    limit = max(1, int(args.limit or 1))
    num = max(10, min(100, limit))
    query = f'site:{pipeline._PROVIDER_HOST[provider]} "{city}"'.strip()

    params = {
        "engine": "google",
        "q": query,
        "num": num,
        "hl": "en",
        "api_key": api_key,
    }
    data = pipeline._http_get_json("https://serpapi.com/search.json", params=params)

    companies, job_link_orgs = _build_companies(
        data, provider=provider, city=city, limit=limit
    )
    verified = _verify_companies_with_jobs(
        companies, provider, job_link_orgs=job_link_orgs
    )
    payload = {"companies": companies}

    out_path = Path(args.out)
    if out_path.suffix.lower() != ".json":
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        city_slug = _slugify(city)
        filename = f"companies_{city_slug}_{provider}_{timestamp}.json"
        out_path = out_path / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    print(f"Wrote {len(companies)} companies to {out_path}")
    print(f"Verified {len(verified)} companies with live jobs")

    origin_path = Path(args.origin)
    added = _update_origin_companies(verified, origin_path)
    print(f"Added {added} companies to {origin_path}")


if __name__ == "__main__":
    main()
