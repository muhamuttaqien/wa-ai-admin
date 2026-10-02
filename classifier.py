import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from usage_store import record_openai_usage

load_dotenv()
client = OpenAI()
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

def history_text(history):
    if not history:
        return "(Belum ada percakapan sebelumnya.)"
    return "\n".join(
        f"{'Pelanggan' if x['role'] == 'user' else 'Admin'}: {x['content']}"
        for x in history
    )

def classify_message(message: str, history=None, sender=None) -> dict:
    history = history or []
    response = client.responses.create(
        model=MODEL,
        input=[
            {"role": "system", "content": """Anda adalah AI Admin Indonesia AI.
Tentukan intent layanan pesan TERBARU dengan mempertimbangkan riwayat.

Kategori valid:
1. AI Corporate Training - pelatihan untuk perusahaan, organisasi, instansi, atau tim.
2. AI Intensive Bootcamp - program pembelajaran intensif AI untuk individu.
3. Unknown - intent belum jelas atau tidak terkait langsung dengan dua layanan.

Pesan lanjutan yang singkat boleh mewarisi konteks percakapan sebelumnya.
Pahami konteks semantik, bukan keyword saja.

Kembalikan HANYA JSON:
{"category":"...","confidence":0.0,"reason":"..."}"""},
            {"role": "user", "content": f"""RIWAYAT:
{history_text(history)}

PESAN TERBARU:
{message}

Klasifikasikan intent pesan terbaru dalam konteks percakapan."""}
        ]
    )
    record_openai_usage(sender, "classifier", MODEL, response)
    return json.loads(response.output_text)
