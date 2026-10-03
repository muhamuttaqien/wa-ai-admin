# WhatsApp AI Admin — Indonesia AI

AI-powered WhatsApp admin untuk **Indonesia AI**, dibangun menggunakan official Meta WhatsApp Business Platform / Cloud API, FastAPI, OpenAI API, SQLite, dan Flask Admin Dashboard.

Repository saat ini melayani dua jalur utama:

- **B2C — AI Intensive Bootcamp**
- **B2B — AI Corporate Training**

Versi aktif saat ini menggunakan **semantic state extraction berbasis LLM pada setiap inbound customer message**. Implementasi `state_parser.py` berbasis local regex telah dihapus karena terlalu rentan terhadap typo, singkatan, dan variasi bahasa WhatsApp. Periodic product classification dan cache-friendly response generation tetap dipertahankan untuk mengontrol biaya API.

---

# 1. Quick Start

Jalankan sistem dari tiga terminal.

Masuk ke project dan aktifkan environment:

```bash
cd ~/Desktop/Indonesia-AI/wa-ai-admin
conda activate indonesia-ai
```

## Terminal 1 — ngrok

```bash
ngrok http 8000 --url https://moneyless-stroller-mounted.ngrok-free.dev
```

Webhook development:

```text
https://moneyless-stroller-mounted.ngrok-free.dev/webhook
```

Callback yang sama harus dikonfigurasi pada Meta Developer App.

## Terminal 2 — FastAPI / WhatsApp AI Admin

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Local service:

```text
http://127.0.0.1:8000
```

Main webhook endpoints:

```text
GET  /webhook    Meta webhook verification
POST /webhook    Incoming WhatsApp events
```

Setelah mengubah source code atau `.env`, restart Uvicorn apabila tidak menjalankannya dengan `--reload`.

## Terminal 3 — Admin Dashboard

```bash
python dashboard/app.py
```

Dengan `.env.example` saat ini:

```text
http://127.0.0.1:8080
```

Dashboard menggunakan login berbasis session. Selama development, tetap disarankan bind ke `127.0.0.1`. Untuk local HTTP testing, `DASHBOARD_COOKIE_SECURE=false`; ketika dashboard diakses melalui HTTPS, gunakan `DASHBOARD_COOKIE_SECURE=true`.

---

# 2. Installation

Install dependency:

```bash
pip install -r requirements.txt
```

Current requirements:

```text
fastapi
uvicorn[standard]
python-dotenv
openai
requests
Flask>=3.0,<4.0
```

---

# 3. Environment Configuration

Gunakan `.env.example` sebagai template dan simpan credential sebenarnya hanya di `.env` lokal.

```env
# ============================================================
# WHATSAPP / META / OPENAI CLOUD API
# ============================================================
OPENAI_MODEL=gpt-5.6
OPENAI_API_KEY=

WHATSAPP_VERIFY_TOKEN=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=1408846128968304
WHATSAPP_GRAPH_API_VERSION=v26.0

# ============================================================
# CONVERSATION MEMORY / DATABASE
# ============================================================
CONVERSATION_DB_PATH=data/conversations.db
CONVERSATION_MAX_MESSAGES=15

# ============================================================
# MESSAGE BUFFER & NATURAL REPLY TIMING
# ============================================================
REPLY_DELAY_MIN_SECONDS=5
REPLY_DELAY_MAX_SECONDS=15
BUBBLE_DELAY_MIN_SECONDS=1.0
BUBBLE_DELAY_MAX_SECONDS=2.5
BUFFER_POLL_SECONDS=1.0
MAX_BATCH_AGE_SECONDS=45

# ============================================================
# B2C FOLLOW-UP
# ============================================================
B2C_FOLLOWUP_ENABLED=true
B2C_PRE_REGISTRATION_FOLLOWUP_HOURS=3
B2C_PRE_REGISTRATION_SECOND_FOLLOWUP_HOURS=9
B2C_POST_REGISTRATION_FOLLOWUP_HOURS=12

# Last Call campaign
B2C_LAST_CALL_ENABLED=true
B2C_LAST_CALL_DELAY_HOURS=12
BOOTCAMP_REGISTRATION_DEADLINE=2026-11-01

# ============================================================
# B2B FOLLOW-UP
# ============================================================
B2B_FOLLOWUP_ENABLED=true
B2B_PRE_PROPOSAL_FOLLOWUP_HOURS=3
B2B_POST_PROPOSAL_FOLLOWUP_HOURS=12

# ============================================================
# ADMIN DASHBOARD
# ============================================================
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=8080
DASHBOARD_MAX_UPLOAD_MB=20
DASHBOARD_USERNAME=admin
DASHBOARD_PASSWORD=
DASHBOARD_SECRET_KEY=
DASHBOARD_COOKIE_SECURE=true

# Approximate USD → IDR display rate on dashboard
USD_TO_IDR_RATE=16500
```

