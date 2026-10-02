from datetime import datetime, timezone
from conversation import _connect, _lock

TRACKED_FIELDS = (
    "contact_name", "company_name", "representative_division",
    "participant_count", "training_goal", "experience_level",
    "preferred_delivery", "location",
)

CORPORATE_PRIORITY = (
    "contact_name",
    "company_name",
    "representative_division",
    "participant_count",
    "training_goal",
    "experience_level",
    "preferred_delivery",
    "location",
)

BOOTCAMP_PRIORITY = ("training_goal", "experience_level")

QUESTION_TEXT = {
    "contact_name": "Sebelumnya, boleh tahu saya berbicara dengan Bapak/Ibu siapa yah?",
    "company_name": "Bapak/Ibu dari perusahaan atau organisasi apa yah?",
    "representative_division": "Kalau boleh tahu, saat ini Bapak/Ibu mewakili divisi atau tim apa di perusahaan?",
    "participant_count": "Kira-kira nanti pesertanya sekitar berapa orang yah Bapak/Ibu?",
    "training_goal": "Untuk kebutuhan trainingnya, kira-kira fokus atau hasil yang ingin dicapai seperti apa yah Bapak/Ibu?",
    "experience_level": "Kalau untuk pesertanya sendiri, sejauh ini sudah cukup familiar dengan AI atau mayoritas masih pemula yah Bapak/Ibu?",
    "preferred_delivery": "Untuk pelaksanaannya, Bapak/Ibu lebih prefer online, onsite, atau hybrid?",
    "location": "Kalau onsite, rencananya training akan dilaksanakan di kota atau lokasi mana yah Bapak/Ibu?",
}


def init_question_state_db():
    with _lock:
        with _connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversation_state (
                    sender TEXT PRIMARY KEY,
                    pending_field TEXT,
                    last_asked_field TEXT,
                    updated_at TEXT NOT NULL
                )
            """)


def get_state(sender):
    with _lock:
        with _connect() as conn:
            row = conn.execute("SELECT sender, pending_field, last_asked_field, updated_at FROM conversation_state WHERE sender = ?", (sender,)).fetchone()
    return dict(row) if row else {"sender": sender, "pending_field": None, "last_asked_field": None, "updated_at": None}


def save_state(sender, pending_field=None, last_asked_field=None):
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        with _connect() as conn:
            conn.execute("""
                INSERT INTO conversation_state(sender, pending_field, last_asked_field, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(sender) DO UPDATE SET
                    pending_field=excluded.pending_field,
                    last_asked_field=excluded.last_asked_field,
                    updated_at=excluded.updated_at
            """, (sender, pending_field, last_asked_field, now))


def resolve_pending(sender, lead):
    state = get_state(sender)
    pending = state.get("pending_field")
    if pending and lead.get(pending) is not None:
        save_state(sender, None, state.get("last_asked_field"))
        return get_state(sender)
    return state


def choose_next_field(category, lead, state):
    pending = state.get("pending_field")
    if pending and lead.get(pending) is None:
        return None
    if category == "AI Corporate Training":
        priority = CORPORATE_PRIORITY
    elif category == "AI Intensive Bootcamp":
        priority = BOOTCAMP_PRIORITY
    else:
        return None
    for field in priority:
        if lead.get(field) is not None:
            continue
        if field == "location" and lead.get("preferred_delivery") != "Onsite":
            continue
        return field
    return None


def mark_question_asked(sender, field):
    save_state(sender, field, field)


def question_for(field):
    return QUESTION_TEXT.get(field) if field else None


init_question_state_db()
