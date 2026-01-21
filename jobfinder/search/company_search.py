from __future__ import annotations
import logging
import os
from dataclasses import dataclass
from typing import Iterable, List, Dict, Tuple
from urllib.parse import urlparse, unquote
import httpx
from ..serpapi_cache import read_cache as _serpapi_cache_read
from ..serpapi_cache import write_cache as _serpapi_cache_write
from ..models import Company

log = logging.getLogger(__name__)


@dataclass(slots=True)
class DiscoveryResult:
    companies: List[Company]


def _canon_url(u: str) -> str:
    if not u:
        return ""
    p = urlparse(u)
    path = p.path.rstrip("/")
    return f"{p.scheme}://{p.netloc}{path}"


def _first_path_segment(u: str, host: str) -> str | None:
    if not u:
        return None
    p = urlparse(u)
    if p.netloc.lower() != host.lower():
        return None
    parts = [seg for seg in p.path.split("/") if seg]
    if not parts:
        return None
    return parts[0]


def _normalize_name_from_org(org: str) -> str:
    pretty = unquote(org).replace("-", " ").replace("_", " ").strip()
    if not pretty:
        return org
    return " ".join(w.capitalize() if w else w for w in pretty.split())


def _env_int(
    name: str,
    default: int,
    *,
    min_val: int | None = None,
    max_val: int | None = None,
) -> int:
    raw = os.getenv(name)
    try:
        val = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        val = default
    if min_val is not None:
        val = max(min_val, val)
    if max_val is not None:
        val = min(max_val, val)
    return val


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _sanitize_query_term(term: str) -> str:
    return (term or "").replace('"', "").strip()


def _build_city_clauses(cities: List[str], *, combine: bool) -> List[str]:
    cleaned: List[str] = []
    seen = set()
    for c in cities or []:
        c_norm = _sanitize_query_term(c)
        if not c_norm:
            continue
        key = c_norm.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(c_norm)

    if not cleaned:
        return [""]

    if combine and len(cleaned) > 1:
        joined = " OR ".join(f'"{c}"' for c in cleaned)
        return [f"({joined})"]

    return [f'"{c}"' for c in cleaned]


def _provider_sites(wanted: set[str]) -> List[str]:
    sites: List[str] = []
    if "greenhouse" in wanted:
        sites.append("site:boards.greenhouse.io")
    if "lever" in wanted:
        sites.append("site:jobs.lever.co")
    return sites


def _build_provider_clauses(sites: List[str], *, combine: bool) -> List[str]:
    if not sites:
        return []
    if combine and len(sites) > 1:
        joined = " OR ".join(sites)
        return [f"({joined})"]
    return sites


async def _serpapi_search(
    query: str, api_key: str, num: int = 10, *, no_cache: bool = False
) -> List[Dict]:
    url = "https://serpapi.com/search.json"
    params: dict[str, str | int] = {
        "engine": "google",
        "q": query,
        "num": num,
        "api_key": api_key,
    }
    if no_cache:
        params["no_cache"] = "true"
    if not no_cache:
        cached = _serpapi_cache_read(url, params)
        if cached is not None:
            return cached.get("organic_results", [])
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json() or {}
        if not no_cache and isinstance(data, dict):
            _serpapi_cache_write(url, params, payload=data)
        return data.get("organic_results", [])


def _extract_orgs(results: List[Dict]) -> Tuple[List[str], List[str]]:
    gh, lv = set(), set()
    for item in results:
        link = item.get("link") or item.get("url") or ""
        if not link:
            continue
        link = _canon_url(link)
        org = _first_path_segment(link, "boards.greenhouse.io")
        if org:
            gh.add(org)
            continue
        org = _first_path_segment(link, "jobs.lever.co")
        if org:
            lv.add(org)
            continue
    return sorted(gh), sorted(lv)


async def discover_companies(
    cities: List[str],
    keywords: List[str],
    sources: Iterable[str],
    limit: int = 50,
    api_key: str | None = None,
) -> DiscoveryResult:
    if not api_key:
        api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        log.warning("SERPAPI_API_KEY missing. Set in environment or .env")
        return DiscoveryResult(companies=[])
    wanted = {s.strip().lower() for s in (sources or []) if s} or {
        "greenhouse",
        "lever",
    }
    city_mode = (os.getenv("SERPAPI_CITY_MODE") or "or").strip().lower()
    combine_cities = city_mode != "split"
    provider_mode = (os.getenv("SERPAPI_PROVIDER_MODE") or "or").strip().lower()
    combine_providers = provider_mode == "or"
    city_clauses = _build_city_clauses(cities or [], combine=combine_cities)
    provider_clauses = _build_provider_clauses(
        _provider_sites(wanted), combine=combine_providers
    )
    queries: List[str] = []
    kws = " ".join([str(k).strip() for k in (keywords or []) if str(k).strip()])
    for city_clause in city_clauses:
        for provider_clause in provider_clauses:
            parts = [provider_clause] if provider_clause else []
            if city_clause:
                parts.append(city_clause)
            if kws:
                parts.append(kws)
            queries.append(" ".join(parts).strip())
    results: List[Dict] = []
    per_q_default = max(10, min(100, limit))
    per_q = _env_int("SERPAPI_NUM_RESULTS", per_q_default, min_val=10, max_val=100)
    no_cache = _env_bool("SERPAPI_NO_CACHE", False)
    for q in queries:
        results.extend(await _serpapi_search(q, api_key, num=per_q, no_cache=no_cache))
    gh, lv = _extract_orgs(results)
    uniq: dict[tuple[str, str], Company] = {}
    for org in gh:
        name = _normalize_name_from_org(org)
        uniq[("greenhouse", org)] = Company(name=name, provider="greenhouse", org=org)
    for org in lv:
        name = _normalize_name_from_org(org)
        uniq[("lever", org)] = Company(name=name, provider="lever", org=org)
    companies = [
        c for _, c in sorted(uniq.items(), key=lambda kv: (kv[0][0], kv[0][1]))
    ][:limit]
    return DiscoveryResult(companies=companies)
