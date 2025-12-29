from __future__ import annotations

from jobfinder.api import create_app


def test_discover_refresh_and_jobs(
    monkeypatch, serpapi_env, serpapi_stub, provider_stub, temp_db_url
):
    serpapi_stub(
        {
            "boards.greenhouse.io": {
                "organic_results": [{"link": "https://boards.greenhouse.io/acme"}]
            },
            "jobs.lever.co": {
                "organic_results": [{"link": "https://jobs.lever.co/contoso"}]
            },
        }
    )
    provider_stub(
        {
            "greenhouse": {
                "acme": [
                    {
                        "id": "1",
                        "title": "Backend Engineer",
                        "location": "Tel Aviv",
                        "url": "https://example.com/1",
                        "created_at": "2025-01-01T00:00:00Z",
                        "remote": False,
                    }
                ]
            },
            "lever": {
                "contoso": [
                    {
                        "id": "2",
                        "title": "Data Scientist",
                        "location": "Tel Aviv",
                        "url": "https://example.com/2",
                        "created_at": "2025-01-02T00:00:00Z",
                        "remote": True,
                    }
                ]
            },
        }
    )

    app = create_app()
    client = app.test_client()

    discover_resp = client.post(
        "/discover",
        json={
            "cities": ["Tel Aviv"],
            "keywords": ["python"],
            "sources": ["greenhouse", "lever"],
            "limit": 5,
        },
    )
    assert discover_resp.status_code == 200
    companies = discover_resp.get_json()["companies"]
    assert {c["org"] for c in companies} == {"acme", "contoso"}

    refresh_resp = client.post(
        "/refresh",
        json={"companies": companies, "cities": ["Tel Aviv"], "keywords": ["engineer"]},
    )
    assert refresh_resp.status_code == 200
    summary = refresh_resp.get_json()["summary"]
    assert summary["jobs_written"] == 2

    jobs_resp = client.get(
        "/jobs", query_string={"cities": "Tel Aviv", "keywords": "engineer"}
    )
    assert jobs_resp.status_code == 200
    results = jobs_resp.get_json()["results"]

    assert {r["id"] for r in results} == {"1", "2"}
    assert {r["company"] for r in results} == {"acme", "contoso"}

    # city list sent as comma string should still split correctly
    jobs_resp2 = client.get(
        "/jobs", query_string={"cities": "Tel Aviv,Herzliya", "keywords": "engineer"}
    )
    assert jobs_resp2.status_code == 200
    assert jobs_resp2.get_json()["count"] == 2
