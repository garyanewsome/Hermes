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


def add_message(conversation_id: str, role: str, content: str) -> None:
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, now),
        )
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))


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
            "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


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
