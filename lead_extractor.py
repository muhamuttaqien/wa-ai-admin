import json
from dotenv import load_dotenv
from openai import OpenAI
from lead_store import LEAD_FIELDS

load_dotenv()
client = OpenAI()


def _history_text(history):
    if not history:
        return "(Belum ada percakapan sebelumnya.)"
    return "\n".join(
        f"{'Pelanggan' if item['role'] == 'user' else 'Admin'}: {item['content']}"
        for item in history
    )


def extract_lead_updates(message, classification, history, current_lead):
    current = {field: current_lead.get(field) for field in LEAD_FIELDS}
    response = client.responses.create(
        model="gpt-5.6",
        input=[
            {"role": "system", "content": """Anda mengekstrak data lead Indonesia AI dari percakapan WhatsApp.

Ekstrak HANYA fakta yang dinyatakan atau didukung jelas oleh pelanggan. Jangan menebak.

Field:
- product_interest: "AI Corporate Training", "AI Intensive Bootcamp", atau null
- contact_name: nama orang/PIC yang sedang berbicara, atau null
- company_name: nama perusahaan/organisasi, atau null
- representative_division: posisi, jabatan, tim, departemen, atau divisi yang diwakili pelanggan. Pertahankan wording ringkas yang dinyatakan pelanggan, atau null
- participant_count: integer jumlah peserta, atau null
- training_goal: tujuan/kebutuhan utama, atau null
- experience_level: tingkat pengalaman yang dinyatakan, atau null
- preferred_delivery: Online, Onsite, Hybrid, atau null
- location: lokasi yang relevan, atau null
- selected_class: "ML", "CV", "NLP", atau null. Normalisasi Machine Learning/kelas ML menjadi ML, Computer Vision/kelas CV menjadi CV, dan Natural Language Processing/kelas NLP menjadi NLP
- registration_intent: true jika pelanggan jelas memutuskan ingin mendaftar, atau null
- registration_quantity: integer jumlah orang yang akan didaftarkan, atau null

Aturan:
- Kembalikan null untuk field tanpa informasi BARU.
- Jangan menghapus data lama jika pesan terbaru tidak menyebutnya.
- Jika pelanggan mengoreksi data lama, keluarkan nilai baru.
- product_interest boleh menggunakan hasil klasifikasi jika jelas.
- Jangan mengubah pertanyaan Admin menjadi fakta pelanggan.
- Jangan menebak nama, perusahaan, divisi, jabatan, lokasi, delivery mode, atau level pengalaman.
- Jika pelanggan berkata misalnya "Saya Andi dari HR PT Maju Digital", ekstrak contact_name=Andi, company_name=PT Maju Digital, representative_division=HR.
- participant_count harus integer.

Kembalikan HANYA JSON dengan semua field:
{
  "product_interest": null,
  "contact_name": null,
  "company_name": null,
  "representative_division": null,
  "participant_count": null,
  "training_goal": null,
  "experience_level": null,
  "preferred_delivery": null,
  "location": null,
  "selected_class": null,
  "registration_intent": null,
  "registration_quantity": null
}"""},
            {"role": "user", "content": f"""CURRENT LEAD PROFILE:
{json.dumps(current, ensure_ascii=False)}

CLASSIFICATION:
{json.dumps(classification, ensure_ascii=False)}

RIWAYAT:
{_history_text(history)}

PESAN TERBARU PELANGGAN:
{message}

Ekstrak hanya informasi BARU atau koreksi yang didukung percakapan."""}
        ]
    )
    data = json.loads(response.output_text)
    result = {field: data.get(field) for field in LEAD_FIELDS}
    if result["participant_count"] is not None:
        try:
            result["participant_count"] = int(result["participant_count"])
        except (TypeError, ValueError):
            result["participant_count"] = None
    if result["product_interest"] not in {None, "AI Corporate Training", "AI Intensive Bootcamp"}:
        result["product_interest"] = None
    if result["preferred_delivery"] == "Offline":
        result["preferred_delivery"] = "Onsite"
    if result["preferred_delivery"] not in {None, "Online", "Onsite", "Hybrid"}:
        result["preferred_delivery"] = None
    if result.get("selected_class") is not None:
        raw_class = str(result["selected_class"]).strip().lower()
        class_map = {
            "ml": "ML",
            "machine learning": "ML",
            "machine learning (ml)": "ML",
            "cv": "CV",
            "computer vision": "CV",
            "computer vision (cv)": "CV",
            "nlp": "NLP",
            "natural language processing": "NLP",
            "natural language processing (nlp)": "NLP",
        }
        result["selected_class"] = class_map.get(raw_class)
    if result.get("registration_intent") is not True:
        result["registration_intent"] = None
    if result.get("registration_quantity") is not None:
        try:
            result["registration_quantity"] = int(result["registration_quantity"])
        except (TypeError, ValueError):
            result["registration_quantity"] = None
    return result
