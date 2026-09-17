"""Tasks (tracked by which quadrant they're filed under) and habit tracking — a separate Postgres
database from the SQLite conversation history in db.py. Kept out of
Hindsight deliberately: Hindsight is semantic recall over durable facts,
not a place for structured, constantly-mutating state like task status
or habit streaks."""

from contextlib import contextmanager
from datetime import date, timedelta

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
        # The tasks schema changed (urgent/important booleans -> a single
        # quadrant column) after a real deploy already created the table with
        # the old shape — CREATE TABLE IF NOT EXISTS is a no-op against an
        # existing table, so every redeploy since kept silently running
        # against stale columns (surfaced as 500s on every /tasks request).
        # No real task data exists yet worth preserving, so just drop and
        # recreate on mismatch instead of writing a real migration for a
        # schema that's still actively settling this early on.
        has_table = conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'tasks'"
        ).fetchone()
        has_current_columns = conn.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'tasks' AND column_name = 'position'"
        ).fetchone()
        if has_table and not has_current_columns:
            conn.execute("DROP TABLE tasks")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                notes TEXT,
                quadrant TEXT NOT NULL CHECK (quadrant IN ('do', 'schedule', 'next', 'backlog')),
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done')),
                due_date DATE,
                position DOUBLE PRECISION NOT NULL DEFAULT 0,
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
    quadrant: str,
    due_date: str | None = None,
    notes: str | None = None,
) -> dict:
    with _connect() as conn:
        # Append to the end of this quadrant's own order — the position
        # space is per-quadrant, not global, so moving a task to a
        # different quadrant never has to renumber anything there.
        row = conn.execute(
            """
            INSERT INTO tasks (title, notes, quadrant, due_date, position)
            VALUES (%s, %s, %s, %s, COALESCE((SELECT MAX(position) + 1 FROM tasks WHERE quadrant = %s), 0))
            RETURNING id, title, notes, quadrant, status, due_date, position
            """,
            (title, notes, quadrant, due_date, quadrant),
        ).fetchone()
    return dict(row)


def list_tasks(status: str | None = "open") -> list[dict]:
    query = "SELECT id, title, notes, quadrant, status, due_date, position FROM tasks"
    params: tuple = ()
    if status:
        query += " WHERE status = %s"
        params = (status,)
    query += " ORDER BY quadrant, position"
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def find_open_tasks_by_title(title_query: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, title, notes, quadrant, status, due_date, position
            FROM tasks
            WHERE status = 'open' AND title ILIKE %s
            ORDER BY created_at DESC
            """,
            (f"%{title_query}%",),
        ).fetchall()
    return [dict(row) for row in rows]


def update_task(
    task_id: int,
    quadrant: str | None = None,
    title: str | None = None,
    notes: str | None = None,
    position: float | None = None,
) -> None:
    fields, params = [], []
    if quadrant is not None:
        fields.append("quadrant = %s")
        params.append(quadrant)
    if title is not None:
        fields.append("title = %s")
        params.append(title)
    if notes is not None:
        fields.append("notes = %s")
        params.append(notes)
    if position is not None:
        fields.append("position = %s")
        params.append(position)
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


def habit_last_n_days(habit_id: int, days: int = 7) -> list[dict]:
    """Real per-day history, oldest to newest (last element is today) — not
    derived from the streak, so a gap earlier in the week shows correctly
    even if today's log continues an otherwise-broken streak. Each day
    carries its own date so the UI can toggle a specific day, not just
    today."""
    today = date.today()
    start = today - timedelta(days=days - 1)
    with _connect() as conn:
        rows = conn.execute(
            "SELECT logged_date FROM habit_logs WHERE habit_id = %s AND logged_date >= %s",
            (habit_id, start),
        ).fetchall()
    logged_dates = {row["logged_date"] for row in rows}
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "logged": (start + timedelta(days=i)) in logged_dates}
        for i in range(days)
    ]


def set_habit_log(habit_id: int, on_date: date, logged: bool) -> None:
    with _connect() as conn:
        if logged:
            conn.execute(
                "INSERT INTO habit_logs (habit_id, logged_date) VALUES (%s, %s) ON CONFLICT (habit_id, logged_date) DO NOTHING",
                (habit_id, on_date),
            )
        else:
            conn.execute(
                "DELETE FROM habit_logs WHERE habit_id = %s AND logged_date = %s",
                (habit_id, on_date),
            )


def list_habits_with_streaks() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT id, name FROM habits ORDER BY name").fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "streak": habit_streak(row["name"]),
            "last_7_days": habit_last_n_days(row["id"]),
        }
        for row in rows
    ]
