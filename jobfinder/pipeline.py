# file: jobfinder/pipeline.py
from __future__ import annotations

import importlib
import importlib.util
import inspect
import json
import logging
import os
import re
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, cast
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from . import db, filtering
from .serpapi_cache import read_cache as _serpapi_cache_read
from .serpapi_cache import write_cache as _serpapi_cache_write
from .filtering import apply_filters
from .models import Job as JobModel

log = logging.getLogger(__name__)

# Supported provider names used by scan()
PROVIDERS: Tuple[str, ...] = (
    "greenhouse",
    "lever",
    "ashby",
    "smartrecruiters",
    "breezy",
    "comeet",
    "workday",
    "recruitee",
    "jobvite",
    "icims",
    "workable",
)

# Hostnames per provider used by discover()
_PROVIDER_HOST = {
    "greenhouse": "boards.greenhouse.io",
    "lever": "jobs.lever.co",
    "ashby": "jobs.ashbyhq.com",
    "smartrecruiters": "jobs.smartrecruiters.com",
    "breezy": "breezy.hr",
    "comeet": "comeet.com",
    "workday": "myworkdayjobs.com",
    "recruitee": "recruitee.com",
    "jobvite": "jobvite.com",
    "icims": "icims.com",
    "workable": "apply.workable.com",
}

_CITY_ALIASES = {
    # Normalize common spelling variations for query + matching.
    "tel aviv": ["tel aviv", "tel-aviv", "tel aviv-yafo", "tel aviv yafo"],
    "tel aviv-yafo": ["tel aviv-yafo", "tel aviv yafo", "tel aviv"],
    "tel aviv yafo": ["tel aviv yafo", "tel aviv-yafo", "tel aviv"],
    "herzliya": ["herzliya", "hertzliya", "herzlia"],
    "kfar saba": ["kfar saba", "kfar sava"],
    "raanana": ["raanana", "ra'anana", "ra-anana", "ra anana"],
    "petach tikva": ["petach tikva", "petah tikva", "petach tikvah", "petah tikvah"],
    "petah tikva": ["petach tikva", "petah tikva", "petach tikvah", "petah tikvah"],
    "hod hasharon": ["hod hasharon", "hod ha-sharon", "hod ha sharon"],
    "netanya": ["netanya", "netnaya"],
    "ramat gan": ["ramat gan", "ramat-gan"],
    "bnei brak": ["bnei brak", "bnei-brak"],
    "givatayim": ["givatayim", "giv'atayim", "givataym"],
    "airport city": ["airport city", "airport-city"],
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


def _expand_city_aliases(cities: List[str]) -> List[str]:
    """
    Expand known city variations (e.g., Ra'anana spellings/nearby areas) while keeping order.
    """
    seen = set()
    expanded: List[str] = []
    for c in cities or []:
        base = (c or "").strip()
        if not base:
            continue
        variants = [base, *_CITY_ALIASES.get(base.lower(), [])]
        for v in variants:
            v_norm = (v or "").strip()
            if not v_norm:
                continue
            key = v_norm.lower()
            if key in seen:
                continue
            seen.add(key)
            expanded.append(v_norm)
    return expanded


def _env_int(
    name: str,
    default: int,
    *,
    min_val: Optional[int] = None,
    max_val: Optional[int] = None,
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


def _build_city_queries(
    cities: List[str], *, combine: bool
) -> List[Tuple[str, Optional[str]]]:
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
        return [("", None)]

    if combine and len(cleaned) > 1:
        joined = " OR ".join(f'"{c}"' for c in cleaned)
        return [(f"({joined})", None)]

    return [(f'"{c}"', c) for c in cleaned]


def _build_provider_queries(
    providers: List[str], *, combine: bool
) -> List[Tuple[Optional[str], str]]:
    cleaned: List[str] = []
    seen = set()
    for p in providers or []:
        p_norm = (p or "").strip().lower()
        if not p_norm:
            continue
        if p_norm in seen:
            continue
        if p_norm not in _PROVIDER_HOST:
            continue
        seen.add(p_norm)
        cleaned.append(p_norm)

    if not cleaned:
        return []

    if combine and len(cleaned) > 1:
        joined = " OR ".join(f"site:{_PROVIDER_HOST[p]}" for p in cleaned)
        return [(None, f"({joined})")]

    return [(p, f"site:{_PROVIDER_HOST[p]}") for p in cleaned]


def _provider_from_url(url: str) -> Optional[str]:
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        return None
    if not host:
        return None
    for provider, base in _PROVIDER_HOST.items():
        base_norm = base.lower()
        if host == base_norm or host.endswith("." + base_norm):
            return provider
    return None


def _subdomain_parts(host: str, base: str) -> List[str]:
    host = (host or "").lower().strip(".")
    base = (base or "").lower().strip(".")
    if not host or not base:
        return []
    if host == base:
        return []
    suffix = "." + base
    if not host.endswith(suffix):
        return []
    sub = host[: -len(suffix)]
    if not sub:
        return []
    return [p for p in sub.split(".") if p]


def _extract_icims_org_from_host(host: str) -> Optional[str]:
    parts = _subdomain_parts(host, "icims.com")
    if not parts:
        return None
    label = parts[-1]
    if label.startswith("careers-"):
        label = label[len("careers-") :]
    if label in {"careers", "jobs"}:
        return None
    return label or None


def _extract_workday_org_from_host(host: str) -> Optional[str]:
    parts = _subdomain_parts(host, "myworkdayjobs.com")
    if not parts:
        return None
    first = parts[0]
    if first.startswith("wd") and first[2:].isdigit():
        return parts[1] if len(parts) > 1 else None
    if first in {"careers", "jobs"}:
        return None
    return first


def _http_get_json(
    url: str, params: Optional[Dict[str, Any]] = None, timeout: float = 25.0
) -> Any:
    # why: no external deps
    qs = ("?" + urlencode(params)) if params else ""
    req = Request(
        url + qs, headers={"User-Agent": "jobfinder/0.3", "Accept": "application/json"}
    )
    ctx = ssl.create_default_context()
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        data = resp.read()
        return json.loads(data.decode("utf-8", errors="ignore"))


_RESERVED_SLUGS = {
    "www",
    "jobs",
    "job",
    "career",
    "careers",
    "apply",
    "search",
    "positions",
    "position",
    "en",
    "en-us",
    "en_us",
    "o",
    "p",  # recruitee / breezy junk
}

_slug_re = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])$")