## Important notes

`OPENAI_MODEL=gpt-5.6` adalah konfigurasi aktif yang direkomendasikan saat ini. `classifier.py`, `state_extractor.py`, dan `response_generator.py` membaca model dari environment variable yang sama.

`.env` tidak boleh di-commit. Pastikan `.gitignore` tetap mengecualikan `.env`, database SQLite runtime, Python cache, dan environment lokal.

Meta temporary access token dapat expire. Error Meta `401` dengan OAuth error code `190` menunjukkan masalah authentication/access token, bukan masalah flow AI.

---

# 4. Current Architecture

```text
WhatsApp Customer
       │
       ▼
Meta WhatsApp Cloud API
       │
       ▼
FastAPI Webhook (main.py)
       │
       ├── Message buffer / debounce
       ├── Persistent conversation + lead state
       │
       ├── Periodic semantic product classifier
       │
       ├── Semantic State Extractor (LLM, every inbound turn)
       │
       ├── Deterministic B2C/B2B Conversation Flow
       │
       ├── Grounded business knowledge + curated links
       │
       ├── Media / document actions
       │
       ├── Cache-friendly Response Generator
       │
       ├── Follow-up scheduler
       │
       ├── Admin notifications / human handoff
       │
       └── OpenAI usage telemetry
       │
       ▼
Meta WhatsApp Cloud API
       │
       ▼
WhatsApp Customer

SQLite
  │
  ├── conversations
  ├── lead profile / flow state
  ├── message buffers
  ├── follow-ups
  ├── admin notifications
  └── api_usage
       │
       ▼
Flask Admin Dashboard
       │
       ├── B2C / B2B leads
       ├── conversation history
       ├── API token/cost telemetry
       ├── human notifications
       └── human text/media reply
```

Prinsip utamanya adalah:

```text
Semantic understanding → deterministic business flow → controlled action/media → natural response generation
```

LLM memahami bahasa customer, sedangkan keputusan bisnis seperti stage, media yang harus dikirim, notification, dan follow-up tetap dikontrol oleh application logic.

---

# 5. Semantic Understanding Pipeline

## 5.1 Periodic Product Classification

`classifier.py` menentukan salah satu kategori:

```text
AI Intensive Bootcamp
AI Corporate Training
Unknown
```

Untuk menghemat API call, classification tidak dilakukan pada setiap message jika `product_interest` sudah diketahui.

Current behavior:

```text
Inbound #1, product unknown → classifier API call
Inbound #2–#9             → reuse persistent product_interest
Inbound #10               → classifier API refresh
Inbound #11–#19           → reuse persistent product_interest
Inbound #20               → classifier API refresh
... dan seterusnya
```

Hanya inbound customer/user messages yang dihitung.

Contoh terminal log:

```text
M6 CLASSIFIER : API CALL (product not known; inbound #1)
M6 CLASSIFIER : SKIPPED (persistent state; inbound #4)
M6 CLASSIFIER : API CALL (10-message refresh; inbound #10)
```

Periodic refresh memungkinkan conversation yang panjang berpindah dari Bootcamp ke Corporate Training atau sebaliknya tanpa mengunci kategori selamanya.

## 5.2 Semantic State Extractor

`state_extractor.py` menggantikan local regex/state parser lama.

State extractor dipanggil **sekali untuk setiap inbound customer turn** dan hanya mengembalikan structured JSON, bukan customer-facing response.

Contoh output:

```json
{
  "lead_updates": {
    "selected_class": "CV"
  },
  "signals": {
    "selected_class": "CV"
  }
}
```

State extractor dapat menangkap antara lain:

```text
contact_name
company_name
representative_division
participant_count
training_goal
experience_level
preferred_delivery
location
selected_class
registration_intent
registration_quantity
b2c_intro_confirmed
registration_confirmed
payment_claimed
meeting_request
```

Extractor menggunakan recent history untuk memahami jawaban singkat dan konteks. Ia juga diinstruksikan memahami typo/singkatan secara semantik, misalnya:

```text
"sudah saa trannnsfer kak"
"udh tf"
"barusan bayar"
```

Jika konteksnya jelas, pesan tersebut dapat menghasilkan:

```json
{"signals":{"payment_claimed":true}}
```

