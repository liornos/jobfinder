from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List


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
        "jobs.lever.co": {
            "organic_results": [{"link": "https://jobs.lever.co/contoso/789"}]
        },
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

    companies = pipeline.discover(
        cities=["NYC"], keywords=["dev"], sources=["greenhouse"], limit=1
    )

    assert len(companies) == 1
    assert len(calls) == 1  # additional provider/city loops short-circuit after limit


def test_discover_combines_providers_with_or(monkeypatch, serpapi_env):
    calls: List[dict] = []

    def fake_http(url: str, params=None, timeout: float = 25.0):
        calls.append(params or {})
        return {
            "organic_results": [
                {"link": "https://boards.greenhouse.io/acme/jobs/1"},
                {"link": "https://jobs.lever.co/contoso/2"},
            ]
        }

    monkeypatch.setattr(pipeline, "_http_get_json", fake_http)
    monkeypatch.setenv("SERPAPI_PROVIDER_MODE", "or")

    companies = pipeline.discover(
        cities=["Tel Aviv"],
        keywords=["python"],
        sources=["greenhouse", "lever"],
        limit=10,
    )

    assert len(calls) == 1
    q = calls[0].get("q", "")
    assert "site:boards.greenhouse.io" in q
    assert "site:jobs.lever.co" in q
    ids = {(c["provider"], c["org"]) for c in companies}
    assert ("greenhouse", "acme") in ids
    assert ("lever", "contoso") in ids


def test_discover_requires_api_key(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    companies = pipeline.discover(cities=["Paris"], keywords=["data"])
    assert companies == []


def test_scan_normalizes_and_dedupes(monkeypatch, provider_stub):
    now = datetime.now(timezone.utc)
    created_at_1 = (now - timedelta(days=3)).replace(microsecond=0).isoformat()
    created_at_2 = (now - timedelta(days=2)).replace(microsecond=0).isoformat()
    created_at_3 = (now - timedelta(days=1)).replace(microsecond=0).isoformat()
    jobs_by_provider = {
        "greenhouse": {
            "acme": [
                {
                    "id": "1",
                    "title": "Data Engineer",
                    "location": "New York, NY",
                    "url": "https://example.com/1",
                    "created_at": created_at_1,
                    "remote": False,
                },
                {
                    "id": "1",  # duplicate id should be removed
                    "title": "Data Engineer (dup)",
                    "location": "New York, NY",
                    "url": "https://example.com/1",
                    "created_at": created_at_2,
                    "remote": False,
                },
                {
                    "id": "2",
                    "title": "Backend Engineer",
                    "location": "New York, NY",
                    "url": "https://example.com/2",
                    "created_at": created_at_3,
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
        "greenhouse": {
            "acme": [
                {
                    "id": "gh-1",
                    "title": "GH Role",
                    "location": "Remote",
                    "url": "https://gh/1",
                }
            ]
        },
        "lever": {
            "contoso": [
                {
                    "id": "lv-1",
                    "title": "Lever Role",
                    "location": "Remote",
                    "url": "https://lv/1",
                }
            ]
        },
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


def test_refresh_and_query_jobs(monkeypatch, provider_stub, tmp_path):
    db_url = f"sqlite:///{(tmp_path / 'jobs.db').as_posix()}"
    monkeypatch.setenv("JOBFINDER_DATABASE_URL", db_url)

    provider_stub(
        {
            "greenhouse": {
                "acme": [
                    {
                        "id": "1",
                        "title": "Platform Engineer",
                        "location": "New York, NY",
                        "url": "https://example.com/1",
                        "created_at": "2025-01-01T00:00:00Z",
                    }
                ]
            }
        }
    )

    companies = [{"name": "Acme", "org": "acme", "provider": "greenhouse"}]
    summary = pipeline.refresh(
        companies=companies, cities=["New York"], keywords=["engineer"]
    )
    assert summary["jobs_written"] == 1

    results = pipeline.query_jobs(
        cities=["New York"], keywords=["engineer"], only_active=True, limit=50
    )
    assert len(results) == 1
    assert results[0]["id"] == "1"

    # Second refresh with no jobs should mark the existing one inactive
    provider_stub({"greenhouse": {"acme": []}})
    pipeline.refresh(companies=companies, cities=["New York"], keywords=["engineer"])

    active_results = pipeline.query_jobs(only_active=True, limit=50)
    assert active_results == []

    all_results = pipeline.query_jobs(only_active=False, limit=50)
    assert len(all_results) == 1
    assert all_results[0]["is_active"] is False


def test_query_jobs_applies_filters_before_limit(
    monkeypatch, provider_stub, temp_db_url
):
    provider_stub(
        {
            "greenhouse": {
                "acme": [
                    {
                        "id": "10",
                        "title": "Platform Engineer",
                        "location": "Haifa",
                        "url": "https://example.com/10",
                        "created_at": "2025-01-10T00:00:00Z",
                    },
                    {
                        "id": "09",
                        "title": "Backend Engineer",
                        "location": "Haifa",
                        "url": "https://example.com/9",
                        "created_at": "2025-01-09T00:00:00Z",
                    },
                    {
                        "id": "08",
                        "title": "Backend Engineer",
                        "location": "Haifa",
                        "url": "https://example.com/8",
                        "created_at": "2025-01-08T00:00:00Z",
                    },
                    {
                        "id": "07",
                        "title": "Backend Engineer",
                        "location": "Haifa",
                        "url": "https://example.com/7",
                        "created_at": "2025-01-07T00:00:00Z",
                    },
                    {
                        "id": "06",
                        "title": "Backend Engineer",
                        "location": "Haifa",
                        "url": "https://example.com/6",
                        "created_at": "2025-01-06T00:00:00Z",
                    },
                    {
                        "id": "05",
                        "title": "Tel Aviv Engineer",
                        "location": "Tel Aviv",
                        "url": "https://example.com/5",
                        "created_at": "2025-01-05T00:00:00Z",
                    },
                    {
                        "id": "04",
                        "title": "Tel Aviv Engineer",
                        "location": "Tel Aviv",
                        "url": "https://example.com/4",
                        "created_at": "2025-01-04T00:00:00Z",
                    },
                ]
            }
        }
    )

    companies = [{"name": "Acme", "org": "acme", "provider": "greenhouse"}]
    pipeline.refresh(companies=companies, cities=[], keywords=["engineer"])

    results = pipeline.query_jobs(cities=["Tel Aviv"], keywords=["engineer"], limit=2)
    assert [r["id"] for r in results] == ["05", "04"]
