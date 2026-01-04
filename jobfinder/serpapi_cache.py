from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _env_int(name: str, default: int, *, min_val: int | None = None) -> int:
    raw = os.getenv(name)
    try:
        val = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        val = default
    if min_val is not None:
        val = max(min_val, val)
    return val


def _cache_settings() -> Tuple[int, Path]:
    ttl = _env_int("SERPAPI_CACHE_TTL_SECONDS", 86400, min_val=0)
    cache_dir = os.getenv("SERPAPI_CACHE_DIR")
    if cache_dir:
        path = Path(os.path.expanduser(cache_dir))
    else:
        path = Path.cwd() / ".serpapi_cache"
    return ttl, path


def _cache_key(url: str, params: Optional[Dict[str, Any]]) -> str:
    items = sorted((str(k), str(v)) for k, v in (params or {}).items())
    raw = json.dumps(
        {"url": url, "params": items}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def read_cache(url: str, params: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    ttl, cache_dir = _cache_settings()
    if ttl <= 0:
        return None
    key = _cache_key(url, params)
    path = cache_dir / f"{key}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        return None
    ts = data.get("ts")
    if not isinstance(ts, (int, float)):
        return None
    if time.time() - ts > ttl:
        try:
            path.unlink()
        except Exception:
            pass
        return None
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None
    return payload


def write_cache(
    url: str, params: Optional[Dict[str, Any]], payload: Dict[str, Any]
) -> None:
    ttl, cache_dir = _cache_settings()
    if ttl <= 0:
        return
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = _cache_key(url, params)
        path = cache_dir / f"{key}.json"
        tmp = path.with_suffix(".tmp")
        data = {"ts": time.time(), "payload": payload}
        tmp.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        return
