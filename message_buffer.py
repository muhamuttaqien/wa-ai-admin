import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone

from conversation import _connect, _lock

MIN_DELAY = int(os.getenv("REPLY_DELAY_MIN_SECONDS", "15"))
MAX_DELAY = int(os.getenv("REPLY_DELAY_MAX_SECONDS", "30"))
MAX_BATCH_AGE = int(os.getenv("MAX_BATCH_AGE_SECONDS", "45"))

if MIN_DELAY < 0 or MAX_DELAY < MIN_DELAY:
    raise ValueError("Invalid REPLY_DELAY_MIN_SECONDS/REPLY_DELAY_MAX_SECONDS")
if MAX_BATCH_AGE <= 0:
    raise ValueError("MAX_BATCH_AGE_SECONDS must be > 0")


def _now():
    return datetime.now(timezone.utc)


def init_buffer_db():
    with _lock:
        with _connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inbound_buffer (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT UNIQUE,
                    sender TEXT NOT NULL,
                    content TEXT NOT NULL,
                    received_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_inbound_buffer_sender_id
                ON inbound_buffer(sender, id)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reply_batches (
                    sender TEXT PRIMARY KEY,
                    due_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)


def enqueue_message(sender: str, message_id: str | None, content: str) -> dict:
    now = _now()
    message_id = message_id or f"local:{sender}:{now.timestamp()}:{random.random()}"

    with _lock:
        with _connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO inbound_buffer(message_id, sender, content, received_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (message_id, sender, content, now.isoformat()),
                )
            except sqlite3.IntegrityError:
                return {"queued": False, "duplicate": True, "due_at": None}

            row = conn.execute(
                "SELECT due_at, created_at FROM reply_batches WHERE sender = ?",
                (sender,),
            ).fetchone()

            # True debounce: every new customer bubble restarts the quiet timer.
            # MAX_BATCH_AGE prevents a continuously-typing customer from postponing
            # the reply forever.
            delay = random.randint(MIN_DELAY, MAX_DELAY)
            candidate_due = now + timedelta(seconds=delay)

            if row is None:
                created_at = now
                due_at = min(
                    candidate_due,
                    created_at + timedelta(seconds=MAX_BATCH_AGE),
                )
                conn.execute(
                    """
                    INSERT INTO reply_batches(sender, due_at, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (sender, due_at.isoformat(), created_at.isoformat()),
                )
            else:
                created_at = datetime.fromisoformat(row["created_at"])
                hard_deadline = created_at + timedelta(seconds=MAX_BATCH_AGE)
                due_at = min(candidate_due, hard_deadline)
                conn.execute(
                    """
                    UPDATE reply_batches
                    SET due_at = ?
                    WHERE sender = ?
                    """,
                    (due_at.isoformat(), sender),
                )

    return {"queued": True, "duplicate": False, "due_at": due_at.isoformat()}


def due_senders(limit: int = 20) -> list[str]:
    now = _now().isoformat()
    with _lock:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT sender
                FROM reply_batches
                WHERE due_at <= ?
                ORDER BY due_at ASC
                LIMIT ?
                """,
                (now, limit),
            ).fetchall()
    return [row["sender"] for row in rows]


def is_batch_due(sender: str) -> bool:
    """Re-check the deadline immediately before processing.

    A new message may arrive after due_senders() selected this sender. In that
    case enqueue_message() moves due_at forward and this guard prevents the old
    worker iteration from replying too early.
    """
    now = _now()
    with _lock:
        with _connect() as conn:
            row = conn.execute(
                "SELECT due_at FROM reply_batches WHERE sender = ?",
                (sender,),
            ).fetchone()
    return bool(row and datetime.fromisoformat(row["due_at"]) <= now)


def get_buffered_messages(sender: str) -> list[dict]:
    with _lock:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, message_id, content, received_at
                FROM inbound_buffer
                WHERE sender = ?
                ORDER BY id ASC
                """,
                (sender,),
            ).fetchall()
    return [dict(row) for row in rows]


def complete_batch(sender: str, message_ids: list[str]):
    with _lock:
        with _connect() as conn:
            if message_ids:
                placeholders = ",".join("?" for _ in message_ids)
                conn.execute(
                    f"DELETE FROM inbound_buffer WHERE message_id IN ({placeholders})",
                    message_ids,
                )
            conn.execute("DELETE FROM reply_batches WHERE sender = ?", (sender,))

            # Messages may have arrived while this batch was being processed.
            remaining = conn.execute(
                "SELECT 1 FROM inbound_buffer WHERE sender = ? LIMIT 1",
                (sender,),
            ).fetchone()
            if remaining:
                now = _now()
                delay = random.randint(MIN_DELAY, MAX_DELAY)
                due_at = now + timedelta(seconds=delay)
                conn.execute(
                    """
                    INSERT INTO reply_batches(sender, due_at, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(sender) DO UPDATE SET
                        due_at = excluded.due_at,
                        created_at = excluded.created_at
                    """,
                    (sender, due_at.isoformat(), now.isoformat()),
                )


def retry_batch_later(sender: str, seconds: int = 10):
    now = _now()
    due_at = now + timedelta(seconds=seconds)
    with _lock:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO reply_batches(sender, due_at, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(sender) DO UPDATE SET due_at = excluded.due_at
                """,
                (sender, due_at.isoformat(), now.isoformat()),
            )


def inspect_buffer() -> list[dict]:
    with _lock:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT b.sender, r.due_at, COUNT(*) AS message_count,
                       GROUP_CONCAT(b.content, ' | ') AS messages
                FROM inbound_buffer b
                LEFT JOIN reply_batches r ON r.sender = b.sender
                GROUP BY b.sender, r.due_at
                ORDER BY MIN(b.id)
                """
            ).fetchall()
    return [dict(row) for row in rows]


init_buffer_db()
