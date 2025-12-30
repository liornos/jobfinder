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
