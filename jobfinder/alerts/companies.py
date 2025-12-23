from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def resolve_companies_json() -> Path:
    # Supports both repo-root static/companies.json and jobfinder/static/companies.json
    candidates = [
        Path.cwd() / "static" / "companies.json",
        Path.cwd() / "jobfinder" / "static" / "companies.json",
        Path(__file__).resolve().parents[1] / "static" / "companies.json",  # jobfinder/static
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "companies.json not found. Expected one of: "
        + ", ".join(str(c) for c in candidates)
    )


def load_companies(path: Path | None = None) -> List[Dict[str, Any]]:
    p = path or resolve_companies_json()
    data = json.loads(p.read_text(encoding="utf-8"))

    # Your file is: { "companies": [ ... ] }
    if isinstance(data, dict) and isinstance(data.get("companies"), list):
        data = data["companies"]

    if not isinstance(data, list):
        raise ValueError(f"{p} must contain {{'companies': [..]}} or a JSON list")

    out: List[Dict[str, Any]] = []
    for c in data:
        if not isinstance(c, dict):
            continue

        provider = (c.get("provider") or "").strip()
        org = (c.get("org") or "").strip()
        if not provider or not org:
            continue

        out.append(
            {
                "name": (c.get("name") or org).strip(),
                "city": (c.get("city") or "").strip() or None,
                "provider": provider,
                "org": org,
                "careers_url": (c.get("careers_url") or "").strip() or None,
            }
        )

    return out

