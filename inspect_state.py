import sqlite3
from conversation import DB_PATH

with sqlite3.connect(DB_PATH) as conn:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT
            l.sender,
            l.product_interest,
            l.company_name,
            l.participant_count,
            l.training_goal,
            l.experience_level,
            l.preferred_delivery,
            l.location,
            s.pending_field,
            s.last_asked_field,
            s.updated_at AS state_updated_at
        FROM leads l
        LEFT JOIN conversation_state s ON s.sender = l.sender
        ORDER BY l.updated_at DESC
    """).fetchall()

if not rows:
    print("Belum ada lead/state.")
else:
    for i, row in enumerate(rows, 1):
        print("=" * 72)
        print(f"LEAD / STATE #{i}")
        print("=" * 72)
        for key in row.keys():
            print(f"{key:20}: {row[key]}")
        print()
