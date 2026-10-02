from datetime import datetime, timezone
from conversation import _connect, _lock

LEAD_FIELDS = (
    "product_interest",
    "contact_name",
    "company_name",
    "representative_division",
    "participant_count",
    "training_goal",
    "experience_level",
    "preferred_delivery",
    "location",
    "selected_class",
    "registration_intent",
    "registration_quantity",
)


def _columns(conn):
    return {row["name"] for row in conn.execute("PRAGMA table_info(leads)").fetchall()}


def init_lead_db() -> None:
    """Create the leads table and migrate older Milestone 4 schemas safely."""
    with _lock:
        with _connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    sender TEXT PRIMARY KEY,
                    product_interest TEXT,
                    contact_name TEXT,
                    company_name TEXT,
                    representative_division TEXT,
                    participant_count INTEGER,
                    training_goal TEXT,
                    experience_level TEXT,
                    preferred_delivery TEXT,
                    location TEXT,
                    selected_class TEXT,
                    registration_intent INTEGER,
                    registration_quantity INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            existing = _columns(conn)
            migrations = {
                "contact_name": "TEXT",
                "representative_division": "TEXT",
                "selected_class": "TEXT",
                "registration_intent": "INTEGER",
                "registration_quantity": "INTEGER",
            }
            for column, column_type in migrations.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE leads ADD COLUMN {column} {column_type}")


def get_lead(sender: str) -> dict:
    with _lock:
        with _connect() as conn:
            row = conn.execute(
                """
                SELECT sender, product_interest, contact_name, company_name,
                       representative_division, participant_count, training_goal,
                       experience_level, preferred_delivery, location, selected_class, registration_intent,
                       registration_quantity, created_at, updated_at
                FROM leads WHERE sender = ?
                """,
                (sender,),
            ).fetchone()
    if row is None:
        return {"sender": sender, **{field: None for field in LEAD_FIELDS}}
    return dict(row)


def upsert_lead(sender: str, updates: dict) -> dict:
    clean = {field: updates[field] for field in LEAD_FIELDS
             if field in updates and updates[field] is not None}
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        with _connect() as conn:
            exists = conn.execute("SELECT 1 FROM leads WHERE sender = ?", (sender,)).fetchone()
            if not exists:
                conn.execute("INSERT INTO leads(sender, created_at, updated_at) VALUES (?, ?, ?)",
                             (sender, now, now))
            if clean:
                assignments = ", ".join(f"{field} = ?" for field in clean)
                conn.execute(
                    f"UPDATE leads SET {assignments}, updated_at = ? WHERE sender = ?",
                    (*clean.values(), now, sender),
                )
    return get_lead(sender)


init_lead_db()