Ini penting karena `payment_claimed` digunakan untuk membuat notification pembayaran dan membuka Human Reply di dashboard.

## 5.3 Local State Parser Removed

`state_parser.py` **tidak lagi digunakan dan telah dihapus** dari current architecture.

Alasan utamanya adalah local regex parser dapat sukses secara teknis tetapi gagal secara semantik pada bahasa WhatsApp yang memiliki typo, singkatan, variasi susunan kata, dan konteks percakapan.

Current pipeline tidak lagi memiliki log:

```text
M6 LOCAL PARSER
M6 STATE FALLBACK
```

Sebagai gantinya:

```text
STATE EXTRACTOR : API CALL {...}
```

Legacy `lead_extractor.py` dan `flow_analyzer.py` masih tersedia sebagai reference/rollback, tetapi bukan bagian dari active `main.py` pipeline.

---

# 6. Conversation Flow

`conversation_flow.py` menentukan stage bisnis berdasarkan lead state dan semantic signals.

LLM tidak diberi kebebasan untuk menentukan sendiri apakah proposal, QRIS, PDF pendaftaran, atau infographic harus dikirim. `main.py` dan flow planner yang mengontrol action tersebut.

Ini memisahkan:

```text
Understanding  → state_extractor.py
Business flow  → conversation_flow.py
Wording        → response_generator.py
Delivery       → main.py + whatsapp.py
```

---

# 7. B2C — AI Intensive Bootcamp

Current high-level flow:

```text
Bootcamp inquiry
      ↓
B2C_OVERVIEW
      ↓
Bootcamp infographic
      ↓
ML / CV / NLP selection
      ↓
Class-specific information + responsive Q&A
      ↓
Registration intent
      ↓
Confirm selected class + quantity
      ↓
Registration procedure PDF + QRIS
      ↓
Customer claims payment
      ↓
Payment acknowledgement
      ↓
REGISTRATION_PAYMENT_CONFIRMATION notification
      ↓
Human Reply becomes available
```

Current Bootcamp media library:

```text
B2C Document/
├── AI Intensive Bootcamp.pdf
├── Dashboard Belajar.png
├── Infografis AI Intensive Bootcamp (Red).jpg
├── Infografis AI Intensive Bootcamp (White).jpg
├── Prosedur Pendaftaran & Pembayaran AI Intensive Bootcamp.pdf
├── QRIS Transfer Pembayaran Indonesia AI.jpg
├── Tanggal Jatuh Tempo.jpg
├── Last Call H-5.jpg
├── Last Call H-3.jpg
├── Last Call H-1.jpg
└── Last Call H.jpg
```

Do not move these Bootcamp assets into `B2B Document/` unless the media mapping in `main.py` is intentionally changed as well.

---

# 8. B2B — AI Corporate Training

Current high-level flow:

```text
Corporate Training inquiry
      ↓
name + company + representative division/team
      ↓
participant estimate
      ↓
online / onsite / hybrid
      ↓
training goal
      ↓
Corporate Training proposal PDF
      ↓
responsive discussion
      ↓
Quick Call / Quick Meeting when requested
      ↓
human handling when required
```

Current Corporate document mapping:

```text
B2B Document/
└── Proposal Penawaran AI Corporate Training.pdf
```

---

# 9. Automated Media Delivery

`main.py` owns the canonical media mapping. Media can be selected by deterministic conversation flow or by semantic `media_request` from `state_extractor.py`.

```text
bootcamp_brochure          → AI Intensive Bootcamp.pdf
bootcamp_infographic       → Infografis AI Intensive Bootcamp (Red).jpg
bootcamp_infographic_red   → Infografis AI Intensive Bootcamp (Red).jpg
bootcamp_infographic_white → Infografis AI Intensive Bootcamp (White).jpg
learning_dashboard         → Dashboard Belajar.png
bootcamp_registration_doc  → Prosedur Pendaftaran & Pembayaran AI Intensive Bootcamp.pdf
bootcamp_qris              → QRIS Transfer Pembayaran Indonesia AI.jpg
payment_due_date           → Tanggal Jatuh Tempo.jpg
corporate_proposal         → Proposal Penawaran AI Corporate Training.pdf
```

`bootcamp_registration_bundle` sends the registration procedure PDF and QRIS together. Last Call assets are reserved for the campaign scheduler and are not selected from ordinary customer chat.

Semantic media selection is relevance-based, not limited to explicit requests for a file. For example, a natural question about installments, payment terms, or due dates can produce `media_request=payment_due_date`, so the due-date image accompanies the answer. Resend requests can also select the relevant media without advancing the conversation stage.

