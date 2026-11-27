"""The daily body and food numbers on the Fitness page: weigh-in, calories
burned and eaten, and macros. One row per day, filled in a piece at a time.
Code does every difference and average. Weeks run Monday to Sunday."""

import datetime
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app import planner_db

router = APIRouter()

# "weight" is the home weigh-in, "weight_pf" the one at the gym.
WEIGHTS = ("weight", "weight_pf")
CALORIES = ("burned_total", "burned_active", "calories_in", "carbs_g", "fat_g", "protein_g")
NUMBERS = (*WEIGHTS, *CALORIES)
TEXTS = ("weight_note", "weight_pf_note", "calories_as_of", "body_note", "gym_session", "gym_note")
FIELDS = (*NUMBERS, "calories_partial", *TEXTS)
_PLACES = {"weight": "0.01", "weight_pf": "0.01", "carbs_g": "0.1", "fat_g": "0.1", "protein_g": "0.1"}


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
    weight_pf: float | None = _number(40, 1000)
    # True while the day's calories are still "so far": left out of averages.
    calories_partial: bool | None = None
    weight_note: str | None = Field(default=None, max_length=2000)
    weight_pf_note: str | None = Field(default=None, max_length=2000)
    calories_as_of: str | None = Field(default=None, max_length=20)
    body_note: str | None = Field(default=None, max_length=2000)
    gym_session: str | None = Field(default=None, max_length=2000)
    gym_note: str | None = Field(default=None, max_length=2000)


def public(row: dict) -> dict:
    day = {name: None if row[name] is None else float(row[name]) for name in NUMBERS}
    day.update({name: row[name] for name in TEXTS})
    day["calories_partial"] = row["calories_partial"]
    both = day["calories_in"] is not None and day["burned_total"] is not None
    # Eaten minus burned: negative is a deficit.
    day["balance"] = round(day["calories_in"] - day["burned_total"]) if both else None
    return {"date": row["log_date"].isoformat(), **day}


def _value(name: str, value):
    if name in NUMBERS:
        return None if value is None else Decimal(str(value)).quantize(Decimal(_PLACES.get(name, "1")), ROUND_HALF_UP)
    if name == "calories_partial":
        return bool(value)
    return (value or "").strip() or None


def save(on: datetime.date, request: DayRequest, conn=None) -> dict | None:
    """Changes the fields sent and returns the day, or None if nothing is
    left on it."""
    if on > planner_db._today():
        raise ValueError("That date is in the future")
    sent = {name: _value(name, value) for name, value in request.model_dump(exclude_unset=True).items()}
    if not sent:
        raise ValueError("Nothing to save")
    if conn is not None:
        return _save(conn, on, sent)
    with planner_db._connect() as own:
        return _save(own, on, sent)


def _save(conn, on: datetime.date, sent: dict) -> dict | None:
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('daily_log'))")
    row = conn.execute("SELECT * FROM daily_log WHERE log_date = %s", (on,)).fetchone()
    merged = {name: sent[name] if name in sent else (row[name] if row else None) for name in FIELDS}
    merged["calories_partial"] = bool(merged["calories_partial"])
    total, active = merged["burned_total"], merged["burned_active"]
    if total is not None and active is not None and active > total:
        raise ValueError(f"{on:%b %-d}: active calories can't be more than total calories burned")
    if all(merged[name] is None for name in (*NUMBERS, *TEXTS)):
        conn.execute("DELETE FROM daily_log WHERE log_date = %s", (on,))
        return None
    # With no calories left there is nothing to be partial about.
    if all(merged[name] is None for name in CALORIES):
        merged["calories_partial"], merged["calories_as_of"] = False, None
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
    return public(saved)


def summary(days: list[dict], start: datetime.date, end: datetime.date) -> dict:
    """Averages over the days that have each number, with how many that was."""
    inside = [d for d in days if start.isoformat() <= d["date"] <= end.isoformat()]
    averages, counts = {}, {}
    for name in (*NUMBERS, "balance"):
        # Unfinished calorie days would drag the averages down.
        counted = [d for d in inside if not (d["calories_partial"] and name not in WEIGHTS)]
        values = [d[name] for d in counted if d[name] is not None]
        places = 1 if name in _PLACES else 0
        averages[name] = round(sum(values) / len(values), places) if values else None
        counts[name] = len(values)
    return {"start": start.isoformat(), "days": len(inside), "average": averages, "counts": counts}


def week_summary(days: list[dict], start: datetime.date) -> dict:
    return summary(days, start, start + datetime.timedelta(days=6))


def between(conn, start: datetime.date, end: datetime.date) -> list[dict]:
    """Logged days in the range, oldest first."""
    rows = conn.execute(
        "SELECT * FROM daily_log WHERE log_date BETWEEN %s AND %s ORDER BY log_date", (start, end)
    ).fetchall()
    return [public(row) for row in rows]


def log(weeks: int) -> dict:
    today = planner_db._today()
    monday = today - datetime.timedelta(days=today.weekday())
    start = monday - datetime.timedelta(weeks=weeks - 1)
    last_monday = monday - datetime.timedelta(weeks=1)
    with planner_db._connect() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_log WHERE log_date >= %s ORDER BY log_date DESC", (min(start, last_monday),)
        ).fetchall()
    days = [public(row) for row in rows]
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
