# WhatsApp AI Admin — Indonesia AI

AI-powered WhatsApp admin for **Indonesia AI**, built on the official Meta WhatsApp Cloud API, FastAPI, OpenAI, SQLite, and a Flask admin dashboard.

The current repository is **Milestone 6C**. It supports AI Intensive Bootcamp (B2C) and AI Corporate Training (B2B), persistent lead/conversation state, grounded business knowledge, automated media delivery, inactivity follow-up, human handoff, dashboard replies and file uploads, API-cost optimization, prompt caching, per-lead token/cost telemetry, and GPT-5.6 Luna as the default active model.

---

# 1. Quick Start

Run the system from **three terminals**.

First enter the project and activate the environment in each terminal as needed:

```bash
cd ~/Desktop/Indonesia-AI/wa-ai-admin
conda activate indonesia-ai
```

## Terminal 1 — ngrok

```bash
ngrok http 8000 --url https://moneyless-stroller-mounted.ngrok-free.dev
```

Current public webhook:

```text
https://moneyless-stroller-mounted.ngrok-free.dev/webhook
```

The same callback URL must be configured in Meta Developer → WhatsApp → Webhooks.

## Terminal 2 — FastAPI / WhatsApp AI Admin

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Local service:

```text
http://127.0.0.1:8000
```

Main endpoints:

```text
GET  /webhook    Meta webhook verification
POST /webhook    Incoming WhatsApp events
```

## Terminal 3 — Admin Dashboard

```bash
python dashboard/app.py
```

With the recommended configuration below, open:

```text
http://127.0.0.1:10080
```

Keep the dashboard on `127.0.0.1` during development. It currently has no production-grade authentication layer and should not be exposed publicly as-is.

---

# 2. Environment Configuration (`.env`)

Create `.env` in the repository root:

```bash
nano .env
```

Recommended current configuration:

```env
# =========================================================
# OpenAI
# =========================================================
OPENAI_API_KEY=YOUR_OPENAI_API_KEY

# Milestone 6C default
OPENAI_MODEL=gpt-5.6-luna

# To compare against GPT-5.6 Sol, temporarily use:
# OPENAI_MODEL=gpt-5.6

# =========================================================
# Meta WhatsApp Cloud API
# =========================================================
WHATSAPP_ACCESS_TOKEN=YOUR_META_WHATSAPP_ACCESS_TOKEN
WHATSAPP_PHONE_NUMBER_ID=1408846128968304
WHATSAPP_GRAPH_API_VERSION=v26.0
WHATSAPP_VERIFY_TOKEN=YOUR_PRIVATE_WEBHOOK_VERIFY_TOKEN

# =========================================================
# Conversation / SQLite
# =========================================================
CONVERSATION_DB_PATH=data/conversations.db
CONVERSATION_MAX_MESSAGES=15

# =========================================================
# Natural reply timing / buffering
# =========================================================
REPLY_DELAY_MIN_SECONDS=5
REPLY_DELAY_MAX_SECONDS=15
BUBBLE_DELAY_MIN_SECONDS=1.0
BUBBLE_DELAY_MAX_SECONDS=2.5
BUFFER_POLL_SECONDS=1.0
MAX_BATCH_AGE_SECONDS=45

# =========================================================
# B2C inactivity follow-up
# =========================================================
B2C_FOLLOWUP_ENABLED=true
B2C_PRE_REGISTRATION_FOLLOWUP_HOURS=3
B2C_POST_REGISTRATION_FOLLOWUP_HOURS=12

# =========================================================
# B2B inactivity follow-up
# =========================================================
B2B_FOLLOWUP_ENABLED=true
B2B_PRE_PROPOSAL_FOLLOWUP_HOURS=3
B2B_POST_PROPOSAL_FOLLOWUP_HOURS=24

# =========================================================
# Admin Dashboard
# =========================================================
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=10080
DASHBOARD_MAX_UPLOAD_MB=20
```

## Important `.env` notes

`OPENAI_MODEL` is shared by the active Milestone 6 LLM calls: classifier, state fallback, and response generator. The current default in code is `gpt-5.6-luna`.

