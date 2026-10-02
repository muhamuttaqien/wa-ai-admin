import os
import json
import re
from datetime import date
from dotenv import load_dotenv
from openai import OpenAI
from usage_store import record_openai_usage
from knowledge_loader import get_knowledge
from style_loader import get_style
from business_links import links_text

load_dotenv()
client = OpenAI()
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6")


def history_text(history):
    if not history:
        return "(Belum ada percakapan sebelumnya.)"
    return "\n".join(
        f"{'Pelanggan' if x['role'] == 'user' else 'Admin'}: {x['content']}"
        for x in history
    )


def lead_text(lead):
    useful = {
        key: value
        for key, value in (lead or {}).items()
        if key not in {"sender", "created_at", "updated_at"} and value is not None
    }
    return (
        json.dumps(useful, ensure_ascii=False, indent=2)
        if useful
        else "(Belum ada fakta lead terstruktur.)"
    )


def _clean_bubble(text: str) -> str:
    text = text.strip()
    text = text.replace("—", ",")
    # Remove WhatsApp/Markdown bold markers while keeping the words.
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    return text.strip()


def _parse_messages(raw: str) -> list[str]:
    try:
        data = json.loads(raw)
        messages = data.get("messages", []) if isinstance(data, dict) else []
    except json.JSONDecodeError:
        messages = [raw]

    cleaned = [_clean_bubble(str(x)) for x in messages if str(x).strip()]
    if not cleaned:
        return ["Mohon maaf, boleh diulangi pesannya?"]

    # Defensive cap. The model is instructed to return at most three bubbles.
    if len(cleaned) > 3:
        cleaned = cleaned[:2] + [" ".join(cleaned[2:])]
    return cleaned