def _is_valid_org_slug(slug: str | None) -> bool:
    if not slug:
        return False
    s = slug.strip().lower()
    if s in _RESERVED_SLUGS:
        return False
    # reject too-short 1-letter slugs
    if len(s) < 2:
        return False
    # must contain at least two letters (rejects numeric-only and 1-letter combos)
    if sum(1 for ch in s if ch.isalpha()) < 2:
        return False
    return bool(_slug_re.match(s))


def _extract_org_from_url(_provider: str, url: str) -> Optional[str]:
    try:

        def _validated_slug(val: Optional[str]) -> Optional[str]:
            if not val:
                return None
            s = val.strip().lower()
            return s if _is_valid_org_slug(s) else None

        p = urlparse(url)
        host = (p.netloc or "").lower()
        segs = [s for s in (p.path or "").split("/") if s]
        if _provider == "comeet" and len(segs) >= 2 and segs[0].lower() == "jobs":
            return _validated_slug(segs[1])
        if _provider == "icims":
            org = _validated_slug(_extract_icims_org_from_host(host))
            if org:
                return org
            if segs:
                first = segs[0].lower()
                if first not in {"jobs", "career", "careers"}:
                    return _validated_slug(first)
            return None
        if _provider == "workday":
            if not segs:
                return _validated_slug(_extract_workday_org_from_host(host))
            lower_segs = [s.lower() for s in segs]
            if "inline" in lower_segs:
                idx = lower_segs.index("inline")
                if len(segs) > idx + 1:
                    return _validated_slug(segs[idx + 1])
            first = lower_segs[0]
            if re.match(r"^[a-z]{2}(-[a-z]{2})?$", first) and len(segs) > 1:
                second = segs[1].lower()
                if second not in {"details", "job", "jobs", "apply", "applymanually"}:
                    return _validated_slug(second)
            if first not in {"careers", "jobs", "job", "details", "apply", "wday"}:
                return _validated_slug(segs[0])
            return _validated_slug(_extract_workday_org_from_host(host))
        return _validated_slug(segs[0]) if segs else None
    except Exception:
        return None


