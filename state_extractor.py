"""Semantic conversation-state extraction using one OpenAI API call per inbound message.

This replaces the Milestone 6 deterministic regex/local state parser. The model
extracts only structured lead updates and flow signals; response wording remains
handled separately by response_generator.py.
"""
import json
import os

from openai import OpenAI
from usage_store import record_openai_usage

client = OpenAI()
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")


def extract_state(message, category, history, current_lead, flow, sender=None):
    """Extract new lead facts and flow signals semantically from the latest message."""
    history_text = "\n".join(
        f"{'Pelanggan' if x['role'] == 'user' else 'Admin'}: {x['content']}"
        for x in (history or [])[-8:]
    ) or "(Belum ada riwayat.)"

    response = client.responses.create(
        model=MODEL,
        input=[
            {
                "role": "system",
                "content": """Anda adalah semantic state extractor untuk WhatsApp Admin Indonesia AI.
Ekstrak HANYA informasi baru yang jelas dari pesan pelanggan terbaru. Gunakan riwayat untuk memahami konteks jawaban singkat, typo, singkatan, dan bahasa percakapan. Jangan menebak fakta yang tidak didukung pelanggan. Kembalikan JSON saja, tanpa markdown.

lead_updates boleh berisi:
- contact_name
- company_name
- representative_division
- participant_count (integer)
- training_goal
- experience_level
- preferred_delivery (Online/Onsite/Hybrid)
- location
- selected_class (ML/CV/NLP)
- registration_intent (true)
- registration_quantity (integer)

signals boleh berisi:
- b2c_intro_confirmed (true)
- selected_class (ML/CV/NLP)
- registration_intent (true)
- registration_quantity (integer)
- registration_confirmed (true)
- payment_claimed (true)
- meeting_request (Quick Call/Quick Meeting)
- media_request, salah satu dari:
  bootcamp_brochure
  bootcamp_infographic
  bootcamp_infographic_red
  bootcamp_infographic_white
  learning_dashboard
  bootcamp_registration_doc
  bootcamp_qris
  payment_due_date
  bootcamp_registration_bundle
  corporate_proposal

Catatan: last_call_h5/last_call_h3/last_call_h1/last_call_today adalah aset campaign internal.
Jangan pilih aset Last Call dari percakapan pelanggan biasa.

Aturan penting:
- Pahami typo/singkatan secara semantik. Contoh "sudah saa trannnsfer", "udh tf", atau "barusan bayar" dapat berarti payment_claimed=true bila konteks jelas.
- Jika pelanggan secara eksplisit bertanya/menyatakan minat tentang AI Intensive Bootcamp, b2c_intro_confirmed=true.
- Jika pelanggan memilih ML/CV/NLP, isi selected_class pada lead_updates dan signals.
- Jika pelanggan menyatakan ingin mendaftar, registration_intent=true.
- Jika pelanggan mengonfirmasi pertanyaan Admin tentang pendaftaran/jumlah, gunakan riwayat untuk menentukan registration_confirmed dan quantity bila jelas.
- Jika pelanggan meminta media/dokumen dikirim atau dikirim ulang, isi media_request secara semantik meskipun ada typo, singkatan, atau susunan kalimat bebas.
- Contoh: "kirimin lagi infografiis sebelumnya" -> media_request="bootcamp_infographic".
- "ada brosur lengkapnya?" atau "kirim pdf programnya" -> media_request="bootcamp_brochure".
- "kirim infografis merah" -> media_request="bootcamp_infographic_red".
- "yang versi putih ada?" -> media_request="bootcamp_infographic_white".
- "dashboard belajarnya seperti apa?" atau "kirim gambar dashboard" -> media_request="learning_dashboard".
- "kirim QRIS lagi" -> media_request="bootcamp_qris".
- "kirim prosedur/pdf pendaftaran lagi" -> media_request="bootcamp_registration_doc".
- "tanggal jatuh temponya gimana?" atau "kirim info jatuh tempo" -> media_request="payment_due_date".
- Jika pelanggan meminta prosedur pendaftaran DAN QRIS sekaligus -> media_request="bootcamp_registration_bundle".
- "kirim proposal lagi" -> media_request="corporate_proposal".
- Untuk permintaan generik seperti "boleh kirim ulang?", gunakan Current flow dan riwayat: bila registration_doc_sent=true pada B2C, media_request="bootcamp_registration_bundle"; bila hanya infographic_sent=true, media_request="bootcamp_infographic"; bila proposal_sent=true pada B2B, media_request="corporate_proposal".
- Permintaan media ulang tidak boleh mengubah registration/payment/proposal state lain.
- Jangan mengubah pertanyaan atau pernyataan Admin menjadi fakta pelanggan.
- Field yang tidak memiliki informasi baru harus dihilangkan.""",
            },
            {
                "role": "user",
                "content": f"""Kategori: {category}
Current lead: {json.dumps(current_lead, ensure_ascii=False)}
Current flow: {json.dumps(flow, ensure_ascii=False)}
Riwayat:\n{history_text}
Pesan terbaru:\n{message}

Kembalikan persis dalam bentuk: {{\"lead_updates\":{{}},\"signals\":{{}}}}""",
            },
        ],
    )
    record_openai_usage(sender, "state_extractor", MODEL, response)

    try:
        data = json.loads(response.output_text)
    except Exception:
        return {"lead_updates": {}, "signals": {}}

    lead = data.get("lead_updates") if isinstance(data.get("lead_updates"), dict) else {}
    sig = data.get("signals") if isinstance(data.get("signals"), dict) else {}

    if lead.get("preferred_delivery") == "Offline":
        lead["preferred_delivery"] = "Onsite"
    if lead.get("preferred_delivery") not in {None, "Online", "Onsite", "Hybrid"}:
        lead.pop("preferred_delivery", None)
    if lead.get("selected_class") not in {None, "ML", "CV", "NLP"}:
        lead.pop("selected_class", None)
    if sig.get("selected_class") not in {None, "ML", "CV", "NLP"}:
        sig.pop("selected_class", None)
    if sig.get("meeting_request") not in {None, "Quick Call", "Quick Meeting"}:
        sig.pop("meeting_request", None)
    if sig.get("media_request") not in {
        None,
        "bootcamp_brochure",
        "bootcamp_infographic",
        "bootcamp_infographic_red",
        "bootcamp_infographic_white",
        "learning_dashboard",
        "bootcamp_registration_doc",
        "bootcamp_qris",
        "payment_due_date",
        "bootcamp_registration_bundle",
        "corporate_proposal",
    }:
        sig.pop("media_request", None)

    for obj, key in (
        (lead, "participant_count"),
        (lead, "registration_quantity"),
        (sig, "registration_quantity"),
    ):
        if key in obj:
            try:
                obj[key] = int(obj[key])
            except (TypeError, ValueError):
                obj.pop(key, None)

    for obj, key in (
        (lead, "registration_intent"),
        (sig, "b2c_intro_confirmed"),
        (sig, "registration_intent"),
        (sig, "registration_confirmed"),
        (sig, "payment_claimed"),
    ):
        if key in obj and obj[key] is not True:
            obj.pop(key, None)

    return {"lead_updates": lead, "signals": sig}