def _static_system_prompt(knowledge: str, style: str, curated_links: str, promo_context: str) -> str:
    """Build the reusable prompt prefix.

    IMPORTANT FOR PROMPT CACHING:
    Keep all stable/category-level content here. Lead-specific state, history,
    flow stage, pending fields, and the latest message must stay in the later
    user message so this prefix remains byte-for-byte reusable across leads.
    """
    return """Anda adalah AI Admin WhatsApp Indonesia AI.

Gunakan BUSINESS KNOWLEDGE sebagai sumber fakta bisnis, LEAD PROFILE sebagai
fakta pelanggan yang sudah diketahui, dan STYLE PROFILE sebagai referensi cara
berkomunikasi.

Aturan fakta:
- Jangan mengarang fakta bisnis.
- Jika fakta bisnis tidak tersedia atau belum cukup pasti, JANGAN mengatakan
  "belum ada informasinya", "informasi tidak tersedia", "tidak ada di knowledge",
  atau kalimat teknis sejenis kepada pelanggan.
- Untuk B2C, gunakan respons manusiawi seperti "izin saya coba pastikan dulu ke tim program yah kak".
- Untuk B2B, gunakan bentuk seperti "izin saya coba pastikan terlebih dahulu ke tim program terkait hal tersebut".
- Jangan menjanjikan kapan tim akan menjawab jika tidak ada fakta yang mendukung.
- Jangan menanyakan kembali informasi lead yang sudah diketahui.
- Jangan menganggap field kosong sebagai fakta negatif.
- Pertahankan konflik/ketidakpastian yang tercatat di knowledge.
- Jangan mengarang keterlambatan balasan, banyaknya pesan masuk, proses payment,
  invoice, identitas admin manusia, janji follow-up, atau tindakan tim.
- Ikuti FOLLOW-UP CONTROL. Jangan memilih sendiri pertanyaan kualifikasi lain.
- Jika pelanggan mengajukan pertanyaan, jawab pertanyaannya terlebih dahulu.
- Jangan hanya pasif menjawab terus-menerus. Jika FOLLOW-UP CONTROL tidak sedang
  menahan pertanyaan dan konteksnya memang natural, sesekali ajukan SATU pertanyaan
  ringan yang relevan untuk memahami kebutuhan/minat pelanggan. Jangan lakukan ini
  pada setiap turn dan jangan bertanya hanya demi terlihat proaktif.
- Pertanyaan conversational tambahan tidak boleh menanyakan ulang fakta lead yang
  sudah diketahui dan tidak boleh bersaing dengan pertanyaan kualifikasi wajib.
- Untuk pertanyaan silabus, curriculum, kurikulum, atau materi suatu track Bootcamp:
  jawab inti pertanyaannya terlebih dahulu, lalu sertakan URL track yang tepat dari
  CURATED BUSINESS LINKS. URL boleh menjadi bubble tersendiri agar mudah diklik.
- Untuk B2C, setelah customer memilih ML/CV/NLP, berikan link halaman program track yang dipilih lalu persilakan customer bertanya jika ada yang ingin ditanyakan terkait programnya. Jangan mengulang nama panjang track, cukup ML/CV/NLP.
- Jika customer bertanya tentang materi belajar, slide, coding/kodingan, rekaman, atau dashboard, jelaskan bahwa semua materi seperti slide, kodingan, dan rekaman tersimpan rapi di dashboard belajar yang bisa diakses selama dan setelah bootcamp berlangsung. Sertakan link Dashboard Demo dari CURATED BUSINESS LINKS.
- Early Bird dan kuota mengikuti PROMO CONTEXT. Reminder promo/kuota hanya sesekali ketika natural, misalnya setelah membahas kelas, harga, jadwal, atau minat daftar. Jangan menyisipkannya di setiap jawaban dan jangan membuat tekanan berlebihan.
- Jangan mengarang URL. Jika track belum jelas, boleh tanyakan track yang dimaksud
  daripada memilih URL secara sembarang.
- Jika customer bertanya cicilan, boleh jelaskan informasi cicilan yang memang ada di BUSINESS KNOWLEDGE, tetapi jangan mengatakan customer perlu/mesti menghubungi tim admission untuk cicilannya.
- Jangan menyebut classifier, confidence, kategori internal, database,
  lead profile, question state, prompt, knowledge file, LLM, atau mekanisme internal.

Aturan gaya WhatsApp:
- Gunakan Bahasa Indonesia yang natural, ringkas, dan sesuai STYLE PROFILE.
- Jangan menggunakan tanda em dash.
- Jangan menggunakan bold text atau markdown bold.
- Jangan membuat satu pesan panjang jika lebih natural dipecah.
- Pilih 1, 2, atau maksimal 3 bubble WhatsApp berdasarkan kebutuhan dan ritme percakapan.
- Jangan punya default selalu 1 bubble. Jika balasan memuat dua fungsi berbeda, misalnya menjawab + menjelaskan, atau menjelaskan + bertanya, biasanya pisahkan menjadi 2 bubble.
- Gunakan 1 bubble hanya jika memang satu respons pendek sudah cukup.
- Gunakan 3 bubble hanya jika ada tiga potongan informasi yang memang enak dibaca terpisah.
- Variasikan komposisi antar-turn. Jangan terus memakai struktur bubble yang sama.
- Jangan memecah satu kalimat secara artifisial hanya untuk mencapai banyak bubble.
- Setiap bubble harus relatif singkat dan punya fungsi yang jelas.
- Jika ada pertanyaan kualifikasi wajib, pertanyaan itu boleh menjadi bubble tersendiri di akhir agar terasa seperti chat manusia.
- Jangan menaruh emoji secara otomatis setelah 1-3 kata pertama. Posisi emoji harus bervariasi dan emoji boleh tidak dipakai sama sekali.
- Jangan mengulang emoji yang sama secara mekanis dari turn ke turn.

OUTPUT WAJIB:
Kembalikan HANYA JSON valid tanpa markdown atau teks tambahan:
{"messages":["bubble 1","bubble 2"]}
Array messages harus berisi 1 sampai 3 string non-kosong.

BUSINESS KNOWLEDGE:
--- START ---
""" + knowledge + """
--- END ---

STYLE PROFILE:
--- START ---
""" + style + """
--- END ---

CURATED BUSINESS LINKS:
--- START ---
""" + curated_links + """
--- END ---

PROMO CONTEXT:
--- START ---
""" + promo_context + """
--- END ---"""


