"""Cross-run deduplication via a persistent SQLite store keyed by apply-URL hash.

A job is "new" only if its canonical apply URL has not been recorded before, so
repeated daily runs never append a posting twice. Use a file path that persists
(mount a volume in serverless deployments) to keep the dedup history.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .models import NormalizedJob, utcnow

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    key        TEXT PRIMARY KEY,
    apply_url  TEXT,
    company    TEXT,
    first_seen TEXT
);
"""


class Deduper:
    def __init__(self, db_path: str | Path = ":memory:"):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.conn.execute(_SCHEMA)
        self.conn.commit()
        self._lock = threading.Lock()

    def is_new(self, job: NormalizedJob) -> bool:
        """Atomically record the job; return True iff it was not seen before."""
        key = job.dedup_key()
        with self._lock:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO seen_jobs (key, apply_url, company, first_seen) "
                "VALUES (?, ?, ?, ?)",
                (key, job.apply_url, job.company, utcnow().isoformat()),
            )
            self.conn.commit()
            return cur.rowcount == 1

    def seen(self, job: NormalizedJob) -> bool:
        with self._lock:
            row = self.conn.execute(
                "SELECT 1 FROM seen_jobs WHERE key = ?", (job.dedup_key(),)
            ).fetchone()
        return row is not None

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Deduper":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
