"""The daily body and food numbers on the Fitness page: weigh-in, calories
burned and eaten, and macros. One row per day, filled in a piece at a time.
Code does every difference and average. Weeks run Monday to Sunday."""

import datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app import planner_db

router = APIRouter()

FIELDS = ("weight", "burned_total", "burned_active", "calories_in", "protein_g", "carbs_g", "fat_g")
_PLACES = {"weight": "0.01", "protein_g": "0.1", "carbs_g": "0.1", "fat_g": "0.1"}


def _number(low: float, high: float):
    return Field(default=None, ge=low, le=high, allow_inf_nan=False)


class DayRequest(BaseModel):
    """Only the fields sent are changed; null clears one."""

    model_config = ConfigDict(extra="forbid")

    weight: float | None = _number(40, 1000)  # pounds
    burned_total: float | None = _number(0, 20000)
    burned_active: float | None = _number(0, 20000)
    calories_in: float | None = _number(0, 20000)
    protein_g: float | None = _number(0, 2000)
    carbs_g: float | None = _number(0, 2000)
    fat_g: float | None = _number(0, 2000)


def _public(row: dict) -> dict:
    day = {name: None if row[name] is None else float(row[name]) for name in FIELDS}
    both = day["calories_in"] is not None and day["burned_total"] is not None
    # Eaten minus burned: negative is a deficit.
    day["balance"] = round(day["calories_in"] - day["burned_total"]) if both else None
    return {"date": row["log_date"].isoformat(), **day}


def save(on: datetime.date, request: DayRequest) -> dict | None:
    """Changes the fields sent and returns the day, or None if nothing is
    left on it."""
    if on > planner_db._today():
        raise ValueError("That date is in the future")
    sent = {
        name: None if value is None else Decimal(str(value)).quantize(Decimal(_PLACES.get(name, "1")), ROUND_HALF_UP)
        for name, value in request.model_dump(exclude_unset=True).items()
    }
    if not sent:
        raise ValueError("Nothing to save")
    with planner_db._connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('daily_log'))")
        row = conn.execute("SELECT * FROM daily_log WHERE log_date = %s", (on,)).fetchone()
        merged = {name: sent[name] if name in sent else (row[name] if row else None) for name in FIELDS}
        total, active = merged["burned_total"], merged["burned_active"]
        if total is not None and active is not None and active > total:
            raise ValueError("Active calories can't be more than total calories burned")
        if all(value is None for value in merged.values()):
            conn.execute("DELETE FROM daily_log WHERE log_date = %s", (on,))
            return None
        columns = ", ".join(FIELDS)
        marks = ", ".join(f"%({name})s" for name in FIELDS)
        updates = ", ".join(f"{name} = EXCLUDED.{name}" for name in FIELDS)
        saved = conn.execute(
            f"""
            INSERT INTO daily_log (log_date, {columns}) VALUES (%(log_date)s, {marks})
            ON CONFLICT (log_date) DO UPDATE SET {updates}, updated_at = now()
            RETURNING *
            """,
            {**merged, "log_date": on},
        ).fetchone()
    return _public(saved)


def week_summary(days: list[dict], start: datetime.date) -> dict:
    """Averages over the days that have each number, with how many that was."""
    end = start + datetime.timedelta(days=6)
    inside = [d for d in days if start.isoformat() <= d["date"] <= end.isoformat()]
    averages, counts = {}, {}
    for name in (*FIELDS, "balance"):
        values = [d[name] for d in inside if d[name] is not None]
        places = 1 if name in _PLACES else 0
        averages[name] = round(sum(values) / len(values), places) if values else None
        counts[name] = len(values)
    return {"start": start.isoformat(), "days": len(inside), "average": averages, "counts": counts}


def log(weeks: int) -> dict:
    today = planner_db._today()
    monday = today - datetime.timedelta(days=today.weekday())
    start = monday - datetime.timedelta(weeks=weeks - 1)
    last_monday = monday - datetime.timedelta(weeks=1)
    with planner_db._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_log WHERE log_date >= %s ORDER BY log_date DESC", (min(start, last_monday),)
        ).fetchall()
    days = [_public(row) for row in rows]
    return {
        "today": today.isoformat(),
        "start": start.isoformat(),
        "days": [d for d in days if d["date"] >= start.isoformat()],
        "this_week": week_summary(days, monday),
        "last_week": week_summary(days, last_monday),
    }


@router.get("/daily")
def get_daily(weeks: int = Query(default=13, ge=1, le=520)):
    return log(weeks)


@router.put("/daily/{on}")
def put_daily(on: datetime.date, request: DayRequest):
    try:
        return {"day": save(on, request)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