For Bootcamp registration, the normal bundle order is procedure PDF → QRIS → natural admin guidance. For ordinary single assets, the delivery pattern is explanatory bubble → asset → remaining bubble(s). Missing required files raise an explicit `Media file tidak ditemukan` error.

---

# 10. Media Resend

Customers can request previously delivered material again.

Examples:

```text
kirim ulang QRIS
kirim QRIS lagi
kirim ulang prosedur pendaftaran
kirim PDF lagi
kirim ulang infografis
kirim ulang proposal
```

For B2C, a generic `kirim ulang` can resend the most recently relevant asset. If registration documents were already delivered, the system resends the registration bundle (procedure PDF + QRIS).

Resend is an explicit delivery action and should not unnecessarily advance the business stage.

---

# 11. Cache-Friendly Response Generator

`response_generator.py` tetap menggunakan LLM untuk menghasilkan natural customer-facing wording.

Prompt dipisahkan menjadi stable prefix dan dynamic suffix:

```text
STABLE PREFIX
├── admin behavior/rules
├── business knowledge
├── style
├── curated links
└── promotion context
       │
       ▼
 explicit cache breakpoint
════════════════════════════
DYNAMIC SUFFIX
├── lead profile
├── recent conversation history
├── product category
├── latest customer message
├── current flow stage
└── follow-up context
```

Current response call menggunakan explicit prompt caching dengan TTL 30 menit.

Caching tidak membuat reply menjadi statis. Customer message, history, lead state, dan flow stage tetap dinamis. Tujuannya hanya mengurangi biaya pemrosesan stable prompt yang berulang.

Current customer-facing output is constrained to 1–3 WhatsApp bubbles. `_parse_messages()` enforces a hard maximum of three bubbles, while the prompt asks each bubble to stay relatively short. There is currently no character-per-bubble hard cap and no `max_output_tokens` hard limit in the response call, so brevity is primarily prompt-controlled.

Customer-facing style also instructs the admin to speak as Indonesia AI directly rather than sounding like it is quoting a website, and to avoid source-referencing phrases such as “berdasarkan yang tercantum”. Colon punctuation should be avoided in prose; technical URLs remain intact.

---

# 12. OpenAI Model Selection

Default current configuration:

```env
OPENAI_MODEL=gpt-5.6
```

Active components yang membaca variable ini:

```text
classifier.py
state_extractor.py
response_generator.py
```

Jika ingin melakukan eksperimen dengan model lain yang memang didukung oleh code/pricing telemetry, ubah `.env` lalu restart Uvicorn.

Current production/development preference repository ini adalah GPT-5.6 (`gpt-5.6`) karena semantic state extraction dan customer-facing conversation membutuhkan pemahaman bahasa yang cukup kuat.

---

# 13. OpenAI API Usage Telemetry

`usage_store.py` menyimpan telemetry per WhatsApp sender ke SQLite.

Stored fields:

```text
sender
call_type
model
input_tokens
cached_input_tokens
cache_write_tokens
output_tokens
estimated_cost_usd
created_at
```

Active call types:

```text
classifier
state_extractor
response_generator
```

Contoh terminal log:

```text
API USAGE [response_generator] : in=5212 cached=4237 write=0 out=101 cost=$0.006763 (≈ Rp 112)
```

Dashboard Lead Detail juga menampilkan:

```text
API Calls
Input Tokens
Cached Input
Cache Writes
Output Tokens
Estimated Cost $...
≈ Rp ...
```

Dashboard membaca approximate conversion rate dari:

```env
USD_TO_IDR_RATE=16500
```

Catatan: current terminal formatting di `usage_store.py` menggunakan `16500` secara langsung, sedangkan dashboard membaca `USD_TO_IDR_RATE`. Jika ingin kurs terminal ikut configurable, ubah `usage_store.py` agar membaca environment variable yang sama.

Telemetry cost adalah operational estimate, bukan billing invoice resmi.

Inspect usage satu lead:

```bash
python inspect_api_usage.py 628xxxxxxxxxx
```

---

# 14. Conversation Memory and Persistent Lead State

Default database:

```text
data/conversations.db
```

`conversation.py` menyimpan conversation history. Structured lead dan program flow disimpan melalui komponen state terkait.

Conversation roles mencakup:

```text
user
assistant
human_admin
```

Human admin reply yang berhasil dikirim juga masuk history sehingga AI pada turn berikutnya dapat memahami intervensi admin sebelumnya.

`CONVERSATION_MAX_MESSAGES` mengontrol recent context yang dimuat untuk model, bukan berarti database hanya menyimpan sejumlah itu.

---