`WHATSAPP_ACCESS_TOKEN` must be a valid Meta access token. A `401` with Meta error code `190` indicates an authentication/token problem rather than an AI-flow problem. Temporary development tokens can expire; use an appropriate long-lived/System User setup for a persistent deployment.

`CONVERSATION_DB_PATH` is shared by the FastAPI service and Flask dashboard. `CONVERSATION_MAX_MESSAGES` controls recent history loaded into model context, not how much history is retained in SQLite.

Never commit `.env`, API keys, Meta tokens, webhook secrets, or a live customer database.

---

# 3. Installation

Install dependencies:

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

The project is currently developed with Conda:

```bash
conda activate indonesia-ai
```

---

# 4. Current Architecture

```text
WhatsApp Customer
       │
       ▼
Meta WhatsApp Cloud API
       │
       ▼
FastAPI webhook / main.py
       │
       ├── inbound buffering / debounce
       ├── load persistent lead + conversation state
       │
       ├── Milestone 6 optimized understanding
       │     ├── periodic semantic classifier
       │     ├── local state-aware parser
       │     └── single LLM state fallback when needed
       │
       ├── deterministic B2C/B2B flow planner
       ├── grounded Indonesia AI knowledge
       ├── style + curated business links
       ├── cache-friendly LLM response generation
       ├── automatic documents/images
       ├── follow-up scheduler
       ├── admin notifications
       └── per-lead OpenAI usage telemetry
       │
       ▼
Meta WhatsApp Cloud API
       │
       ▼
WhatsApp Customer

SQLite
  │
  ├── messages / leads / state / flow
  ├── follow-ups / notifications
  ├── inbound buffers / reply batches
  └── api_usage
       │
       ▼
Flask Admin Dashboard
       │
       ├── B2C / B2B leads
       ├── lead detail + history
       ├── OpenAI token/cost telemetry
       ├── notifications / human handling
       └── text + PDF/JPG/PNG reply through Meta
```

The design principle is: **deterministic business state where possible, LLM generation where useful**. The application does not make the LLM rediscover simple structured state on every turn.

---

# 5. Milestone 6 — API Cost Optimization

Milestone 6 reduces unnecessary OpenAI calls while keeping customer-facing replies dynamic.

## 5.1 Periodic re-classification

`product_interest` remains persistent in the lead profile, but classification is not skipped forever.

Current behavior in `main.py`:

```text
Product not known        → classifier API call
Product already known    → reuse persistent category
Every 10th user message  → classifier API refresh
```

Only incoming customer/user messages are counted for this periodic refresh. AI/human-admin bubbles do not count toward the 10-message interval.

Runtime logs show the path, for example:

```text
M6 CLASSIFIER : API CALL (product not known; inbound #1)
M6 CLASSIFIER : SKIPPED (persistent state; inbound #4)
M6 CLASSIFIER : API CALL (10-message refresh; inbound #10)
```

## 5.2 Local state-aware parser

`state_parser.py` handles common structured information locally, avoiding an API call when the answer is clear.

Examples include:

- Bootcamp track: ML / CV / NLP.
- Registration intent and quantity.
- Payment claim.
- Participant count.
- Online / onsite / hybrid preference.
- Quick Call / Meeting intent.
- Context-aware confirmations such as `iya`, when the previous question makes the meaning clear.
- B2C progression signals such as an explicit Bootcamp inquiry.

This parser determines state, not fixed customer-facing wording. The final reply is still generated by the response model.

## 5.3 Single-call LLM state fallback

When local parsing is insufficient, `state_parser.py` can make one semantic fallback call. This is especially useful for free-form B2B information such as company context, division, or training goals.

The optimized path is therefore:

```text
Incoming message
      ↓
Local parser
      │
      ├── sufficient ──────────────┐
      │                            │
      └── ambiguous → 1 LLM call ──┤
                                   ↓
                         deterministic flow
                                   ↓
                         response generator
```

The older `lead_extractor.py` and `flow_analyzer.py` remain in the repository for reference/rollback, but the current `main.py` no longer uses them as the normal Milestone 6 extraction pipeline.

---

# 6. Milestone 6A — Token / Cost Telemetry per Lead

