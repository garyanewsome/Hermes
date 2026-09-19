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
        # NEVER drop/recreate a table here to "handle" a schema change, no
        # matter how early-stage this looks. An earlier version of this
        # function did exactly that (drop tasks if it predated the quadrant
        # column, again if it predated position) on the reasoning that no
        # real data existed yet to lose — true the first time, false by the
        # second: it silently deleted a real, in-use set of tasks on a
        # routine deploy, with no backup to recover from. Any future schema
        # change adds columns additively (ALTER TABLE ... ADD COLUMN IF NOT
        # EXISTS, with a backfill UPDATE if existing rows need real values,
        # never a default that discards information) and touches existing
        # rows only to migrate their data forward, never to wipe them.
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
        # Deliberately separate from `tasks` — a plain everyday checklist
        # (groceries, errands), kept simple on purpose so it never grows
        # the quadrant/notes/due-date machinery that makes sense for the
        # music-production/dev task board but would just be friction here.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todo_lists (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS todo_items (
                id SERIAL PRIMARY KEY,
                list_id INTEGER NOT NULL REFERENCES todo_lists(id) ON DELETE CASCADE,
                text TEXT NOT NULL,
                done BOOLEAN NOT NULL DEFAULT false,
                due_date DATE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute("ALTER TABLE todo_items ADD COLUMN IF NOT EXISTS due_date DATE")


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
    query = "SELECT id, title, notes, quadrant, status, due_date, position, completed_at FROM tasks"
    params: tuple = ()
    if status:
        query += " WHERE status = %s"
        params = (status,)
    # Board order (quadrant/position) doesn't mean anything once a task is
    # done — most-recently-finished-first is what you actually want when
    # looking back at what got done.
    query += " ORDER BY completed_at DESC" if status == "done" else " ORDER BY quadrant, position"
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def reopen_task(task_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE tasks SET status = 'open', completed_at = NULL WHERE id = %s", (task_id,))


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
    due_date: str | None = None,
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
    if due_date is not None:
        # "" (present but empty) means clear it — a real NULL, not the
        # literal string "" — vs None meaning the field was never sent.
        fields.append("due_date = %s")
        params.append(due_date or None)
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


def delete_habit(habit_id: int) -> None:
    # habit_logs has ON DELETE CASCADE on its habit_id foreign key, so its
    # rows for this habit go with it — no separate cleanup needed.
    with _connect() as conn:
        conn.execute("DELETE FROM habits WHERE id = %s", (habit_id,))


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


# ---- Todo lists ----------------------------------------------------------


def list_todo_lists() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT l.id, l.name,
                   count(i.id) FILTER (WHERE NOT i.done) AS open_count
            FROM todo_lists l
            LEFT JOIN todo_items i ON i.list_id = l.id
            GROUP BY l.id, l.name
            ORDER BY l.created_at
            """
        ).fetchall()
    return [dict(row) for row in rows]


def create_todo_list(name: str) -> dict:
    with _connect() as conn:
        row = conn.execute(
            "INSERT INTO todo_lists (name) VALUES (%s) RETURNING id, name",
            (name,),
        ).fetchone()
    return {**dict(row), "open_count": 0}


def rename_todo_list(list_id: int, name: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE todo_lists SET name = %s WHERE id = %s", (name, list_id))


def delete_todo_list(list_id: int) -> None:
    # todo_items has ON DELETE CASCADE on its list_id foreign key, so its
    # rows for this list go with it — no separate cleanup needed.
    with _connect() as conn:
        conn.execute("DELETE FROM todo_lists WHERE id = %s", (list_id,))


def list_todo_items(list_id: int) -> list[dict]:
    # Open items first (in the order they were added), done items below —
    # the common shape for a simple checklist, so finishing something
    # doesn't reshuffle what you're still working through.
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, list_id, text, done, due_date, created_at
            FROM todo_items
            WHERE list_id = %s
            ORDER BY done, created_at
            """,
            (list_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_todo_item(list_id: int, text: str) -> dict:
    with _connect() as conn:
        row = conn.execute(
            "INSERT INTO todo_items (list_id, text) VALUES (%s, %s) RETURNING id, list_id, text, done, due_date, created_at",
            (list_id, text),
        ).fetchone()
    return dict(row)


def update_todo_item(
    item_id: int,
    text: str | None = None,
    done: bool | None = None,
    due_date: str | None = None,
) -> None:
    fields, params = [], []
    if text is not None:
        fields.append("text = %s")
        params.append(text)
    if done is not None:
        fields.append("done = %s")
        params.append(done)
    if due_date is not None:
        # "" (present but empty) means clear it — same convention as
        # update_task's due_date arg.
        fields.append("due_date = %s")
        params.append(due_date or None)
    if not fields:
        return
    params.append(item_id)
    with _connect() as conn:
        conn.execute(f"UPDATE todo_items SET {', '.join(fields)} WHERE id = %s", params)


def delete_todo_item(item_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM todo_items WHERE id = %s", (item_id,))
