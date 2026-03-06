from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from jobfinder import db, pipeline

from .emailer_gmail import send_email_gmail

log = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _job_key(row: Dict[str, Any]) -> str:
    for key in ("job_key", "id", "url"):
        val = str(row.get(key) or "").strip()
        if val:
            return val
    return ""


def _fmt_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except Exception:
        return ""


def _render_email_body(alert: db.SavedSearchAlert, jobs: List[Dict[str, Any]]) -> str:
    lines = [
        f"JobFinder alert #{alert.id}",
        f"Generated at: {_utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]
    if alert.name:
        lines.append(f"Name: {alert.name}")
    if alert.cities:
        lines.append("Cities: " + ", ".join(alert.cities))
    if alert.title_keywords:
        lines.append("Title keywords: " + ", ".join(alert.title_keywords))
    if alert.keywords:
        lines.append("Keywords: " + ", ".join(alert.keywords))
    lines.extend(["", f"New jobs: {len(jobs)}", ""])

    for idx, job in enumerate(jobs[:80], start=1):
        lines.append(
            f"{idx}. {str(job.get('title') or 'Untitled')} - {str(job.get('company') or 'Unknown')}"
        )
        location = str(job.get("location") or "").strip()
        provider = str(job.get("provider") or "").strip()
        created = _fmt_date(job.get("created_at"))
        url = str(job.get("url") or "").strip()
        if location:
            lines.append(f"   Location: {location}")
        if provider:
            lines.append(f"   Provider: {provider}")
        if created:
            lines.append(f"   Date: {created}")
        if url:
            lines.append(f"   Link: {url}")
        lines.append("")

    if len(jobs) > 80:
        lines.append("Only the first 80 jobs are listed in this email.")
    return "\n".join(lines).rstrip() + "\n"


def _build_query(alert: db.SavedSearchAlert) -> Dict[str, Any]:
    return {
        "provider": alert.provider or None,
        "remote": alert.remote or "any",
        "min_score": int(alert.min_score or 0),
        "max_age_days": alert.max_age_days,
        "cities": list(alert.cities or []),
        "keywords": list(alert.keywords or []),
        "title_keywords": list(alert.title_keywords or []),
        "only_active": bool(alert.only_active),
        "lite": True,
        "limit": int(alert.send_limit or 200),
        "offset": 0,
    }


def _run_single_alert(
    *, alert_id: int, run_time: Optional[datetime] = None
) -> Dict[str, Any]:
    now = run_time or _utcnow()
    with db.session_scope() as session:
        alert = db.get_saved_search_alert(session, alert_id=alert_id)
        if alert is None:
            return {"status": "missing", "alert_id": alert_id, "sent": 0}
        if not alert.is_active:
            return {"status": "inactive", "alert_id": alert_id, "sent": 0}

        try:
            jobs = pipeline.query_jobs(**_build_query(alert))
            keys = [_job_key(row) for row in jobs]
            keys = [k for k in keys if k]
            seen = db.get_seen_job_keys_for_alert(
                session, alert_id=alert.id, job_keys=keys
            )
            new_jobs = [
                row for row in jobs if (key := _job_key(row)) and key not in seen
            ]

            if not new_jobs:
                db.record_alert_delivery(
                    session,
                    alert_id=alert.id,
                    status="noop",
                    jobs_count=0,
                    subject=f"JobFinder alert #{alert.id}",
                )
                db.touch_saved_search_alert_run(
                    session, alert=alert, ran_at=now, sent=False
                )
                return {"status": "noop", "alert_id": alert.id, "sent": 0}

            subject = f"JobFinder alert: {len(new_jobs)} new jobs"
            send_email_gmail(
                subject=subject,
                text=_render_email_body(alert, new_jobs),
                to_addrs=[alert.user.email],
            )
            db.mark_seen_job_keys_for_alert(
                session,
                alert_id=alert.id,
                job_keys=[_job_key(row) for row in new_jobs],
                first_seen_at=now,
            )
            db.record_alert_delivery(
                session,
                alert_id=alert.id,
                status="sent",
                jobs_count=len(new_jobs),
                subject=subject,
            )
            db.touch_saved_search_alert_run(session, alert=alert, ran_at=now, sent=True)
            return {"status": "sent", "alert_id": alert.id, "sent": len(new_jobs)}
        except Exception as exc:
            db.record_alert_delivery(
                session,
                alert_id=alert.id,
                status="error",
                jobs_count=0,
                subject=f"JobFinder alert #{alert.id}",
                error_text=str(exc),
            )
            db.touch_saved_search_alert_run(
                session, alert=alert, ran_at=now, sent=False
            )
            log.exception("Saved-search alert %s failed: %s", alert.id, exc)
            return {"status": "error", "alert_id": alert.id, "sent": 0}


def run_due_alerts_once(
    *, now: Optional[datetime] = None, batch_limit: int = 200
) -> Dict[str, Any]:
    db.init_db()
    now_val = now or _utcnow()
    with db.session_scope() as session:
        alert_ids = db.list_due_saved_search_alert_ids(
            session, now=now_val, limit=batch_limit
        )

    summary = {
        "processed": 0,
        "sent_alerts": 0,
        "sent_jobs": 0,
        "noop": 0,
        "error": 0,
        "inactive": 0,
        "missing": 0,
    }
    for alert_id in alert_ids:
        result = _run_single_alert(alert_id=alert_id, run_time=now_val)
        summary["processed"] += 1
        status = str(result.get("status") or "")
        if status == "sent":
            summary["sent_alerts"] += 1
        elif status in summary:
            summary[status] = int(summary.get(status, 0)) + 1
        summary["sent_jobs"] += int(result.get("sent", 0))

    summary["due"] = len(alert_ids)
    return summary


def run_forever(*, interval_seconds: int = 900, batch_limit: int = 200) -> None:
    interval = max(5, int(interval_seconds or 900))
    while True:
        try:
            summary = run_due_alerts_once(batch_limit=batch_limit)
            log.info("Saved-search alerts run: %s", summary)
        except Exception as exc:
            log.exception("Saved-search alerts loop failed: %s", exc)
        time.sleep(interval)


def main() -> None:
    mode = (os.getenv("ALERTS_RUN_MODE") or "once").strip().lower()
    batch_limit = int(os.getenv("ALERTS_BATCH_LIMIT", "200"))
    if mode == "loop":
        interval_seconds = int(os.getenv("ALERTS_INTERVAL_SECONDS", "900"))
        run_forever(interval_seconds=interval_seconds, batch_limit=batch_limit)
        return
    summary = run_due_alerts_once(batch_limit=batch_limit)
    print(summary)


if __name__ == "__main__":
    main()
