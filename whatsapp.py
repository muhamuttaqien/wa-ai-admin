import os
import random
import time
import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
GRAPH_API_VERSION = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v26.0")
BUBBLE_DELAY_MIN = float(os.getenv("BUBBLE_DELAY_MIN_SECONDS", "1.0"))
BUBBLE_DELAY_MAX = float(os.getenv("BUBBLE_DELAY_MAX_SECONDS", "2.5"))


def send_text_message(to: str, text: str) -> dict:
    if not ACCESS_TOKEN:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN belum diatur di .env")
    if not PHONE_NUMBER_ID:
        raise RuntimeError("WHATSAPP_PHONE_NUMBER_ID belum diatur di .env")

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    if not response.ok:
        raise RuntimeError(
            f"WhatsApp send failed ({response.status_code}): {response.text}"
        )
    return response.json()


def send_text_messages(to: str, messages: list[str]) -> list[dict]:
    results = []
    for index, text in enumerate(messages):
        if index > 0:
            time.sleep(random.uniform(BUBBLE_DELAY_MIN, BUBBLE_DELAY_MAX))
        results.append(send_text_message(to, text))
    return results


def upload_media(file_path: str, mime_type: str) -> str:
    """Upload a local asset to Meta and return its media id."""
    if not ACCESS_TOKEN or not PHONE_NUMBER_ID:
        raise RuntimeError("WhatsApp credentials belum diatur di .env")
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    with open(file_path, "rb") as fh:
        response = requests.post(
            url,
            headers=headers,
            data={"messaging_product": "whatsapp", "type": mime_type},
            files={"file": (os.path.basename(file_path), fh, mime_type)},
            timeout=30,
        )
    if not response.ok:
        raise RuntimeError(f"WhatsApp media upload failed ({response.status_code}): {response.text}")
    return response.json()["id"]


def send_media_message(to: str, file_path: str, media_type: str, caption: str | None = None, mime_type: str | None = None) -> dict:
    """Upload and send an image or document through WhatsApp Cloud API."""
    if media_type not in {"image", "document"}:
        raise ValueError("media_type must be 'image' or 'document'")
    if mime_type is None:
        mime_type = "image/jpeg" if media_type == "image" else "application/pdf"
    mime = mime_type
    media_id = upload_media(file_path, mime)
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages"
    obj = {"id": media_id}
    if caption:
        obj["caption"] = caption
    if media_type == "document":
        obj["filename"] = os.path.basename(file_path)
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": media_type,
        media_type: obj,
    }
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    response = requests.post(url, headers=headers, json=payload, timeout=20)
    if not response.ok:
        raise RuntimeError(f"WhatsApp media send failed ({response.status_code}): {response.text}")
    return response.json()
