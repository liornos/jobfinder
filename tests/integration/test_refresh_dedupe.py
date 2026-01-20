from __future__ import annotations


def test_refresh_dedupes_duplicate_jobs(client, provider_stub):
    provider_stub(
        {
            "greenhouse": {
                "acme": [
                    {
                        "id": "1",
                        "title": "Backend Engineer",
                        "location": "Tel Aviv",
                        "url": "https://gh/1",
                        "remote": False,
                    },
                    {
                        "id": "1",
                        "title": "Backend Engineer",
                        "location": "Tel Aviv",
                        "url": "https://gh/1",
                        "remote": False,
                    },
                ]
            }
        }
    )
    companies = [{"name": "Acme", "org": "acme", "provider": "greenhouse"}]

    refresh_resp = client.post("/refresh", json={"companies": companies})
    assert refresh_resp.status_code == 200
    summary = refresh_resp.get_json()["summary"]
    assert summary["jobs_seen"] == 1

    jobs_resp = client.get("/jobs", query_string={"provider": "greenhouse"})
    assert jobs_resp.status_code == 200
    data = jobs_resp.get_json()
    assert data["count"] == 1
    assert {row["id"] for row in data["results"]} == {"1"}
