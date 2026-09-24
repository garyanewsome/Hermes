"""Text extraction for document attachments (Phase 2 of the chat-
attachments plan) — PDF via pypdf, plain text/markdown read directly.
Kept separate from main.py since it's a distinct concern (parsing, not
request handling) and may grow (other formats) without main.py bloating.
"""

MAX_DOCUMENT_CHARS = 12000


def extract_text(local_path: str, mime_type: str) -> str | None:
    """Best-effort — returns None (not an exception) on a file this
    doesn't know how to read or can't parse, so one bad upload doesn't
    fail the whole chat turn."""
    if mime_type == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(local_path)
            return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip() or None
        except Exception:
            return None
    if mime_type == "text/plain":
        try:
            with open(local_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except OSError:
            return None
    return None


def cap_text(text: str, max_chars: int = MAX_DOCUMENT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[... truncated, {len(text) - max_chars} more characters not shown ...]"
