# file: jobfinder/providers/_http.py
from __future__ import annotations
import json
import ssl
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def get_json(
    url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 30
) -> Any:
    """Fetch JSON from a URL."""
    qs = ("?" + urlencode(params)) if params else ""
    req = Request(
        url + qs, headers={"User-Agent": "jobfinder/0.3", "Accept": "application/json"}
    )
    ctx = ssl.create_default_context()
    with urlopen(req, timeout=timeout, context=ctx) as resp:
        data = resp.read()
        return json.loads(data.decode("utf-8", errors="ignore"))
