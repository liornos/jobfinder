from __future__ import annotations

from typing import Any, Dict, List

import jobfinder.api as api_module
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


def test_search_email_route_renders_page(client):
    resp = client.get("/search-email")
    assert resp.status_code == 200
    assert b'id="emailInput"' in resp.data


def test_jobs_email_sends_filtered_results(monkeypatch, client):
    captured_query: Dict[str, Any] = {}
    captured_email: Dict[str, Any] = {}

    def fake_query_jobs(**kwargs):
        captured_query.update(kwargs)
        return [
            {
                "id": "1",
                "title": "Backend Engineer",
                "company": "Acme",
                "location": "Tel Aviv",
                "provider": "lever",
                "url": "https://example.com/jobs/1",
            }
        ]

    def fake_send_email_gmail(*, subject, text, to_addrs):
        captured_email["subject"] = subject
        captured_email["text"] = text
        captured_email["to_addrs"] = list(to_addrs)

    monkeypatch.setattr(pipeline, "query_jobs", fake_query_jobs)
    monkeypatch.setattr(api_module, "send_email_gmail", fake_send_email_gmail)

    resp = client.post(
        "/jobs/email",
        json={
            "email": "dev@example.com",
            "cities": "Tel Aviv",
            "title_keywords": ["Backend"],
            "fast": True,
            "lite": True,
            "limit": 120,
        },
    )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["sent"] is True
    assert data["count"] == 1
    assert captured_query["cities"] == ["Tel Aviv"]
    assert captured_query["title_keywords"] == ["Backend"]
    assert captured_query["limit"] == 120
    assert captured_email["to_addrs"] == ["dev@example.com"]
    assert "JobFinder" in captured_email["subject"]
    assert "Backend Engineer" in captured_email["text"]


def test_jobs_email_requires_valid_email(client):
    resp = client.post(
        "/jobs/email",
        json={"email": "not-an-email", "cities": "Tel Aviv"},
    )
    assert resp.status_code == 400
    assert "Invalid email" in resp.get_json()["error"]


def test_saved_alert_create_list_delete_flow(client):
    create_resp = client.post(
        "/alerts/searches",
        json={
            "email": "dev@example.com",
            "cities": "Tel Aviv",
            "title_keywords": ["Backend"],
            "frequency_minutes": 30,
            "send_limit": 100,
        },
    )
    assert create_resp.status_code == 200
    create_data = create_resp.get_json()
    assert create_data["created"] is True
    alert_id = int(create_data["alert"]["id"])

    list_resp = client.get("/alerts/searches?email=dev@example.com")
    assert list_resp.status_code == 200
    list_data = list_resp.get_json()
    assert list_data["count"] == 1
    assert list_data["alerts"][0]["id"] == alert_id
    assert list_data["alerts"][0]["title_keywords"] == ["Backend"]

    delete_resp = client.delete(f"/alerts/searches/{alert_id}?email=dev@example.com")
    assert delete_resp.status_code == 200
    assert delete_resp.get_json()["deleted"] is True

    after_delete = client.get("/alerts/searches?email=dev@example.com")
    assert after_delete.status_code == 200
    assert after_delete.get_json()["count"] == 0


def test_saved_alert_duplicate_create_updates_existing(client):
    first = client.post(
        "/alerts/searches",
        json={
            "email": "dev@example.com",
            "cities": "Tel Aviv",
            "title_keywords": ["Backend"],
            "frequency_minutes": 60,
        },
    )
    assert first.status_code == 200
    first_data = first.get_json()
    alert_id = int(first_data["alert"]["id"])
    assert first_data["created"] is True

    second = client.post(
        "/alerts/searches",
        json={
            "email": "dev@example.com",
            "cities": "Tel Aviv",
            "title_keywords": ["Backend"],
            "frequency_minutes": 15,
        },
    )
    assert second.status_code == 200
    second_data = second.get_json()
    assert second_data["created"] is False
    assert int(second_data["alert"]["id"]) == alert_id
    assert int(second_data["alert"]["frequency_minutes"]) == 15


def test_alerts_run_endpoint_calls_worker_when_enabled(monkeypatch, client):
    monkeypatch.setenv("ALLOW_ALERTS_RUN_ENDPOINT", "1")

    def fake_run_due_alerts_once(*, batch_limit):
        assert batch_limit == 12
        return {"processed": 1, "sent_alerts": 1, "sent_jobs": 3}

    monkeypatch.setattr(api_module, "run_due_alerts_once", fake_run_due_alerts_once)

    resp = client.post("/alerts/run", json={"batch_limit": 12})
    assert resp.status_code == 200
    assert resp.get_json()["summary"]["sent_jobs"] == 3


def test_alerts_run_endpoint_disabled_by_default(client):
    resp = client.post("/alerts/run", json={})
    assert resp.status_code == 403
    assert "disabled" in resp.get_json()["error"].lower()
