"""Tasks (Eisenhower matrix) and habit tracking — a separate Postgres
database from the SQLite conversation history in db.py. Kept out of
Hindsight deliberately: Hindsight is semantic recall over durable facts,
not a place for structured, constantly-mutating state like task status
or habit streaks."""

from contextlib import contextmanager
from datetime import date

import psycopg
from psycopg.rows import dict_row

from app.config import PLANNER_DB_URL


@contextmanager
def _connect():
    conn = psycopg.connect(PLANNER_DB_URL, row_factory=dict_row)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_planner_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                notes TEXT,
                urgent BOOLEAN NOT NULL DEFAULT false,
                important BOOLEAN NOT NULL DEFAULT false,
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
                due_date DATE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                completed_at TIMESTAMPTZ
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS habits (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS habit_logs (
                id SERIAL PRIMARY KEY,
                habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
                logged_date DATE NOT NULL,
                UNIQUE (habit_id, logged_date)
            )
            """
        )


# ---- Tasks -----------------------------------------------------------


def create_task(
    title: str,
    urgent: bool = False,
    important: bool = False,
    due_date: str | None = None,
    notes: str | None = None,
) -> dict:
    with _connect() as conn:
        row = conn.execute(
            """
            INSERT INTO tasks (title, notes, urgent, important, due_date)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, title, notes, urgent, important, status, due_date
            """,
            (title, notes, urgent, important, due_date),
        ).fetchone()
    return dict(row)


def list_tasks(status: str | None = "open") -> list[dict]:
    query = "SELECT id, title, notes, urgent, important, status, due_date FROM tasks"
    params: tuple = ()
    if status:
        query += " WHERE status = %s"
        params = (status,)
    query += " ORDER BY important DESC, urgent DESC, due_date NULLS LAST, created_at"
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def find_open_tasks_by_title(title_query: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, title, notes, urgent, important, status, due_date
            FROM tasks
            WHERE status = 'open' AND title ILIKE %s
            ORDER BY created_at DESC
            """,
            (f"%{title_query}%",),
        ).fetchall()
    return [dict(row) for row in rows]


def update_task(task_id: int, urgent: bool | None = None, important: bool | None = None) -> None:
    fields, params = [], []
    if urgent is not None:
        fields.append("urgent = %s")
        params.append(urgent)
    if important is not None:
        fields.append("important = %s")
        params.append(important)
    if not fields:
        return
    params.append(task_id)
    with _connect() as conn:
        conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id = %s", params)


def complete_task(task_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'done', completed_at = now() WHERE id = %s",
            (task_id,),
        )


def delete_task(task_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM tasks WHERE id = %s", (task_id,))


# ---- Habits ------------------------------------------------------------


def get_or_create_habit(name: str) -> dict:
    with _connect() as conn:
        row = conn.execute(
            """
            INSERT INTO habits (name) VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id, name
            """,
            (name,),
        ).fetchone()
    return dict(row)


def log_habit(name: str, on_date: date | None = None) -> dict:
    on_date = on_date or date.today()
    habit = get_or_create_habit(name)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO habit_logs (habit_id, logged_date) VALUES (%s, %s)
            ON CONFLICT (habit_id, logged_date) DO NOTHING
            """,
            (habit["id"], on_date),
        )
    return habit


def habit_streak(name: str) -> int:
    """Consecutive days logged, counting back from today (or yesterday, so
    a habit already logged yesterday doesn't show as broken before today's
    log happens)."""
    with _connect() as conn:
        habit = conn.execute("SELECT id FROM habits WHERE name = %s", (name,)).fetchone()
        if not habit:
            return 0
        rows = conn.execute(
            "SELECT logged_date FROM habit_logs WHERE habit_id = %s ORDER BY logged_date DESC",
            (habit["id"],),
        ).fetchall()

    logged_dates = {row["logged_date"] for row in rows}
    if not logged_dates:
        return 0

    today = date.today()
    cursor = today if today in logged_dates else today.fromordinal(today.toordinal() - 1)
    streak = 0
    while cursor in logged_dates:
        streak += 1
        cursor = cursor.fromordinal(cursor.toordinal() - 1)
    return streak


def list_habits_with_streaks() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT id, name FROM habits ORDER BY name").fetchall()
    return [{"id": row["id"], "name": row["name"], "streak": habit_streak(row["name"])} for row in rows]
