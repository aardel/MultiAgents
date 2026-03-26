from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

from app.models import TaskEvent, TaskJob, TaskState

DB_PATH = Path(
    os.environ.get("AGENT_ORCH_DB_PATH", str(Path(__file__).resolve().parents[2] / "data.db"))
)
DATABASE_URL = os.environ.get("AGENT_ORCH_DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith(
    "postgres://"
)


def _sqlite_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _postgres_conn():
    import psycopg

    return psycopg.connect(DATABASE_URL)


def init_db() -> None:
    if USE_POSTGRES:
        with _postgres_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_id TEXT PRIMARY KEY,
                        payload TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kv_store (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS task_events (
                        event_id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        message TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS task_jobs (
                        job_id TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
            conn.commit()
        return

    with _sqlite_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_events (
                event_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_jobs (
                job_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )


def save_task(task: TaskState) -> None:
    payload = json.dumps(task.model_dump(mode="json"))
    if USE_POSTGRES:
        with _postgres_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tasks(task_id, payload)
                    VALUES (%s, %s)
                    ON CONFLICT (task_id) DO UPDATE SET payload = EXCLUDED.payload
                    """,
                    (task.task_id, payload),
                )
            conn.commit()
        return

    with _sqlite_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tasks(task_id, payload) VALUES (?, ?)",
            (task.task_id, payload),
        )


def load_task(task_id: str) -> TaskState | None:
    if USE_POSTGRES:
        with _postgres_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM tasks WHERE task_id = %s", (task_id,))
                row = cur.fetchone()
        if not row:
            return None
        return TaskState.model_validate(json.loads(row[0]))

    with _sqlite_conn() as conn:
        row = conn.execute("SELECT payload FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        return None
    return TaskState.model_validate(json.loads(row["payload"]))


def set_value(key: str, value: str) -> None:
    if USE_POSTGRES:
        with _postgres_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO kv_store(key, value)
                    VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """,
                    (key, value),
                )
            conn.commit()
        return

    with _sqlite_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO kv_store(key, value) VALUES (?, ?)",
            (key, value),
        )


def get_value(key: str) -> str | None:
    if USE_POSTGRES:
        with _postgres_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM kv_store WHERE key = %s", (key,))
                row = cur.fetchone()
        if not row:
            return None
        return row[0]

    with _sqlite_conn() as conn:
        row = conn.execute("SELECT value FROM kv_store WHERE key = ?", (key,)).fetchone()
    if not row:
        return None
    return row["value"]


def add_task_event(task_id: str, event_type: str, message: str) -> TaskEvent:
    event = TaskEvent(
        event_id=uuid4().hex[:12],
        task_id=task_id,
        event_type=event_type,
        message=message,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    if USE_POSTGRES:
        with _postgres_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO task_events(event_id, task_id, event_type, message, created_at)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        event.event_id,
                        event.task_id,
                        event.event_type,
                        event.message,
                        event.created_at,
                    ),
                )
            conn.commit()
        return event

    with _sqlite_conn() as conn:
        conn.execute(
            """
            INSERT INTO task_events(event_id, task_id, event_type, message, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.task_id,
                event.event_type,
                event.message,
                event.created_at,
            ),
        )
    return event


def list_task_events(task_id: str) -> list[TaskEvent]:
    if USE_POSTGRES:
        with _postgres_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT event_id, task_id, event_type, message, created_at
                    FROM task_events
                    WHERE task_id = %s
                    ORDER BY created_at ASC
                    """,
                    (task_id,),
                )
                rows = cur.fetchall()
        return [
            TaskEvent(
                event_id=row[0],
                task_id=row[1],
                event_type=row[2],
                message=row[3],
                created_at=row[4],
            )
            for row in rows
        ]

    with _sqlite_conn() as conn:
        rows = conn.execute(
            """
            SELECT event_id, task_id, event_type, message, created_at
            FROM task_events
            WHERE task_id = ?
            ORDER BY created_at ASC
            """,
            (task_id,),
        ).fetchall()
    return [
        TaskEvent(
            event_id=row["event_id"],
            task_id=row["task_id"],
            event_type=row["event_type"],
            message=row["message"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def save_task_job(job: TaskJob) -> None:
    payload = json.dumps(job.model_dump(mode="json"))
    if USE_POSTGRES:
        with _postgres_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO task_jobs(job_id, task_id, payload)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (job_id) DO UPDATE SET payload = EXCLUDED.payload
                    """,
                    (job.job_id, job.task_id, payload),
                )
            conn.commit()
        return

    with _sqlite_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO task_jobs(job_id, task_id, payload) VALUES (?, ?, ?)",
            (job.job_id, job.task_id, payload),
        )


def load_task_job(job_id: str) -> TaskJob | None:
    if USE_POSTGRES:
        with _postgres_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT payload FROM task_jobs WHERE job_id = %s", (job_id,))
                row = cur.fetchone()
        if not row:
            return None
        return TaskJob.model_validate(json.loads(row[0]))

    with _sqlite_conn() as conn:
        row = conn.execute("SELECT payload FROM task_jobs WHERE job_id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return TaskJob.model_validate(json.loads(row["payload"]))
