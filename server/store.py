"""Persistence: SQLite (WAL, one connection per call) for job state, JSON files per job for requests and results.

runs/jobs.db            one row per job: status, stage, progress, message, and `meta` (JSON: round, k, rounds,
                        infeasible, warnings, reach, cache_key, elapsed ...)
runs/<job>/request.json the request as sent
runs/<job>/results.json the ranked candidates
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Anchored to the repo root (not the working directory); RUNS_DIR overrides it (tests use a temp folder).
DEFAULT_RUNS_DIR = Path(os.environ.get("RUNS_DIR") or Path(__file__).resolve().parent.parent / "runs")
DEFAULT_DB_PATH = DEFAULT_RUNS_DIR / "jobs.db"

FINISHED = ("done", "failed", "cancelled")


def get_db_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """A fresh connection (never shared across threads) with row access and a busy timeout."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Create the jobs table (WAL mode); add the `meta` column to databases made before it existed."""
    conn = get_db_connection(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    stage TEXT,
                    progress REAL DEFAULT 0.0,
                    message TEXT,
                    updated_at TIMESTAMP NOT NULL,
                    meta TEXT
                )
                """
            )
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
        if "meta" not in cols:
            with conn:
                conn.execute("ALTER TABLE jobs ADD COLUMN meta TEXT")
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_job(
    job_id: str,
    status: str = "queued",
    stage: str | None = None,
    progress: float = 0.0,
    message: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert (or reset) a job record."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO jobs (job_id, status, stage, progress, message, updated_at, meta)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    status = excluded.status, stage = excluded.stage, progress = excluded.progress,
                    message = excluded.message, updated_at = excluded.updated_at
                """,
                (job_id, status, stage, float(progress), message, _now(), json.dumps(meta or {}, allow_nan=False)),
            )
    finally:
        conn.close()
    return get_job(job_id, db_path=db_path)


def update_job_status(
    job_id: str,
    status: str | None = None,
    stage: str | None = None,
    progress: float | None = None,
    message: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Update the given fields (and merge `meta`), inserting the row if it does not exist."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute("SELECT meta FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            conn.close()
            return create_job(job_id, status or "running", stage, progress or 0.0, message, db_path, meta)
        fields, params = [], []
        for col, val in (("status", status), ("stage", stage), ("progress", None if progress is None else float(progress)),
                         ("message", message)):
            if val is not None:
                fields.append(f"{col} = ?")
                params.append(val)
        if meta:
            cur = json.loads(row["meta"] or "{}")
            cur.update(meta)
            fields.append("meta = ?")
            params.append(json.dumps(cur, allow_nan=False))
        fields.append("updated_at = ?")
        params += [_now(), job_id]
        with conn:
            conn.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE job_id = ?", params)
    finally:
        conn.close()
    return get_job(job_id, db_path=db_path)


def fail_stale_jobs(db_path: str | Path = DEFAULT_DB_PATH) -> int:
    """At startup, mark jobs left queued/running by a previous server process as failed (reason: restart)."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            rows = conn.execute("SELECT job_id, meta FROM jobs WHERE status IN ('queued', 'running')").fetchall()
            for r in rows:
                meta = json.loads(r["meta"] or "{}")
                meta["failure_reason"] = "restart"
                conn.execute(
                    "UPDATE jobs SET status = 'failed', message = ?, meta = ?, updated_at = ? WHERE job_id = ?",
                    ("Server restarted before this job finished. Please retry.", json.dumps(meta), _now(), r["job_id"]))
            return len(rows)
    finally:
        conn.close()


def find_by_cache_key(key: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    """The newest job for this canonical request that is finished-and-done, or still waiting/running."""
    conn = get_db_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT job_id, status FROM jobs WHERE json_extract(meta, '$.cache_key') = ? "
            "AND status IN ('done', 'queued', 'running') ORDER BY rowid DESC", (key,)).fetchall()
    finally:
        conn.close()
    for r in rows:
        if r["status"] != "done" or (Path(db_path).parent / r["job_id"] / "results.json").exists():
            return {"job_id": r["job_id"], "status": r["status"]}
    return None


def set_message_if_running(job_id: str, message: str, db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Change the message only while the job is still running (a finished job's final message must win)."""
    conn = get_db_connection(db_path)
    try:
        with conn:
            conn.execute("UPDATE jobs SET message = ?, updated_at = ? WHERE job_id = ? AND status = 'running'",
                         (message, _now(), job_id))
    finally:
        conn.close()


def count_active(db_path: str | Path = DEFAULT_DB_PATH) -> tuple[int, int]:
    """(running, queued) job counts."""
    conn = get_db_connection(db_path)
    try:
        r = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'running'").fetchone()[0]
        q = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'queued'").fetchone()[0]
        return int(r), int(q)
    finally:
        conn.close()


def save_request(job_id: str, request: dict[str, Any], base_dir: str | Path = DEFAULT_RUNS_DIR) -> None:
    """Keep the request next to the results so a run can be reproduced."""
    d = Path(base_dir) / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")


def get_request(job_id: str, base_dir: str | Path = DEFAULT_RUNS_DIR) -> dict[str, Any] | None:
    f = Path(base_dir) / job_id / "request.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def save_results(
    job_id: str,
    candidates: list[dict[str, Any]],
    base_dir: str | Path = DEFAULT_RUNS_DIR,
) -> Path:
    """Save the final candidate JSON list to runs/{job_id}/results.json (written whole, then renamed)."""
    results_dir = Path(base_dir) / job_id
    results_dir.mkdir(parents=True, exist_ok=True)
    results_file = results_dir / "results.json"
    tmp = results_dir / "results.json.tmp"
    tmp.write_text(json.dumps(candidates, indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(results_file)
    return results_file


def get_job_results(
    job_id: str,
    base_dir: str | Path = DEFAULT_RUNS_DIR,
) -> list[dict[str, Any]]:
    """Load candidates from runs/{job_id}/results.json if it exists."""
    results_file = Path(base_dir) / job_id / "results.json"
    if not results_file.exists():
        return []
    try:
        with open(results_file, encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def get_job(
    job_id: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    include_candidates: bool = True,
) -> dict[str, Any] | None:
    """Job record with its meta merged in, queue_position for queued jobs, and (optionally) candidates."""
    conn = get_db_connection(db_path)
    try:
        row = conn.execute(
            "SELECT rowid AS rid, job_id, status, stage, progress, message, updated_at, meta FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if not row:
            return None
        job_data: dict[str, Any] = json.loads(row["meta"] or "{}")
        job_data.update(
            job_id=row["job_id"], status=row["status"], stage=row["stage"],
            progress=float(row["progress"]) if row["progress"] is not None else 0.0,
            message=row["message"], updated_at=row["updated_at"], queue_position=None,
        )
        if row["status"] == "queued":
            ahead = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'queued' AND rowid < ?", (row["rid"],)).fetchone()[0]
            running = conn.execute("SELECT COUNT(*) FROM jobs WHERE status = 'running'").fetchone()[0]
            job_data["queue_position"] = int(ahead + running)
    finally:
        conn.close()

    if include_candidates:
        runs_dir = Path(db_path).parent
        job_data["candidates"] = get_job_results(job_id, base_dir=runs_dir)
        job_data["request"] = get_request(job_id, base_dir=runs_dir)

    return job_data
