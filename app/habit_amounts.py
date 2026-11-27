"""Habits that count something: minutes practiced, pages read, body weight.

A habit with a unit keeps one number per day. With `add_up` a second entry that
day adds to it (practice time); without, it replaces it (weight). Code does
every total."""

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import planner_db

router = APIRouter()

CHART_WEEKS = 12
LATEST_DAYS = 365
MAX_AMOUNT = 1_000_000


class SettingsRequest(BaseModel):
    unit: str | None = Field(default=None, max_length=20)
    add_up: bool = True
    hide_streak: bool = False


class NewHabitRequest(SettingsRequest):
    name: str = Field(max_length=100)


class AmountRequest(BaseModel):
    date: date
    amount: float = Field(gt=0, le=MAX_AMOUNT, allow_inf_nan=False)
    # "add" follows the habit's rule; "set" always replaces the day's number.
    mode: str = Field(default="add", pattern="^(add|set)$")


def _unit(unit: str | None) -> str | None:
    return " ".join((unit or "").split()) or None


def create(request: NewHabitRequest) -> int:
    name = " ".join(request.name.split())
    if not name:
        raise ValueError("Name the habit")
    with planner_db._connect() as conn:
        row = conn.execute(
            """
            INSERT INTO habits (name, unit, add_up, hide_streak) VALUES (%s, %s, %s, %s)
            ON CONFLICT (name) DO NOTHING RETURNING id
            """,
            (name, _unit(request.unit), request.add_up, request.hide_streak),
        ).fetchone()
    if row is None:
        raise ValueError(f"There's already a habit called {name}")
    return row["id"]


def update_settings(habit_id: int, request: SettingsRequest) -> bool:
    """Changing or clearing the unit keeps the numbers already logged."""
    with planner_db._connect() as conn:
        return conn.execute(
            "UPDATE habits SET unit = %s, add_up = %s, hide_streak = %s WHERE id = %s",
            (_unit(request.unit), request.add_up, request.hide_streak, habit_id),
        ).rowcount > 0


def log_amount(habit_id: int, on: date, amount: float, mode: str = "add") -> float | None:
    """Logs the day with a number and returns what the day now holds, or None
    if the habit doesn't exist."""
    if on > planner_db._today():
        raise ValueError("That date is in the future")
    value = Decimal(str(amount)).quantize(Decimal("0.01"), ROUND_HALF_UP)
    if value <= 0 or value > MAX_AMOUNT:
        raise ValueError("Enter a number above zero")
    with planner_db._connect() as conn:
        habit = conn.execute("SELECT unit, add_up FROM habits WHERE id = %s", (habit_id,)).fetchone()
        if habit is None:
            return None
        if not habit["unit"]:
            raise ValueError("This habit doesn't track a number")
        adding = mode == "add" and habit["add_up"]
        total = "coalesce(habit_logs.amount, 0) + EXCLUDED.amount" if adding else "EXCLUDED.amount"
        stored = conn.execute(
            f"""
            INSERT INTO habit_logs (habit_id, logged_date, amount) VALUES (%s, %s, %s)
            ON CONFLICT (habit_id, logged_date) DO UPDATE SET amount = {total}
            RETURNING amount::float8 AS amount
            """,
            (habit_id, on, value),
        ).fetchone()["amount"]
    return stored


def summary(amounts: dict[date, float], today: date) -> dict:
    """The numbers shown beside a habit. Weeks run Monday to Sunday."""
    monday = today - timedelta(days=today.weekday())
    last_monday = monday - timedelta(days=7)

    def between(start: date, end: date) -> float:
        return round(sum(n for day, n in amounts.items() if start <= day <= end), 2)

    latest = max(amounts) if amounts else None
    return {
        "today": amounts.get(today),
        "this_week": between(monday, today),
        "last_week": between(last_monday, monday - timedelta(days=1)),
        "latest": None if latest is None else {"date": latest.isoformat(), "amount": amounts[latest]},
    }


def chart(amounts: dict[date, float], add_up: bool, today: date) -> dict:
    """Weekly totals for habits that add up, otherwise each logged value."""
    if not add_up:
        start = today - timedelta(days=LATEST_DAYS - 1)
        points = [{"date": d.isoformat(), "value": amounts[d]} for d in sorted(amounts) if d >= start]
        return {"kind": "values", "points": points}
    monday = today - timedelta(days=today.weekday())
    first = monday - timedelta(weeks=CHART_WEEKS - 1)
    if amounts:
        # Starts at the first week with a number, so new habits aren't a row of zeros.
        earliest = min(amounts)
        first = max(first, earliest - timedelta(days=earliest.weekday()))
    weeks = []
    while amounts and first <= monday:
        total = sum(n for d, n in amounts.items() if first <= d < first + timedelta(days=7))
        weeks.append({"date": first.isoformat(), "value": round(total, 2)})
        first += timedelta(days=7)
    return {"kind": "weeks", "points": weeks}


def _found(result):
    if result is None or result is False:
        raise HTTPException(status_code=404, detail="That habit no longer exists")
    return result


def _refuse(action):
    try:
        return action()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/habits")
def post_habit(request: NewHabitRequest):
    return {"id": _refuse(lambda: create(request))}


@router.patch("/habits/{habit_id}")
def patch_habit(habit_id: int, request: SettingsRequest):
    _found(update_settings(habit_id, request))
    return {"status": "ok"}


@router.put("/habits/{habit_id}/amount")
def put_amount(habit_id: int, request: AmountRequest):
    amount = _found(_refuse(lambda: log_amount(habit_id, request.date, request.amount, request.mode)))
    return {"amount": amount}
