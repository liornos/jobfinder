from __future__ import annotations

import json
import os
from math import radians, sin, cos, asin, sqrt
from typing import Optional, Tuple, Dict
import httpx

CACHE_PATH = os.getenv("JOBFINDER_GEOCODE_CACHE", "geocode_cache.json")
UA = {"User-Agent": "jobfinder/0.3.0 (+github.com/your/repo)"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    c = 2 * asin(sqrt(a))
    return R * c


def _load_cache() -> Dict[str, Tuple[float, float]]:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
            return {k: (v[0], v[1]) for k, v in d.items()}
    except Exception:
        return {}


def _save_cache(d: Dict[str, Tuple[float, float]]) -> None:
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass


async def geocode_place(place: str) -> Optional[Tuple[float, float]]:
    place_key = place.strip().lower()
    cache = _load_cache()
    if place_key in cache:
        return cache[place_key]
    url = "https://nominatim.openstreetmap.org/search"
    params: dict[str, str | int] = {"q": place, "format": "jsonv2", "limit": 1}
    async with httpx.AsyncClient(timeout=20, headers=UA) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json() or []
        if not data:
            return None
        lat = float(data[0]["lat"])
        lon = float(data[0]["lon"])
        cache[place_key] = (lat, lon)
        _save_cache(cache)
        return lat, lon