`usage_store.py` records OpenAI usage in SQLite per WhatsApp sender.

Each active API call can record:

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

Current call types include:

```text
classifier
state_fallback
response_generator
```

The database table is:

```text
api_usage
```

## Inspect one lead from terminal

```bash
python inspect_api_usage.py 628xxxxxxxxxx
```

The output summarizes API calls, input tokens, cached input, cache writes, output tokens, estimated USD cost, and usage by call type.

## Dashboard telemetry

Lead Detail contains an **OpenAI API Usage** section showing:

```text
API Calls
Input Tokens
Cached Input
Cache Writes
Output Tokens
Estimated Cost
usage by call type
```

The cost is an estimate produced by `usage_store.py`; it should be treated as operational telemetry rather than an invoice. If OpenAI pricing changes, update the rate constants in that file.

---

# 7. Milestone 6B — Cache-Friendly Response Generator

`response_generator.py` separates the prompt into a stable prefix and dynamic suffix.

Conceptually:

```text
STABLE PREFIX
├── AI Admin instructions
├── business knowledge
├── style
├── curated links
└── promo context
        │
        ▼
 explicit cache breakpoint
════════════════════════════
DYNAMIC SUFFIX
├── lead profile
├── recent conversation history
├── category
├── newest customer message
├── program-flow stage
└── follow-up control
```

The current response call uses explicit prompt caching with a 30-minute TTL:

```python
prompt_cache_options={"mode": "explicit", "ttl": "30m"}
```

The stable developer block contains the explicit cache breakpoint. Dynamic lead/history content is placed after it.

Prompt caching does **not** make replies fixed. It reuses processing of the stable prefix; each customer reply is still generated from the current message, history, lead state, and flow stage.

Use Milestone 6A telemetry to verify whether `cached_input_tokens` increases during repeated calls.

---

# 8. Milestone 6C — GPT-5.6 Luna

The active Milestone 6 model is configurable through `.env`:

```env
OPENAI_MODEL=gpt-5.6-luna
```

The following active components read this setting:

```text
classifier.py
state_parser.py
response_generator.py
```

To A/B test against Sol:

```env
OPENAI_MODEL=gpt-5.6
```

Then restart Uvicorn.

`usage_store.py` is model-aware for the GPT-5.6 Sol/Luna identifiers currently supported by this repository, so telemetry uses the matching configured rate table. Unknown models are deliberately recorded with an estimated cost of `$0` rather than silently applying the wrong rate.

Note: legacy/reference files may still contain older hard-coded model names. They are not part of the normal optimized `main.py` pipeline.

---

# 9. Semantic Classification

`classifier.py` classifies the conversation into:

```text
AI Intensive Bootcamp
AI Corporate Training
Unknown
```

Classification is semantic and can use conversation context. Once a valid product is identified, the category is persisted in the lead profile and reused between periodic classifier refreshes.

---

# 10. Buffering and Natural Reply Timing

`message_buffer.py` groups consecutive customer bubbles before processing them as one conversational unit.

Relevant settings:

```env
REPLY_DELAY_MIN_SECONDS=5
REPLY_DELAY_MAX_SECONDS=15
BUFFER_POLL_SECONDS=1.0
MAX_BATCH_AGE_SECONDS=45
BUBBLE_DELAY_MIN_SECONDS=1.0
BUBBLE_DELAY_MAX_SECONDS=2.5
```

This helps avoid replying prematurely when a customer sends several short WhatsApp bubbles in succession.

---

# 11. Persistent Conversation Memory and Lead State

`conversation.py` stores chat history in SQLite. `lead_store.py`, `question_state.py`, and `conversation_flow.py` maintain structured state alongside raw messages.

Conversation roles include:

```text
user
assistant
human_admin
```

Human-admin replies are therefore visible to subsequent AI turns as part of the conversation context.

The default database is:

```text
data/conversations.db
```

---

# 12. Grounded Indonesia AI Knowledge

Authoritative business context is kept outside the LLM in Markdown files:

```text
knowledge/
├── general.md
├── corporate_training.md
└── intensive_bootcamp.md
```

Styles are separated similarly:

