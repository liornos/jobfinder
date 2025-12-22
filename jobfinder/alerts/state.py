from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Set


class AlertState:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_jobs (
                    job_id TEXT PRIMARY KEY,
                    first_seen_utc TEXT NOT NULL
                )
                """
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def already_seen(self, job_ids: Iterable[str]) -> Set[str]:
        ids = [i for i in job_ids if i]
        if not ids:
            return set()

        seen: Set[str] = set()
        with self._conn() as con:
            chunk = 900
            for i in range(0, len(ids), chunk):
                part = ids[i : i + chunk]
                q = f"SELECT job_id FROM seen_jobs WHERE job_id IN ({','.join(['?'] * len(part))})"
                for (job_id,) in con.execute(q, part):
                    seen.add(job_id)
        return seen

    def mark_seen(self, job_ids: Iterable[str]) -> int:
        ids = [i for i in job_ids if i]
        if not ids:
            return 0

        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        with self._conn() as con:
            for job_id in ids:
                try:
                    con.execute(
                        "INSERT INTO seen_jobs(job_id, first_seen_utc) VALUES(?, ?)",
                        (job_id, now),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    pass
        return inserted
