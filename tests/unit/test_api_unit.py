from __future__ import annotations

from typing import Any, Dict, List

import jobfinder.pipeline as pipeline


def test_healthz_returns_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True}


def test_discover_calls_pipeline_and_returns_companies(monkeypatch, client):
    captured: Dict[str, Any] = {}

    def fake_discover(*, cities, keywords, sources, limit):
        captured["cities"] = cities
        captured["keywords"] = keywords
        captured["sources"] = sources
        captured["limit"] = limit
        return [{"provider": "lever", "org": "acme"}]

    monkeypatch.setattr(pipeline, "discover", fake_discover)
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")

    resp = client.post(
        "/discover",
        json={
            "cities": "Tel Aviv,Haifa",
            "keywords": ["python"],
            "sources": "lever",
            "limit": 3,
        },
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["companies"][0]["org"] == "acme"
    assert captured["cities"] == ["Tel Aviv", "Haifa"]
    assert captured["keywords"] == ["python"]
    assert captured["sources"] == ["lever"]
    assert captured["limit"] == 3


def test_discover_returns_500_on_exception(monkeypatch, client):
    def bad_discover(*, cities, keywords, sources, limit):
        raise RuntimeError("boom")

    monkeypatch.setattr(pipeline, "discover", bad_discover)
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")

    resp = client.post("/discover", json={"cities": ["Tel Aviv"]})
    assert resp.status_code == 500
    assert "boom" in resp.get_json()["error"]


def test_scan_calls_pipeline_and_filters_title_keywords(monkeypatch, client):
    fake_jobs: List[Dict[str, Any]] = [
        {"id": "x1", "company": "Acme", "title": "QA Engineer"},
        {"id": "x2", "company": "Acme", "title": "Designer"},
    ]
    captured: Dict[str, Any] = {}

    def fake_scan(**kwargs):
        captured.update(kwargs)
        return fake_jobs

    monkeypatch.setattr(pipeline, "scan", fake_scan)

    resp = client.post(
        "/scan",
        json={
            "companies": [{"provider": "lever", "org": "x"}],
            "cities": "Tel Aviv",
            "title_keywords": ["qa"],
        },
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert [r["id"] for r in data["results"]] == ["x1"]
    assert captured["cities"] == ["Tel Aviv"]
    assert captured["companies"] == [{"provider": "lever", "org": "x"}]


def test_scan_returns_500_on_pipeline_exception(monkeypatch, client):
    def bad_scan(**kwargs):
        raise ValueError("nope")

    monkeypatch.setattr(pipeline, "scan", bad_scan)

    resp = client.post("/scan", json={"companies": []})
    assert resp.status_code == 500
    assert resp.get_json()["error"] == "nope"
