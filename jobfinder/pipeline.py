# file: jobfinder/pipeline.py
from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import logging
import os
import ssl
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .filtering import apply_filters, score

log = logging.getLogger(__name__)

# Supported provider names used by scan()
PROVIDERS: Tuple[str, ...] = ("greenhouse", "lever", "ashby", "smartrecruiters", "breezy", "comeet", "workday", "recruitee", "jobvite", "icims")

# Hostnames per provider used by discover()
_PROVIDER_HOST = {
    "greenhouse": "boards.greenhouse.io",
    "lever": "jobs.lever.co",
    "ashby": "jobs.ashbyhq.com",
    "smartrecruiters": "jobs.smartrecruiters.com",
    "breezy": "breezy.hr",
    "comeet": "comeet.co",
    "workday": "myworkdayjobs.com",
    "recruitee": "recruitee.com",
    "jobvite": "jobvite.com",
    "icims": "icims.com",
}

# ----------------- utils -----------------

def _norm(s: Optional[str]) -> str:
    return (s or "").strip()

def _as_str_list(seq) -> List[str]:
    # why: avoid `.strip()` on non-strings
    if not seq:
        return []
    out: List[str] = []
    for x in seq:
        s = str(x).strip()
        if s:
            out.append(s)
    return out

def _http_get_json(url: str, params: Optional[Dict[str, Any]] = None, timeout: float = 25.0) -> Any:
    # why: no external deps
    qs = ("?" + urlencode(params)) if params else ""
    req = Request(url + qs, headers={"User-Agent": "jobfinder/0.3", "Accept": "application/json"})
    ctx = ssl.create_default_context()
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        data = resp.read()
        return json.loads(data.decode("utf-8", errors="ignore"))

def _extract_org_from_url(_provider: str, url: str) -> Optional[str]:
    try:
        p = urlparse(url)
        segs = [s for s in (p.path or "").split("/") if s]
        return segs[0].lower() if segs else None
    except Exception:
        return None

def _import_provider(provider: str):
    # try both layouts; log details
    last_exc: Optional[BaseException] = None
    for modname in (f"jobfinder.providers.{provider}", f"providers.{provider}"):
        try:
            spec = importlib.util.find_spec(modname)
            if spec is None:
                log.debug("find_spec(%s) -> None", modname)
                continue
            log.debug("find_spec(%s) -> origin=%s", modname, getattr(spec, "origin", None))
            mod = importlib.import_module(modname)
            log.info("Imported provider module: %s (%s)", modname, getattr(mod, "__file__", None))
            return mod
        except Exception as e:
            last_exc = e
            log.warning("Import attempt failed: %s (%s)", modname, e, exc_info=True)
    log.error("Provider module not found: %s | sys.path[0]=%s", provider, sys.path[0] if sys.path else None)
    if last_exc:
        log.error("Last import error for %s: %s", provider, last_exc)
    return None

def _call_fetch(fetch_fn, org: str) -> List[Dict[str, Any]]:
    # flexible signature
    for kwargs in ({"org": org}, {"slug": org}, {"company": org}, {}):
        try:
            log.debug("Calling %s with %r", getattr(fetch_fn, "__qualname__", fetch_fn), kwargs or {"_positional": "org"})
            if kwargs:
                return list(fetch_fn(**kwargs))
            else:
                return list(fetch_fn(org))
        except TypeError:
            continue
        except Exception as e:
            log.warning("fetch_jobs failed for org=%s using %s: %s", org, kwargs, e, exc_info=True)
            break
    return []

def _infer_work_mode(title: str, location: str, remote_flag: Optional[bool]) -> str:
    t, l = title.lower(), location.lower()
    if "hybrid" in t or "hybrid" in l:
        return "hybrid"
    if remote_flag is True or "remote" in t or "remote" in l or "work from home" in l:
        return "remote"
    if "onsite" in t or "on-site" in t or "onsite" in l or "on-site" in l:
        return "onsite"
    return ""

