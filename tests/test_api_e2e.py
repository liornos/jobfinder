from __future__ import annotations

from jobfinder.api import create_app


def test_discover_and_scan_endpoints(monkeypatch, serpapi_env, serpapi_stub, provider_stub):
    serpapi_stub(
        {
            "boards.greenhouse.io": {"organic_results": [{"link": "https://boards.greenhouse.io/acme"}]},
            "jobs.lever.co": {"organic_results": [{"link": "https://jobs.lever.co/contoso"}]},
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
        json={"cities": ["Tel Aviv"], "keywords": ["python"], "sources": ["greenhouse", "lever"], "limit": 5},
    )
    assert discover_resp.status_code == 200
    companies = discover_resp.get_json()["companies"]
    assert {c["org"] for c in companies} == {"acme", "contoso"}

    scan_resp = client.post("/scan", json={"companies": companies, "cities": ["Tel Aviv"], "keywords": ["engineer"]})
    assert scan_resp.status_code == 200
    results = scan_resp.get_json()["results"]

    assert {r["id"] for r in results} == {"1", "2"}
    assert {r["company"] for r in results} == {"acme", "contoso"}
