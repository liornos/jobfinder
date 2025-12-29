from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Iterable, List, Dict, Tuple
from urllib.parse import urlparse, unquote
import httpx
from ..models import Company


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


async def _serpapi_search(query: str, api_key: str, num: int = 10) -> List[Dict]:
    url = "https://serpapi.com/search.json"
    params = {"engine": "google", "q": query, "num": num, "api_key": api_key}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json() or {}
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
        raise RuntimeError("SERPAPI_API_KEY missing. Set in environment or .env")
    wanted = {s.strip().lower() for s in (sources or []) if s} or {
        "greenhouse",
        "lever",
    }
    queries: List[str] = []
    kws = " ".join(keywords) if keywords else ""
    for city in cities or [""]:
        if "greenhouse" in wanted:
            queries.append(f'site:boards.greenhouse.io "{city}" {kws}'.strip())
        if "lever" in wanted:
            queries.append(f'site:jobs.lever.co "{city}" {kws}'.strip())
    results: List[Dict] = []
    per_q = max(10, min(50, limit))
    for q in queries:
        results.extend(await _serpapi_search(q, api_key, num=per_q))
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