```text
styles/
├── b2c_bootcamp.md
├── b2b_corporate.md
└── neutral.md
```

`knowledge_loader.py`, `style_loader.py`, and `business_links.py` feed controlled context into response generation.

Time-sensitive facts such as active Bootcamp batch dates, prices, promotions, schedules, and registration information must be reviewed whenever the business offering changes.

---

# 13. B2C — AI Intensive Bootcamp Flow

The current B2C flow is intentionally concise:

```text
Bootcamp inquiry
      ↓
short overview + infographic
      ↓
ML / CV / NLP selection
      ↓
class-specific information / responsive Q&A
      ↓
registration intent
      ↓
confirm class + quantity
      ↓
registration/payment procedure + QRIS
      ↓
payment claim
      ↓
acknowledgement + human/payment verification
```

Current Bootcamp assets are stored under the existing directory name:

```text
B2B Document/
├── Infografis AI Intensitve Bootcamp.jpg
├── Prosedur Pendaftaran & Pembayaran AI Intensitve Bootcamp.pdf
└── QRIS Transfer Pembayaran Indonesia AI.jpg
```

The folder name is retained for compatibility even though these are B2C assets.

---

# 14. B2B — AI Corporate Training Flow

The Corporate Training flow gathers the minimum information needed for a useful business follow-up:

```text
name + company + division/team
      ↓
participant estimate
      ↓
online / onsite preference
      ↓
training goal
      ↓
proposal
      ↓
responsive discussion / Quick Call / Meeting
```

Current proposal asset:

```text
B2C Document/
└── Proposal Penawaran AI Corporate Training.pdf
```

Again, the existing folder name is retained for compatibility even though this is a B2B asset.

---

# 15. WhatsApp Media and Documents

`whatsapp.py` handles official Meta Cloud API outbound delivery, including local media upload to Meta and sending media by returned media ID.

The automated flow can send Bootcamp infographic, registration procedure, QRIS, and Corporate Training proposal assets.

A Meta `401` / OAuth error code `190` indicates an access-token authentication issue. Refresh/replace the Meta token and restart the service rather than changing the AI pipeline.

---

# 16. Follow-up Scheduler

`followup_scheduler.py` stores inactivity follow-ups persistently in SQLite.

Current defaults:

```text
B2C pre-registration       3 hours
B2C post-registration     12 hours
B2B pre-proposal           3 hours
B2B post-proposal         24 hours
```

Inbound customer activity resets/cancels the relevant pending follow-up. Human handling also cancels applicable automation when appropriate.

---

# 17. Admin Notifications

`notification_store.py` creates actionable dashboard notifications.

Current examples:

```text
B2C
- NEED_PROGRAM_CONFIRMATION
- REGISTRATION_PAYMENT_CONFIRMATION

B2B
- PROPOSAL_SENT
- QUICK_MEETING_REQUESTED
```

Notification status can progress through unread/in-progress/resolved states according to the dashboard workflow.

---

# 18. Admin Dashboard

Start:

```bash
python dashboard/app.py
```

Default local URL:

```text
http://127.0.0.1:10080
```

Current dashboard capabilities include:

- B2C lead list.
- B2B lead list.
- Filters and summary statistics.
- Funnel-related lead information.
- Lead Detail.
- Conversation history.
- Follow-up information.
- Admin notifications.
- OpenAI API usage/cost telemetry.
- Human Handling.
- Human text/media reply.

Dashboard timestamps are formatted for admin readability in WIB while persisted timestamps can remain UTC.

---

# 19. Human Handling and File Upload

When a lead has an actionable Human Handling state, an admin can reply from Lead Detail using the same Meta WhatsApp Cloud API.

Supported modes:

```text
text only
file only
text + file
```

Supported upload types:

```text
PDF
JPG / JPEG
PNG
```

For text + file, the text is used as the WhatsApp media caption.

Maximum upload size:

```env
DASHBOARD_MAX_UPLOAD_MB=20
```

A successful Human Admin response is stored with:

```text
role = human_admin
```

It can also resolve the relevant notification and cancel the pending automated follow-up.

---

# 20. Repository Structure

