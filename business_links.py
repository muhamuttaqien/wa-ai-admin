"""Curated public links that the response model may safely share.

Keep these explicit. Do not let the LLM invent Indonesia AI URLs.
"""

BOOTCAMP_TRACK_LINKS = {
    "ML": "https://aiforindonesia.com/bootcamp-machine-learning/",
    "CV": "https://aiforindonesia.com/bootcamp-computer-vision/",
    "NLP": "https://aiforindonesia.com/bootcamp-natural-language-processing/",
}

BOOTCAMP_CURRICULUM_LINKS = {
    "ML": "https://aiforindonesia.com/bootcamp-machine-learning/#curriculum",
    "CV": "https://aiforindonesia.com/bootcamp-computer-vision/#curriculum",
    "NLP": "https://aiforindonesia.com/bootcamp-natural-language-processing/#curriculum",
}

DASHBOARD_DEMO_LINK = "https://aiforindonesia.com/dashboard-demo"


def track_page_url(selected_class: str | None) -> str | None:
    return BOOTCAMP_TRACK_LINKS.get(selected_class or "")


def curriculum_url(selected_class: str | None) -> str | None:
    return BOOTCAMP_CURRICULUM_LINKS.get(selected_class or "")


def links_text(category: str) -> str:
    if category != "AI Intensive Bootcamp":
        return "(Tidak ada curated link khusus untuk kategori ini.)"

    lines = [
        "Gunakan hanya URL berikut jika relevan. Jangan membuat atau menebak URL lain:",
        f"- Dashboard belajar demo: {DASHBOARD_DEMO_LINK}",
    ]
    for short in ("ML", "CV", "NLP"):
        lines.append(f"- {short} halaman program: {BOOTCAMP_TRACK_LINKS[short]}")
        lines.append(f"- {short} curriculum/silabus: {BOOTCAMP_CURRICULUM_LINKS[short]}")
    return "\n".join(lines)
