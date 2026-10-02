import json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()


def analyze_flow_signals(message: str, category: str, history=None) -> dict:
    history = history or []
    history_text = "\n".join(
        f"{'Pelanggan' if x['role']=='user' else 'Admin'}: {x['content']}" for x in history[-8:]
    ) or "(Belum ada riwayat.)"
    response = client.responses.create(
        model="gpt-5.6",
        input=[
            {"role":"system","content":"""Ekstrak sinyal state percakapan WhatsApp Indonesia AI. Jangan menebak. Kembalikan JSON saja.

Field:
- b2c_intro_confirmed: true jika pelanggan mengonfirmasi/menunjukkan jelas ingin membahas AI Intensive Bootcamp, false/null jika tidak jelas.
- selected_class: hanya salah satu "ML", "CV", "NLP", atau null. Normalisasi nama panjang ke singkatan ini.
- registration_intent: true jika pelanggan jelas ingin daftar/mendaftar, false/null jika tidak.
- registration_quantity: integer jumlah orang yang akan didaftarkan jika jelas, atau null.
- registration_confirmed: true hanya jika pelanggan secara jelas mengiyakan konfirmasi admin mengenai kelas yang dipilih DAN jumlah orang yang akan didaftarkan. Jawaban seperti "iya kak", "betul", atau "benar" dapat menjadi true jika riwayat terakhir jelas berisi pertanyaan konfirmasi registrasi. Jangan anggap "baik kak" atau "ok kak" sebagai konfirmasi.
- payment_claimed: true jika pelanggan menyatakan pembayaran sudah dilakukan/ditransfer, false/null jika tidak.
- meeting_request: hanya "Quick Call", "Quick Meeting", atau null jika pelanggan meminta salah satunya.

Jangan mengubah pertanyaan admin menjadi fakta pelanggan. Jangan anggap sekadar bertanya harga sebagai niat daftar."""},
            {"role":"user","content":f"""Kategori: {category}
Riwayat:
{history_text}
Pesan terbaru pelanggan:
{message}

JSON:"""}
        ]
    )
    try:
        data = json.loads(response.output_text)
    except Exception:
        data = {}
    allowed = {"ML", "CV", "NLP"}
    selected = data.get("selected_class")
    if selected not in allowed:
        selected = None
    meeting = data.get("meeting_request")
    if meeting not in {"Quick Call", "Quick Meeting"}:
        meeting = None
    qty = data.get("registration_quantity")
    try:
        qty = int(qty) if qty is not None else None
    except (TypeError, ValueError):
        qty = None
    return {
        "b2c_intro_confirmed": True if data.get("b2c_intro_confirmed") is True else None,
        "selected_class": selected,
        "registration_intent": True if data.get("registration_intent") is True else None,
        "registration_quantity": qty,
        "registration_confirmed": True if data.get("registration_confirmed") is True else None,
        "payment_claimed": True if data.get("payment_claimed") is True else None,
        "meeting_request": meeting,
    }