```text
wa-ai-admin/
├── main.py
├── classifier.py
├── state_parser.py
├── response_generator.py
├── usage_store.py
├── whatsapp.py
├── message_buffer.py
├── acknowledgement.py
│
├── conversation.py
├── lead_store.py
├── question_state.py
├── conversation_flow.py
├── followup_scheduler.py
├── notification_store.py
│
├── lead_extractor.py          # legacy/reference
├── flow_analyzer.py           # legacy/reference
│
├── knowledge_loader.py
├── style_loader.py
├── business_links.py
│
├── knowledge/
│   ├── general.md
│   ├── corporate_training.md
│   └── intensive_bootcamp.md
│
├── styles/
│   ├── b2c_bootcamp.md
│   ├── b2b_corporate.md
│   └── neutral.md
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
├── B2B Document/
│   ├── Infografis AI Intensitve Bootcamp.jpg
│   ├── Prosedur Pendaftaran & Pembayaran AI Intensitve Bootcamp.pdf
│   └── QRIS Transfer Pembayaran Indonesia AI.jpg
│
├── B2C Document/
│   └── Proposal Penawaran AI Corporate Training.pdf
│
├── data/
│   └── conversations.db       # generated/used locally
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
├── apply_dashboard_icons.py
│
├── requirements.txt
├── .env                       # local secret; do not commit
├── .gitignore
└── README.md
```

---

# 21. Development / Inspection Utilities

Inspect leads:

```bash
python inspect_leads.py
```

Inspect conversation memory:

```bash
python inspect_memory.py
```

Inspect state, flow, follow-ups, and buffer:

```bash
python inspect_state.py
python inspect_flow.py
python inspect_followups.py
python inspect_buffer.py
```

Inspect OpenAI usage for one lead:

```bash
python inspect_api_usage.py 628xxxxxxxxxx
```

Reset one test lead completely:

```bash
python reset_test_lead.py 628xxxxxxxxxx
```

The current reset utility clears that sender's conversation history, lead profile, question/program flow state, notifications, buffers/reply batches, follow-ups, and API telemetry when the relevant tables exist. This is useful for repeatable B2C/B2B tests from message #1.

Seed dummy dashboard data:

```bash
python seed_dummy_leads.py
```

Do not run the dummy seeder against a production database.

---

# 22. Testing Milestone 6 Cost Optimization

For a clean cost/quality experiment:

```bash
python reset_test_lead.py 628xxxxxxxxxx
```

Run one complete B2C or B2B conversation, then inspect:

```bash
python inspect_api_usage.py 628xxxxxxxxxx
```

For Luna vs Sol A/B testing, keep the conversation scenario approximately the same and change only:

```env
OPENAI_MODEL=gpt-5.6-luna
```

or:

```env
OPENAI_MODEL=gpt-5.6
```

Restart Uvicorn after changing the model. Compare:

```text
conversation quality
API call count
input tokens
cached input tokens
cache-write tokens
output tokens
estimated cost
```

Do not change parser logic, prompt structure, and model simultaneously if the goal is to measure the contribution of one optimization.

---

# 23. Meta Webhook Configuration

Current development callback:

```text
https://moneyless-stroller-mounted.ngrok-free.dev/webhook
```

The verify token configured in Meta must match:

```env
WHATSAPP_VERIFY_TOKEN=...
```

Subscribe the WhatsApp webhook to the relevant `messages` field/events.

If the ngrok domain changes, update both the ngrok command and Meta callback configuration.

---

# 24. Database

Current MVP database:

```text
data/conversations.db
```

The FastAPI service and dashboard share this SQLite database.

It contains customer-related information such as conversations, WhatsApp sender identifiers, lead fields, state, follow-ups, notifications, and API usage. Do not commit or publish a live database.

SQLite is suitable for the current local/MVP workflow. A production deployment can later evaluate PostgreSQL or another managed database depending on concurrency, backup, operations, and deployment requirements.

---

# 25. Security and Production Notes

Never commit or publish:

```text
.env
OPENAI_API_KEY
WHATSAPP_ACCESS_TOKEN
WHATSAPP_VERIFY_TOKEN
live customer database
private customer data/documents
```

Before production deployment, review at minimum:

