import os
import sqlite3
from pathlib import Path
from threading import Lock
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("CONVERSATION_DB_PATH", BASE_DIR / "data" / "conversations.db"))
MAX_MESSAGES = int(os.getenv("CONVERSATION_MAX_MESSAGES", "12"))

_lock = Lock()


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock:
        with _connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'human_admin')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

            # Older databases only allowed user/assistant. Migrate them in place so
            # dashboard replies can be stored distinctly as human_admin.
            table_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='conversation_messages'"
            ).fetchone()["sql"]
            if "human_admin" not in (table_sql or ""):
                conn.execute("ALTER TABLE conversation_messages RENAME TO conversation_messages_old")
                conn.execute("""
                    CREATE TABLE conversation_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        sender TEXT NOT NULL,
                        role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'human_admin')),
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    INSERT INTO conversation_messages(id, sender, role, content, created_at)
                    SELECT id, sender, role, content, created_at
                    FROM conversation_messages_old
                """)
                conn.execute("DROP TABLE conversation_messages_old")

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_sender_id
                ON conversation_messages(sender, id)
            """)


def get_history(sender: str) -> list[dict]:
    with _lock:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content
                FROM conversation_messages
                WHERE sender = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (sender, MAX_MESSAGES),
            ).fetchall()

    rows = list(reversed(rows))
    return [{"role": ("assistant" if row["role"] == "human_admin" else row["role"]), "content": row["content"]} for row in rows]


def add_message(sender: str, role: str, content: str) -> None:
    if role not in {"user", "assistant", "human_admin"}:
        raise ValueError("role must be 'user', 'assistant', or 'human_admin'")

    now = datetime.now(timezone.utc).isoformat()

    with _lock:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO conversation_messages(sender, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (sender, role, content, now),
            )


def clear_history(sender: str) -> None:
    with _lock:
        with _connect() as conn:
            conn.execute(
                "DELETE FROM conversation_messages WHERE sender = ?",
                (sender,),
            )


def count_messages(sender: str) -> int:
    with _lock:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM conversation_messages
                WHERE sender = ?
                """,
                (sender,),
            ).fetchone()

    return int(row["total"])


def count_user_messages(sender: str) -> int:
    """Return the number of inbound user messages stored for this sender."""
    with _lock:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total
                FROM conversation_messages
                WHERE sender = ? AND role = 'user'
                """,
                (sender,),
            ).fetchone()

    return int(row["total"])


# Ensure the database/table exists when this module is imported.
init_db()
