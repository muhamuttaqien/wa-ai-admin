import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from conversation import _connect, _lock

load_dotenv()

B2C_ENABLED = os.getenv("B2C_FOLLOWUP_ENABLED", "true").strip().lower() in {"1","true","yes","on"}
B2C_PRE_HOURS = float(os.getenv("B2C_PRE_REGISTRATION_FOLLOWUP_HOURS", "3"))
B2C_PRE_SECOND_HOURS = float(os.getenv("B2C_PRE_REGISTRATION_SECOND_FOLLOWUP_HOURS", "9"))
B2C_POST_HOURS = float(os.getenv("B2C_POST_REGISTRATION_FOLLOWUP_HOURS", "12"))

B2B_ENABLED = os.getenv("B2B_FOLLOWUP_ENABLED", "true").strip().lower() in {"1","true","yes","on"}
B2B_PRE_HOURS = float(os.getenv("B2B_PRE_PROPOSAL_FOLLOWUP_HOURS", "3"))
B2B_POST_HOURS = float(os.getenv("B2B_POST_PROPOSAL_FOLLOWUP_HOURS", "12"))

# Hard safety margin for WhatsApp free-form follow-ups. The official customer
# service window is 24 hours after the latest inbound customer message. We use
# 23.5 hours so scheduler/polling/network delays cannot push a send over 24h.
WHATSAPP_FREEFORM_MAX_AGE_HOURS = 23.5

# B2C Last Call campaign. This uses a separate queue so it never replaces the
# existing 3h/12h inactivity follow-up for the same sender.
LAST_CALL_ENABLED = os.getenv("B2C_LAST_CALL_ENABLED", "true").strip().lower() in {"1","true","yes","on"}
LAST_CALL_DELAY_HOURS = float(os.getenv("B2C_LAST_CALL_DELAY_HOURS", "12"))
BOOTCAMP_REGISTRATION_DEADLINE = os.getenv("BOOTCAMP_REGISTRATION_DEADLINE", "2026-11-01").strip()
JAKARTA = ZoneInfo("Asia/Jakarta")

LAST_CALL_H5 = "b2c_last_call_h5"
LAST_CALL_H3 = "b2c_last_call_h3"
LAST_CALL_H1 = "b2c_last_call_h1"
LAST_CALL_TODAY = "b2c_last_call_today"
LAST_CALL_BY_DAYS = {5: LAST_CALL_H5, 3: LAST_CALL_H3, 1: LAST_CALL_H1, 0: LAST_CALL_TODAY}

for name, value in {
    "B2C_PRE_REGISTRATION_FOLLOWUP_HOURS": B2C_PRE_HOURS,
    "B2C_PRE_REGISTRATION_SECOND_FOLLOWUP_HOURS": B2C_PRE_SECOND_HOURS,
    "B2C_POST_REGISTRATION_FOLLOWUP_HOURS": B2C_POST_HOURS,
    "B2B_PRE_PROPOSAL_FOLLOWUP_HOURS": B2B_PRE_HOURS,
    "B2B_POST_PROPOSAL_FOLLOWUP_HOURS": B2B_POST_HOURS,
    "B2C_LAST_CALL_DELAY_HOURS": LAST_CALL_DELAY_HOURS,
}.items():
    if value < 0:
        raise ValueError(f"{name} must be >= 0")

B2C_PRE = "b2c_pre_registration"
B2C_PRE_SECOND = "b2c_pre_registration_second"
B2C_POST = "b2c_post_registration"
B2B_PRE = "b2b_pre_proposal"
B2B_POST = "b2b_post_proposal"
KINDS = {B2C_PRE, B2C_PRE_SECOND, B2C_POST, B2B_PRE, B2B_POST}


def _now():
    return datetime.now(timezone.utc)


