#!/usr/bin/env python3
"""
Generate 100 dummy leads for the Indonesia AI WhatsApp Admin dashboard.

Default DB:
    data/conversations.db

Usage:
    python seed_dummy_leads.py

Optional:
    CONVERSATION_DB_PATH=/path/to/db python seed_dummy_leads.py

Safe behavior:
- Uses sender IDs beginning with dummy_
- Deletes/recreates only previous dummy_* test data
- Does not touch real leads
- Adapts inserts to columns that actually exist in each table
"""

import os
import random
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.getenv("CONVERSATION_DB_PATH", "data/conversations.db")
random.seed(42)

FIRST_NAMES = [
    "Andi","Budi","Citra","Dewi","Eka","Fajar","Gita","Hendra","Indah","Joko",
    "Kartika","Lukman","Maya","Nadia","Oki","Putri","Raka","Sari","Taufik","Vina",
    "Wahyu","Yuni","Zaki","Alya","Bagas","Dimas","Farah","Galih","Intan","Kevin",
    "Laila","Mira","Naufal","Rani","Rizky","Salma","Tegar","Tiara","Yusuf","Zahra",
    "Aditya","Bella","Dian","Firman","Hana","Iqbal","Nisa","Rafi","Sinta","Yoga"
]
COMPANIES = [
    "PT Nusantara Digital","PT Maju Teknologi","CV Kreasi Data","PT Sinar Industri",
    "PT Solusi Cerdas","PT Garuda Engineering","PT Inovasi Bersama","PT Prima Logistik",
    "PT Karya Finansial","PT Sentra Retail","PT Mitra Energi","PT Aruna Teknologi"
]
DIVISIONS = ["HR","IT","Engineering","Data","Innovation","Learning & Development","Operations"]
B2B_GOALS = ["Generative AI Tools","AI Engineering","Other"]
CLASSES = ["ML","CV","NLP"]

