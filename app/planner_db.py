"""Tasks (tracked by which quadrant they're filed under) and habit tracking — a separate Postgres
database from the SQLite conversation history in db.py. Kept out of
Hindsight deliberately: Hindsight is semantic recall over durable facts,
not a place for structured, constantly-mutating state like task status
or habit streaks."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import APP_TIMEZONE, PLANNER_DB_URL

_TZ = ZoneInfo(APP_TIMEZONE)


def _today() -> date:
    # Never date.today() here — see APP_TIMEZONE's comment in config.py.
    # That's naive to the system clock's timezone, which is UTC in the pod
    # regardless of the host's actual local time.
    return datetime.now(_TZ).date()


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
        # Additive, same as tasks' own position column above — backfilled
        # below rather than defaulted to 0, so existing lists/items don't
        # all collapse onto the same position (they'd still *render* in a
        # reasonable order via the id/created_at tiebreak, but the first
        # drag-reorder on any of them would be starting from a meaningless
        # value instead of their actual current order).
        conn.execute("ALTER TABLE todo_lists ADD COLUMN IF NOT EXISTS position DOUBLE PRECISION")
        conn.execute("ALTER TABLE todo_items ADD COLUMN IF NOT EXISTS position DOUBLE PRECISION")
        conn.execute(
            """
            UPDATE todo_lists SET position = sub.rn
            FROM (SELECT id, ROW_NUMBER() OVER (ORDER BY created_at) AS rn FROM todo_lists) sub
            WHERE todo_lists.id = sub.id AND todo_lists.position IS NULL
            """
        )
        conn.execute(
            """
            UPDATE todo_items SET position = sub.rn
            FROM (SELECT id, ROW_NUMBER() OVER (PARTITION BY list_id ORDER BY created_at) AS rn FROM todo_items) sub
            WHERE todo_items.id = sub.id AND todo_items.position IS NULL
            """
        )
        # NULL = one-off (the default/common case); a positive integer = an
        # item that, on completion, resets itself to open with due_date
        # pushed out that many days from today rather than staying checked
        # off — "take out trash every 3 days" without needing the full
        # streak-tracking machinery habits already own (a recurring todo
        # doesn't need a log of every past completion, just "when's it due
        # next").
        conn.execute("ALTER TABLE todo_items ADD COLUMN IF NOT EXISTS recurrence_days INTEGER")
        # The other recurrence mode: specific days of the week ("every Mon/
        # Wed/Fri") instead of a fixed N-day interval. Comma-separated ISO
        # weekday numbers (1=Monday..7=Sunday), e.g. "1,3,5" — a plain TEXT
        # column rather than a Postgres array so it round-trips through
        # Python as a single string with zero type-adapter fuss. The two
        # recurrence modes are mutually exclusive on a given item (see
        # update_todo_item); NULL here means "not using this mode."
        conn.execute("ALTER TABLE todo_items ADD COLUMN IF NOT EXISTS recurrence_weekdays TEXT")
        # Every Obsidian task the nightly import (app/vault_tasks.py) has
        # ever brought in, keyed by a hash of its normalized text. Kept
        # separately from todo_items on purpose: a task you complete OR
        # delete in Hermes must never get re-imported the next night just
        # because it's still an open checkbox in the vault, so "already
        # imported" can't be inferred from whether the item still exists.
        # todo_item_id is informational only — no FK, so deleting the item
        # (or its whole list) doesn't take the tombstone with it.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vault_task_imports (
                task_key TEXT PRIMARY KEY,
                todo_item_id INTEGER,
                imported_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        # Simplenote-style scratchpad — no title field, the first line of
        # `content` serves as the title in the list. A quick-capture spot
        # for ideas on the go, meant to get copied into Obsidian later, not
        # to replace it.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        # A fixed logical canvas size (width/height, independent of whatever
        # device you're drawing on) so a sketch's coordinate space — and its
        # exports — stay consistent whether it was started on the tablet or
        # opened later on a phone. `strokes` is a JSON array of
        # {tool, color, width, points: [{x, y, pressure}, ...]} — vector,
        # not a raster snapshot, so it can be re-rendered at any size and
        # exported as SVG or PNG on demand instead of only ever being a flat
        # image.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sketches (
                id SERIAL PRIMARY KEY,
                title TEXT,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                strokes JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
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
    on_date = on_date or _today()
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

    today = _today()
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
    today = _today()
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
    # due_today_count / overdue_count drive the sidebar's "something's due
    # today" star and "something's overdue" ! markers — computed from the app's own timezone-aware today (see _today's own
    # comment for why: Postgres's CURRENT_DATE would use the pod's/DB
    # server's timezone, which isn't necessarily APP_TIMEZONE).
    today = _today()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT l.id, l.name, l.position,
                   count(i.id) FILTER (WHERE NOT i.done) AS open_count,
                   count(i.id) FILTER (WHERE NOT i.done AND i.due_date = %s) AS due_today_count,
                   count(i.id) FILTER (WHERE NOT i.done AND i.due_date < %s) AS overdue_count
            FROM todo_lists l
            LEFT JOIN todo_items i ON i.list_id = l.id
            GROUP BY l.id, l.name, l.position
            ORDER BY l.position
            """,
            (today, today),
        ).fetchall()
    return [dict(row) for row in rows]


