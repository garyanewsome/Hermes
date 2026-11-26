"""Activities logged one at a time: walks, rides, a deep squat sit. Gym
lifting lives in workouts.py / workout_import.py.

An activity name is typed once and then offered again; capitals and spacing
fold into the spelling already stored."""

from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import planner_db

router = APIRouter()

# Offered before anything is logged. The first is the form's default.
SUGGESTED = ("Work walk", "Walk", "Bike", "Elliptical")


class ActivityRequest(BaseModel):
    activity: str = Field(max_length=80)
    date: date
    minutes: float = Field(gt=0, le=1440, allow_inf_nan=False)
    distance: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    distance_unit: Literal["mi", "km"] = "mi"


def _key(name: str) -> str:
    return " ".join(name.split()).casefold()


def _names(conn) -> dict[str, str]:
    """Every known activity, key to spelling. The newest spelling wins."""
    names = {_key(name): name for name in SUGGESTED}
    for row in conn.execute("SELECT activity FROM activities ORDER BY id").fetchall():
        names[_key(row["activity"])] = row["activity"]
    return names


def _clean(conn, request: ActivityRequest) -> dict:
    name = " ".join(request.activity.split())
    if not name:
        raise ValueError("Name the activity")
    if request.date > planner_db._today() + timedelta(days=1):
        raise ValueError("That date is in the future")
    seconds = round(request.minutes * 60)
    if seconds < 1:
        raise ValueError("Time must be at least a second")
    distance = None if request.distance is None else round(request.distance, 2)
    if distance == 0:
        raise ValueError("Distance is too small; leave it blank instead")
    return {
        "activity": _names(conn).get(_key(name), name),
        "date": request.date,
        "distance": distance,
        "unit": None if distance is None else request.distance_unit,
        "seconds": seconds,
    }


def add(request: ActivityRequest) -> int:
    with planner_db._connect() as conn:
        return conn.execute(
            """
            INSERT INTO activities (activity, activity_date, distance, distance_unit, duration_seconds)
            VALUES (%(activity)s, %(date)s, %(distance)s, %(unit)s, %(seconds)s) RETURNING id
            """,
            _clean(conn, request),
        ).fetchone()["id"]


def update(activity_id: int, request: ActivityRequest) -> bool:
    with planner_db._connect() as conn:
        # paste_id is cleared: once edited by hand, re-pasting that day must
        # not overwrite the correction.
        return conn.execute(
            """
            UPDATE activities SET activity = %(activity)s, activity_date = %(date)s, distance = %(distance)s,
                   distance_unit = %(unit)s, duration_seconds = %(seconds)s, paste_id = NULL
            WHERE id = %(id)s
            """,
            {**_clean(conn, request), "id": activity_id},
        ).rowcount > 0


def delete(activity_id: int) -> bool:
    with planner_db._connect() as conn:
        return conn.execute("DELETE FROM activities WHERE id = %s", (activity_id,)).rowcount > 0


def entries(conn, start: date | None = None, end: date | None = None) -> list[dict]:
    """Oldest first; activity_date is a date object."""
    return conn.execute(
        """
        SELECT id, activity_date, activity, distance::float8 AS distance, distance_unit, duration_seconds
        FROM activities
        WHERE (%(start)s::date IS NULL OR activity_date >= %(start)s)
          AND (%(end)s::date IS NULL OR activity_date <= %(end)s)
        ORDER BY activity_date, id
        """,
        {"start": start, "end": end},
    ).fetchall()


@router.get("/activities")
def get_activities(start: date | None = None, end: date | None = None):
    with planner_db._connect() as conn:
        rows = entries(conn, start, end)
        names = _names(conn)
    suggested = [names[_key(name)] for name in SUGGESTED]
    own = sorted((n for k, n in names.items() if k not in {_key(s) for s in SUGGESTED}), key=str.casefold)
    return {
        "types": suggested + own,
        "entries": [
            {**{k: v for k, v in row.items() if k != "activity_date"}, "date": row["activity_date"].isoformat()}
            for row in reversed(rows)
        ],
    }


@router.post("/activities")
def post_activity(request: ActivityRequest):
    try:
        return {"id": add(request)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/activities/{activity_id}")
def put_activity(activity_id: int, request: ActivityRequest):
    try:
        found = update(activity_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not found:
        raise HTTPException(status_code=404, detail="That entry no longer exists")
    return {"status": "ok"}


@router.delete("/activities/{activity_id}")
def remove_activity(activity_id: int):
    if not delete(activity_id):
        raise HTTPException(status_code=404, detail="That entry no longer exists")
    return {"status": "ok"}
