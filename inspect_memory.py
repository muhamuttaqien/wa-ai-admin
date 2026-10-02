import sqlite3
from pathlib import Path

db = Path("data/conversations.db")

if not db.exists():
    print("Database belum ada:", db)
    raise SystemExit(0)

with sqlite3.connect(db) as conn:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, sender, role, content, created_at
        FROM conversation_messages
        ORDER BY id
        """
    ).fetchall()

if not rows:
    print("Database ada, tetapi belum ada conversation message.")
else:
    for row in rows:
        print(
            f"[{row['id']}] {row['created_at']} | "
            f"{row['sender']} | {row['role']} | {row['content']}"
        )