# 15. Message Buffer and Natural Reply Timing

Customer sering mengirim beberapa WhatsApp bubble secara berurutan. `message_buffer.py` menggabungkannya sebelum satu conversational turn diproses.

Relevant settings:

```env
REPLY_DELAY_MIN_SECONDS=5
REPLY_DELAY_MAX_SECONDS=15
BUBBLE_DELAY_MIN_SECONDS=1.0
BUBBLE_DELAY_MAX_SECONDS=2.5
BUFFER_POLL_SECONDS=1.0
MAX_BATCH_AGE_SECONDS=45
```

Short acknowledgement seperti `baik kak` atau `OK kak` dapat disimpan tanpa memaksa AI mengirim bubble balasan tambahan.

---

# 16. Grounded Business Knowledge

Business facts dipisahkan dari LLM behavior dan disimpan di:

```text
knowledge/
├── general.md
├── website_snapshot.md
├── corporate_training.md
└── intensive_bootcamp.md
```

Conversation style disimpan di:

```text
styles/
├── b2c_bootcamp.md
├── b2b_corporate.md
└── neutral.md
```

Supporting modules:

```text
knowledge_loader.py
style_loader.py
business_links.py
```

`intensive_bootcamp.md` dan `corporate_training.md` menjadi core curated knowledge yang detail. `website_snapshot.md` menyimpan snapshot terpilih dari halaman resmi sebagai knowledge pelengkap. Current Bootcamp duration adalah 12 minggu / 3 bulan dan wording lama 18 minggu / 4–5 bulan tidak digunakan lagi.

Business facts yang berubah seiring waktu, seperti batch date, price, promotion, schedule, curriculum links, dan registration information harus diperbarui pada controlled knowledge source, bukan dibiarkan ditebak model.

---

# 17. Follow-up Scheduler

`followup_scheduler.py` mengelola persistent inactivity follow-up. Normal B2C pre-registration menggunakan dua tahap. Follow-up pertama berjalan 3 jam setelah inbound terakhir. Jika customer tetap tidak membalas, follow-up kedua berjalan 9 jam setelah follow-up pertama, yaitu sekitar 12 jam dari inbound awal, lalu berhenti. Inbound baru membatalkan pending follow-up dan menghitung ulang dari aktivitas customer terbaru.

```env
B2C_FOLLOWUP_ENABLED=true
B2C_PRE_REGISTRATION_FOLLOWUP_HOURS=3
B2C_PRE_REGISTRATION_SECOND_FOLLOWUP_HOURS=9
B2C_POST_REGISTRATION_FOLLOWUP_HOURS=12

B2B_FOLLOWUP_ENABLED=true
B2B_PRE_PROPOSAL_FOLLOWUP_HOURS=3
B2B_POST_PROPOSAL_FOLLOWUP_HOURS=12
```

Free-form automated follow-up tetap menggunakan safety window terhadap inbound customer terbaru agar tidak melewati WhatsApp customer-service window yang dikontrol sistem. Human handling juga dapat membatalkan pending follow-up.

## B2C Last Call campaign

Last Call memakai queue/table terpisah dari normal follow-up. Pada H-5, H-3, H-1, dan hari terakhir pendaftaran, inbound B2C Bootcamp dapat menjadwalkan media Last Call sekitar 12 jam setelah inbound terbaru. Inbound baru sebelum due time mereset timer. Payment claim membatalkan Last Call.

```env
B2C_LAST_CALL_ENABLED=true
B2C_LAST_CALL_DELAY_HOURS=12
BOOTCAMP_REGISTRATION_DEADLINE=2026-11-01
```

Untuk deadline Batch 12 pada 1 November 2026, tanggal campaign adalah H-5 27 Oktober, H-3 29 Oktober, H-1 31 Oktober, dan H 1 November. Last Call tidak mengubah conversation stage.

---

# 18. Admin Notifications and Human Handoff

`notification_store.py` menyimpan actionable notifications di table `admin_notifications`.

Current notification examples:

```text
B2C
- NEED_PROGRAM_CONFIRMATION
- REGISTRATION_PAYMENT_CONFIRMATION

B2B
- PROPOSAL_SENT
- QUICK_MEETING_REQUESTED
```

Status:

```text
unread
in_progress
resolved
```

Human Reply tersedia ketika lead memiliki notification aktif. Dashboard juga menyediakan aktivasi manual Human Handling yang membuat `MANUAL_HUMAN_HANDLING`, sehingga admin dapat membuka Human Reply tanpa menunggu event otomatis.

Human Reply aktif ketika notification memiliki status:

```text
unread
atau
in_progress
```

