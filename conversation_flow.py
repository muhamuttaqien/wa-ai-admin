from datetime import datetime, timezone
from conversation import _connect, _lock


def _columns(conn):
    return {row["name"] for row in conn.execute("PRAGMA table_info(program_flow_state)").fetchall()}


def init_flow_db():
    with _lock:
        with _connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS program_flow_state (
                    sender TEXT PRIMARY KEY,
                    b2c_intro_confirmed INTEGER DEFAULT 0,
                    infographic_sent INTEGER DEFAULT 0,
                    class_link_sent_for TEXT,
                    registration_doc_sent INTEGER DEFAULT 0,
                    registration_confirmed INTEGER DEFAULT 0,
                    payment_claimed INTEGER DEFAULT 0,
                    proposal_sent INTEGER DEFAULT 0,
                    meeting_request TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            existing = _columns(conn)
            if "class_link_sent_for" not in existing:
                conn.execute("ALTER TABLE program_flow_state ADD COLUMN class_link_sent_for TEXT")
            if "registration_confirmed" not in existing:
                conn.execute("ALTER TABLE program_flow_state ADD COLUMN registration_confirmed INTEGER DEFAULT 0")


def get_flow(sender):
    with _lock:
        with _connect() as conn:
            row = conn.execute("SELECT * FROM program_flow_state WHERE sender=?", (sender,)).fetchone()
    if row:
        d = dict(row)
        for k in ("b2c_intro_confirmed","infographic_sent","registration_doc_sent","registration_confirmed","payment_claimed","proposal_sent"):
            d[k] = bool(d.get(k))
        return d
    return {"sender":sender,"b2c_intro_confirmed":False,"infographic_sent":False,"class_link_sent_for":None,"registration_doc_sent":False,"registration_confirmed":False,"payment_claimed":False,"proposal_sent":False,"meeting_request":None}


def update_flow(sender, **updates):
    allowed = {"b2c_intro_confirmed","infographic_sent","class_link_sent_for","registration_doc_sent","registration_confirmed","payment_claimed","proposal_sent","meeting_request"}
    clean = {k:v for k,v in updates.items() if k in allowed and v is not None}
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        with _connect() as conn:
            conn.execute("INSERT OR IGNORE INTO program_flow_state(sender, updated_at) VALUES (?,?)", (sender,now))
            if clean:
                vals=[]; assigns=[]
                for k,v in clean.items():
                    if k in {"b2c_intro_confirmed","infographic_sent","registration_doc_sent","registration_confirmed","payment_claimed","proposal_sent"}:
                        v = 1 if v else 0
                    assigns.append(f"{k}=?"); vals.append(v)
                conn.execute(f"UPDATE program_flow_state SET {', '.join(assigns)}, updated_at=? WHERE sender=?", (*vals,now,sender))
    return get_flow(sender)


def plan_flow(category, lead, flow):
    """Return stage, one required question, and media action. Keep flows short."""
    if category == "AI Intensive Bootcamp":
        if not flow.get("b2c_intro_confirmed"):
            return {"stage":"B2C_INTRO","question":"Kakak mau tanya program AI Intensive Bootcampnya yah?","media":None}
        if not flow.get("infographic_sent"):
            return {"stage":"B2C_OVERVIEW","question":"Dari tiga kelasnya, kakak lebih tertarik Machine Learning (ML), Computer Vision (CV), atau Natural Language Processing (NLP)?","media":"bootcamp_infographic"}
        if not lead.get("selected_class"):
            return {"stage":"B2C_CLASS_SELECTION","question":"Kalau dari ketiganya, kakak lebih tertarik ML, CV, atau NLP?","media":None}
        if flow.get("class_link_sent_for") != lead.get("selected_class"):
            return {"stage":"B2C_CLASS_INFO","question":None,"media":None}
        if lead.get("registration_intent") and not flow.get("registration_confirmed"):
            qty = lead.get("registration_quantity") or 1
            return {"stage":"B2C_REGISTRATION_CONFIRM","question":f"Baik kak, berarti kakak mau daftar kelas {lead.get('selected_class')} untuk {qty} orang saja yah kak?","media":None}
        if lead.get("registration_intent") and flow.get("registration_confirmed") and not flow.get("registration_doc_sent"):
            return {"stage":"B2C_SEND_REGISTRATION_DOC","question":None,"media":"bootcamp_registration_bundle"}
        if flow.get("payment_claimed"):
            return {"stage":"B2C_PAYMENT_CHECK","question":None,"media":None}
        return {"stage":"B2C_RESPONSIVE","question":None,"media":None}

    if category == "AI Corporate Training":
        missing_identity = [x for x in ("contact_name","company_name","representative_division") if not lead.get(x)]
        if missing_identity:
            return {"stage":"B2B_IDENTIFICATION","question":"Sebelumnya boleh tahu saya berbicara dengan Bapak/Ibu siapa, dari perusahaan apa, dan saat ini mewakili divisi atau tim apa yah?","media":None}
        if not lead.get("participant_count"):
            return {"stage":"B2B_PARTICIPANTS","question":"Untuk estimasi pesertanya kira-kira berapa orang yah Bapak/Ibu?","media":None}
        if not lead.get("preferred_delivery"):
            return {"stage":"B2B_DELIVERY","question":"Untuk pelaksanaannya lebih prefer online atau offline/onsite yah Bapak/Ibu?","media":None}
        if not lead.get("training_goal"):
            return {"stage":"B2B_GOAL","question":"Untuk kebutuhan trainingnya lebih mengarah ke AI Engineering, Generative AI Tools, atau ada kebutuhan lainnya yah Bapak/Ibu?","media":None}
        if not flow.get("proposal_sent"):
            return {"stage":"B2B_SEND_PROPOSAL","question":None,"media":"corporate_proposal"}
        if flow.get("meeting_request"):
            return {"stage":"B2B_MEETING_REQUESTED","question":None,"media":None}
        return {"stage":"B2B_WAITING_CUSTOMER","question":None,"media":None}

    return {"stage":"UNKNOWN","question":None,"media":None}


init_flow_db()
