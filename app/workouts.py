"""Workout log storage and API. Parsing lives in workout_parser.py.

Saving replaces a day's entries by kind: lift lines replace that day's lifts,
walk lines replace its walks, and a kind the paste doesn't mention is left
alone. So re-sending a day never duplicates, and adding the walk note after
the lifting log doesn't wipe the lifts. Every saved paste is kept verbatim in
workout_pastes, including ones whose entries were later replaced."""

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import planner_db, workout_parser

router = APIRouter()


class WorkoutPasteRequest(BaseModel):
    text: str


def _existing_counts(conn, day: str) -> dict:
    lifts = conn.execute("SELECT count(*) AS n FROM lift_sets WHERE workout_date = %s", (day,)).fetchone()["n"]
    walks = conn.execute("SELECT count(*) AS n FROM walks WHERE workout_date = %s", (day,)).fetchone()["n"]
    return {"lift_sets": lifts, "walks": walks}


def preview(text: str) -> dict:
    """Parses without saving, and says what saving would replace."""
    result = workout_parser.parse(text, planner_db._today())
    with planner_db._connect() as conn:
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
        paste_id = conn.execute(
            "INSERT INTO workout_pastes (raw_text) VALUES (%s) RETURNING id", (text,)
        ).fetchone()["id"]
        for day in result["days"]:
            if day["lifts"]:
                conn.execute("DELETE FROM lift_sets WHERE workout_date = %s", (day["date"],))
            if day["walks"]:
                conn.execute("DELETE FROM walks WHERE workout_date = %s", (day["date"],))
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
            for position, walk in enumerate(day["walks"], start=1):
                conn.execute(
                    """
                    INSERT INTO walks
                        (paste_id, workout_date, position, activity, distance, distance_unit, duration_seconds)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (paste_id, day["date"], position, walk["activity"], walk["distance"],
                     walk["distance_unit"], walk["duration_seconds"]),
                )
    return {**result, "saved": True}


def history(start: date | None = None, end: date | None = None) -> list[dict]:
    """Saved days, newest first, one entry per set and per walk."""
    where = "WHERE (%(start)s::date IS NULL OR workout_date >= %(start)s) AND (%(end)s::date IS NULL OR workout_date <= %(end)s)"
    params = {"start": start, "end": end}
    with planner_db._connect() as conn:
        sets = conn.execute(
            f"""
            SELECT workout_date, exercise, bodyweight, weight::float8 AS weight, weight_unit AS unit, reps
            FROM lift_sets {where} ORDER BY workout_date, position
            """,
            params,
        ).fetchall()
        walks = conn.execute(
            f"""
            SELECT workout_date, activity, distance::float8 AS distance, distance_unit, duration_seconds
            FROM walks {where} ORDER BY workout_date, position
            """,
            params,
        ).fetchall()
    days: dict[date, dict] = {}
    for key, rows in (("sets", sets), ("walks", walks)):
        for row in rows:
            entry = dict(row)
            day = entry.pop("workout_date")
            days.setdefault(day, {"date": day.isoformat(), "sets": [], "walks": []})[key].append(entry)
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
