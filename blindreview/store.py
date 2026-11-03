"""SQLite journal with atomic idempotent job creation and state transitions."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .common import ProtocolError, TERMINAL, canonical_json


class JobStore:
    def __init__(self, db_file: Path) -> None:
        db_file.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_file), check_same_thread=False, timeout=15)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock, self._db:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA busy_timeout=15000")
            self._db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY, request TEXT NOT NULL,
                state TEXT NOT NULL, created_at REAL NOT NULL,
                started_at REAL, finished_at REAL, heartbeat_at REAL,
                progress_at REAL, pid INTEGER, result_sha256 TEXT,
                error TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0
            )""")

    def submit(self, job: dict[str, str]) -> tuple[dict[str, Any], bool]:
        """Idempotent insert guarded by SQLite's primary key even across processes."""
        with self._lock, self._db:
            now = time.time()
            cur = self._db.execute("""INSERT OR IGNORE INTO jobs
                (job_id,request,state,created_at,heartbeat_at) VALUES (?,?,?,?,?)""",
                (job["job_id"], canonical_json(job), "QUEUED", now, now))
            row = self._db.execute("SELECT * FROM jobs WHERE job_id=?", (job["job_id"],)).fetchone()
            if not row or row["request"] != canonical_json(job):
                raise ProtocolError("Job ID already exists with a different request")
            return self._serialize(row), cur.rowcount == 1

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            return self._serialize(row) if row else None

    @staticmethod
    def _serialize(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["request"] = json.loads(record["request"])
        record["cancel_requested"] = bool(record["cancel_requested"])
        return record

    def transition(self, job_id: str, new_state: str, *, expected: tuple[str, ...] | None = None,
                   error: str | None = None, pid: int | None = None,
                   result_sha256: str | None = None) -> bool:
        """Atomic compare-and-swap state change across SQLite connections."""
        with self._lock, self._db:
            old = self._db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if not old or old["state"] in TERMINAL:
                return False
            allowed = expected if expected is not None else (old["state"],)
            if old["state"] not in allowed:
                return False
            now = time.time()
            started = now if new_state == "RUNNING" else old["started_at"]
            ended = now if new_state in TERMINAL else old["finished_at"]
            placeholders = ",".join("?" for _ in allowed)
            cur = self._db.execute(f"""UPDATE jobs SET state=?, started_at=?, finished_at=?,
                heartbeat_at=?, progress_at=?, pid=?, error=?, result_sha256=?
                WHERE job_id=? AND state IN ({placeholders})""",
                (new_state, started, ended, now, now,
                 pid if pid is not None else old["pid"], error, result_sha256,
                 job_id, *allowed))
            return cur.rowcount == 1

    def set_pid(self, job_id: str, pid: int) -> None:
        with self._lock, self._db:
            self._db.execute("UPDATE jobs SET pid=? WHERE job_id=? AND state='RUNNING'", (pid, job_id))

    def heartbeat(self, job_id: str, *, progress: bool = False) -> None:
        with self._lock, self._db:
            if progress:
                self._db.execute("UPDATE jobs SET heartbeat_at=?, progress_at=? WHERE job_id=? AND state='RUNNING'",
                                 (time.time(), time.time(), job_id))
            else:
                self._db.execute("UPDATE jobs SET heartbeat_at=? WHERE job_id=? AND state='RUNNING'",
                                 (time.time(), job_id))

    def cancel(self, job_id: str) -> bool:
        with self._lock, self._db:
            row = self.get(job_id)
            if not row or row["state"] in TERMINAL:
                return False
            self._db.execute("UPDATE jobs SET cancel_requested=1 WHERE job_id=?", (job_id,))
            if row["state"] == "QUEUED":
                self.transition(job_id, "CANCELLED", expected=("QUEUED",), error="Cancelled before execution")
            return True

    def unfinished(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM jobs WHERE state NOT IN ('COMPLETED','FAILED','TIMED_OUT','CANCELLED','INTERRUPTED')").fetchall()
            return [self._serialize(r) for r in rows]

    def recover(self) -> list[str]:
        """Preserve queued jobs; fail closed on in-flight jobs after process restart.

        An interrupted child may still exist after SIGKILL; never silently spawn a
        duplicate. Operator can inspect/terminate orphans before submitting new ID.
        """
        interrupted = []
        for job in self.unfinished():
            if job["state"] == "RUNNING":
                if self.transition(job["job_id"], "INTERRUPTED", expected=("RUNNING",),
                                   error="Worker restarted: confirm original subprocess is stopped before retry"):
                    interrupted.append(job["job_id"])
        return interrupted

    def close(self) -> None:
        with self._lock:
            self._db.close()
