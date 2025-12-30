from __future__ import annotations

import json
from pathlib import Path

from jobfinder import pipeline
from jobfinder.providers import greenhouse

from tests.unit.providers.contract import assert_normalized_job


def test_greenhouse_parsing_is_stable(monkeypatch):
    fixture = json.loads(
        Path("tests/fixtures/greenhouse_jobs.json").read_text(encoding="utf-8")
    )
    captured = {}

    def fake_get_json(url, params=None):
        captured["url"] = url
        captured["params"] = params
        return fixture

    monkeypatch.setattr(greenhouse, "get_json", fake_get_json)

    raw_jobs = greenhouse.fetch_jobs("acme", content=True, limit=50)
    assert raw_jobs
    assert raw_jobs[0]["title"] == "Data Engineer"
    assert raw_jobs[0]["url"].startswith("https://boards.greenhouse.io/")
    assert captured["params"] == {"content": "true"}

    company = {"name": "Acme", "org": "acme"}
    normalized = [pipeline._normalize_job(company, "greenhouse", j) for j in raw_jobs]
    for job in normalized:
        assert_normalized_job(job)
