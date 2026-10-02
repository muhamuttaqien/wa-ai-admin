from datetime import datetime, timezone
from conversation import _connect, _lock

VALID_CHANNELS = {"B2C", "B2B"}
VALID_STATUSES = {"unread", "in_progress", "resolved"}

def _now():
    return datetime.now(timezone.utc).isoformat()

def init_notification_db():
    with _lock:
        with _connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS admin_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    notification_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT,
                    status TEXT NOT NULL DEFAULT 'unread',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_notifications_channel_status ON admin_notifications(channel, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_notifications_sender ON admin_notifications(sender)")

def create_notification(sender, channel, notification_type, title, message=None, dedupe_open=True):
    if channel not in VALID_CHANNELS:
        raise ValueError("Invalid notification channel")
    now = _now()
    with _lock:
        with _connect() as conn:
            if dedupe_open:
                existing = conn.execute("""
                    SELECT id FROM admin_notifications
                    WHERE sender=? AND channel=? AND notification_type=?
                      AND status IN ('unread','in_progress')
                    ORDER BY id DESC LIMIT 1
                """, (sender, channel, notification_type)).fetchone()
                if existing:
                    return existing["id"]
            cur = conn.execute("""
                INSERT INTO admin_notifications
                (sender, channel, notification_type, title, message, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'unread', ?)
            """, (sender, channel, notification_type, title, message, now))
            return cur.lastrowid

def list_notifications(channel=None, limit=100):
    sql = "SELECT * FROM admin_notifications"
    args = []
    if channel:
        sql += " WHERE channel=?"
        args.append(channel)
    sql += " ORDER BY CASE status WHEN 'unread' THEN 0 WHEN 'in_progress' THEN 1 ELSE 2 END, created_at DESC LIMIT ?"
    args.append(limit)
    with _lock:
        with _connect() as conn:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]

def update_notification_status(notification_id, status):
    if status not in VALID_STATUSES:
        raise ValueError("Invalid notification status")
    resolved_at = _now() if status == "resolved" else None
    with _lock:
        with _connect() as conn:
            conn.execute("""
                UPDATE admin_notifications
                SET status=?, resolved_at=?
                WHERE id=?
            """, (status, resolved_at, notification_id))

def open_notifications_for_sender(sender):
    """Return only notifications that currently justify human handling."""
    with _lock:
        with _connect() as conn:
            return [dict(r) for r in conn.execute("""
                SELECT * FROM admin_notifications
                WHERE sender=? AND status IN ('unread','in_progress')
                ORDER BY created_at DESC
            """, (sender,)).fetchall()]

def get_notification(notification_id):
    with _lock:
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM admin_notifications WHERE id=?", (notification_id,)
            ).fetchone()
    return dict(row) if row else None

def notification_counts(channel):
    with _lock:
        with _connect() as conn:
            rows = conn.execute("""
                SELECT status, COUNT(*) AS n FROM admin_notifications
                WHERE channel=? GROUP BY status
            """, (channel,)).fetchall()
    counts = {"unread": 0, "in_progress": 0, "resolved": 0}
    for r in rows:
        counts[r["status"]] = r["n"]
    return counts

init_notification_db()