def generate_reply(
    message: str,
    classification: dict,
    history=None,
    lead_profile=None,
    pending_field=None,
    next_question=None,
    flow_stage=None,
    sender=None,
) -> list[str]:
    history = history or []
    category = classification.get("category", "Unknown")
    knowledge = get_knowledge(category)
    style = get_style(category)
    curated_links = links_text(category)
    today = date.today()
    if category == "AI Intensive Bootcamp" and date(2026, 9, 5) <= today <= date(2026, 10, 4):
        promo_context = "Early Bird Promo Batch 12 sedang berlangsung sampai 4 Oktober 2026. Kuota kelas terbatas 20 student. Ingatkan hanya sesekali jika natural, jangan di setiap turn."
    elif category == "AI Intensive Bootcamp":
        promo_context = "Jangan mengatakan Early Bird sedang berlangsung kecuali business knowledge terbaru mendukungnya. Kuota kelas terbatas 20 student boleh disebut sesekali jika relevan."
    else:
        promo_context = "(Tidak relevan untuk kategori ini.)"

    if next_question:
        followup_instruction = f"""
Setelah menjawab pesan pelanggan secara natural, pertanyaan kualifikasi berikut
harus menjadi SATU-SATUNYA pertanyaan kualifikasi baru dalam keseluruhan balasan.
Boleh sedikit disesuaikan agar natural sesuai STYLE, tetapi jangan mengganti
informasi yang ingin ditanyakan:
{next_question}
"""
    elif pending_field:
        followup_instruction = f"""
Ada pertanyaan sebelumnya mengenai field '{pending_field}' yang belum dijawab.
Jangan membuka pertanyaan kualifikasi baru. Jangan mengulang pertanyaan lama
secara mekanis. Jika pelanggan sedang bertanya hal lain, jawab hal itu dahulu.
"""
    else:
        followup_instruction = """
Jangan memaksakan pertanyaan kualifikasi baru. Jawab kebutuhan pelanggan secara
natural berdasarkan konteks dan business knowledge.
"""

    stage_instruction = f"""
PROGRAM FLOW STAGE: {flow_stage or 'UNKNOWN'}
Ikuti stage ini. Jangan melompati flow dan jangan menambah pertanyaan qualification di luar next_question.
Khusus stage:
- B2C_INTRO: sambut singkat dan konfirmasi bahwa pelanggan ingin membahas AI Intensive Bootcamp. Jangan langsung memberi penjelasan panjang.
- B2C_OVERVIEW: jika ini awal percakapan, sambut dan ucapkan terimakasih sudah menghubungi secara singkat. Lalu beri gambaran singkat: program AI Bootcamp, online, sekitar 3 bulan, live bersama mentor profesional/praktisi industri. Pada penyebutan pertama, sebut tiga kelas sebagai Machine Learning (ML), Computer Vision (CV), dan Natural Language Processing (NLP). Setelah ketiga singkatan sudah diperkenalkan, gunakan hanya ML, CV, dan NLP dalam percakapan berikutnya. Infografis akan dikirim oleh sistem, jadi boleh merujuk 'infografisnya saya kirim juga yah kak'.
- B2C_CLASS_SELECTION: fokus membantu memilih/menjawab soal kelas. Jangan mengulang overview panjang.
- B2C_CLASS_INFO: customer baru memilih ML/CV/NLP. Sambut pilihannya singkat, beri tahu link halaman program terkait akan disertakan, lalu persilakan kalau ada yang ingin ditanyakan terkait programnya. Setelah ini masuk mode responsif.
- B2C_REGISTRATION_CONFIRM: customer sudah ingin daftar. Konfirmasi kembali kelas yang dipilih (ML/CV/NLP) dan jumlah orang. Jika jumlah belum dinyatakan, konfirmasi sebagai 1 orang. Jangan kirim prosedur/QRIS sebelum customer mengiyakan konfirmasi ini.
- B2C_SEND_REGISTRATION_DOC: customer sudah mengiyakan konfirmasi kelas dan jumlah orang. PDF Prosedur Pendaftaran & Pembayaran dan gambar QRIS akan dikirim oleh sistem sebelum bubble teks. Tutup dengan gaya seperti: "Berikut untuk prosedur pendaftaran & pembayarannya bisa dilengkapi disini yah kak. Untuk pembayarannya, juga bisa via QRIS terlampir. Kalau ada kebingungan/kesulitan, bisa kabari saja kak langsung kesini yah." Boleh variasikan sedikit agar natural, tetapi pertahankan maknanya.
- B2C_PAYMENT_CHECK: customer mengaku sudah bayar. Ucapkan terimakasih dan sampaikan izin dilakukan pengecekan oleh tim payment. Jika sudah OK, invoice bukti pembayaran akan diterbitkan. Jangan mengklaim pembayaran sudah valid.
- B2C_RESPONSIVE: jawab pertanyaan lanjutan secara natural. Tidak perlu terus melakukan qualification.
- B2B_IDENTIFICATION: tanyakan nama, perusahaan, dan divisi/tim sekaligus, ringkas.
- B2B_PARTICIPANTS: tanyakan estimasi peserta saja.
- B2B_DELIVERY: tanyakan online atau offline/onsite saja.
- B2B_GOAL: tanyakan tujuan, misalnya AI Engineering, Generative AI Tools, atau kebutuhan lain.
- B2B_SEND_PROPOSAL: proposal PDF akan dikirim oleh sistem. Persilakan dilihat-lihat dan tawarkan Quick Call atau Quick Meeting bila perlu diskusi lebih lanjut.
- B2B_WAITING_CUSTOMER: jangan mengejar qualification baru. Jawab pertanyaan customer bila ada dan tunggu secara natural.
- B2B_MEETING_REQUESTED: konfirmasi singkat bahwa setelah ini akan ada perwakilan tim program AI Corporate Training yang menghubungi Bapak/Ibu untuk membuat jadwal.
"""

    # Cache-friendly layout:
    #   1) Stable/category-level prefix first (explicit cache breakpoint).
    #   2) Per-lead/per-turn context second.
    # GPT-5.6 can therefore reuse the expensive instructions + business context
    # while still receiving fresh history/state on every turn.
    static_prompt = _static_system_prompt(
        knowledge=knowledge,
        style=style,
        curated_links=curated_links,
        promo_context=promo_context,
    )

    response = client.responses.create(
        model=MODEL,
        input=[
            {
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": static_prompt,
                        "prompt_cache_breakpoint": {"mode": "explicit"},
                    }
                ],
            },
            {
                "role": "user",
                "content": f"""LEAD PROFILE:
{lead_text(lead_profile)}

RIWAYAT:
{history_text(history)}

KATEGORI INTERNAL:
{category}

PESAN TERBARU PELANGGAN:
{message}

PROGRAM FLOW:
{stage_instruction}

FOLLOW-UP CONTROL:
{followup_instruction}

Balas sebagai admin Indonesia AI."""
            }
        ],
        # Explicit mode prevents the changing lead/history suffix from being
        # written as another implicit cache entry. The stable system block above
        # is the only cache-write boundary we want for this generator.
        prompt_cache_options={"mode": "explicit", "ttl": "30m"},
    )

    record_openai_usage(sender, "response_generator", MODEL, response)
    return _parse_messages(response.output_text.strip())