def _normalize_comeet_careers_url(url: str) -> Optional[str]:
    if not url:
        return None
    try:
        p = urlparse(url)
        host = (p.netloc or "").lower()
        if not host:
            return None
        if host.endswith("comeet.com"):
            host = "www.comeet.com"
        segs = [s for s in (p.path or "").split("/") if s]
        if "jobs" in segs:
            idx = segs.index("jobs")
            slug = segs[idx + 1] if len(segs) > idx + 1 else None
            company_uid = segs[idx + 2] if len(segs) > idx + 2 else None
            if slug and company_uid:
                return f"https://{host}/jobs/{slug}/{company_uid}"
            if slug:
                return f"https://{host}/jobs/{slug}"
        if segs:
            return f"https://{host}/{segs[0]}"
        return f"https://{host}"
    except Exception:
        return None


def _normalize_city_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _extract_city_from_result(item: Dict[str, Any], cities: List[str]) -> Optional[str]:
    if not cities:
        return None
    parts: List[str] = []
    for key in ("title", "snippet", "displayed_link", "link"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val)
        elif isinstance(val, list):
            parts.extend([str(v) for v in val if v])
    highlighted = item.get("snippet_highlighted_words")
    if isinstance(highlighted, list):
        parts.extend([str(v) for v in highlighted if v])
    elif isinstance(highlighted, str) and highlighted.strip():
        parts.append(highlighted)

    haystack = _normalize_city_text(" ".join(parts))
    if not haystack:
        return None

    normalized: List[Tuple[str, str]] = []
    seen = set()
    for c in cities:
        c_norm = _normalize_city_text(c)
        if not c_norm or c_norm in seen:
            continue
        seen.add(c_norm)
        normalized.append((c, c_norm))

    if any(c_norm != "israel" for _, c_norm in normalized):
        normalized = [x for x in normalized if x[1] != "israel"] + [
            x for x in normalized if x[1] == "israel"
        ]

    for original, c_norm in normalized:
        if c_norm and c_norm in haystack:
            return original
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
            log.debug(
                "find_spec(%s) -> origin=%s", modname, getattr(spec, "origin", None)
            )
            mod = importlib.import_module(modname)
            log.info(
                "Imported provider module: %s (%s)",
                modname,
                getattr(mod, "__file__", None),
            )
            return mod
        except Exception as e:
            last_exc = e
            log.warning("Import attempt failed: %s (%s)", modname, e, exc_info=True)
    log.error(
        "Provider module not found: %s | sys.path[0]=%s",
        provider,
        sys.path[0] if sys.path else None,
    )
    if last_exc:
        log.error("Last import error for %s: %s", provider, last_exc)
    return None


def _log_provider_fetch(
    *,
    status: str,
    provider: str,
    org: str,
    elapsed_ms: int,
    jobs: Optional[int] = None,
    error: Optional[str] = None,
    exc_info: Optional[bool] = None,
) -> None:
    extra = {
        "provider": provider,
        "org": org,
        "elapsed_ms": elapsed_ms,
        "status": status,
    }
    if jobs is not None:
        extra["jobs"] = jobs
    if error:
        extra["error"] = error
    msg = f"provider_fetch {status}"
    if status == "fail":
        log.warning(msg, exc_info=exc_info, extra=extra)
    else:
        log.info(msg, extra=extra)


def _call_fetch(
    fetch_fn,
    org: str,
    company: Optional[Dict[str, Any]] = None,
    *,
    provider: str,
) -> List[Dict[str, Any]]:
    # flexible signature
    t0 = time.perf_counter()
    attempts: List[Dict[str, Any]] = []
    if company:
        attempts.append({"org": org, "company": company})
        careers_url = (company.get("careers_url") or "").strip()
        if careers_url:
            attempts.append({"org": org, "careers_url": careers_url})
    attempts.extend(({"org": org}, {"slug": org}, {"company": org}, {}))
    for kwargs in attempts:
        try:
            log.debug(
                "Calling %s with %r",
                getattr(fetch_fn, "__qualname__", fetch_fn),
                kwargs or {"_positional": "org"},
            )
            if kwargs:
                jobs = list(fetch_fn(**kwargs))
            else:
                jobs = list(fetch_fn(org))
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            _log_provider_fetch(
                status="ok",
                provider=provider,
                org=org,
                elapsed_ms=elapsed_ms,
                jobs=len(jobs),
            )
            return jobs
        except TypeError:
            continue
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            _log_provider_fetch(
                status="fail",
                provider=provider,
                org=org,
                elapsed_ms=elapsed_ms,
                error=str(e),
                exc_info=True,
            )
            return []
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    _log_provider_fetch(
        status="skipped",
        provider=provider,
        org=org,
        elapsed_ms=elapsed_ms,
        error="no_compatible_signature",
    )
    return []


