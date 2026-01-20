from __future__ import annotations

from types import SimpleNamespace

from jobfinder import pipeline


def test_refresh_partial_provider_failure_keeps_working(client, monkeypatch):
    def fetch_ok(org=None, **_):
        return [
            {
                "id": "1",
                "title": "Data Engineer",
                "location": "Tel Aviv",
                "url": "https://gh/1",
                "remote": False,
            }
        ]

    def fetch_fail(*args, **kwargs):
        raise RuntimeError("boom")

    def fake_import(provider: str):
        if provider == "greenhouse":
            return SimpleNamespace(fetch_jobs=fetch_ok)
        if provider == "lever":
            return SimpleNamespace(fetch_jobs=fetch_fail)
        return None

    monkeypatch.setattr(pipeline, "_import_provider", fake_import)

    companies = [
        {"name": "Acme", "org": "acme", "provider": "greenhouse"},
        {"name": "Badco", "org": "badco", "provider": "lever"},
    ]

    refresh_resp = client.post("/refresh", json={"companies": companies})
    assert refresh_resp.status_code == 200
    summary = refresh_resp.get_json()["summary"]
    assert summary["jobs_written"] == 1

    jobs_resp = client.get("/jobs", query_string={"provider": "greenhouse"})
    assert jobs_resp.status_code == 200
    assert jobs_resp.get_json()["count"] == 1

    lever_resp = client.get("/jobs", query_string={"provider": "lever"})
    assert lever_resp.status_code == 200
    assert lever_resp.get_json()["count"] == 0
