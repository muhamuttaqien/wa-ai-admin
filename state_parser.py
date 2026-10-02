import os
"""Milestone 6: cheap state-aware parsing with one LLM fallback.

Common/structured WhatsApp answers are parsed locally. The fallback is used only
when the current flow expects structured information that cannot be extracted
safely with deterministic rules.
"""
import json
import re
from openai import OpenAI
from usage_store import record_openai_usage

client = OpenAI()
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

CLASSES = {
    "ml": "ML", "machine learning": "ML",
    "cv": "CV", "computer vision": "CV",
    "nlp": "NLP", "natural language processing": "NLP",
}


def _last_assistant(history):
    for item in reversed(history or []):
        if item.get("role") in {"assistant", "human_admin"}:
            return item.get("content", "")
    return ""


def _yes(text):
    t = text.strip().lower()
    return bool(re.fullmatch(r"(?:iya|ya|yap|yes|betul|benar|iya kak|ya kak|betul kak|benar kak)[.! ]*", t))


def parse_local_state(message, category, history, current_lead, flow):
    """Return deterministic lead updates + flow signals, without an API call."""
    text = message.strip()
    low = text.lower()
    last_admin = _last_assistant(history).lower()
    lead = {}
    signals = {}

    # Product is authoritative once classification/state has established it.
    if category in {"AI Intensive Bootcamp", "AI Corporate Training"}:
        lead["product_interest"] = category

    # Explicit Bootcamp inquiry already establishes intent. Do not ask the
    # customer to reconfirm that they want to discuss the Bootcamp. This moves
    # the flow directly from B2C_INTRO to B2C_OVERVIEW.
    if category == "AI Intensive Bootcamp":
        mentions_bootcamp = bool(re.search(r"\bboot\s*camp\b|\bbootcamp\b|ai\s+intensive\s+bootcamp", low))
        inquiry_or_interest = bool(re.search(
            r"\b(?:mau|ingin|pengen|pengin|tertarik|boleh|bisa)\b.*\b(?:tanya|tau|tahu|info|informasi|tentang|terkait|bootcamp)\b"
            r"|\b(?:tanya|info|informasi)\b.*\bbootcamp\b"
            r"|\bterkait\b.*\bbootcamp\b",
            low,
        ))
        if mentions_bootcamp and inquiry_or_interest:
            signals["b2c_intro_confirmed"] = True
            signals["explicit_bootcamp_inquiry"] = True

    # B2C class selection.
    found = []
    for phrase, value in CLASSES.items():
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", low):
            found.append(value)
    found = list(dict.fromkeys(found))
    # Avoid treating a question listing all three classes as a selection.
    if len(found) == 1:
        lead["selected_class"] = found[0]
        signals["selected_class"] = found[0]

    # Registration intent and quantity.
    if re.search(r"\b(mau|ingin|hendak|boleh|jadi|akan)\s+(?:ikut|daftar|mendaftar|registrasi)\b|\bdaftar\s+(?:ya|yah|aja|saja)\b", low):
        lead["registration_intent"] = True
        signals["registration_intent"] = True
    qty_match = re.search(r"\b(\d{1,3})\s*(?:orang|peserta|pax)\b", low)
    if qty_match:
        qty = int(qty_match.group(1))
        if category == "AI Intensive Bootcamp" and (lead.get("registration_intent") or current_lead.get("registration_intent")):
            lead["registration_quantity"] = qty
            signals["registration_quantity"] = qty
        elif category == "AI Corporate Training":
            lead["participant_count"] = qty

    # Delivery mode.
    has_online = bool(re.search(r"\bonline\b|zoom|google meet", low))
    has_onsite = bool(re.search(r"\boffline\b|\bonsite\b|on-site|datang ke|di kantor", low))
    has_hybrid = bool(re.search(r"\bhybrid\b", low))
    if has_hybrid:
        lead["preferred_delivery"] = "Hybrid"
    elif has_online and not has_onsite:
        lead["preferred_delivery"] = "Online"
    elif has_onsite and not has_online:
        lead["preferred_delivery"] = "Onsite"

    # Payment claim.
    if re.search(r"\b(sudah|udah|telah)\s+(?:bayar|transfer|melakukan pembayaran)\b|\bpembayaran(?:nya)?\s+(?:sudah|udah)\b", low):
        signals["payment_claimed"] = True

    # Meeting request.
    if re.search(r"\bquick\s*call\b|\bcall\b", low) and re.search(r"mau|ingin|boleh|bisa|jadwal|schedule|request|minta", low):
        signals["meeting_request"] = "Quick Call"
    elif re.search(r"\bquick\s*meeting\b|\bmeeting\b", low) and re.search(r"mau|ingin|boleh|bisa|jadwal|schedule|request|minta", low):
        signals["meeting_request"] = "Quick Meeting"

    # State-aware yes/no interpretation. A bare "iya" is meaningful only when
    # the immediately preceding admin message establishes what is confirmed.
    if _yes(text):
        if (
            category == "AI Intensive Bootcamp"
            and not flow.get("b2c_intro_confirmed")
            and (
                re.search(r"mau\s+tanya.*bootcamp|program\s+ai\s+intensive\s+bootcamp|bahas.*bootcamp", last_admin)
                or "bootcamp" in last_admin
            )
        ):
            signals["b2c_intro_confirmed"] = True
        if category == "AI Intensive Bootcamp" and re.search(r"berarti.*mau daftar.*untuk\s+\d+\s+orang", last_admin):
            signals["registration_confirmed"] = True
            q = re.search(r"untuk\s+(\d+)\s+orang", last_admin)
            if q and not current_lead.get("registration_quantity"):
                lead["registration_quantity"] = int(q.group(1))
                signals["registration_quantity"] = int(q.group(1))

    return {"lead_updates": lead, "signals": signals}


