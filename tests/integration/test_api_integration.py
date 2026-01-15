from __future__ import annotations


def test_refresh_inserts_jobs(client, provider_stub):
    provider_stub(
        {
            "greenhouse": {
                "acme": [
                    {
                        "id": "1",
                        "title": "Data Engineer",
                        "location": "Tel Aviv",
                        "url": "https://gh/1",
                        "remote": False,
                    },
                    {
                        "id": "2",
                        "title": "QA Engineer",
                        "location": "Haifa",
                        "url": "https://gh/2",
                        "remote": False,
                    },
                ]
            }
        }
    )
    companies = [{"name": "Acme", "org": "acme", "provider": "greenhouse"}]

    refresh_resp = client.post(
        "/refresh", json={"companies": companies, "cities": ["Tel Aviv"]}
    )
    assert refresh_resp.status_code == 200
    assert refresh_resp.get_json()["summary"]["jobs_written"] == 2

    jobs_resp = client.get("/jobs", query_string={"provider": "greenhouse"})
    assert jobs_resp.status_code == 200
    data = jobs_resp.get_json()
    assert data["count"] == 2
    assert {r["id"] for r in data["results"]} == {"1", "2"}


def test_debug_refresh_includes_report(client, provider_stub):
    provider_stub(
        {
            "greenhouse": {
                "acme": [
                    {
                        "id": "1",
                        "title": "Data Engineer",
                        "location": "Tel Aviv",
                        "url": "https://gh/1",
                        "remote": False,
                    },
                    {
                        "id": "2",
                        "title": "QA Engineer",
                        "location": "Haifa",
                        "url": "https://gh/2",
                        "remote": False,
                    },
                ]
            }
        }
    )
    companies = [{"name": "Acme", "org": "acme", "provider": "greenhouse"}]

    refresh_resp = client.post(
        "/debug/refresh", json={"companies": companies, "cities": ["Tel Aviv"]}
    )
    assert refresh_resp.status_code == 200
    payload = refresh_resp.get_json()
    summary = payload["summary"]
    assert summary["jobs_written"] == 2
    assert summary["companies_total"] == 1
    assert summary["companies_failed"] == 0

    rows = payload["companies"]
    assert len(rows) == 1
    row = rows[0]
    assert row["provider"] == "greenhouse"
    assert row["org"] == "acme"
    assert row["status"] == "ok"
    assert row["jobs_fetched"] == 2
    assert row["jobs_written"] == 2
    assert row["elapsed_ms"] >= 0


def test_refresh_updates_existing_jobs(client, provider_stub):
    companies = [{"name": "Acme", "org": "acme", "provider": "greenhouse"}]

    provider_stub(
        {
            "greenhouse": {
                "acme": [
                    {
                        "id": "1",
                        "title": "Data Engineer",
                        "location": "Tel Aviv",
                        "url": "https://gh/1",
                        "remote": False,
                    }
                ]
            }
        }
    )
    first = client.post("/refresh", json={"companies": companies})
    assert first.status_code == 200

    provider_stub(
        {
            "greenhouse": {
                "acme": [
                    {
                        "id": "1",
                        "title": "Senior Data Engineer",
                        "location": "Tel Aviv",
                        "url": "https://gh/1",
                        "remote": False,
                    }
                ]
            }
        }
    )
    second = client.post("/refresh", json={"companies": companies})
    assert second.status_code == 200

    jobs_resp = client.get("/jobs", query_string={"provider": "greenhouse"})
    data = jobs_resp.get_json()
    assert data["count"] == 1
    assert data["results"][0]["title"] == "Senior Data Engineer"


def test_refresh_report_includes_failure(client, monkeypatch):
    from types import SimpleNamespace

    from jobfinder import pipeline

    def fake_import(provider: str):
        if provider == "lever":
            raise RuntimeError("boom")
        return SimpleNamespace(
            fetch_jobs=lambda org=None, **_: [
                {"id": "1", "title": "X", "location": "Tel Aviv", "url": "u"}
            ]
        )

    monkeypatch.setattr(pipeline, "_import_provider", fake_import)

    companies = [
        {"name": "Good", "org": "good", "provider": "greenhouse"},
        {"name": "Bad", "org": "bad", "provider": "lever"},
    ]

    resp = client.post("/debug/refresh", json={"companies": companies})
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["summary"]["companies_total"] == 2
    assert data["summary"]["companies_ok"] == 1
    assert data["summary"]["companies_failed"] == 1

    by_org = {r["org"]: r for r in data["companies"]}
    assert by_org["good"]["status"] == "ok"
    assert by_org["bad"]["status"] == "error"
    assert "boom" in by_org["bad"]["error"]


def test_query_filters_provider_city_and_keyword(client, provider_stub):
    provider_stub(
        {
            "greenhouse": {
                "acme": [
                    {
                        "id": "gh-1",
                        "title": "Data Engineer",
                        "location": "Tel Aviv",
                        "url": "https://gh/1",
                        "remote": False,
                    },
                    {
                        "id": "gh-2",
                        "title": "QA Engineer",
                        "location": "Tel Aviv",
                        "url": "https://gh/2",
                        "remote": False,
                    },
                ]
            },
            "lever": {
                "contoso": [
                    {
                        "id": "lv-1",
                        "title": "Data Engineer",
                        "location": "Tel Aviv",
                        "url": "https://lv/1",
                        "remote": False,
                    }
                ]
            },
        }
    )
    companies = [
        {"name": "Acme", "org": "acme", "provider": "greenhouse"},
        {"name": "Contoso", "org": "contoso", "provider": "lever"},
    ]

    refresh_resp = client.post("/refresh", json={"companies": companies})
    assert refresh_resp.status_code == 200

    jobs_resp = client.get(
        "/jobs",
        query_string={
            "provider": "greenhouse",
            "cities": "Tel Aviv",
            "keywords": "data",
            "min_score": 35,
        },
    )
    assert jobs_resp.status_code == 200
    data = jobs_resp.get_json()
    assert {r["id"] for r in data["results"]} == {"gh-1"}