def _normalize_job(company: Dict[str, Any], provider: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    org = company.get("org") or company.get("name") or ""
    title = _norm(str(raw.get("title")))
    location = _norm(str(raw.get("location") or raw.get("city") or raw.get("office") or ""))
    url = _norm(str(raw.get("url") or raw.get("apply_url") or raw.get("absolute_url") or ""))
    jid = _norm(str(raw.get("id") or raw.get("job_id") or url))
    created_at = _norm(str(raw.get("created_at") or raw.get("updated_at") or raw.get("published_at") or ""))
    remote_val = raw.get("remote")
    remote_flag = remote_val if isinstance(remote_val, bool) else None
    work_mode = _infer_work_mode(title, location, remote_flag)
    return {
        "id": jid or url or f"{provider}:{org}:{title}",
        "title": title,
        "company": (company.get("name") or org or "").strip(),
        "provider": provider,
        "location": location,
        "url": url,
        "created_at": created_at,
        "remote": remote_flag if remote_flag is not None else (work_mode == "remote"),
        "extra": {**raw, "work_mode": work_mode},
    }

def _city_match(location: str, cities: Iterable[Any]) -> bool:
    loc = (location or "").lower()
    for c in cities or []:
        c2 = str(c).strip().lower()
        if c2 and c2 in loc:
            return True
    return False

def _dedupe(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for j in jobs:
        key = j.get("id") or j.get("url")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(j)
    return out

# --------------- compat shim for filtering ----------------

def _apply_filters_compat(
    results: List[Dict[str, Any]],
    *,
    provider: Optional[str],
    remote: str,
    min_score: int,
    max_age_days: Optional[int],
    cities: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Introspects filtering.apply_filters and passes only supported kwargs.
    Falls back to simpler call patterns if needed.
    """
    filt = {
        "provider": provider,
        "remote": remote,
        "min_score": min_score,
        "max_age_days": max_age_days,
        "cities": cities,
    }
    try:
        sig = inspect.signature(apply_filters)
        param_names = {p.name for p in sig.parameters.values()}
        # exclude the first positional param if it's named 'jobs'
        param_names.discard("jobs")
        param_names.discard("rows")

        if "filters" in param_names:
            return apply_filters(results, filt)

        kwargs = {}
        if "provider" in param_names:
            kwargs["provider"] = provider
        if "remote" in param_names:
            kwargs["remote"] = remote
        if "min_score" in param_names:
            kwargs["min_score"] = min_score
        if "max_age_days" in param_names:
            kwargs["max_age_days"] = max_age_days
        if "cities" in param_names:
            kwargs["cities"] = cities
        return apply_filters(results, **kwargs)
    except TypeError:
        # very old signature: try progressively simpler forms
        try:
            return apply_filters(results, min_score=min_score, max_age_days=max_age_days)
        except TypeError:
            try:
                return apply_filters(results, min_score=min_score)
            except TypeError:
                try:
                    return apply_filters(results)
                except Exception:
                    return results
    except Exception:
        return results

# ----------------- diagnostics -----------------

def diagnose_providers() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "cwd": os.getcwd(),
        "sys_path_head": sys.path[:5],
        "providers": {},
    }
    for name in PROVIDERS:
        entry: Dict[str, Any] = {"candidates": [], "imported": False, "module_file": None, "error": None}
        for modname in (f"jobfinder.providers.{name}", f"providers.{name}"):
            spec = importlib.util.find_spec(modname)
            entry["candidates"].append(
                {"module": modname, "found": bool(spec), "origin": getattr(spec, "origin", None) if spec else None}
            )
            if spec:
                try:
                    mod = importlib.import_module(modname)
                    entry["imported"] = True
                    entry["module_file"] = getattr(mod, "__file__", None)
                    entry["has_fetch"] = callable(getattr(mod, "fetch_jobs", None))
                    break
                except Exception as e:
                    entry["error"] = f"{type(e).__name__}: {e}"
        report["providers"][name] = entry
    return report

# ----------------- discover -----------------

def discover(
    *,
    cities: List[str],
    keywords: List[str],
    sources: Optional[List[str]] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
        raise RuntimeError("MISSING API KEY")
    if not sources:
        sources = list(_PROVIDER_HOST.keys())
    q_keywords = " ".join([k for k in (keywords or []) if _norm(k)]) if keywords else ""
    results: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for provider in sources:
        host = _PROVIDER_HOST.get(provider)
        if not host:
            continue
        for city in (cities or [""]):
            q = f'site:{host} "{city}" {q_keywords}'.strip()
            params = {"engine": "google", "q": q, "num": 10, "hl": "en", "api_key": api_key}
            data = _http_get_json("https://serpapi.com/search.json", params=params)
            for item in (data.get("organic_results") or []):
                link = item.get("link") or ""
                if not link or host not in link:
                    continue
                org = _extract_org_from_url(provider, link)
                if not org:
                    continue
                key = (provider, org)
                if key in results:
                    continue
                careers_url = f"https://{host}/{org}"
                results[key] = {
                    "name": org,
                    "org": org,
                    "provider": provider,
                    "careers_url": careers_url,
                    "city": city,
                }
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return list(results.values())

# ----------------- scan -----------------

def scan(
    *,
    companies: List[Dict[str, Any]],
    cities: Optional[List[Any]] = None,
    keywords: Optional[List[Any]] = None,
    provider: Optional[Any] = None,
    remote: str = "any",
    min_score: int = 0,
    max_age_days: Optional[int] = None,
    geo: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    log.info("scan() starting | cwd=%s | provider=%s | cities=%s | companies=%d",
             os.getcwd(), provider, cities, len(companies or []))
    log.debug("sys.path[0..4]=%s", sys.path[:5])

    companies = companies or []
    cities = _as_str_list(cities or (geo or {}).get("cities"))
    keywords = _as_str_list(keywords)
    prov_filter = (str(provider).strip().lower()) if (provider is not None and provider != "") else None

    results: List[Dict[str, Any]] = []

    for c in companies:
        cprov = (str(c.get("provider") or "")).strip().lower()
        if prov_filter and cprov != prov_filter:
            continue
        if cprov not in PROVIDERS:
            log.warning("Unknown provider '%s' for company %s", cprov, c)
            continue

        org = (str(c.get("org") or c.get("name") or "")).strip()
        if not org:
            log.warning("Missing org/name for company %s", c)
            continue

        mod = _import_provider(cprov)
        fetch = getattr(mod, "fetch_jobs", None) if mod else None
        raw_jobs = _call_fetch(fetch, org) if callable(fetch) else []

        for rj in raw_jobs or []:
            j = _normalize_job(c, cprov, rj)
            try:
                j["score"] = j.get("score") or score(j, keywords)
            except Exception:
                j["score"] = int(j.get("score") or 0)

            if cities and not _city_match(j.get("location", ""), cities):
                continue

            results.append(j)

    results = _dedupe(results)

    # Compat path for different filtering.apply_filters signatures
    results = _apply_filters_compat(
        results,
        provider=prov_filter,
        remote=remote,
        min_score=int(min_score or 0),
        max_age_days=max_age_days,
        cities=cities,
    )

    log.info("scan() done | results=%d", len(results))
    return results