def needs_llm_fallback(message, category, current_lead, flow, parsed):
    """Use fallback only when the flow expects data and local parsing missed it."""
    lead = parsed["lead_updates"]
    if category == "AI Corporate Training":
        if any(not current_lead.get(k) for k in ("contact_name", "company_name", "representative_division")):
            return not any(lead.get(k) for k in ("contact_name", "company_name", "representative_division"))
        if not current_lead.get("participant_count"):
            return lead.get("participant_count") is None
        if not current_lead.get("preferred_delivery"):
            return lead.get("preferred_delivery") is None
        if not current_lead.get("training_goal"):
            return lead.get("training_goal") is None
    return False


def llm_state_fallback(message, category, history, current_lead, sender=None):
    """One call replaces the old lead_extractor + flow_analyzer fallback path."""
    history_text = "\n".join(
        f"{'Pelanggan' if x['role']=='user' else 'Admin'}: {x['content']}" for x in (history or [])[-8:]
    ) or "(Belum ada riwayat.)"
    response = client.responses.create(
        model=MODEL,
        input=[
            {"role":"system","content":"""Ekstrak HANYA informasi baru yang jelas dari pesan pelanggan untuk state WhatsApp Indonesia AI. Jangan menebak. Kembalikan JSON saja.

lead_updates boleh berisi: contact_name, company_name, representative_division, participant_count (integer), training_goal, experience_level, preferred_delivery (Online/Onsite/Hybrid), location, selected_class (ML/CV/NLP), registration_intent (true), registration_quantity (integer).
signals boleh berisi: b2c_intro_confirmed (true), selected_class (ML/CV/NLP), registration_intent (true), registration_quantity (integer), registration_confirmed (true), payment_claimed (true), meeting_request (Quick Call/Quick Meeting).

Jangan mengubah pertanyaan Admin menjadi fakta pelanggan. Untuk jawaban singkat, gunakan riwayat hanya untuk memahami pertanyaan yang sedang dijawab. Jangan keluarkan field yang tidak memiliki informasi baru."""},
            {"role":"user","content":f"""Kategori: {category}
Current lead: {json.dumps(current_lead, ensure_ascii=False)}
Riwayat:\n{history_text}
Pesan terbaru:\n{message}

Kembalikan: {{\"lead_updates\":{{}},\"signals\":{{}}}}"""}
        ]
    )
    record_openai_usage(sender, "state_fallback", MODEL, response)
    try:
        data = json.loads(response.output_text)
    except Exception:
        return {"lead_updates": {}, "signals": {}}
    lead = data.get("lead_updates") if isinstance(data.get("lead_updates"), dict) else {}
    sig = data.get("signals") if isinstance(data.get("signals"), dict) else {}
    # Small validation boundary.
    if lead.get("preferred_delivery") == "Offline": lead["preferred_delivery"] = "Onsite"
    if lead.get("preferred_delivery") not in {None, "Online", "Onsite", "Hybrid"}: lead.pop("preferred_delivery", None)
    if lead.get("selected_class") not in {None, "ML", "CV", "NLP"}: lead.pop("selected_class", None)
    if sig.get("selected_class") not in {None, "ML", "CV", "NLP"}: sig.pop("selected_class", None)
    if sig.get("meeting_request") not in {None, "Quick Call", "Quick Meeting"}: sig.pop("meeting_request", None)
    for obj, key in ((lead,"participant_count"),(lead,"registration_quantity"),(sig,"registration_quantity")):
        if key in obj:
            try: obj[key] = int(obj[key])
            except (TypeError, ValueError): obj.pop(key, None)
    return {"lead_updates": lead, "signals": sig}


def merge_state(local, fallback):
    """Deterministic local values win; fallback only fills missing keys."""
    return {
        "lead_updates": {**fallback.get("lead_updates", {}), **local.get("lead_updates", {})},
        "signals": {**fallback.get("signals", {}), **local.get("signals", {})},
    }
