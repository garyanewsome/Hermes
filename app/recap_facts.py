"""What happened in a week. Every count, total and comparison in the recap is
worked out here, in code."""

from datetime import date, timedelta

from app import chores, planner_db, trends, workout_charts, workout_import
from app.config import APP_TIMEZONE


def _activities(rows: list[dict]) -> list[dict]:
    found: dict[str, dict] = {}
    for row in rows:
        entry = found.setdefault(
            workout_import.exercise_key(row["activity"]),
            {"name": row["activity"], "count": 0, "seconds": 0, "miles": 0.0},
        )
        entry["count"] += 1
        entry["seconds"] += row["duration_seconds"] or 0
        if row["distance"] is not None:
            km = row["distance_unit"] == "km"
            entry["miles"] += row["distance"] / 1.609344 if km else row["distance"]
    return [
        {"name": e["name"], "count": e["count"], "minutes": round(e["seconds"] / 60), "miles": round(e["miles"], 2)}
        for e in sorted(found.values(), key=lambda e: e["name"].casefold())
    ]


def _new_bests(conn, start: date, end: date) -> list[dict]:
    """Exercises whose best set this week beats everything before it. A first
    ever session isn't a record."""
    aliases = {
        row["alias_key"]: row["canonical"]
        for row in conn.execute("SELECT alias_key, canonical FROM exercise_aliases").fetchall()
    }
    rows = conn.execute(
        """
        SELECT exercise, workout_date, weight::float8 AS weight, weight_unit AS unit,
               per_side::float8 AS per_side, reps
        FROM lift_sets WHERE workout_date <= %s ORDER BY workout_date, position
        """,
        (end,),
    ).fetchall()
    grouped: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        recorded = item.pop("exercise")
        name = aliases.get(workout_import.exercise_key(recorded), recorded)
        group = grouped.setdefault(workout_import.exercise_key(name), {"name": name, "before": [], "week": []})
        group["week" if item.pop("workout_date") >= start else "before"].append(item)
    bests = []
    for group in grouped.values():
        if not group["before"] or not group["week"]:
            continue
        old = workout_import.best_set(group["before"])
        new = workout_import.best_set(group["week"])
        # Ties go to the first listed, so only a strictly better set wins.
        if workout_import.best_set([old, new]) is new:
            bests.append({"exercise": group["name"], "new": new, "old": old})
    return sorted(bests, key=lambda b: b["exercise"].casefold())


def week_facts(week_start: date) -> dict:
    """`week_start` is a Monday. "Slipping" is as things stand today."""
    today = planner_db._today()
    end = week_start + timedelta(days=6)
    previous = week_start - timedelta(weeks=1)
    next_start, next_end = end + timedelta(days=1), end + timedelta(days=7)
    with planner_db._connect() as conn:
        def rows(query, **params):
            return [dict(r) for r in conn.execute(query, {"tz": APP_TIMEZONE, **params}).fetchall()]

        before, this = trends.weekly(conn, previous, 2)
        tasks_done = rows(
            """SELECT title FROM tasks WHERE status = 'done'
               AND (completed_at AT TIME ZONE %(tz)s)::date BETWEEN %(a)s AND %(b)s ORDER BY completed_at""",
            a=week_start, b=end,
        )
        todos_done = rows(
            """SELECT item_text AS text, list_name AS list FROM todo_completions
               WHERE (completed_at AT TIME ZONE %(tz)s)::date BETWEEN %(a)s AND %(b)s ORDER BY completed_at""",
            a=week_start, b=end,
        )
        habits = rows(
            """SELECT h.name,
                 count(l.id) FILTER (WHERE l.logged_date BETWEEN %(a)s AND %(b)s) AS days,
                 count(l.id) FILTER (WHERE l.logged_date BETWEEN %(p)s AND %(a)s::date - 1) AS previous
               FROM habits h LEFT JOIN habit_logs l ON l.habit_id = h.id
               GROUP BY h.id, h.name ORDER BY lower(h.name)""",
            a=week_start, b=end, p=previous,
        )
        gym = rows(
            """SELECT s.workout_date AS date, coalesce(string_agg(DISTINCT w.session_name, ', '), '') AS session,
                      count(*) AS sets,
                      round(coalesce(sum(s.weight * s.reps * CASE WHEN s.weight_unit = 'kg' THEN %(kg)s ELSE 1 END), 0))::int
                          AS volume
               FROM lift_sets s LEFT JOIN workouts w ON w.id = s.workout_id
               WHERE s.workout_date BETWEEN %(a)s AND %(b)s GROUP BY s.workout_date ORDER BY s.workout_date""",
            a=week_start, b=end, kg=workout_import.LB_PER_KG,
        )
        previous_volume = rows(
            """SELECT round(coalesce(sum(weight * reps * CASE WHEN weight_unit = 'kg' THEN %(kg)s ELSE 1 END), 0))::int
                      AS volume
               FROM lift_sets WHERE workout_date BETWEEN %(p)s AND %(a)s::date - 1""",
            a=week_start, p=previous, kg=workout_import.LB_PER_KG,
        )[0]["volume"]
        logged = rows(
            """SELECT activity, distance::float8 AS distance, distance_unit, duration_seconds FROM activities
               WHERE activity_date BETWEEN %(a)s AND %(b)s ORDER BY activity_date, id""",
            a=week_start, b=end,
        )
        chores_done = rows(
            """SELECT c.name, l.done_date AS date FROM chore_logs l JOIN chores c ON c.id = l.chore_id
               WHERE l.done_date BETWEEN %(a)s AND %(b)s ORDER BY l.done_date, lower(c.name)""",
            a=week_start, b=end,
        )
        overdue_todos = rows(
            """SELECT i.text, l.name AS list, i.due_date AS date FROM todo_items i
               JOIN todo_lists l ON l.id = i.list_id
               WHERE NOT i.done AND i.due_date < %(today)s ORDER BY i.due_date""",
            today=today,
        )
        overdue_tasks = rows(
            "SELECT title, due_date AS date FROM tasks WHERE status = 'open' AND due_date < %(today)s ORDER BY due_date",
            today=today,
        )
        upcoming = rows(
            """SELECT text AS title, due_date AS date FROM todo_items
               WHERE NOT done AND due_date BETWEEN %(a)s AND %(b)s
               UNION ALL
               SELECT title, due_date FROM tasks WHERE status = 'open' AND due_date BETWEEN %(a)s AND %(b)s
               ORDER BY date, title""",
            a=next_start, b=next_end,
        )
        bests = _new_bests(conn, week_start, end)

    for group in (gym, chores_done, overdue_todos, overdue_tasks, upcoming):
        for row in group:
            row["date"] = row["date"].isoformat()
    return {
        "week_start": week_start.isoformat(),
        "week_end": end.isoformat(),
        "as_of": today.isoformat(),
        "complete": today > end,
        "tasks_done": [t["title"] for t in tasks_done],
        "todos_done": todos_done,
        "habits": habits,
        "gym": gym,
        "volume": sum(d["volume"] for d in gym),
        "previous_volume": previous_volume,
        "previous_gym_days": before["gym_days"],
        "new_bests": bests,
        "activities": _activities(logged),
        "chores_done": chores_done,
        "slipping": {
            "todos": overdue_todos,
            "tasks": overdue_tasks,
            "chores": [c["name"] for c in chores.list_chores() if c["due"]],
            "habits": [h["name"] for h in habits if h["days"] == 0 and h["previous"] > 0],
        },
        "upcoming": upcoming,
    }
