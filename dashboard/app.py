import os, sys
import tempfile
from pathlib import Path
from flask import Flask, render_template, redirect, request, url_for, abort
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from dashboard.dashboard_store import leads, lead, conversation, followup, summary, api_usage
from notification_store import (list_notifications, notification_counts, update_notification_status,
                                open_notifications_for_sender, get_notification)
from conversation import add_message
from whatsapp import send_text_message, send_media_message
from followup_scheduler import cancel_followup

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("DASHBOARD_MAX_UPLOAD_MB", "20")) * 1024 * 1024

ALLOWED_HUMAN_UPLOADS = {
    ".pdf": ("document", "application/pdf"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".png": ("image", "image/png"),
}


@app.template_filter("usd_to_idr")
def usd_to_idr(value):
    """Convert estimated USD API cost to an approximate IDR value for display."""
    try:
        rate = float(os.getenv("USD_TO_IDR_RATE", "16500"))
        return f"{float(value) * rate:,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "0"


@app.template_filter("format_wib")
def format_wib(value):
    """Convert an ISO-8601 UTC timestamp to a human-readable WIB timestamp."""
    if not value:
        return "-"

    from datetime import datetime
    from zoneinfo import ZoneInfo

    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

        # Treat naive timestamps as UTC for backward compatibility.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))

        dt_wib = dt.astimezone(ZoneInfo("Asia/Jakarta"))

        months = {
            1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
            5: "Mei", 6: "Jun", 7: "Jul", 8: "Agu",
            9: "Sep", 10: "Okt", 11: "Nov", 12: "Des",
        }

        return f"{dt_wib.day} {months[dt_wib.month]} {dt_wib.year}, {dt_wib:%H:%M} WIB"

    except (ValueError, TypeError):
        return str(value)

HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
PORT = int(os.getenv("DASHBOARD_PORT", "1008"))

@app.get("/")
def home():
    return redirect(url_for("b2c"))

def _page(channel):
    all_leads = leads(channel)
    filters = {
        "q": request.args.get("q", "").strip(),
        "class": request.args.get("class", "").strip(),
        "registration": request.args.get("registration", "").strip(),
        "payment": request.args.get("payment", "").strip(),
        "delivery": request.args.get("delivery", "").strip(),
        "goal": request.args.get("goal", "").strip(),
        "status": request.args.get("status", "").strip(),
    }

    def matches(item):
        q = filters["q"].lower()
        if q:
            haystack = " ".join(str(item.get(k) or "") for k in (
                "sender", "contact_name", "company_name", "selected_class",
                "training_goal", "preferred_delivery"
            )).lower()
            if q not in haystack:
                return False

        if channel == "B2C":
            if filters["class"] and (item.get("selected_class") or "") != filters["class"]:
                return False
            reg = filters["registration"]
            if reg == "confirmed" and not item.get("registration_confirmed"):
                return False
            if reg == "interested" and (item.get("registration_confirmed") or not item.get("registration_intent")):
                return False
            if reg == "exploring" and (item.get("registration_confirmed") or item.get("registration_intent")):
                return False
            if filters["payment"] == "claimed" and not item.get("payment_claimed"):
                return False
            if filters["payment"] == "not_claimed" and item.get("payment_claimed"):
                return False
        else:
            if filters["delivery"] and (item.get("preferred_delivery") or "") != filters["delivery"]:
                return False
            if filters["goal"] and (item.get("training_goal") or "") != filters["goal"]:
                return False
            status = filters["status"]
            if status == "meeting" and not item.get("meeting_request"):
                return False
            if status == "proposal" and (item.get("meeting_request") or not item.get("proposal_sent")):
                return False
            if status == "qualifying" and (item.get("meeting_request") or item.get("proposal_sent")):
                return False
        return True

    filtered_leads = [item for item in all_leads if matches(item)]
    return render_template(
        "dashboard.html",
        channel=channel,
        leads=filtered_leads,
        total_leads=len(all_leads),
        filters=filters,
        notifications=list_notifications(channel, 100),
        counts=notification_counts(channel),
        summary=summary(channel),
    )

@app.get("/b2c")
def b2c():
    return _page("B2C")

@app.get("/b2b")
def b2b():
    return _page("B2B")

@app.get("/lead/<sender>")
def lead_detail(sender):
    item = lead(sender)
    if not item:
        abort(404)
    channel = "B2C" if item.get("product_interest") == "AI Intensive Bootcamp" else "B2B"
    return render_template(
        "lead.html",
        channel=channel,
        lead=item,
        messages=conversation(sender),
        followup=followup(sender),
        open_notifications=open_notifications_for_sender(sender),
        api_usage=api_usage(sender),
    )


@app.post("/lead/<sender>/reply")
def human_reply(sender):
    item = lead(sender)
    if not item:
        abort(404)

    message = request.form.get("message", "").strip()
    upload = request.files.get("file")
    notification_id = request.form.get("notification_id", type=int)
    has_file = bool(upload and upload.filename)
    if (not message and not has_file) or not notification_id:
        abort(400)
    if has_file and len(message) > 1024:
        abort(400, description="Caption file maksimum 1024 karakter.")

    notification = get_notification(notification_id)
    if (
        not notification
        or notification.get("sender") != sender
        or notification.get("status") not in {"unread", "in_progress"}
    ):
        abort(403)

    # Only notification-triggered cases may be answered by a human admin.
    # Resolve only after Meta accepts the outbound message/file.
    if has_file:
        filename = secure_filename(upload.filename)
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_HUMAN_UPLOADS:
            abort(415, description="Format file tidak didukung. Gunakan PDF, JPG, JPEG, atau PNG.")

        media_type, mime_type = ALLOWED_HUMAN_UPLOADS[ext]
        # Never trust the browser-provided MIME type; determine it from the allow-listed extension.
        with tempfile.TemporaryDirectory(prefix="wa-admin-upload-") as tmpdir:
            file_path = Path(tmpdir) / filename
            upload.save(file_path)
            send_media_message(
                sender,
                str(file_path),
                media_type,
                caption=message or None,
                mime_type=mime_type,
            )

        history_text = f"[File: {filename}]"
        if message:
            history_text += f"\n{message}"
        add_message(sender, "human_admin", history_text)
    else:
        send_text_message(sender, message)
        add_message(sender, "human_admin", message)

    cancel_followup(sender)
    update_notification_status(notification_id, "resolved")
    return redirect(url_for("lead_detail", sender=sender))

@app.post("/notification/<int:notification_id>/status")
def notification_status(notification_id):
    status = request.form.get("status", "")
    update_notification_status(notification_id, status)
    return redirect(request.referrer or url_for("home"))

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)
