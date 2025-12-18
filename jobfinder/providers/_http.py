# file: jobfinder/providers/_http.py
from __future__ import annotations
from typing import Any, Dict, Optional
import requests

def get_json(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Any:
    """Fetch JSON from a URL."""
    resp = requests.get(url, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
