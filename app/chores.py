"""Chores: jobs that are never finished, only last done. Kept apart from
todos on purpose — logging one leaves it on the list, and there are no due
dates, only an optional "about every N days"."""

import datetime
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import planner_db

router = APIRouter()


class ChoreRequest(BaseModel):
    name: str = Field(max_length=120)
    every_days: int | None = Field(default=None, ge=1, le=3650)


class ChoreLogRequest(BaseModel):
    # Omitted means today, by the app's clock rather than the device's.
    date: datetime.date | None = None


def list_chores() -> list[dict]:
    """Never done first, then longest ago."""
    today = planner_db._today()
    with planner_db._connect() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.every_days, max(l.done_date) AS last_done, count(l.done_date) AS times
            FROM chores c LEFT JOIN chore_logs l ON l.chore_id = c.id
            GROUP BY c.id
            ORDER BY max(l.done_date) NULLS FIRST, lower(c.name)
            """
        ).fetchall()
    chores = []
    for row in rows:
        last = row["last_done"]
        days_ago = None if last is None else (today - last).days
        every = row["every_days"]
        chores.append(
            {
                **row,
                "last_done": None if last is None else last.isoformat(),
                "days_ago": days_ago,
                # With an interval, never done counts as due.
                "due": every is not None and (days_ago is None or days_ago >= every),
            }
        )
    return chores


def _clean_name(conn, name: str, chore_id: int | None = None) -> str:
    name = " ".join(name.split())
    if not name:
        raise ValueError("Name the chore")
    # One at a time, so two saves can't both pass the duplicate check.
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('chore_name'))")
    rows = conn.execute("SELECT id, name FROM chores").fetchall()
    if any(row["id"] != chore_id and row["name"].casefold() == name.casefold() for row in rows):
        raise ValueError(f"There's already a chore called {name}")
    return name


def add_chore(request: ChoreRequest) -> int:
    with planner_db._connect() as conn:
        name = _clean_name(conn, request.name)
        return conn.execute(
            "INSERT INTO chores (name, every_days) VALUES (%s, %s) RETURNING id", (name, request.every_days)
        ).fetchone()["id"]


def update_chore(chore_id: int, request: ChoreRequest) -> bool:
    with planner_db._connect() as conn:
        name = _clean_name(conn, request.name, chore_id)
        return conn.execute(
            "UPDATE chores SET name = %s, every_days = %s WHERE id = %s", (name, request.every_days, chore_id)
        ).rowcount > 0


def delete_chore(chore_id: int) -> bool:
    """Takes the chore's history with it."""
    with planner_db._connect() as conn:
        return conn.execute("DELETE FROM chores WHERE id = %s", (chore_id,)).rowcount > 0


def chore_dates(chore_id: int) -> list[str] | None:
    """Newest first; None if there's no such chore."""
    with planner_db._connect() as conn:
        if conn.execute("SELECT 1 FROM chores WHERE id = %s", (chore_id,)).fetchone() is None:
            return None
        rows = conn.execute(
            "SELECT done_date FROM chore_logs WHERE chore_id = %s ORDER BY done_date DESC", (chore_id,)
        ).fetchall()
    return [row["done_date"].isoformat() for row in rows]


def log_chore(chore_id: int, on: date | None = None) -> bool:
    """One entry per day, so a double tap doesn't count twice."""
    today = planner_db._today()
    on = on or today
    if on > today:
        raise ValueError("That date is in the future")
    with planner_db._connect() as conn:
        if conn.execute("SELECT 1 FROM chores WHERE id = %s", (chore_id,)).fetchone() is None:
            return False
        conn.execute(
            "INSERT INTO chore_logs (chore_id, done_date) VALUES (%s, %s) ON CONFLICT DO NOTHING", (chore_id, on)
        )
    return True


def unlog_chore(chore_id: int, on: date) -> bool:
    with planner_db._connect() as conn:
        return conn.execute(
            "DELETE FROM chore_logs WHERE chore_id = %s AND done_date = %s", (chore_id, on)
        ).rowcount > 0


def _refuse(action):
    try:
        return action()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _found(result):
    if result is False or result is None:
        raise HTTPException(status_code=404, detail="That no longer exists")
    return result


# Every change returns the fresh list, so the page needs one round trip.
@router.get("/chores")
def get_chores():
    return {"chores": list_chores(), "today": planner_db._today().isoformat()}


@router.post("/chores")
def post_chore(request: ChoreRequest):
    _refuse(lambda: add_chore(request))
    return get_chores()


@router.put("/chores/{chore_id}")
def put_chore(chore_id: int, request: ChoreRequest):
    _found(_refuse(lambda: update_chore(chore_id, request)))
    return get_chores()


@router.delete("/chores/{chore_id}")
def remove_chore(chore_id: int):
    _found(delete_chore(chore_id))
    return get_chores()


@router.get("/chores/{chore_id}/history")
def get_chore_history(chore_id: int):
    dates = chore_dates(chore_id)
    if dates is None:
        raise HTTPException(status_code=404, detail="That no longer exists")
    return {"dates": dates}


@router.post("/chores/{chore_id}/log")
def post_chore_log(chore_id: int, request: ChoreLogRequest):
    _found(_refuse(lambda: log_chore(chore_id, request.date)))
    return get_chores()


@router.delete("/chores/{chore_id}/log/{on}")
def remove_chore_log(chore_id: int, on: date):
    _found(unlog_chore(chore_id, on))
    return get_chores()
