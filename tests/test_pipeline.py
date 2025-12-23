from __future__ import annotations

from typing import List

import pytest

from jobfinder import pipeline


def test_discover_builds_unique_companies(monkeypatch, serpapi_env, serpapi_stub):
    payloads = {
        "boards.greenhouse.io": {
            "organic_results": [
                {"link": "https://boards.greenhouse.io/acme/jobs/123?gh_src=abc"},
                {"link": "https://boards.greenhouse.io/acme/jobs/duplicate"},
                {"link": "https://boards.greenhouse.io/umbrella/jobs/456"},
            ]
        },
        "jobs.lever.co": {"organic_results": [{"link": "https://jobs.lever.co/contoso/789"}]},
    }
    serpapi_stub(payloads)

    companies = pipeline.discover(
        cities=["Tel Aviv"],
        keywords=["python"],
        sources=["greenhouse", "lever"],
        limit=10,
    )

    ids = {(c["provider"], c["org"]) for c in companies}
    assert ("greenhouse", "acme") in ids
    assert ("greenhouse", "umbrella") in ids
    assert ("lever", "contoso") in ids
    assert len(ids) == len(companies)  # deduped by provider/org


def test_discover_stops_after_limit(monkeypatch, serpapi_env):
    calls: List[dict] = []

    def fake_http(url: str, params=None, timeout: float = 25.0):
        calls.append(params or {})
        return {
            "organic_results": [
                {"link": "https://boards.greenhouse.io/first/jobs/1"},
                {"link": "https://boards.greenhouse.io/second/jobs/2"},
            ]
        }

    monkeypatch.setattr(pipeline, "_http_get_json", fake_http)

    companies = pipeline.discover(cities=["NYC"], keywords=["dev"], sources=["greenhouse"], limit=1)

    assert len(companies) == 1
    assert len(calls) == 1  # additional provider/city loops short-circuit after limit


def test_discover_requires_api_key(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        pipeline.discover(cities=["Paris"], keywords=["data"])


def test_scan_normalizes_and_dedupes(monkeypatch, provider_stub):
    jobs_by_provider = {
        "greenhouse": {
            "acme": [
                {
                    "id": "1",
                    "title": "Data Engineer",
                    "location": "New York, NY",
                    "url": "https://example.com/1",
                    "created_at": "2025-01-01T00:00:00Z",
                    "remote": False,
                },
                {
                    "id": "1",  # duplicate id should be removed
                    "title": "Data Engineer (dup)",
                    "location": "New York, NY",
                    "url": "https://example.com/1",
                    "created_at": "2025-01-02T00:00:00Z",
                    "remote": False,
                },
                {
                    "id": "2",
                    "title": "Backend Engineer",
                    "location": "New York, NY",
                    "url": "https://example.com/2",
                    "created_at": "2025-01-03T00:00:00Z",
                    "remote": True,
                },
            ]
        }
    }
    provider_stub(jobs_by_provider)

    companies = [{"name": "Acme", "org": "acme", "provider": "greenhouse"}]
    results = pipeline.scan(
        companies=companies,
        cities=["New York"],
        keywords=["engineer"],
        provider=None,
        remote="any",
        min_score=0,
        max_age_days=365,
    )

    assert len(results) == 2  # deduped id=1
    assert {r["id"] for r in results} == {"1", "2"}
    assert all(r["provider"] == "greenhouse" for r in results)
    assert all(r["company"] == "Acme" for r in results)


def test_scan_respects_provider_filter(monkeypatch, provider_stub):
    jobs_by_provider = {
        "greenhouse": {"acme": [{"id": "gh-1", "title": "GH Role", "location": "Remote", "url": "https://gh/1"}]},
        "lever": {"contoso": [{"id": "lv-1", "title": "Lever Role", "location": "Remote", "url": "https://lv/1"}]},
    }
    provider_stub(jobs_by_provider)

    companies = [
        {"name": "Acme", "org": "acme", "provider": "greenhouse"},
        {"name": "Contoso", "org": "contoso", "provider": "lever"},
    ]
    results = pipeline.scan(
        companies=companies,
        cities=[],
        keywords=[],
        provider="lever",
        remote="any",
        min_score=0,
        max_age_days=None,
    )

    assert len(results) == 1
    assert results[0]["id"] == "lv-1"
