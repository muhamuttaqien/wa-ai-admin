from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"

FILES = {
    "general": "general.md",
    "AI Corporate Training": "corporate_training.md",
    "AI Intensive Bootcamp": "intensive_bootcamp.md",
}

def _read(name: str) -> str:
    path = KNOWLEDGE_DIR / name
    return path.read_text(encoding="utf-8")

def get_knowledge(category: str) -> str:
    parts = [_read(FILES["general"])]
    filename = FILES.get(category)
    if filename:
        parts.append(_read(filename))
    return "\n\n".join(parts)
