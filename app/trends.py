"""Numbers behind the Trends page. Weeks run Monday to Sunday in the app's
timezone, and all counting happens here."""

from datetime import date, timedelta

from fastapi import APIRouter, Query

from app import planner_db
from app.config import APP_TIMEZONE

router = APIRouter()

HABIT_GRID_WEEKS = 52

# Each returns (day, how much) rows between two dates. Completion times are
# stored with a timezone, so they're turned into local days here.
_DAILY = {
    "tasks": """
        SELECT (completed_at AT TIME ZONE %(tz)s)::date AS day, count(*) AS n FROM tasks
        WHERE status = 'done' AND (completed_at AT TIME ZONE %(tz)s)::date BETWEEN %(start)s AND %(end)s
        GROUP BY 1""",
    "todos": """
        SELECT (completed_at AT TIME ZONE %(tz)s)::date AS day, count(*) AS n FROM todo_completions
        WHERE (completed_at AT TIME ZONE %(tz)s)::date BETWEEN %(start)s AND %(end)s
        GROUP BY 1""",
    "habits": """
        SELECT logged_date AS day, count(*) AS n FROM habit_logs
        WHERE logged_date BETWEEN %(start)s AND %(end)s GROUP BY 1""",
    "chores": """
        SELECT done_date AS day, count(*) AS n FROM chore_logs
        WHERE done_date BETWEEN %(start)s AND %(end)s GROUP BY 1""",
    # A day with any lifting counts once.
    "gym_days": """
        SELECT DISTINCT workout_date AS day, 1 AS n FROM lift_sets
        WHERE workout_date BETWEEN %(start)s AND %(end)s""",
    "activity_minutes": """
        SELECT activity_date AS day, coalesce(sum(duration_seconds), 0) / 60.0 AS n FROM activities
        WHERE activity_date BETWEEN %(start)s AND %(end)s GROUP BY 1""",
}


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def weekly(conn, start: date, weeks: int) -> list[dict]:
    """Totals per week for `weeks` weeks beginning at the Monday `start`."""
    totals = {start + timedelta(weeks=i): dict.fromkeys(_DAILY, 0) for i in range(weeks)}
    params = {"tz": APP_TIMEZONE, "start": start, "end": start + timedelta(weeks=weeks, days=-1)}
    for name, query in _DAILY.items():
        for row in conn.execute(query, params).fetchall():
            totals[monday_of(row["day"])][name] += float(row["n"])
    return [{"start": week.isoformat(), **{k: round(v) for k, v in values.items()}} for week, values in totals.items()]


def trends(weeks: int) -> dict:
    today = planner_db._today()
    this_week = monday_of(today)
    start = this_week - timedelta(weeks=weeks - 1)
    grid_start = this_week - timedelta(weeks=HABIT_GRID_WEEKS - 1)
    with planner_db._connect() as conn:
        per_week = weekly(conn, start, weeks)
        habits = conn.execute("SELECT id, name FROM habits ORDER BY lower(name)").fetchall()
        logs = conn.execute(
            "SELECT habit_id, logged_date FROM habit_logs WHERE logged_date >= %s ORDER BY logged_date",
            (grid_start,),
        ).fetchall()
        first = conn.execute(
            "SELECT (min(completed_at) AT TIME ZONE %s)::date AS day FROM todo_completions", (APP_TIMEZONE,)
        ).fetchone()["day"]
    dates: dict[int, list[str]] = {}
    for row in logs:
        dates.setdefault(row["habit_id"], []).append(row["logged_date"].isoformat())
    return {
        "start": start.isoformat(),
        "today": today.isoformat(),
        "weeks": per_week,
        "habit_grid": {"start": grid_start.isoformat(), "weeks": HABIT_GRID_WEEKS},
        "habits": [{"id": h["id"], "name": h["name"], "dates": dates.get(h["id"], [])} for h in habits],
        # Todo history only exists from when it started being recorded.
        "todo_history_since": None if first is None else first.isoformat(),
    }


@router.get("/trends")
def get_trends(weeks: int = Query(default=13, ge=1, le=104)):
    return trends(weeks)
