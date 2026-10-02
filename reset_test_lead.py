import sys
from conversation import clear_history, _connect, _lock
from lead_store import init_lead_db
from question_state import init_question_state_db
from conversation_flow import init_flow_db
from followup_scheduler import init_followup_db

if len(sys.argv) != 2:
    raise SystemExit("Usage: python reset_test_lead.py <sender>")
sender=sys.argv[1]
init_lead_db(); init_question_state_db(); init_flow_db(); init_followup_db(); clear_history(sender)
with _lock:
    with _connect() as conn:
        conn.execute("DELETE FROM leads WHERE sender=?",(sender,))
        conn.execute("DELETE FROM conversation_state WHERE sender=?",(sender,))
        conn.execute("DELETE FROM program_flow_state WHERE sender=?",(sender,))
        conn.execute("DELETE FROM admin_notifications WHERE sender=?",(sender,))
        conn.execute("DELETE FROM inbound_buffer WHERE sender=?",(sender,))
        conn.execute("DELETE FROM reply_batches WHERE sender=?",(sender,))
        exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='api_usage'").fetchone()
        if exists:
            conn.execute("DELETE FROM api_usage WHERE sender=?",(sender,))
        for table in ("followups", "b2c_followups"):
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                conn.execute(f"DELETE FROM {table} WHERE sender=?", (sender,))
print(f"Test data cleared for sender: {sender}")
