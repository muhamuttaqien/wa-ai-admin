import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

load_dotenv()

from classifier import classify_message
from conversation import add_message, count_messages, count_user_messages, get_history
from conversation_flow import get_flow, plan_flow, update_flow
from state_parser import parse_local_state, needs_llm_fallback, llm_state_fallback, merge_state
from lead_store import get_lead, upsert_lead
from message_buffer import complete_batch, due_senders, enqueue_message, get_buffered_messages, is_batch_due, retry_batch_later
from response_generator import generate_reply
from business_links import DASHBOARD_DEMO_LINK, curriculum_url, track_page_url
from whatsapp import send_text_message, send_media_message
from acknowledgement import is_acknowledgement_only
from notification_store import create_notification
from followup_scheduler import cancel_followup, due_followups, mark_followup_sent, schedule_for_b2c_state, schedule_for_b2b_state

VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
BUFFER_POLL_SECONDS = float(os.getenv("BUFFER_POLL_SECONDS", "1.0"))
_worker_stop = threading.Event()
ROOT = Path(__file__).resolve().parent

MEDIA = {
    "bootcamp_infographic": (ROOT / "B2B Document" / "Infografis AI Intensitve Bootcamp.jpg", "image"),
    "bootcamp_registration_doc": (ROOT / "B2B Document" / "Prosedur Pendaftaran & Pembayaran AI Intensitve Bootcamp.pdf", "document"),
    "bootcamp_qris": (ROOT / "B2B Document" / "QRIS Transfer Pembayaran Indonesia AI.jpg", "image"),
    "corporate_proposal": (ROOT / "B2C Document" / "Proposal Penawaran AI Corporate Training.pdf", "document"),
}


def _combined_text(buffered):
    return "\n".join(x["content"].strip() for x in buffered if x["content"].strip())


def _send_reply_with_optional_media(sender, replies, media_key):
    results=[]
    if not media_key:
        for text in replies:
            results.append(send_text_message(sender,text))
        return results

    if media_key == "bootcamp_registration_bundle":
        # Registration assets first, then close with the natural admin guidance.
        for key in ("bootcamp_registration_doc", "bootcamp_qris"):
            path, media_type = MEDIA[key]
            if not path.exists():
                raise RuntimeError(f"Media file tidak ditemukan: {path}")
            results.append(send_media_message(sender,str(path),media_type))
        for text in replies:
            results.append(send_text_message(sender,text))
        return results

    # Other assets: first explanatory bubble, asset, then remaining bubble(s).
    if replies:
        results.append(send_text_message(sender,replies[0]))
    path, media_type = MEDIA[media_key]
    if not path.exists():
        raise RuntimeError(f"Media file tidak ditemukan: {path}")
    results.append(send_media_message(sender,str(path),media_type))
    for text in replies[1:]:
        results.append(send_text_message(sender,text))
    return results


def _ensure_b2c_links(replies, message, lead, stage):
    """Guarantee requested public links without letting the model invent URLs."""
    replies = list(replies)
    lower = message.lower()
    selected = lead.get("selected_class")

    if stage == "B2C_CLASS_INFO" and selected:
        url = track_page_url(selected)
        if url and not any(url in x for x in replies):
            if len(replies) < 3:
                replies.append(url)
            else:
                replies[-1] = replies[-1].rstrip() + "\n" + url

    dashboard_terms = ("dashboard", "slide", "materi", "rekaman", "recording", "koding", "coding")
    if any(term in lower for term in dashboard_terms):
        if not any(DASHBOARD_DEMO_LINK in x for x in replies):
            if len(replies) < 3:
                replies.append(DASHBOARD_DEMO_LINK)
            else:
                replies[-1] = replies[-1].rstrip() + "\n" + DASHBOARD_DEMO_LINK

    curriculum_terms = ("silabus", "kurikulum", "curriculum")
    if selected and any(term in lower for term in curriculum_terms):
        url = curriculum_url(selected)
        if url and not any(url in x for x in replies):
            if len(replies) < 3:
                replies.append(url)
            else:
                replies[-1] = replies[-1].rstrip() + "\n" + url
    return replies


def process_due_followups():
    for item in due_followups():
        sender = item["sender"]
        kind = item["kind"]
        try:
            texts = {
                "b2c_pre_registration": "Bagaimana kak, apa ada yang ingin ditanyakan lagi terkait program bootcampnya?",
                "b2c_post_registration": "Bagaimana kak, apakah ada kesulitan di pendaftarannya?",
                "b2b_pre_proposal": "Haloo Bapak/Ibu, izin follow up kembali yah. Apa ada yang ingin ditanyakan lebih lanjut terkait program AI Corporate Trainingnya?",
                "b2b_post_proposal": "Haloo Bapak/Ibu, izin follow up kembali terkait proposal yang sebelumnya sudah kami kirimkan. Kalau dirasa perlu untuk diskusi lebih lanjut, tim kami bisa untuk Quick Call ataupun Quick Meeting dengan tim dari perusahaan Bapak/Ibu.",
            }
            text = texts.get(kind)
            if not text:
                mark_followup_sent(sender)
                continue
            send_text_message(sender, text)
            add_message(sender, "assistant", text)
            mark_followup_sent(sender)
            print(f"FOLLOW-UP SENT : {sender} [{kind}]")
        except Exception as exc:
            print("Follow-up send error:", exc)