def nowstr(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def columns(conn, table):
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()

def table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None

def insert_adaptive(conn, table, values):
    cols = columns(conn, table)
    data = {k: v for k, v in values.items() if k in cols}
    if not data:
        return
    keys = list(data)
    sql = f"INSERT OR REPLACE INTO {table} ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})"
    conn.execute(sql, [data[k] for k in keys])

def delete_dummy(conn, table):
    if table_exists(conn, table) and "sender" in columns(conn, table):
        conn.execute(f"DELETE FROM {table} WHERE sender LIKE 'dummy_%'")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

if not table_exists(conn, "leads"):
    raise SystemExit(f"Table 'leads' not found in {DB_PATH}. Run the main app once first.")

# Re-running this script remains clean and deterministic.
for table in [
    "admin_notifications", "followups", "b2c_followups",
    "conversation_messages", "conversation_state",
    "program_flow_state", "leads"
]:
    delete_dummy(conn, table)

now = datetime.now()

for i in range(100):
    sender = f"dummy_{i+1:03d}"
    name = FIRST_NAMES[i % len(FIRST_NAMES)]
    created = now - timedelta(days=random.randint(0, 44), hours=random.randint(0, 20))
    updated = created + timedelta(hours=random.randint(0, 48))
    if updated > now:
        updated = now

    is_b2c = i < 50

    if is_b2c:
        selected = random.choice(CLASSES + [None])
        # Different stages so funnel cards are non-empty.
        registration = selected is not None and i % 3 != 0
        payment = registration and i % 5 in (1, 2)

        lead = {
            "sender": sender,
            "contact_name": name,
            "name": name,
            "product_interest": "AI Intensive Bootcamp",
            "selected_class": selected,
            "registration_intent": 1 if registration else 0,
            "registration_quantity": 1 if registration else None,
            "company_name": None,
            "participant_count": 1,
            "training_goal": None,
            "experience_level": random.choice(["Beginner","Beginner","Intermediate"]),
            "preferred_delivery": "Online",
            "location": random.choice(["Jakarta","Bandung","Surabaya","Depok","Yogyakarta"]),
            "created_at": nowstr(created),
            "updated_at": nowstr(updated),
        }
        insert_adaptive(conn, "leads", lead)

        insert_adaptive(conn, "program_flow_state", {
            "sender": sender,
            "b2c_intro_confirmed": 1,
            "infographic_sent": 1,
            "class_link_sent_for": selected,
            "registration_doc_sent": 1 if registration else 0,
            "payment_claimed": 1 if payment else 0,
            "proposal_sent": 0,
            "meeting_request": 0,
            "updated_at": nowstr(updated),
        })

        user_msg = (
            f"Halo kak, saya {name}. Saya tertarik bootcamp"
            + (f" kelas {selected}." if selected else ". Kelas yang tersedia apa saja?")
        )
        bot_msg = (
            f"Halo kak {name}, terima kasih sudah menghubungi Indonesia AI. "
            + (f"Untuk kelas {selected}, saya bantu informasinya yah kak." if selected
               else "Saat ini tersedia kelas ML, CV, dan NLP kak.")
        )
        insert_adaptive(conn, "conversation_messages", {
            "sender": sender, "role": "user", "content": user_msg, "created_at": nowstr(created)
        })
        insert_adaptive(conn, "conversation_messages", {
            "sender": sender, "role": "assistant", "content": bot_msg,
            "created_at": nowstr(created + timedelta(minutes=1))
        })

        if payment and table_exists(conn, "admin_notifications"):
            insert_adaptive(conn, "admin_notifications", {
                "sender": sender,
                "channel": "B2C",
                "notification_type": "REGISTRATION_PAYMENT_CONFIRMATION",
                "title": "Payment confirmation",
                "message": f"{name} menginformasikan pembayaran bootcamp.",
                "status": "unread" if i % 2 else "in_progress",
                "created_at": nowstr(updated),
            })

    else:
        company = COMPANIES[(i-50) % len(COMPANIES)]
        division = DIVISIONS[(i-50) % len(DIVISIONS)]
        participants = random.choice([5, 10, 15, 20, 25, 30, 40, 50])
        delivery = random.choice(["Online","Onsite","Hybrid"])
        goal = B2B_GOALS[(i-50) % len(B2B_GOALS)]
        proposal = i % 4 != 0
        meeting = proposal and i % 5 == 0

        lead = {
            "sender": sender,
            "contact_name": name,
            "name": name,
            "product_interest": "AI Corporate Training",
            "company_name": company,
            "representative_division": division,
            "division": division,
            "participant_count": participants,
            "training_goal": goal,
            "experience_level": None,
            "preferred_delivery": delivery,
            "location": random.choice(["Jakarta","Bandung","Surabaya","Tangerang","Depok"]),
            "selected_class": None,
            "registration_intent": 0,
            "registration_quantity": None,
            "created_at": nowstr(created),
            "updated_at": nowstr(updated),
        }
        insert_adaptive(conn, "leads", lead)

        insert_adaptive(conn, "program_flow_state", {
            "sender": sender,
            "b2c_intro_confirmed": 0,
            "infographic_sent": 0,
            "registration_doc_sent": 0,
            "payment_claimed": 0,
            "proposal_sent": 1 if proposal else 0,
            "meeting_request": 1 if meeting else 0,
            "updated_at": nowstr(updated),
        })

        insert_adaptive(conn, "conversation_messages", {
            "sender": sender, "role": "user",
            "content": f"Halo, saya {name} dari {company}, divisi {division}. Kami mencari corporate training untuk sekitar {participants} peserta.",
            "created_at": nowstr(created)
        })
        insert_adaptive(conn, "conversation_messages", {
            "sender": sender, "role": "assistant",
            "content": f"Baik Bapak/Ibu {name}, untuk kebutuhan {goal} dan format {delivery}, saya bantu lanjutkan informasinya.",
            "created_at": nowstr(created + timedelta(minutes=1))
        })

        if proposal and table_exists(conn, "admin_notifications"):
            insert_adaptive(conn, "admin_notifications", {
                "sender": sender, "channel": "B2B",
                "notification_type": "PROPOSAL_SENT",
                "title": "Proposal sent",
                "message": f"Proposal awal sudah dikirim ke {name} dari {company}.",
                "status": "resolved" if i % 3 else "unread",
                "created_at": nowstr(updated),
            })
        if meeting and table_exists(conn, "admin_notifications"):
            insert_adaptive(conn, "admin_notifications", {
                "sender": sender, "channel": "B2B",
                "notification_type": "QUICK_MEETING_REQUESTED",
                "title": "Quick meeting requested",
                "message": f"{name} dari {company} meminta diskusi lanjutan.",
                "status": "unread",
                "created_at": nowstr(updated),
            })

conn.commit()

total = conn.execute("SELECT COUNT(*) FROM leads WHERE sender LIKE 'dummy_%'").fetchone()[0]
b2c = conn.execute(
    "SELECT COUNT(*) FROM leads WHERE sender LIKE 'dummy_%' AND product_interest='AI Intensive Bootcamp'"
).fetchone()[0]
b2b = conn.execute(
    "SELECT COUNT(*) FROM leads WHERE sender LIKE 'dummy_%' AND product_interest='AI Corporate Training'"
).fetchone()[0]
conn.close()

print(f"Done: {total} dummy leads created ({b2c} B2C, {b2b} B2B)")
print(f"Database: {DB_PATH}")