def _infer_work_mode(title: str, location: str, remote_flag: Optional[bool]) -> str:
    title_lower = title.lower()
    location_lower = location.lower()
    if "hybrid" in title_lower or "hybrid" in location_lower:
        return "hybrid"
    if (
        remote_flag is True
        or "remote" in title_lower
        or "remote" in location_lower
        or "work from home" in location_lower
    ):
        return "remote"
    if (
        "onsite" in title_lower
        or "on-site" in title_lower
        or "onsite" in location_lower
        or "on-site" in location_lower
    ):
        return "onsite"
    return ""


def _normalize_job(
    company: Dict[str, Any], provider: str, raw: Dict[str, Any]
) -> Dict[str, Any]:
    org = company.get("org") or company.get("name") or ""
    title = _norm(str(raw.get("title")))
    location = _norm(
        str(raw.get("location") or raw.get("city") or raw.get("office") or "")
    )
    url = _norm(
        str(raw.get("url") or raw.get("apply_url") or raw.get("absolute_url") or "")
    )
    jid = _norm(str(raw.get("id") or raw.get("job_id") or url))
    created_at = _norm(
        str(
            raw.get("created_at")
            or raw.get("updated_at")
            or raw.get("published_at")
            or ""
        )
    )
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
    seen: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    out: List[Dict[str, Any]] = []
    for j in jobs:
        key = j.get("id") or j.get("url")
        if not key:
            out.append(j)
            continue
        if key not in seen:
            seen[key] = j
            order.append(key)
            continue
        existing = seen[key]
        curr_dt = filtering._parse_created_at(j.get("created_at"))
        prev_dt = filtering._parse_created_at(existing.get("created_at"))
        if (curr_dt and prev_dt and curr_dt > prev_dt) or (curr_dt and not prev_dt):
            seen[key] = j
    for key in order:
        out.append(seen[key])
    return out


