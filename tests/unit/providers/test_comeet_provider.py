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

    def fake_get_json(url, params=None):
        captured["url"] = url
        captured["params"] = params
        return fixture

    monkeypatch.setattr(comeet, "get_json", fake_get_json)
    monkeypatch.setattr(
        comeet,
        "_resolve_company_meta",
        lambda org, careers_url: ("liveu", "90.00C", "token123"),
    )

    raw_jobs = comeet.fetch_jobs("liveu", limit=50)
    assert raw_jobs
    assert raw_jobs[0]["id"] == "90.00C"
    assert "comeet" in captured["url"]
    assert captured["params"]["token"] == "token123"

    company = {"name": "LiveU", "org": "liveu"}
    normalized = [pipeline._normalize_job(company, "comeet", j) for j in raw_jobs]
    for job in normalized:
        assert_normalized_job(job)
