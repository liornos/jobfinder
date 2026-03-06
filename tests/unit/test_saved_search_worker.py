from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from jobfinder import db, pipeline
from jobfinder.alerts import saved_search_worker as worker


def test_saved_search_worker_sends_only_new_jobs(monkeypatch, tmp_path):
    db_path = tmp_path / "alerts_worker.db"
    monkeypatch.setenv("JOBFINDER_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    db.init_db()

    with db.session_scope() as session:
        alert, created = db.upsert_saved_search_alert(
            session,
            email="dev@example.com",
            cities=["Tel Aviv"],
            title_keywords=["Backend"],
            frequency_minutes=5,
            send_limit=100,
        )
        assert created is True
        alert_id = int(alert.id)

    sample_jobs = [
        {
            "id": "j-1",
            "title": "Backend Engineer",
            "company": "Acme",
            "location": "Tel Aviv",
            "provider": "lever",
            "url": "https://example.com/jobs/1",
            "created_at": "2026-02-14T09:00:00+00:00",
        },
        {
            "id": "j-2",
            "title": "Platform Engineer",
            "company": "Beta",
            "location": "Tel Aviv",
            "provider": "greenhouse",
            "url": "https://example.com/jobs/2",
            "created_at": "2026-02-14T09:30:00+00:00",
        },
    ]

    sent_calls = []

    def fake_query_jobs(**kwargs):
        assert kwargs["cities"] == ["Tel Aviv"]
        assert kwargs["title_keywords"] == ["Backend"]
        return list(sample_jobs)

    def fake_send_email_gmail(*, subject, text, to_addrs):
        sent_calls.append({"subject": subject, "text": text, "to_addrs": to_addrs})

    monkeypatch.setattr(pipeline, "query_jobs", fake_query_jobs)
    monkeypatch.setattr(worker, "send_email_gmail", fake_send_email_gmail)

    first = worker.run_due_alerts_once(batch_limit=20)
    assert first["processed"] == 1
    assert first["sent_alerts"] == 1
    assert first["sent_jobs"] == 2
    assert len(sent_calls) == 1

    with db.session_scope() as session:
        row = db.get_saved_search_alert(session, alert_id=alert_id)
        assert row is not None
        row.next_run_at = datetime.now(timezone.utc)

    second = worker.run_due_alerts_once(batch_limit=20)
    assert second["processed"] == 1
    assert second["noop"] == 1
    assert second["sent_alerts"] == 0
    assert second["sent_jobs"] == 0
    assert len(sent_calls) == 1

    with db.session_scope() as session:
        seen_rows = list(
            session.scalars(
                select(db.AlertSeenJob).where(db.AlertSeenJob.alert_id == alert_id)
            ).all()
        )
        assert len(seen_rows) == 2


def test_deleted_alert_is_not_processed(monkeypatch, tmp_path):
    db_path = tmp_path / "alerts_worker_delete.db"
    monkeypatch.setenv("JOBFINDER_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    db.init_db()

    with db.session_scope() as session:
        alert, _ = db.upsert_saved_search_alert(
            session,
            email="dev@example.com",
            cities=["Tel Aviv"],
            title_keywords=["Backend"],
        )
        alert_id = int(alert.id)
        deleted = db.delete_saved_search_alert(
            session, alert_id=alert_id, email="dev@example.com"
        )
        assert deleted is True

    def fail_query_jobs(**kwargs):  # pragma: no cover - should not run
        raise AssertionError("query_jobs should not be called for deleted alert")

    monkeypatch.setattr(pipeline, "query_jobs", fail_query_jobs)

    summary = worker.run_due_alerts_once(batch_limit=20)
    assert summary["processed"] == 0
    assert summary["due"] == 0