def _parse_utc(value: str):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def init_followup_db():
    with _lock:
        with _connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS followups (
                    sender TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    sent_at TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_followups_due ON followups(due_at)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS b2c_last_call_followups (
                    sender TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    sent_at TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_b2c_last_call_due ON b2c_last_call_followups(due_at)")

            # One-time compatibility migration from Milestone 4E.3.
            old_exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='b2c_followups'"
            ).fetchone()
            if old_exists:
                rows = conn.execute(
                    "SELECT sender, kind, due_at, scheduled_at, sent_at FROM b2c_followups"
                ).fetchall()
                kind_map = {
                    "pre_registration": B2C_PRE,
                    "post_registration": B2C_POST,
                }
                for row in rows:
                    new_kind = kind_map.get(row["kind"])
                    if new_kind:
                        conn.execute("""
                            INSERT OR IGNORE INTO followups(sender, kind, due_at, scheduled_at, sent_at)
                            VALUES (?, ?, ?, ?, ?)
                        """, (row["sender"], new_kind, row["due_at"], row["scheduled_at"], row["sent_at"]))


def cancel_followup(sender: str):
    with _lock:
        with _connect() as conn:
            conn.execute("DELETE FROM followups WHERE sender=?", (sender,))


def schedule_followup(sender: str, kind: str):
    if kind not in KINDS:
        raise ValueError("Unknown follow-up kind")

    enabled = B2C_ENABLED if kind.startswith("b2c_") else B2B_ENABLED
    if not enabled:
        cancel_followup(sender)
        return None

    hours = {
        B2C_PRE: B2C_PRE_HOURS,
        B2C_PRE_SECOND: B2C_PRE_SECOND_HOURS,
        B2C_POST: B2C_POST_HOURS,
        B2B_PRE: B2B_PRE_HOURS,
        B2B_POST: B2B_POST_HOURS,
    }[kind]

    now = _now()
    due = now + timedelta(hours=hours)
    with _lock:
        with _connect() as conn:
            conn.execute("""
                INSERT INTO followups(sender, kind, due_at, scheduled_at, sent_at)
                VALUES (?, ?, ?, ?, NULL)
                ON CONFLICT(sender) DO UPDATE SET
                    kind=excluded.kind,
                    due_at=excluded.due_at,
                    scheduled_at=excluded.scheduled_at,
                    sent_at=NULL
            """, (sender, kind, due.isoformat(), now.isoformat()))
    return due.isoformat()


def schedule_b2c_second_pre_followup(sender: str):
    """Schedule the second pre-registration reminder 9h after reminder #1.

    The WhatsApp safety check still uses the latest inbound customer message,
    not this bot-generated reminder. No third reminder is scheduled.
    """
    return schedule_followup(sender, B2C_PRE_SECOND)


def schedule_for_b2c_state(sender: str, lead: dict, flow: dict):
    if not B2C_ENABLED:
        cancel_followup(sender)
        return None
    if flow.get("payment_claimed"):
        cancel_followup(sender)
        return None
    if lead.get("registration_intent"):
        return schedule_followup(sender, B2C_POST)
    if flow.get("b2c_intro_confirmed"):
        return schedule_followup(sender, B2C_PRE)
    cancel_followup(sender)
    return None


def cancel_last_call(sender: str):
    with _lock:
        with _connect() as conn:
            conn.execute("DELETE FROM b2c_last_call_followups WHERE sender=?", (sender,))


def _registration_deadline():
    try:
        return datetime.strptime(BOOTCAMP_REGISTRATION_DEADLINE, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("BOOTCAMP_REGISTRATION_DEADLINE must use YYYY-MM-DD format") from exc


def schedule_last_call_for_b2c(sender: str, lead: dict, flow: dict):
    """Schedule Last Call +12h when the current WIB date is H-5/H-3/H-1/H.

    This queue is independent from normal follow-ups and does not change the
    conversation stage. A later inbound message cancels this row at webhook time
    and, after processing, creates a fresh timer only if its date is eligible.
    """
    if not LAST_CALL_ENABLED:
        cancel_last_call(sender)
        return None
    if lead.get("product_interest") != "AI Intensive Bootcamp":
        cancel_last_call(sender)
        return None
    if flow.get("payment_claimed"):
        cancel_last_call(sender)
        return None

    now = _now()
    today_wib = now.astimezone(JAKARTA).date()
    days_left = (_registration_deadline() - today_wib).days
    kind = LAST_CALL_BY_DAYS.get(days_left)
    if not kind:
        cancel_last_call(sender)
        return None

    due = now + timedelta(hours=LAST_CALL_DELAY_HOURS)
    with _lock:
        with _connect() as conn:
            conn.execute("""
                INSERT INTO b2c_last_call_followups(sender, kind, due_at, scheduled_at, sent_at)
                VALUES (?, ?, ?, ?, NULL)
                ON CONFLICT(sender) DO UPDATE SET
                    kind=excluded.kind, due_at=excluded.due_at,
                    scheduled_at=excluded.scheduled_at, sent_at=NULL
            """, (sender, kind, due.isoformat(), now.isoformat()))
    print(f"LAST CALL SCHEDULED : {sender} [{kind}] due={due.isoformat()}")
    return due.isoformat()


def due_last_call_followups(limit: int = 20):
    """Return only eligible Last Calls safely inside the free-form window."""
    if not LAST_CALL_ENABLED:
        return []

    now = _now()
    safe = []
    with _lock:
        with _connect() as conn:
            rows = conn.execute("""
                SELECT lc.sender, lc.kind, lc.due_at,
                       (SELECT cm.created_at FROM conversation_messages cm
                        WHERE cm.sender=lc.sender AND cm.role='user'
                        ORDER BY cm.id DESC LIMIT 1) AS last_user_at,
                       COALESCE(pfs.payment_claimed, 0) AS payment_claimed,
                       l.product_interest AS product_interest
                FROM b2c_last_call_followups lc
                LEFT JOIN program_flow_state pfs ON pfs.sender=lc.sender
                LEFT JOIN leads l ON l.sender=lc.sender
                WHERE lc.sent_at IS NULL AND lc.due_at <= ?
                ORDER BY lc.due_at ASC LIMIT ?
            """, (now.isoformat(), limit)).fetchall()

            for row in rows:
                reason = None
                if row["product_interest"] != "AI Intensive Bootcamp":
                    reason = "lead is no longer Bootcamp"
                elif bool(row["payment_claimed"]):
                    reason = "payment already claimed"
                elif not row["last_user_at"]:
                    reason = "no inbound customer timestamp"
                else:
                    age_hours = (now - _parse_utc(row["last_user_at"])).total_seconds() / 3600.0
                    if age_hours >= WHATSAPP_FREEFORM_MAX_AGE_HOURS:
                        reason = f"last customer message {age_hours:.2f}h ago"

                if reason:
                    conn.execute("DELETE FROM b2c_last_call_followups WHERE sender=?", (row["sender"],))
                    print(f"LAST CALL BLOCKED : {row['sender']} [{row['kind']}] {reason}")
                    continue
                safe.append({"sender": row["sender"], "kind": row["kind"], "due_at": row["due_at"]})
    return safe


def mark_last_call_sent(sender: str):
    with _lock:
        with _connect() as conn:
            conn.execute("UPDATE b2c_last_call_followups SET sent_at=? WHERE sender=?", (_now().isoformat(), sender))


def inspect_last_call_followups():
    with _lock:
        with _connect() as conn:
            rows = conn.execute("SELECT sender, kind, due_at, scheduled_at, sent_at FROM b2c_last_call_followups ORDER BY due_at").fetchall()
    return [dict(r) for r in rows]


def schedule_for_b2b_state(sender: str, lead: dict, flow: dict):
    if not B2B_ENABLED:
        cancel_followup(sender)
        return None

    # Once a Quick Call/Meeting has been requested, the conversation is
    # entering human follow-up and should not receive an inactivity reminder.
    if flow.get("meeting_request"):
        cancel_followup(sender)
        return None

    if flow.get("proposal_sent"):
        return schedule_followup(sender, B2B_POST)

    # Any established Corporate Training conversation before proposal delivery
    # is eligible for the 3-hour pre-proposal inactivity follow-up.
    if lead.get("product_interest") == "AI Corporate Training":
        return schedule_followup(sender, B2B_PRE)

    cancel_followup(sender)
    return None


def due_followups(limit: int = 20):
    """Return only due follow-ups that are safely inside WhatsApp's 24h window.

    Any due follow-up whose latest stored inbound customer message is missing or
    already >= 23.5 hours old is deleted instead of being returned to main.py.
    This makes the safety check fail closed: process_due_followups() can only
    receive free-form follow-ups that are still safely inside the window.
    """
    if not (B2C_ENABLED or B2B_ENABLED):
        return []

    now = _now()
    now_iso = now.isoformat()
    safe = []

    with _lock:
        with _connect() as conn:
            rows = conn.execute("""
                SELECT
                    f.sender,
                    f.kind,
                    f.due_at,
                    (
                        SELECT cm.created_at
                        FROM conversation_messages AS cm
                        WHERE cm.sender = f.sender AND cm.role = 'user'
                        ORDER BY cm.id DESC
                        LIMIT 1
                    ) AS last_user_at
                FROM followups AS f
                WHERE f.sent_at IS NULL AND f.due_at <= ?
                ORDER BY f.due_at ASC
                LIMIT ?
            """, (now_iso, limit)).fetchall()

            for row in rows:
                last_user_at = row["last_user_at"]
                if not last_user_at:
                    conn.execute("DELETE FROM followups WHERE sender=?", (row["sender"],))
                    print(f"FOLLOW-UP BLOCKED : {row['sender']} [{row['kind']}] no inbound customer timestamp")
                    continue

                age_hours = (now - _parse_utc(last_user_at)).total_seconds() / 3600.0
                if age_hours >= WHATSAPP_FREEFORM_MAX_AGE_HOURS:
                    conn.execute("DELETE FROM followups WHERE sender=?", (row["sender"],))
                    print(
                        f"FOLLOW-UP BLOCKED : {row['sender']} [{row['kind']}] "
                        f"last customer message {age_hours:.2f}h ago"
                    )
                    continue

                safe.append({
                    "sender": row["sender"],
                    "kind": row["kind"],
                    "due_at": row["due_at"],
                })

    return safe


def mark_followup_sent(sender: str):
    now = _now().isoformat()
    with _lock:
        with _connect() as conn:
            conn.execute("UPDATE followups SET sent_at=? WHERE sender=?", (now, sender))


def inspect_followups():
    with _lock:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT sender, kind, due_at, scheduled_at, sent_at FROM followups ORDER BY due_at"
            ).fetchall()
    return [dict(r) for r in rows]


init_followup_db()
