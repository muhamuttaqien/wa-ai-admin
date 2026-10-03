from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

FILES = {
    "general": "general.md",
    "website_snapshot": "website_snapshot.md",
    "AI Corporate Training": "corporate_training.md",
    "AI Intensive Bootcamp": "intensive_bootcamp.md",
}


def _read(name: str) -> str:
    path = KNOWLEDGE_DIR / name
    return path.read_text(encoding="utf-8")


def get_knowledge(category: str) -> str:
    # Website content is a local reviewed snapshot. No HTTP/web request is made
    # while handling WhatsApp messages.
    parts = [
        _read(FILES["general"]),
        _read(FILES["website_snapshot"]),
    ]
    filename = FILES.get(category)
    if filename:
        parts.append(_read(filename))
    return "\n\n".join(parts)