def create_todo_list(name: str) -> dict:
    with _connect() as conn:
        row = conn.execute(
            """
            INSERT INTO todo_lists (name, position)
            VALUES (%s, COALESCE((SELECT MAX(position) + 1 FROM todo_lists), 0))
            RETURNING id, name, position
            """,
            (name,),
        ).fetchone()
    return {**dict(row), "open_count": 0, "due_today_count": 0, "overdue_count": 0}


def update_todo_list(list_id: int, name: str | None = None, position: float | None = None) -> None:
    fields, params = [], []
    if name is not None:
        fields.append("name = %s")
        params.append(name)
    if position is not None:
        fields.append("position = %s")
        params.append(position)
    if not fields:
        return
    params.append(list_id)
    with _connect() as conn:
        conn.execute(f"UPDATE todo_lists SET {', '.join(fields)} WHERE id = %s", params)


def delete_todo_list(list_id: int) -> None:
    # todo_items has ON DELETE CASCADE on its list_id foreign key, so its
    # rows for this list go with it — no separate cleanup needed.
    with _connect() as conn:
        conn.execute("DELETE FROM todo_lists WHERE id = %s", (list_id,))


def find_todo_list_by_name(name: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name FROM todo_lists WHERE name ILIKE %s ORDER BY created_at LIMIT 1",
            (f"%{name}%",),
        ).fetchone()
    return dict(row) if row else None


def get_or_create_todo_list(name: str) -> dict:
    # Chat's add_todo_item tool: naming a list that doesn't exist yet should
    # just create it (same reasoning as habits' get_or_create_habit), not
    # error — "add X to my errands list" is a perfectly normal way to start
    # a new list, not a typo to reject.
    existing = find_todo_list_by_name(name)
    if existing:
        return existing
    return create_todo_list(name)