Jika tidak ada open notification, dashboard menampilkan:

```text
Human reply hanya tersedia ketika ada notifikasi aktif untuk lead ini.
```

## Payment handoff

Ketika state extractor menghasilkan:

```json
{"signals":{"payment_claimed":true}}
```

`main.py` membuat:

```text
REGISTRATION_PAYMENT_CONFIRMATION
```

Flow yang diharapkan:

```text
Customer: "sudah saya transfer kak"
        ↓
state_extractor → payment_claimed=true
        ↓
AI acknowledges payment claim
        ↓
REGISTRATION_PAYMENT_CONFIRMATION created as unread
        ↓
Human Reply unlocked
        ↓
Admin verifies payment / responds
        ↓
notification can be resolved
```

Dashboard tidak menginfer notification dari wording AI. Notification harus dibuat sebagai explicit application event.

---

# 19. Admin Dashboard

Start:

```bash
python dashboard/app.py
```

Routes utama:

```text
/       redirect to B2C
/b2c    B2C leads
/b2b    B2B leads
/lead/<sender>  Lead Detail
```

Dashboard dilindungi login berbasis session menggunakan `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`, dan `DASHBOARD_SECRET_KEY`. Route login/logout melindungi halaman dashboard dan Lead Detail.

Current capabilities:

```text
B2C/B2B lead lists
filters and summary statistics
lead detail
conversation history
follow-up information
admin notifications
OpenAI API usage/cost telemetry
human handling
text/media reply
```

Dashboard timestamps ditampilkan dalam WIB untuk admin readability.

---

# 20. Human Admin Text and File Upload

Jika terdapat open notification, admin dapat membalas customer melalui Lead Detail menggunakan Meta WhatsApp Cloud API yang sama.

Supported modes:

```text
text only
file only
text + file
```

Supported file types:

```text
PDF
JPG / JPEG
PNG
```

Maximum upload:

```env
DASHBOARD_MAX_UPLOAD_MB=20
```

Untuk text + file, text digunakan sebagai WhatsApp media caption. Current code membatasi caption file hingga 1024 characters.

Successful human reply disimpan sebagai:

```text
role = human_admin
```

Human handling juga dapat resolve notification terkait dan cancel pending automated follow-up.

---

# 21. WhatsApp / Meta Cloud API

`whatsapp.py` menangani outbound WhatsApp delivery, termasuk text, upload local media ke Meta, dan send media menggunakan media ID.

Current Meta development settings menggunakan:

```env
WHATSAPP_PHONE_NUMBER_ID=1408846128968304
WHATSAPP_GRAPH_API_VERSION=v26.0
```

Webhook callback development:

```text
https://moneyless-stroller-mounted.ngrok-free.dev/webhook
```

Meta Developer App harus subscribe ke WhatsApp `messages` webhook events.

Jika ngrok URL berubah, update Meta callback URL.

---

# 22. Repository Structure

```text
wa-ai-admin/
├── main.py
├── classifier.py
├── state_extractor.py
├── response_generator.py
├── conversation_flow.py
│
├── conversation.py
├── lead_store.py
├── question_state.py
├── message_buffer.py
├── followup_scheduler.py
├── notification_store.py
├── usage_store.py
│
├── whatsapp.py
├── acknowledgement.py
├── business_links.py
├── knowledge_loader.py
├── style_loader.py
│
├── lead_extractor.py          # legacy/reference
├── flow_analyzer.py           # legacy/reference
│
├── knowledge/
│   ├── general.md
│   ├── website_snapshot.md
│   ├── corporate_training.md
│   └── intensive_bootcamp.md
│
├── styles/
│   ├── b2c_bootcamp.md
│   ├── b2b_corporate.md
│   └── neutral.md
│
├── B2C Document/
│   ├── AI Intensive Bootcamp.pdf
│   ├── Dashboard Belajar.png
│   ├── Infografis AI Intensive Bootcamp (Red).jpg
│   ├── Infografis AI Intensive Bootcamp (White).jpg
│   ├── Prosedur Pendaftaran & Pembayaran AI Intensive Bootcamp.pdf
│   ├── QRIS Transfer Pembayaran Indonesia AI.jpg
│   ├── Tanggal Jatuh Tempo.jpg
│   ├── Last Call H-5.jpg
│   ├── Last Call H-3.jpg
│   ├── Last Call H-1.jpg
│   └── Last Call H.jpg
│
├── B2B Document/
│   └── Proposal Penawaran AI Corporate Training.pdf
│
├── dashboard/
│   ├── app.py
│   ├── dashboard_store.py
│   ├── static/
│   │   └── dashboard.css
│   └── templates/
│       ├── base.html
│       ├── dashboard.html
│       └── lead.html
│
├── data/
│   ├── .gitkeep
│   └── conversations.db       # runtime; ignored by Git
│
├── inspect_api_usage.py
├── inspect_buffer.py
├── inspect_flow.py
├── inspect_followups.py
├── inspect_leads.py
├── inspect_memory.py
├── inspect_state.py
├── reset_test_lead.py
├── seed_dummy_leads.py
│
├── requirements.txt
├── .env.example
├── .env                       # local only; do not commit
├── .gitignore
└── README.md
```