def _compute_score(
    job: Dict[str, Any], keywords: List[str], cities: List[str]
) -> Tuple[int, str]:
    """
    Compute score and reasons using filtering.score (expects a Job dataclass).
    """
    try:
        created_at = filtering._parse_created_at(job.get("created_at"))
    except Exception:
        created_at = None

    job_obj = JobModel(
        id=str(job.get("id") or job.get("url") or ""),
        title=job.get("title") or "",
        company=job.get("company") or "",
        url=job.get("url") or "",
        location=job.get("location"),
        remote=job.get("remote"),
        created_at=created_at,
        provider=job.get("provider"),
        extra=job.get("extra"),
    )
    try:
        score_val, reasons = filtering.score(job_obj, keywords, cities)
        reason_str = (
            ", ".join(reasons or [])
            if isinstance(reasons, (list, tuple, set))
            else str(reasons or "")
        )
        return int(score_val or 0), reason_str
    except Exception:
        try:
            return int(job.get("score") or 0), str(job.get("reasons") or "")
        except Exception:
            return 0, ""


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
    filt: Dict[str, Any] = {
        "provider": provider,
        "remote": remote,
        "min_score": min_score,
        "max_age_days": max_age_days,
        "cities": cities,
    }
    apply_filters_fn = cast(Callable[..., List[Dict[str, Any]]], apply_filters)
    try:
        sig = inspect.signature(apply_filters)
        param_names = {p.name for p in sig.parameters.values()}
        # exclude the first positional param if it's named 'jobs'
        param_names.discard("jobs")
        param_names.discard("rows")

        if "filters" in param_names:
            return apply_filters_fn(results, filt)

        kwargs: Dict[str, Any] = {}
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
        return apply_filters_fn(results, **kwargs)
    except TypeError:
        # very old signature: try progressively simpler forms
        try:
            return apply_filters_fn(
                results, min_score=min_score, max_age_days=max_age_days
            )
        except TypeError:
            try:
                return apply_filters_fn(results, min_score=min_score)
            except TypeError:
                try:
                    return apply_filters_fn(results)
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
        entry: Dict[str, Any] = {
            "candidates": [],
            "imported": False,
            "module_file": None,
            "error": None,
        }
        for modname in (f"jobfinder.providers.{name}", f"providers.{name}"):
            spec = importlib.util.find_spec(modname)
            entry["candidates"].append(
                {
                    "module": modname,
                    "found": bool(spec),
                    "origin": getattr(spec, "origin", None) if spec else None,
                }
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
    cities_expanded = _expand_city_aliases(_as_str_list(cities))
    q_keywords = " ".join([k for k in (keywords or []) if _norm(k)]) if keywords else ""
    num_results = _env_int("SERPAPI_NUM_RESULTS", 100, min_val=10, max_val=100)
    no_cache = _env_bool("SERPAPI_NO_CACHE", False)
    city_mode = (os.getenv("SERPAPI_CITY_MODE") or "or").strip().lower()
    combine_cities = city_mode != "split"
    city_queries = _build_city_queries(cities_expanded, combine=combine_cities)
    provider_mode = (os.getenv("SERPAPI_PROVIDER_MODE") or "or").strip().lower()
    combine_providers = provider_mode == "or"
    provider_queries = _build_provider_queries(
        list(sources or []), combine=combine_providers
    )
    results: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for provider_hint, provider_clause in provider_queries:
        host_hint = _PROVIDER_HOST.get(provider_hint) if provider_hint else None
        for city_clause, city_value in city_queries:
            q_parts = []
            if provider_clause:
                q_parts.append(provider_clause)
            if city_clause:
                q_parts.append(city_clause)
            if q_keywords:
                q_parts.append(q_keywords)
            q = " ".join(q_parts).strip()
            params = {
                "engine": "google",
                "q": q,
                "num": num_results,
                "hl": "en",
                "api_key": api_key,
            }
            if no_cache:
                params["no_cache"] = "true"
            data = None
            if not no_cache:
                data = _serpapi_cache_read(
                    "https://serpapi.com/search.json", params=params
                )
            if data is None:
                data = _http_get_json("https://serpapi.com/search.json", params=params)
                if not no_cache:
                    _serpapi_cache_write(
                        "https://serpapi.com/search.json", params=params, payload=data
                    )
            for item in data.get("organic_results") or []:
                link = item.get("link") or ""
                if not link:
                    continue
                provider = provider_hint or _provider_from_url(link)
                if not provider:
                    continue
                host = _PROVIDER_HOST.get(provider)
                if not host:
                    continue
                if host_hint and host_hint not in link:
                    continue
                org = _extract_org_from_url(provider, link)
                if not org:
                    continue
                key = (provider, org)
                if key in results:
                    continue
                resolved_city = city_value or _extract_city_from_result(
                    item, cities_expanded
                )
                if provider == "comeet":
                    careers_url = _normalize_comeet_careers_url(link) or link
                elif provider == "workday":
                    careers_url = link
                else:
                    careers_url = f"https://{host}/{org}"
                results[key] = {
                    "name": org,
                    "org": org,
                    "provider": provider,
                    "careers_url": careers_url,
                    "city": resolved_city,
                }
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break
        if len(results) >= limit:
            break
    return list(results.values())


# ----------------- scan helpers -----------------


def _load_fetchers(
    companies: List[Dict[str, Any]], prov_filter: Optional[str]
) -> Dict[str, Any]:
    """
    Preload provider modules once per scan/refresh to avoid repeated imports.
    """
    fetchers: Dict[str, Any] = {}
    for c in companies:
        cprov = (str(c.get("provider") or "")).strip().lower()
        if prov_filter and cprov != prov_filter:
            continue
        if cprov not in PROVIDERS:
            continue
        if cprov in fetchers:
            continue
        mod = _import_provider(cprov)
        fetchers[cprov] = getattr(mod, "fetch_jobs", None) if mod else None
    return fetchers


def _process_company_jobs(
    company: Dict[str, Any],
    *,
    fetchers: Dict[str, Any],
    prov_filter: Optional[str],
    cities: List[str],
    keywords: List[str],
    filter_by_cities: bool,
    compute_scores: bool,
) -> Tuple[Optional[Tuple[str, str]], List[Dict[str, Any]]]:
    cprov = (str(company.get("provider") or "")).strip().lower()
    if prov_filter and cprov != prov_filter:
        return None, []
    if cprov not in PROVIDERS:
        log.warning("Unknown provider '%s' for company %s", cprov, company)
        return None, []

    org = (str(company.get("org") or company.get("name") or "")).strip()
    if not org:
        log.warning("Missing org/name for company %s", company)
        return None, []

    fetch = fetchers.get(cprov)
    if callable(fetch):
        raw_jobs = _call_fetch(fetch, org, company=company, provider=cprov)
    else:
        _log_provider_fetch(
            status="skipped",
            provider=cprov,
            org=org,
            elapsed_ms=0,
            error="missing_fetcher",
        )
        raw_jobs = []

    company_jobs: List[Dict[str, Any]] = []
    for rj in raw_jobs or []:
        j = _normalize_job(company, cprov, rj)
        if compute_scores:
            score_val, reasons = _compute_score(j, keywords, cities)
            j["score"] = score_val
            if reasons:
                j["reasons"] = reasons

        if (
            filter_by_cities
            and cities
            and not _city_match(j.get("location", ""), cities)
        ):
            continue

        company_jobs.append(j)
    return (cprov, org), company_jobs


def _collect_jobs(
    *,
    companies: List[Dict[str, Any]],
    cities: Optional[List[Any]],
    keywords: Optional[List[Any]],
    provider: Optional[Any],
    remote: str,
    min_score: int,
    max_age_days: Optional[int],
    filter_by_cities: bool,
    apply_filters_flag: bool,
    compute_scores: bool,
) -> Tuple[List[Dict[str, Any]], Dict[Tuple[str, str], List[Dict[str, Any]]]]:
    companies = companies or []
    cities_list = _expand_city_aliases(_as_str_list(cities))
    keywords_list = _as_str_list(keywords)
    prov_filter = (
        (str(provider).strip().lower())
        if (provider is not None and provider != "")
        else None
    )

    fetchers = _load_fetchers(companies, prov_filter)
    per_company: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    if companies:
        max_workers = min(8, len(companies))

        def runner(
            c: Dict[str, Any],
        ) -> Tuple[Optional[Tuple[str, str]], List[Dict[str, Any]]]:
            return _process_company_jobs(
                c,
                fetchers=fetchers,
                prov_filter=prov_filter,
                cities=cities_list,
                keywords=keywords_list,
                filter_by_cities=filter_by_cities,
                compute_scores=compute_scores,
            )

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for key, jobs in pool.map(runner, companies):
                if key is None:
                    continue
                per_company[key] = jobs

    flat_results: List[Dict[str, Any]] = []
    for jobs in per_company.values():
        flat_results.extend(jobs)

    flat_results = _dedupe(flat_results)

    if apply_filters_flag:
        flat_results = _apply_filters_compat(
            flat_results,
            provider=prov_filter,
            remote=remote,
            min_score=int(min_score or 0),
            max_age_days=max_age_days,
            cities=cities_list,
        )

    return flat_results, per_company


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
    log.info(
        "scan() starting | cwd=%s | provider=%s | cities=%s | companies=%d",
        os.getcwd(),
        provider,
        cities,
        len(companies or []),
    )
    log.debug("sys.path[0..4]=%s", sys.path[:5])

    results, _ = _collect_jobs(
        companies=companies,
        cities=cities or (geo or {}).get("cities"),
        keywords=keywords,
        provider=provider,
        remote=remote,
        min_score=min_score,
        max_age_days=max_age_days,
        filter_by_cities=True,
        apply_filters_flag=True,
        compute_scores=True,
    )

    log.info("scan() done | results=%d", len(results))
    return results


# ----------------- refresh (DB ingest) -----------------


def refresh(
    *,
    companies: List[Dict[str, Any]],
    cities: Optional[List[Any]] = None,
    keywords: Optional[List[Any]] = None,
    provider: Optional[Any] = None,
    db_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch jobs from providers and persist them to the database.
    """
    db.init_db(db_url)
    now = datetime.now(timezone.utc)

    jobs, per_company = _collect_jobs(
        companies=companies,
        cities=cities,
        keywords=keywords,
        provider=provider,
        remote="any",
        min_score=0,
        max_age_days=None,
        filter_by_cities=False,  # store everything; filtering happens at query time
        apply_filters_flag=False,
        compute_scores=True,
    )

    refreshed = 0
    marked_inactive = 0

    with db.session_scope(db_url) as session:
        for comp in companies or []:
            try:
                company_row = db.upsert_company(session, comp)
            except ValueError:
                log.warning("Skipping company without provider/org: %s", comp)
                continue

            key = (company_row.provider, company_row.org)
            company_jobs = per_company.get(key, [])
            seen_keys: List[str] = []
            for job in company_jobs:
                row = db.upsert_job(
                    session,
                    company=company_row,
                    job_dict=job,
                    seen_at=now,
                    keywords=_as_str_list(keywords),
                    cities=_expand_city_aliases(_as_str_list(cities)),
                )
                seen_keys.append(row.job_key)
                refreshed += 1

            marked_inactive += db.mark_inactive(
                session,
                provider=company_row.provider,
                org=company_row.org,
                seen_keys=seen_keys,
                seen_at=now,
            )

    return {
        "jobs_seen": len(jobs),
        "jobs_written": refreshed,
        "inactive_marked": marked_inactive,
        "companies": len(companies or []),
    }


# ----------------- query (DB only) -----------------


def query_jobs(
    *,
    provider: Optional[str] = None,
    remote: str = "any",
    min_score: int = 0,
    max_age_days: Optional[int] = None,
    cities: Optional[List[Any]] = None,
    keywords: Optional[List[Any]] = None,
    compute_scores: Optional[bool] = None,
    title_keywords: Optional[List[Any]] = None,
    orgs: Optional[List[Any]] = None,
    company_names: Optional[List[Any]] = None,
    only_active: bool = True,
    limit: int = 500,
    offset: int = 0,
    db_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Read jobs from the DB (no provider HTTP calls) and apply filters in-memory.
    """
    db.init_db(db_url)

    cities_list = _expand_city_aliases(_as_str_list(cities))
    keywords_list = _as_str_list(keywords)
    title_kw_list = _as_str_list(title_keywords)
    compute_needed = bool(keywords_list) or int(min_score or 0) > 0
    if compute_scores is None:
        compute_scores = compute_needed
    else:
        compute_scores = bool(compute_scores)
    prov_filter = (str(provider).strip().lower()) if provider else None
    org_set = {s.lower() for s in _as_str_list(orgs)} if orgs else set()
    company_name_set = (
        {s.lower() for s in _as_str_list(company_names)} if company_names else set()
    )

    limit_val = int(limit or 0)
    offset_val = max(0, int(offset or 0))
    if limit_val <= 0:
        return []

    with db.session_scope(db_url) as session:
        base_stmt = (
            select(db.Job)
            .options(selectinload(db.Job.company))
            .order_by(db.Job.created_at.desc(), db.Job.id.desc())
        )
        if only_active:
            base_stmt = base_stmt.where(db.Job.is_active.is_(True))
        if prov_filter:
            base_stmt = base_stmt.where(db.Job.provider == prov_filter)
        if org_set:
            base_stmt = base_stmt.where(db.Job.org.in_(org_set))
        if company_name_set:
            base_stmt = base_stmt.where(db.Job.company_name.in_(company_name_set))

        batch_size = max(limit_val * 2, 500)
        filtered: List[Dict[str, Any]] = []
        fetch_offset = 0
        target = offset_val + limit_val

        while True:
            stmt = base_stmt.offset(fetch_offset).limit(batch_size)
            rows = session.scalars(stmt).all()
            if not rows:
                break

            jobs_batch = [db.job_to_dict(r) for r in rows]

            if compute_scores:
                # Recompute score at query-time so filters reflect the active keyword set.
                for j in jobs_batch:
                    score_val, reasons = _compute_score(j, keywords_list, cities_list)
                    j["score"] = score_val
                    if reasons:
                        j["reasons"] = reasons

            jobs_batch = _apply_filters_compat(
                jobs_batch,
                provider=prov_filter,
                remote=remote,
                min_score=int(min_score or 0),
                max_age_days=max_age_days,
                cities=cities_list,
            )

            if title_kw_list and hasattr(filtering, "filter_by_title_keywords"):
                try:
                    jobs_batch = filtering.filter_by_title_keywords(
                        jobs_batch, title_kw_list
                    )
                except Exception:
                    pass

            filtered.extend(jobs_batch)
            if len(filtered) >= target:
                break

            if len(rows) < batch_size:
                break

            fetch_offset += batch_size

    return filtered[offset_val : offset_val + limit_val]