- Dashboard authentication and authorization.
- HTTPS and network exposure.
- Meta System User / durable access-token management.
- Secret management and rotation.
- Database backup and recovery.
- Customer-data retention/deletion policy.
- Structured logging and monitoring.
- WhatsApp send retry/idempotency.
- Upload validation and malware/security controls.
- Rate limits and operational alerting.
- Database/concurrency strategy.

The current dashboard should be considered an internal development/admin interface, not a public production application.

---

# 26. Development Progress

| Stage | Capability | Status |
|---|---|---|
| Milestone 1 | Meta WhatsApp inbound webhook | ✅ |
| Milestone 2 | LLM classification + WhatsApp AI reply | ✅ |
| Milestone 3A | Multi-turn conversation memory | ✅ |
| Milestone 3B | Grounded Indonesia AI knowledge | ✅ |
| Milestone 4A | Persistent SQLite memory | ✅ |
| Milestone 4B | Structured lead profile | ✅ |
| Milestone 4C | Conversation/question state | ✅ |
| Milestone 4D/4E | B2C/B2B guided flow + media | ✅ |
| Milestone 4E.4 | Persistent inactivity follow-up | ✅ |
| Milestone 5 | Dashboard + admin notifications | ✅ |
| Human Handling | Dashboard human replies | ✅ |
| Human Media | PDF/JPG/PNG upload from dashboard | ✅ |
| Milestone 6.1 | Periodic classification + local parser + single fallback | ✅ |
| Milestone 6A | Per-lead token/cost telemetry | ✅ |
| Milestone 6B | Cache-friendly response generator | ✅ |
| Milestone 6C | Configurable GPT-5.6 Luna default | ✅ |
| Production hardening | Auth, durable deployment, monitoring, stronger retries, etc. | Planned |

---

# 27. Current Technology Stack

- Python
- FastAPI
- Uvicorn
- Flask
- SQLite
- OpenAI API
- GPT-5.6 Luna by default for the active Milestone 6 pipeline
- Meta WhatsApp Business Platform / Cloud API
- ngrok
- HTML / CSS / Jinja
- Markdown knowledge/style files

---

# 28. Current End-to-End Flow

```text
Customer sends WhatsApp message
        ↓
Meta webhook event
        ↓
Message buffer/debounce
        ↓
Load recent history + persistent lead/state
        ↓
Classify only when needed / every 10th user message
        ↓
Local state-aware parsing
        ↓
Single LLM state fallback only when necessary
        ↓
Update lead + deterministic program flow
        ↓
Load controlled knowledge/style/links
        ↓
Cache-friendly GPT response generation
        ↓
Record per-lead API tokens/cost
        ↓
Send text / links / documents / images through Meta
        ↓
Persist conversation/state
        ↓
Schedule/cancel follow-up as applicable
        ↓
Create admin notification when human action is needed
        ↓
Human Admin can respond from dashboard
        ↓
Human text/file sent through Meta and stored in history
```

---

# 29. Business Scope

## AI Intensive Bootcamp — B2C

For individual learners interested in Indonesia AI's intensive specialist programs, currently represented in the flow by ML, CV, and NLP tracks.

## AI Corporate Training — B2B

For companies, institutions, organizations, and teams requiring AI training tailored to participant profile, delivery preference, and business/training goals.

Business facts should remain grounded in controlled Indonesia AI knowledge rather than invented by the model.

---

# 30. Recommended Next Priorities

The current system is already a functional AI-admin MVP. The next priorities are primarily measurement, reliability, and production hardening:

1. Run controlled Luna vs Sol quality/cost comparisons using the telemetry already implemented.
2. Measure prompt-cache hit behavior and optimize the stable prefix only if telemetry justifies it.
3. Add dashboard authentication before any public deployment.
4. Use a durable Meta access-token strategy for continuous operation.
5. Improve outbound WhatsApp retry/idempotency and error recovery.
6. Add production monitoring and structured logs.
7. Review file-upload security and customer-data retention.
8. Evaluate managed deployment/database options when moving beyond local/MVP usage.

---

# Maintainer

**Indonesia AI**

Website: `https://aiforindonesia.com/`
