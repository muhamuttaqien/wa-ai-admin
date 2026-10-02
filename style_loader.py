from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STYLE_DIR = BASE_DIR / "styles"


def style_name_for(category: str) -> str:
    if category == "AI Corporate Training":
        return "b2b_corporate"
    if category == "AI Intensive Bootcamp":
        return "b2c_bootcamp"
    return "neutral"


def get_style(category: str) -> str:
    path = STYLE_DIR / f"{style_name_for(category)}.md"
    return path.read_text(encoding="utf-8")
