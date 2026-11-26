"""Numbers behind the Workouts charts. Code does all the math here; the
frontend only draws. Weeks run Monday to Sunday. Volume is full load in
pounds (any pasted kilogram sets are converted)."""

from datetime import date, timedelta

from fastapi import APIRouter, Query

from app import activities, planner_db, workout_import

router = APIRouter()


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _pounds(weight: float, unit: str | None) -> float:
    return weight * workout_import.LB_PER_KG if unit == "kg" else weight


def personal_bests(conn) -> list[dict]:
    """All time, one per exercise (linked names together), newest first."""
    aliases = {
        row["alias_key"]: row["canonical"]
        for row in conn.execute("SELECT alias_key, canonical FROM exercise_aliases").fetchall()
    }
    rows = conn.execute(
        """
        SELECT exercise, workout_date, weight::float8 AS weight, weight_unit AS unit,
               per_side::float8 AS per_side, reps, bodyweight
        FROM lift_sets ORDER BY workout_date DESC, position
        """
    ).fetchall()
    grouped: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        recorded = item.pop("exercise")
        name = aliases.get(workout_import.exercise_key(recorded), recorded)
        # Newest first, so the first spelling seen is the current one.
        group = grouped.setdefault(workout_import.exercise_key(name), {"exercise": name, "sets": []})
        item["date"] = item.pop("workout_date").isoformat()
        group["sets"].append(item)
    bests = [{"exercise": g["exercise"], **workout_import.best_set(g["sets"])} for g in grouped.values()]
    bests.sort(key=lambda b: b["exercise"].casefold())
    bests.sort(key=lambda b: b["date"], reverse=True)
    return bests


def charts(weeks: int) -> dict:
    """The last `weeks` weeks, ending with the one in progress."""
    today = planner_db._today()
    start = _monday(today) - timedelta(weeks=weeks - 1)
    # Through tomorrow: the log accepts a date one day ahead.
    end = today + timedelta(days=1)
    with planner_db._connect() as conn:
        sets = conn.execute(
            """
            SELECT workout_date, weight::float8 AS weight, weight_unit AS unit, reps
            FROM lift_sets WHERE workout_date BETWEEN %s AND %s
            """,
            (start, end),
        ).fetchall()
        logged = activities.entries(conn, start, end)
        bests = personal_bests(conn)

    week_starts = [start + timedelta(weeks=i) for i in range(weeks)]
    lifting = {w: {"start": w.isoformat(), "volume": 0.0, "sets": 0, "gym_days": set()} for w in week_starts}
    days: dict[date, dict] = {}

    def day(on: date) -> dict:
        return days.setdefault(on, {"date": on.isoformat(), "sets": 0, "volume": 0.0, "activities": 0, "seconds": 0})

    for item in sets:
        on = item["workout_date"]
        volume = 0.0 if item["weight"] is None else _pounds(item["weight"], item["unit"]) * item["reps"]
        day(on)["sets"] += 1
        day(on)["volume"] += volume
        week = lifting.get(_monday(on))
        if week:
            week["sets"] += 1
            week["volume"] += volume
            week["gym_days"].add(on)

    per_activity: dict[str, dict] = {}
    for item in logged:
        on = item["activity_date"]
        day(on)["activities"] += 1
        day(on)["seconds"] += item["duration_seconds"] or 0
        week = _monday(on)
        if week not in lifting:
            continue
        key = workout_import.exercise_key(item["activity"])
        activity = per_activity.setdefault(
            key,
            {"activity": item["activity"],
             "weeks": {w: {"start": w.isoformat(), "count": 0, "seconds": 0, "miles": 0.0} for w in week_starts}},
        )
        activity["activity"] = item["activity"]  # newest spelling
        bucket = activity["weeks"][week]
        bucket["count"] += 1
        bucket["seconds"] += item["duration_seconds"] or 0
        if item["distance"] is not None:
            km = item["distance_unit"] == "km"
            bucket["miles"] += item["distance"] / 1.609344 if km else item["distance"]

    return {
        "start": start.isoformat(),
        "today": today.isoformat(),
        "weeks": [
            {**w, "volume": round(w["volume"]), "gym_days": len(w["gym_days"])} for w in lifting.values()
        ],
        "activities": [
            {"activity": a["activity"],
             "weeks": [{**w, "miles": round(w["miles"], 2)} for w in a["weeks"].values()]}
            for a in sorted(per_activity.values(), key=lambda a: a["activity"].casefold())
        ],
        "days": [{**days[d], "volume": round(days[d]["volume"])} for d in sorted(days)],
        "bests": bests,
    }


@router.get("/workouts/charts")
def get_charts(weeks: int = Query(default=13, ge=1, le=104)):
    return charts(weeks)
