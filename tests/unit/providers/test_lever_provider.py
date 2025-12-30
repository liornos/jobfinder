from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError

from jobfinder import pipeline
from jobfinder.providers import lever

from tests.unit.providers.contract import assert_normalized_job


def test_lever_parsing_is_stable(monkeypatch):
    fixture = json.loads(
        Path("tests/fixtures/lever_postings.json").read_text(encoding="utf-8")
    )

    monkeypatch.setattr(lever, "get_json", lambda url: fixture)

    raw_jobs = lever.fetch_jobs("lendbuzz", limit=50)
    assert raw_jobs
    assert raw_jobs[0]["title"] == "QA Engineer"
    assert raw_jobs[0]["url"].startswith("https://jobs.lever.co/")

    company = {"name": "Lendbuzz", "org": "lendbuzz"}
    normalized = [pipeline._normalize_job(company, "lever", j) for j in raw_jobs]
    for job in normalized:
        assert_normalized_job(job)


def test_lever_returns_empty_on_404(monkeypatch):
    from jobfinder.providers import _http

    def fake_urlopen(req, timeout=30, context=None):
        raise HTTPError(req.full_url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr(_http, "urlopen", fake_urlopen)

    jobs = lever.fetch_jobs("missing-org")
    assert jobs == []