def list_all_open_todo_items() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT i.id, i.text, i.due_date, l.name AS list_name
            FROM todo_items i
            JOIN todo_lists l ON l.id = i.list_id
            WHERE NOT i.done
            ORDER BY l.name, i.created_at
            """
        ).fetchall()
    return [dict(row) for row in rows]


def find_open_todo_items_by_text(text: str, list_id: int | None = None) -> list[dict]:
    query = """
        SELECT i.id, i.text, i.due_date, l.name AS list_name
        FROM todo_items i JOIN todo_lists l ON l.id = i.list_id
        WHERE NOT i.done AND i.text ILIKE %s
    """
    params: list = [f"%{text}%"]
    if list_id is not None:
        query += " AND i.list_id = %s"
        params.append(list_id)
    query += " ORDER BY i.created_at DESC"
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def _parse_weekdays(value: str | None) -> set[int]:
    if not value:
        return set()
    return {int(d) for d in value.split(",") if d}


def _next_weekday_occurrence(today: date, weekdays: set[int]) -> date:
    # Smallest delta in 1..7 whose ISO weekday (1=Monday..7=Sunday) is one
    # of the selected days — always strictly after today, even if today
    # itself is a selected day, since today's occurrence was just done.
    for delta in range(1, 8):
        candidate = today + timedelta(days=delta)
        if candidate.isoweekday() in weekdays:
            return candidate
    return today + timedelta(days=7)  # unreachable if weekdays is non-empty


def list_todo_items(list_id: int) -> list[dict]:
    # Open items first (in position order), done items below — the common
    # shape for a simple checklist, so finishing something doesn't reshuffle
    # what you're still working through. position is scoped to the whole
    # list (open and done items share one axis), which is fine since the
    # done/open split is the primary sort key regardless.
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, list_id, text, done, due_date, position, recurrence_days, recurrence_weekdays, created_at
            FROM todo_items
            WHERE list_id = %s
            ORDER BY done, position
            """,
            (list_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_todo_item(
    list_id: int,
    text: str,
    recurrence_days: int | None = None,
    recurrence_weekdays: str | None = None,
) -> dict:
    with _connect() as conn:
        row = conn.execute(
            """
            INSERT INTO todo_items (list_id, text, position, recurrence_days, recurrence_weekdays)
            VALUES (%s, %s, COALESCE((SELECT MAX(position) + 1 FROM todo_items WHERE list_id = %s), 0), %s, %s)
            RETURNING id, list_id, text, done, due_date, position, recurrence_days, recurrence_weekdays, created_at
            """,
            (list_id, text, list_id, recurrence_days, recurrence_weekdays),
        ).fetchone()
    return dict(row)


def update_todo_item(
    item_id: int,
    text: str | None = None,
    done: bool | None = None,
    due_date: str | None = None,
    position: float | None = None,
    recurrence_days: int | None = None,
    recurrence_weekdays: str | None = None,
    list_id: int | None = None,
) -> dict:
    # list_id: move the item to another list, appended at the end of it
    # (unless an explicit position is also given). Raises ValueError if the
    # destination list doesn't exist.
    #
    # recurrence_days: None means "don't touch"; 0 is the sentinel for
    # "clear it" (a real interval can never be 0). recurrence_weekdays:
    # None means "don't touch"; "" is the clear sentinel (same convention
    # as due_date, since this is also a string field). The two recurrence
    # modes are mutually exclusive — setting one to a real value clears
    # the other, so an item is never simultaneously "every 3 days" and
    # "every Mon/Wed/Fri."
    if recurrence_days is not None and recurrence_days != 0:
        recurrence_weekdays = ""
    elif recurrence_weekdays is not None and recurrence_weekdays != "":
        recurrence_days = 0

    if done is True:
        with _connect() as conn:
            current = conn.execute(
                "SELECT recurrence_days, recurrence_weekdays FROM todo_items WHERE id = %s", (item_id,)
            ).fetchone()
        effective_days = current["recurrence_days"] if current else None
        effective_weekdays = current["recurrence_weekdays"] if current else None
        if recurrence_days is not None:
            effective_days = None if recurrence_days == 0 else recurrence_days
        if recurrence_weekdays is not None:
            effective_weekdays = recurrence_weekdays or None

        # Recurring items don't stay checked off — completing one resets it
        # to open with the next due date, so finishing early or late never
        # compounds drift; it's always "from when I actually did it," not
        # "from when it was originally scheduled."
        if effective_days:
            done = False
            due_date = (_today() + timedelta(days=effective_days)).isoformat()
        elif effective_weekdays:
            done = False
            due_date = _next_weekday_occurrence(_today(), _parse_weekdays(effective_weekdays)).isoformat()

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
    if position is not None:
        fields.append("position = %s")
        params.append(position)
    if recurrence_days is not None:
        fields.append("recurrence_days = %s")
        params.append(None if recurrence_days == 0 else recurrence_days)
    if recurrence_weekdays is not None:
        fields.append("recurrence_weekdays = %s")
        params.append(recurrence_weekdays or None)
    if list_id is not None:
        with _connect() as conn:
            if conn.execute("SELECT 1 FROM todo_lists WHERE id = %s", (list_id,)).fetchone() is None:
                raise ValueError(f"No todo list with id {list_id}")
        fields.append("list_id = %s")
        params.append(list_id)
        if position is None:
            fields.append("position = COALESCE((SELECT MAX(position) + 1 FROM todo_items WHERE list_id = %s), 0)")
            params.append(list_id)

    with _connect() as conn:
        if fields:
            params.append(item_id)
            row = conn.execute(
                f"""
                UPDATE todo_items SET {', '.join(fields)} WHERE id = %s
                RETURNING id, list_id, text, done, due_date, position, recurrence_days, recurrence_weekdays, created_at
                """,
                params,
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT id, list_id, text, done, due_date, position, recurrence_days, recurrence_weekdays, created_at
                FROM todo_items WHERE id = %s
                """,
                (item_id,),
            ).fetchone()
    # Returned so callers (the PATCH route) can sync the client to what
    # actually happened server-side — critical for a recurring item, where
    # "mark done" can silently turn into "reset to open, due_date advanced"
    # instead of the plain done=True the caller asked for.
    return dict(row)


def delete_todo_item(item_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM todo_items WHERE id = %s", (item_id,))


# ---- Notes ----------------------------------------------------------------


def list_notes() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, created_at, updated_at FROM notes ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def create_note() -> dict:
    with _connect() as conn:
        row = conn.execute(
            "INSERT INTO notes DEFAULT VALUES RETURNING id, content, created_at, updated_at"
        ).fetchone()
    return dict(row)


def create_note_with_content(content: str) -> dict:
    # Separate from create_note() (always blank, for the "+ New note" UI
    # flow that then autosaves as you type) — the add_scratch_note chat
    # tool has the content up front, so it should land in one insert, not
    # a blank note immediately followed by an update.
    with _connect() as conn:
        row = conn.execute(
            "INSERT INTO notes (content) VALUES (%s) RETURNING id, content, created_at, updated_at",
            (content,),
        ).fetchone()
    return dict(row)


def search_notes_content(query: str, limit: int = 5) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, updated_at FROM notes WHERE content ILIKE %s ORDER BY updated_at DESC LIMIT %s",
            (f"%{query}%", limit),
        ).fetchall()
    return [dict(row) for row in rows]


def list_recent_notes(limit: int = 10) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, content, updated_at FROM notes ORDER BY updated_at DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_note(note_id: int, content: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE notes SET content = %s, updated_at = now() WHERE id = %s",
            (content, note_id),
        )


def delete_note(note_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM notes WHERE id = %s", (note_id,))


# ---- Sketches ---------------------------------------------------------------


def list_sketches() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, width, height, strokes, created_at, updated_at FROM sketches ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def create_sketch(width: int, height: int) -> dict:
    with _connect() as conn:
        row = conn.execute(
            """
            INSERT INTO sketches (width, height) VALUES (%s, %s)
            RETURNING id, title, width, height, strokes, created_at, updated_at
            """,
            (width, height),
        ).fetchone()
    return dict(row)


def update_sketch(sketch_id: int, strokes: list | None = None, title: str | None = None) -> None:
    fields, params = [], []
    if strokes is not None:
        fields.append("strokes = %s")
        params.append(Jsonb(strokes))
    if title is not None:
        fields.append("title = %s")
        params.append(title or None)
    if not fields:
        return
    fields.append("updated_at = now()")
    params.append(sketch_id)
    with _connect() as conn:
        conn.execute(f"UPDATE sketches SET {', '.join(fields)} WHERE id = %s", params)


def delete_sketch(sketch_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sketches WHERE id = %s", (sketch_id,))


def get_imported_vault_task_keys() -> set[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT task_key FROM vault_task_imports").fetchall()
    return {row["task_key"] for row in rows}


def record_vault_task_import(task_key: str, todo_item_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO vault_task_imports (task_key, todo_item_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (task_key, todo_item_id),
        )