def process_sender_batch(sender):
    if not is_batch_due(sender): return
    buffered=get_buffered_messages(sender)
    if not buffered:
        complete_batch(sender,[]); return
    ids=[x["message_id"] for x in buffered]; text=_combined_text(buffered)
    print("\n==============================\nPROCESSING BUFFERED WHATSAPP TURN\n==============================")
    print(f"From     : {sender}\nMessages : {len(buffered)}\nCombined : {text}")

    # A short acknowledgement such as "baik kak" or "OK kak" should not
    # produce another bot bubble. It is still stored and it resets the
    # inactivity follow-up timer for an existing Bootcamp conversation.
    if is_acknowledgement_only(text):
        add_message(sender, "user", text)
        lead = get_lead(sender)
        flow = get_flow(sender)
        if lead.get("product_interest") == "AI Intensive Bootcamp":
            schedule_for_b2c_state(sender, lead, flow)
        elif lead.get("product_interest") == "AI Corporate Training":
            schedule_for_b2b_state(sender, lead, flow)
        complete_batch(sender, ids)
        print("ACKNOWLEDGEMENT ONLY : stored, no auto-reply")
        return

    try:
        history=get_history(sender)
        current=get_lead(sender)

        # Milestone 6.1: product intent remains persistent, but re-classify
        # periodically so a long conversation can switch products naturally.
        # The current inbound message is not stored yet, hence +1.
        known_category = current.get("product_interest")
        inbound_message_number = count_user_messages(sender) + 1
        reclassify_due = inbound_message_number % 10 == 0

        if known_category not in {"AI Intensive Bootcamp", "AI Corporate Training"}:
            classification = classify_message(text, history, sender=sender)
            print(f"M6 CLASSIFIER       : API CALL (product not known; inbound #{inbound_message_number})")
        elif reclassify_due:
            classification = classify_message(text, history, sender=sender)
            print(f"M6 CLASSIFIER       : API CALL (10-message refresh; inbound #{inbound_message_number})")
        else:
            classification = {
                "category": known_category,
                "confidence": 1.0,
                "reason": f"Inherited from persistent lead state; next periodic re-classification at inbound #{((inbound_message_number // 10) + 1) * 10}.",
            }
            print(f"M6 CLASSIFIER       : SKIPPED (persistent state; inbound #{inbound_message_number})")

        category = classification.get("category", "Unknown")
        flow = get_flow(sender)

        # Milestone 6.2: parse common structured/state-aware answers locally.
        local_state = parse_local_state(text, category, history, current, flow)
        state = local_state
        print("M6 LOCAL PARSER     :", local_state)

        # Milestone 6.3: if the active flow expects structured data that the
        # local parser cannot safely extract, use ONE combined LLM fallback.
        if needs_llm_fallback(text, category, current, flow, local_state):
            fallback_state = llm_state_fallback(text, category, history, current, sender=sender)
            state = merge_state(local_state, fallback_state)
            print("M6 STATE FALLBACK   : API CALL", fallback_state)
        else:
            print("M6 STATE FALLBACK   : SKIPPED")

        updates = state["lead_updates"]
        if category in {"AI Intensive Bootcamp", "AI Corporate Training"}:
            updates["product_interest"] = category

        print("DEBUG CLASSIFICATION :", classification)
        print("DEBUG LEAD UPDATES   :", updates)
        lead=upsert_lead(sender,updates)
        print("DEBUG SAVED LEAD     :", lead)

        signals=state["signals"]
        # Persist lead-like B2C signals.
        lead_updates={k:v for k,v in signals.items() if k in {"selected_class","registration_intent","registration_quantity"} and v is not None}
        if lead_updates: lead=upsert_lead(sender,lead_updates)
        flow=get_flow(sender)
        flow_updates={}
        if signals.get("b2c_intro_confirmed"): flow_updates["b2c_intro_confirmed"]=True
        if signals.get("payment_claimed"): flow_updates["payment_claimed"]=True
        if signals.get("meeting_request"): flow_updates["meeting_request"]=signals["meeting_request"]
        if signals.get("registration_confirmed"):
            flow_updates["registration_confirmed"] = True
            # If the bot explicitly asked "untuk 1 orang" and the customer
            # confirmed it, persist 1 rather than leaving quantity unknown.
            if not lead.get("registration_quantity"):
                lead = upsert_lead(sender, {"registration_quantity": 1})
        # A new registration intent or a changed class must pass through the
        # explicit confirmation gate before documents are sent.
        if signals.get("registration_intent") and not signals.get("registration_confirmed"):
            flow_updates["registration_confirmed"] = False
        if signals.get("selected_class") and current.get("selected_class") and signals.get("selected_class") != current.get("selected_class"):
            flow_updates["registration_confirmed"] = False
        if flow_updates: flow=update_flow(sender,**flow_updates)

        plan=plan_flow(classification["category"],lead,flow)
        print(f"FLOW STAGE : {plan['stage']}")
        print(f"MEDIA      : {plan['media']}")
        print(f"QUESTION   : {plan['question']}")

        replies=generate_reply(text,classification,history,lead,next_question=plan["question"],flow_stage=plan["stage"],sender=sender)
        if classification["category"] == "AI Intensive Bootcamp":
            replies=_ensure_b2c_links(replies,text,lead,plan["stage"])
            normalized_reply = " ".join(replies).lower()
            if "pastikan dulu ke tim program" in normalized_reply or "pastikan terlebih dahulu ke tim program" in normalized_reply:
                create_notification(
                    sender, "B2C", "NEED_PROGRAM_CONFIRMATION",
                    "Perlu konfirmasi ke tim program Bootcamp",
                    f"Customer {sender} menanyakan informasi yang perlu dikonfirmasi oleh tim program.",
                )
        for i,r in enumerate(replies,1): print(f"REPLY {i}: {r}")
        _send_reply_with_optional_media(sender,replies,plan["media"])

        # Only mark an asset/state after Meta accepted the send sequence.
        if plan["media"]=="bootcamp_infographic": flow=update_flow(sender,infographic_sent=True)
        if plan["stage"]=="B2C_CLASS_INFO" and lead.get("selected_class"):
            flow=update_flow(sender,class_link_sent_for=lead["selected_class"])
        elif plan["media"]=="bootcamp_registration_bundle": flow=update_flow(sender,registration_doc_sent=True)
        elif plan["media"]=="corporate_proposal":
            flow=update_flow(sender,proposal_sent=True)
            create_notification(
                sender, "B2B", "PROPOSAL_SENT",
                "Proposal Penawaran Awal sudah dikirim",
                f"Proposal awal sudah dikirim ke {lead.get('company_name') or sender}.",
            )

        # Human-action notifications are event based, not inferred by the dashboard.
        if classification["category"] == "AI Intensive Bootcamp" and flow.get("payment_claimed"):
            create_notification(
                sender, "B2C", "REGISTRATION_PAYMENT_CONFIRMATION",
                "Konfirmasi pendaftaran & pembayaran",
                f"Customer {sender} menyatakan pembayaran sudah dilakukan. Perlu pengecekan tim.",
            )
        if classification["category"] == "AI Corporate Training" and flow.get("meeting_request"):
            request_name = flow.get("meeting_request")
            create_notification(
                sender, "B2B", "QUICK_MEETING_REQUESTED",
                "Customer meminta Quick Call / Quick Meeting",
                f"{lead.get('company_name') or sender} meminta {request_name}. Perlu ditindaklanjuti tim.",
            )

        add_message(sender,"user",text)
        add_message(sender,"assistant","\n".join(replies))
        complete_batch(sender,ids)
        if classification["category"] == "AI Intensive Bootcamp":
            schedule_for_b2c_state(sender, lead, flow)
        elif classification["category"] == "AI Corporate Training":
            schedule_for_b2b_state(sender, lead, flow)
        print(f"Memory : {count_messages(sender)} total messages")
    except Exception as exc:
        print("Buffered AI/reply error:",exc)
        retry_batch_later(sender,seconds=10)


