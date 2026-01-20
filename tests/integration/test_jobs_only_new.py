from __future__ import annotations

from jobfinder.alerts.state import AlertState


def test_jobs_only_new_filters_seen(client, provider_stub, tmp_path, monkeypatch):
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

    refresh_resp = client.post("/refresh", json={"companies": companies})
    assert refresh_resp.status_code == 200

    state_db = tmp_path / "alerts.db"
    monkeypatch.setenv("ALERT_STATE_DB", state_db.as_posix())
    state = AlertState(state_db)
    state.mark_seen(["1"])

    jobs_resp = client.get("/jobs", query_string={"provider": "greenhouse"})
    assert jobs_resp.status_code == 200
    assert jobs_resp.get_json()["count"] == 2

    only_new_resp = client.get(
        "/jobs", query_string={"provider": "greenhouse", "only_new": "true"}
    )
    assert only_new_resp.status_code == 200
    data = only_new_resp.get_json()
    assert data["count"] == 1
    assert {row["id"] for row in data["results"]} == {"2"}
