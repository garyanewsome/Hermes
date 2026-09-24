import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import DB_PATH


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # One table for every attachment kind (image now, document later)
        # rather than a separate migration per kind — extracted_text sits
        # unused until documents need it.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id INTEGER NOT NULL REFERENCES messages(id),
                kind TEXT NOT NULL,
                path TEXT NOT NULL,
                mime_type TEXT,
                original_filename TEXT,
                extracted_text TEXT,
                created_at TEXT NOT NULL
            )
            """
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_conversation() -> str:
    conversation_id = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, NULL, ?, ?)",
            (conversation_id, now, now),
        )
    return conversation_id


def add_message(conversation_id: str, role: str, content: str) -> int:
    now = _now()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, now),
        )
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
        return cursor.lastrowid


def add_attachment(
    message_id: int, kind: str, path: str, mime_type: str | None, original_filename: str | None
) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO attachments (message_id, kind, path, mime_type, original_filename, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, kind, path, mime_type, original_filename, _now()),
        )


def get_attachments(message_id: int) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, kind, path, mime_type, original_filename FROM attachments WHERE message_id = ? ORDER BY id",
            (message_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def maybe_set_title(conversation_id: str, first_user_message: str) -> None:
    title = first_user_message.strip().replace("\n", " ")
    if len(title) > 60:
        title = title[:57] + "..."
    with _connect() as conn:
        conn.execute(
            "UPDATE conversations SET title = ? WHERE id = ? AND title IS NULL",
            (title, conversation_id),
        )


def rename_conversation(conversation_id: str, title: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, conversation_id))


def conversation_exists(conversation_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    return row is not None


def get_messages(conversation_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, role, content FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [
        {"id": row["id"], "role": row["role"], "content": row["content"], "attachments": get_attachments(row["id"])}
        for row in rows
    ]


def get_last_assistant_message(conversation_id: str) -> str | None:
    """For write_vault_note's default path: pull the model's own most
    recent reply straight from storage instead of asking it to retype
    (large) content as a tool-call argument — same corruption/latency
    risk already solved for generate_image's image URLs, just for text
    instead of a URL."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT content FROM messages WHERE conversation_id = ? AND role = 'assistant' ORDER BY id DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
    return row["content"] if row else None


def list_conversations() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {"id": row["id"], "title": row["title"] or "New chat", "updated_at": row["updated_at"]}
        for row in rows
    ]


def delete_conversation(conversation_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))


def get_message(message_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, conversation_id, role, content FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
    if row is None:
        return None
    return {"id": row["id"], "conversation_id": row["conversation_id"], "role": row["role"], "content": row["content"]}


def delete_message(message_id: int) -> None:
    """Removes exactly this one message, nothing else — for a plain
    "get rid of this" from the UI with no regenerate involved."""
    with _connect() as conn:
        conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))


def delete_messages_from(conversation_id: str, message_id: int) -> None:
    """Drops this message and everything after it (by id, which is also
    insertion order) — the truncation step behind both regenerate (target
    an assistant message) and edit-and-resend (target a user message,
    dropping the stale reply and anything after it)."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM messages WHERE conversation_id = ? AND id >= ?",
            (conversation_id, message_id),
        )


def update_message_content(message_id: int, content: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE messages SET content = ? WHERE id = ?", (content, message_id))