---

# 23. Development Utilities

Inspect leads:

```bash
python inspect_leads.py
```

Inspect memory:

```bash
python inspect_memory.py
```

Inspect state/flow/follow-up/buffer:

```bash
python inspect_state.py
python inspect_flow.py
python inspect_followups.py
python inspect_buffer.py
```

Inspect OpenAI usage:

```bash
python inspect_api_usage.py 628xxxxxxxxxx
```

Reset one test lead:

```bash
python reset_test_lead.py 628xxxxxxxxxx
```

Reset utility digunakan untuk repeatable end-to-end test dari conversation awal dan membersihkan data sender terkait pada table yang didukung utility tersebut, termasuk API telemetry.

Seed dummy dashboard data:

```bash
python seed_dummy_leads.py
```

Jangan gunakan dummy seeder pada production database.

---

# 24. Recommended End-to-End Tests

Setelah perubahan besar, minimal test jalur berikut.

## B2C

```text
1. Ask about AI Intensive Bootcamp
2. Verify infographic is sent from B2C Document/
3. Select ML/CV/NLP
4. Ask curriculum/material/dashboard questions
5. Ask naturally about installment/payment due dates and verify `payment_due_date` media is selected
6. State registration intent
7. Confirm class + quantity
8. Verify procedure PDF + QRIS are both sent
9. Ask "kirim ulang QRIS"
10. Ask generic "kirim ulang" after registration docs
11. Claim payment, including typo-heavy wording
12. Verify STATE EXTRACTOR returns payment_claimed=true
13. Verify REGISTRATION_PAYMENT_CONFIRMATION exists
14. Verify Human Reply becomes available
15. Test manual Human Handling activation
16. Send human text/file reply
```

## B2B

```text
1. Ask about AI Corporate Training
2. Provide name/company/division
3. Provide participant estimate
4. Choose online/onsite/hybrid
5. Provide training goal
6. Verify proposal PDF is sent from B2B Document/
7. Ask to resend proposal
8. Request Quick Call/Meeting
9. Verify notification/human handling behavior
```

---

# 25. Troubleshooting

## Media file not found

Example:

```text
Media file tidak ditemukan: .../B2B Document/Infografis ...
```

Bootcamp files must be under `B2C Document/`. Corporate proposal must be under `B2B Document/`.

Check:

```bash
find "B2B Document" "B2C Document" -maxdepth 1 -type f -print
```

And verify mapping:

```bash
grep -n -A8 'MEDIA = {' main.py
```

## Human Reply remains locked after payment

Check terminal state extraction. Expected:

```text
STATE EXTRACTOR : API CALL {... 'signals': {'payment_claimed': True}}
```

Then inspect notification:

```bash
python - <<'PY'
from notification_store import open_notifications_for_sender
print(open_notifications_for_sender("628xxxxxxxxxx"))
PY
```

It should contain an open `REGISTRATION_PAYMENT_CONFIRMATION` notification.

## Meta 401 / code 190

This is normally Meta access-token authentication. Replace/refresh `WHATSAPP_ACCESS_TOKEN` and restart the service.

## Code changed but behavior remains old

If Uvicorn is running without `--reload`, stop and restart it:

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

## Check which module Python is loading

```bash
python -c "import main; print(main.__file__)"
```

---

# 26. Database

Current database:

```text
data/conversations.db
```

FastAPI and Flask dashboard share this SQLite database.

It can contain customer messages, WhatsApp sender identifiers, lead information, flow state, follow-ups, notifications, and API telemetry. Never commit or publish a live database.

SQLite is appropriate for the current local/MVP workflow. Production deployment may later move to PostgreSQL or another managed database depending on concurrency, backup, availability, and operational requirements.

---

# 27. Security

Never commit or publish:

```text
.env
OPENAI_API_KEY
WHATSAPP_ACCESS_TOKEN
WHATSAPP_VERIFY_TOKEN
live conversations.db
customer private data/documents
```

Before production deployment, review at least:

