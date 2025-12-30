from __future__ import annotations

import json
from pathlib import Path

from jobfinder import pipeline
from jobfinder.providers import comeet

from tests.unit.providers.contract import assert_normalized_job


def test_comeet_parsing_is_stable(monkeypatch):
    fixture = json.loads(
        Path("tests/fixtures/comeet_positions.json").read_text(encoding="utf-8")
    )
    captured = {}

    def fake_get_json(url):
        captured["url"] = url
        return fixture

    monkeypatch.setattr(comeet, "get_json", fake_get_json)

    raw_jobs = comeet.fetch_jobs("liveu", limit=50)
    assert raw_jobs
    assert raw_jobs[0]["id"] == "90.00C"
    assert "comeet.com" in captured["url"]

    company = {"name": "LiveU", "org": "liveu"}
    normalized = [pipeline._normalize_job(company, "comeet", j) for j in raw_jobs]
    for job in normalized:
        assert_normalized_job(job)
