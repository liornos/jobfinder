from __future__ import annotations
import csv, sqlite3, json
from pathlib import Path
from typing import Iterable, Dict, Any


def export_csv(rows: Iterable[Dict[str, Any]], path: str) -> int:
    rows = list(rows)
    if not rows:
        Path(path).write_text("")
        return 0
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


def init_sqlite(path: str):
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, title TEXT, company TEXT, url TEXT, location TEXT,
            remote INTEGER, created_at TEXT, provider TEXT, extra TEXT, score INTEGER, reasons TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)")
    return conn


def upsert_rows_sqlite(conn, rows: Iterable[Dict[str, Any]]) -> int:
    count = 0
    for r in rows:
        conn.execute(
            "INSERT INTO jobs (id, title, company, url, location, remote, created_at, provider, extra, score, reasons) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, company=excluded.company, url=excluded.url, "
            "location=excluded.location, remote=excluded.remote, created_at=excluded.created_at, "
            "provider=excluded.provider, extra=excluded.extra, score=excluded.score, reasons=excluded.reasons",
            (
                r.get("id"),
                r.get("title"),
                r.get("company"),
                r.get("url"),
                r.get("location"),
                int(bool(r.get("remote"))) if r.get("remote") is not None else None,
                r.get("created_at"),
                r.get("provider"),
                json.dumps(r.get("extra")) if r.get("extra") is not None else None,
                r.get("score"),
                r.get("reasons"),
            ),
        )
        count += 1
    conn.commit()
    return count
