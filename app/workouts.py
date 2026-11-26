"""Workout log storage and API. Parsing lives in workout_parser.py.

Saving replaces a day's pasted entries by kind: lift lines replace that day's
lifts, walk lines replace its pasted walks (never ones added through
Add Activity), and a kind the paste doesn't mention is left
alone. So re-sending a day never duplicates, and adding the walk note after
the lifting log doesn't wipe the lifts. Every saved paste is kept verbatim in
workout_pastes, including ones whose entries were later replaced.

Pasted lifts are refused for a date that already has lifts from the
spreadsheet (app/workout_import.py), which would count them twice."""

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import activities, planner_db, workout_parser

router = APIRouter()


class WorkoutPasteRequest(BaseModel):
    text: str


def _existing_counts(conn, day: str) -> dict:
    lifts = conn.execute(
        "SELECT count(*) AS n FROM lift_sets WHERE workout_date = %s AND workout_id IS NULL", (day,)
    ).fetchone()["n"]
    walks = conn.execute(
        "SELECT count(*) AS n FROM activities WHERE activity_date = %s AND paste_id IS NOT NULL", (day,)
    ).fetchone()["n"]
    return {"lift_sets": lifts, "walks": walks}


def _sheet_conflicts(conn, result: dict) -> list[dict]:
    errors = []
    for day in result["days"]:
        if day["lifts"] and conn.execute(
            "SELECT 1 FROM lift_sets WHERE workout_date = %s AND workout_id IS NOT NULL LIMIT 1", (day["date"],)
        ).fetchone():
            errors.append({"line": 0, "message": f"{day['date']} already has lifts from the spreadsheet; "
                                                 "change them there, or paste only the walks"})
    return errors


def preview(text: str) -> dict:
    """Parses without saving, and says what saving would replace."""
    result = workout_parser.parse(text, planner_db._today())
    with planner_db._connect() as conn:
        result["errors"] += _sheet_conflicts(conn, result)
        for day in result["days"]:
            existing = _existing_counts(conn, day["date"])
            day["replaces"] = {
                "lift_sets": existing["lift_sets"] if day["lifts"] else 0,
                "walks": existing["walks"] if day["walks"] else 0,
            }
    return result


def save(text: str) -> dict:
    """All or nothing: any parse error means nothing is written."""
    result = workout_parser.parse(text, planner_db._today())
    if result["errors"]:
        return {**result, "saved": False}
    with planner_db._connect() as conn:
        # One save at a time, so a double submit can't insert a day twice.
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('workout_save'))")
        conflicts = _sheet_conflicts(conn, result)
        if conflicts:
            return {**result, "errors": conflicts, "saved": False}
        paste_id = conn.execute(
            "INSERT INTO workout_pastes (raw_text) VALUES (%s) RETURNING id", (text,)
        ).fetchone()["id"]
        for day in result["days"]:
            if day["lifts"]:
                conn.execute(
                    "DELETE FROM lift_sets WHERE workout_date = %s AND workout_id IS NULL", (day["date"],)
                )
            if day["walks"]:
                conn.execute(
                    "DELETE FROM activities WHERE activity_date = %s AND paste_id IS NOT NULL", (day["date"],)
                )
            position = 0
            for lift in day["lifts"]:
                for reps in lift["reps"]:
                    position += 1
                    conn.execute(
                        """
                        INSERT INTO lift_sets
                            (paste_id, workout_date, position, exercise, bodyweight, weight, weight_unit, reps)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (paste_id, day["date"], position, lift["exercise"], lift["bodyweight"],
                         lift["weight"], lift["unit"], reps),
                    )
            for walk in day["walks"]:
                conn.execute(
                    """
                    INSERT INTO activities
                        (paste_id, activity_date, activity, distance, distance_unit, duration_seconds)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (paste_id, day["date"], walk["activity"], walk["distance"],
                     walk["distance_unit"], walk["duration_seconds"]),
                )
    return {**result, "saved": True}


def history(start: date | None = None, end: date | None = None) -> list[dict]:
    """Saved days, newest first, one entry per set and per activity."""
    def where(column):
        return (f"WHERE (%(start)s::date IS NULL OR {column} >= %(start)s) "
                f"AND (%(end)s::date IS NULL OR {column} <= %(end)s)")

    params = {"start": start, "end": end}
    with planner_db._connect() as conn:
        sets = conn.execute(
            f"""
            SELECT s.workout_date, w.session_name AS session, p.name AS program, s.exercise, s.bodyweight,
                   s.weight::float8 AS weight, s.weight_unit AS unit, s.reps, s.set_type, s.target,
                   s.per_side::float8 AS per_side, s.base_weight::float8 AS base_weight, s.base_kind,
                   s.myo, s.superset, s.note,
                   s.myo_raw, s.full_reps, s.rest_pause_reps, s.partial_reps
            FROM lift_sets s
            LEFT JOIN workouts w ON w.id = s.workout_id
            LEFT JOIN workout_programs p ON p.id = w.program_id
            {where("s.workout_date")} ORDER BY s.workout_date, w.session_name, s.position
            """,
            params,
        ).fetchall()
        logged = [
            {**row, "workout_date": row.pop("activity_date")} for row in activities.entries(conn, start, end)
        ]
    days: dict[date, dict] = {}
    for key, rows in (("sets", sets), ("activities", logged)):
        for row in rows:
            entry = dict(row)
            day = entry.pop("workout_date")
            days.setdefault(day, {"date": day.isoformat(), "sets": [], "activities": []})[key].append(entry)
    for day in days.values():
        # Full load, in code. Pounds and kilograms are totalled separately.
        volume: dict[str, float] = {}
        for item in day["sets"]:
            if item["weight"] is not None:
                volume[item["unit"]] = round(volume.get(item["unit"], 0) + item["weight"] * item["reps"], 2)
        day["volume"] = volume
    return [days[day] for day in sorted(days, reverse=True)]


@router.post("/workouts/preview")
def post_workout_preview(request: WorkoutPasteRequest):
    return preview(request.text)


@router.post("/workouts")
def post_workout(request: WorkoutPasteRequest):
    result = save(request.text)
    if not result["saved"]:
        raise HTTPException(status_code=422, detail=result["errors"])
    return result


@router.get("/workouts")
def get_workouts(start: date | None = None, end: date | None = None):
    return {"days": history(start, end)}
