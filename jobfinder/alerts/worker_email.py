from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

from .companies import load_companies
from .emailer_gmail import send_email_gmail
from .state import AlertState


def _group_by_provider(
    companies: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for c in companies or []:
        prov = (c.get("provider") or "").strip().lower()
        if not prov:
            continue
        grouped.setdefault(prov, []).append(c)
    return grouped


def _dedupe_jobs(jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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


def scan(
    base_url: str,
    cities: List[str],
    keywords: List[str],
    companies: List[Dict[str, Any]],
    top: int,
    *,
    provider: str | None = None,
    timeout: float = 90.0,
) -> List[Dict[str, Any]]:
    url = base_url.rstrip("/") + "/scan"
    payload = {
        "cities": cities,
        "keywords": keywords,
        "top": top,
        "companies": companies,
    }
    if provider:
        payload["provider"] = provider
    with httpx.Client(timeout=httpx.Timeout(timeout)) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    return data.get("results") or []


def render_text(new_jobs: List[Dict[str, Any]]) -> str:
    lines = []
    for j in new_jobs[:40]:
        title = j.get("title") or "Untitled"
        company = j.get("company") or j.get("company_name") or "Unknown"
        loc = j.get("location") or ""
        url = j.get("url") or ""
        lines.append(f"- {title} — {company} ({loc})\n  {url}")
    return "New jobs:\n\n" + "\n".join(lines) + "\n"


def run_once() -> int:
    base_url = os.environ["ALERT_BASE_URL"]  # your Render web-service URL
    cities = [
        c.strip()
        for c in os.environ.get("ALERT_CITIES", "Tel Aviv").split(",")
        if c.strip()
    ]
    keywords = [
        k.strip()
        for k in os.environ.get("ALERT_KEYWORDS", "automation").split(",")
        if k.strip()
    ]
    top = int(os.environ.get("ALERT_TOP", "300"))
    http_timeout = float(os.environ.get("ALERT_HTTP_TIMEOUT", "120"))

    companies = load_companies()  # static/companies.json
    provider_order = [
        p.strip().lower()
        for p in (os.environ.get("ALERT_PROVIDER_ORDER") or "").split(",")
        if p and p.strip()
    ]

    jobs: List[Dict[str, Any]] = []
    if provider_order:
        grouped = _group_by_provider(companies)
        for prov in provider_order:
            if prov not in grouped:
                continue
            jobs.extend(
                scan(
                    base_url,
                    cities=cities,
                    keywords=keywords,
                    companies=grouped[prov],
                    top=top,
                    provider=prov,
                    timeout=http_timeout,
                )
            )
        # add any providers not listed explicitly
        for prov, comps in grouped.items():
            if prov in provider_order:
                continue
            jobs.extend(
                scan(
                    base_url,
                    cities=cities,
                    keywords=keywords,
                    companies=comps,
                    top=top,
                    provider=prov,
                    timeout=http_timeout,
                )
            )
    else:
        jobs = scan(
            base_url,
            cities=cities,
            keywords=keywords,
            companies=companies,
            top=top,
            timeout=http_timeout,
        )

    jobs = _dedupe_jobs(jobs)

    # Use id, fallback to url (important for providers that don't give stable ids)
    ids = [(j.get("id") or j.get("url")) for j in jobs]
    ids = [i for i in ids if i]

    state_db = Path(os.environ.get("ALERT_STATE_DB", "/tmp/jobfinder_alerts.sqlite"))
    state = AlertState(state_db)

    seen = state.already_seen(ids)
    new_jobs = [
        j
        for j in jobs
        if (j.get("id") or j.get("url")) and (j.get("id") or j.get("url")) not in seen
    ]

    if not new_jobs:
        return 0

    subject = f"jobfinder: {len(new_jobs)} new jobs"
    text = render_text(new_jobs)

    to_addrs = (os.environ.get("ALERT_EMAIL_TO") or "").split(",")
    send_email_gmail(subject=subject, text=text, to_addrs=to_addrs)

    # Mark as seen only after successful send
    state.mark_seen([(j.get("id") or j.get("url")) for j in new_jobs])
    return len(new_jobs)


def main() -> None:
    interval = int(os.environ.get("ALERT_INTERVAL_SECONDS", "900"))  # 15m
    while True:
        try:
            run_once()
        except Exception as e:
            # keep worker alive; Render logs will show the exception
            print(f"[alerts] error: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