def buffer_worker():
    print("WhatsApp buffer worker started.")
    while not _worker_stop.is_set():
        try:
            for sender in due_senders(): process_sender_batch(sender)
            process_due_followups()
        except Exception as exc: print("Buffer worker error:",exc)
        _worker_stop.wait(BUFFER_POLL_SECONDS)

@asynccontextmanager
async def lifespan(app):
    _worker_stop.clear(); worker=threading.Thread(target=buffer_worker,daemon=True); worker.start()
    yield
    _worker_stop.set(); worker.join(timeout=3)

app=FastAPI(title="WhatsApp AI Admin",lifespan=lifespan)

@app.get("/")
async def root(): return {"status":"WhatsApp AI Admin is running"}

@app.get("/webhook")
async def verify_webhook(request:Request):
    mode=request.query_params.get("hub.mode"); token=request.query_params.get("hub.verify_token"); challenge=request.query_params.get("hub.challenge")
    if mode=="subscribe" and token==VERIFY_TOKEN: return PlainTextResponse(content=challenge or "")
    return PlainTextResponse(content="Verification failed",status_code=403)

@app.post("/webhook")
async def receive_webhook(request:Request):
    body=await request.json(); messages=[]
    for entry in body.get("entry",[]):
        for change in entry.get("changes",[]): messages.extend(change.get("value",{}).get("messages",[]))
    if not messages: return {"status":"ok"}
    queued=0
    for message in messages:
        sender=message.get("from"); typ=message.get("type"); mid=message.get("id")
        if not sender or typ!="text": continue
        text=message.get("text",{}).get("body","").strip()
        if not text: continue
        result=enqueue_message(sender,mid,text)
        if not result["duplicate"]:
            cancel_followup(sender)
            queued+=1
    return {"status":"ok","queued":queued}