```text
Dashboard authentication/authorization and credential hardening
HTTPS/network exposure
Meta durable/System User token management
secret storage and rotation
database backup/recovery
customer-data retention/deletion
structured logging/monitoring
WhatsApp retry/idempotency
upload validation/security
rate limits
production database/concurrency strategy
```

The current dashboard is an internal development/admin interface, not a public production application.

---

# 28. Git / GitHub

`.gitignore` should keep secrets/runtime data outside Git:

```text
.env
__pycache__/
.venv/
venv/
.DS_Store
data/*.db
data/*.db-shm
data/*.db-wal
```

Typical update workflow:

```bash
git status
git add .
git commit -m "Update WhatsApp AI Admin"
git push
```

Always inspect `git status` before committing to make sure `.env`, live database files, or other secrets are not staged.

---

# 29. Development Progress

| Stage | Capability | Status |
|---|---|---|
| Milestone 1 | Meta WhatsApp inbound webhook | ✅ |
| Milestone 2 | Semantic classification + AI WhatsApp reply | ✅ |
| Milestone 3A | Multi-turn conversation memory | ✅ |
| Milestone 3B | Grounded Indonesia AI knowledge | ✅ |
| Milestone 4A | Persistent SQLite memory | ✅ |
| Milestone 4B | Structured lead profile | ✅ |
| Milestone 4C | Conversation/question state | ✅ |
| Milestone 4D/4E | B2C/B2B guided flow + automatic media | ✅ |
| Milestone 4E.4 | Persistent inactivity follow-up | ✅ |
| Milestone 5 | Dashboard + admin notifications | ✅ |
| Human Handling | Dashboard human replies | ✅ |
| Human Media | PDF/JPG/PNG upload from dashboard | ✅ |
| Milestone 6 | API cost optimization | ✅ |
| Milestone 6A | Per-lead token/cost telemetry | ✅ |
| Milestone 6B | Cache-friendly response generator | ✅ |
| Milestone 6C | Configurable model experiment / Luna phase | Completed experiment |
| Current | GPT-5.6 + semantic state extractor every inbound turn | ✅ Active |
| Current | Local regex `state_parser.py` removed | ✅ |
| Current | Correct B2C/B2B document mapping + semantic media triggers/resend | ✅ |
| Current | Website snapshot + detailed core Bootcamp/Corporate knowledge | ✅ |
| Current | B2C two-stage pre-registration follow-up | ✅ |
| Current | B2C Last Call campaign scheduler | ✅ |
| Current | Dashboard login/logout + manual Human Handling | ✅ |
| Current | Payment notification → Human Reply handoff | ✅ |
| Production hardening | Auth, durable deployment, monitoring, retries, etc. | Planned |

---

# 30. Current Technology Stack

```text
Python
FastAPI
Uvicorn
Flask
SQLite
OpenAI API
GPT-5.6 (current default)
Meta WhatsApp Business Platform / Cloud API
ngrok (development)
Cloudflare Tunnel (planned production endpoint)
HTML / CSS / Jinja
Markdown business knowledge/style files
```

---

# 31. Current End-to-End Flow

```text
Customer sends WhatsApp message
        ↓
Meta webhook
        ↓
Buffer consecutive customer bubbles
        ↓
Load history + persistent lead/flow
        ↓
Classify product if unknown or every 10th inbound message
        ↓
Semantic state extraction (LLM every inbound turn)
        ↓
Update structured lead + flow state
        ↓
Deterministic B2C/B2B flow planning
        ↓
Determine required media / links / notifications
        ↓
Load grounded knowledge + style
        ↓
Cache-friendly natural response generation
        ↓
Record API tokens + estimated cost
        ↓
Send text / PDF / image through Meta
        ↓
Persist conversation
        ↓
Schedule/cancel follow-up
        ↓
Create human-action notification when required
        ↓
Human Admin can reply when notification is open
        ↓
Human reply is sent through Meta and stored in history
```

---

# 32. Current Design Decision

The current implementation intentionally accepts **one semantic state-extraction API call per inbound customer turn** rather than relying on a cheaper regex parser.

This is a quality/reliability trade-off:

```text
Old approach:
local parser first → cheaper, but fragile to WhatsApp language variation

Current approach:
semantic state extractor every inbound → higher API usage, more robust understanding
```

Cost optimization is still retained through:

```text
periodic product classification
prompt caching in response_generator.py
persistent state/history
controlled deterministic flow
per-lead telemetry
```

The goal is not to minimize API calls at all costs, but to keep the AI Admin reliable enough for real customer conversations while retaining measurable cost controls.

