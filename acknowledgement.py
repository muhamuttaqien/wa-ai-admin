import re

# Short social acknowledgements should not trigger another bot reply.
# Keep this deliberately conservative so substantive messages are never swallowed.
_ACK_PATTERNS = [
    r'^(baik|ok|oke|okay|siap|sip)(\s+(kak|ka|pak|bu|bapak|ibu))?[.!🙏🏻😊🙂]*$',
    r'^(makasih|terima\s*kasih|thank\s*you|thanks)(\s+(kak|ka|pak|bu|bapak|ibu))?[.!🙏🏻😊🙂]*$',
]


def is_acknowledgement_only(text: str) -> bool:
    value = ' '.join((text or '').strip().lower().split())
    return bool(value) and any(re.fullmatch(p, value, flags=re.IGNORECASE) for p in _ACK_PATTERNS)
