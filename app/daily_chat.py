"""The Fitness page's daily numbers by chat, read-only: weigh-ins, calories,
macros and the deficit. Code does every average and change."""

import re
from datetime import date, timedelta

from app import chore_chat, daily_log, planner_db, workout_chat

_TREND_WEEKS = 6
_LISTED_DAYS = 14
_REPORT = re.compile(
    r"\bi (just )?(weigh(ed)?( in)?( at)?\s+(about )?\d|(ate|had|burned)\b[^.?!]*\d[^.?!]*\b(cal|calories|kcal|protein|carbs))",
    re.IGNORECASE,
)


def report_note(text: str) -> str | None:
    """An instruction for this turn when the user reports a number that
    belongs in the daily log."""
    if "?" in text or not _REPORT.search(text):
        return None
    return (
        "IMPORTANT: nothing in this chat can save to the Fitness log, and this message has NOT been saved. Unless "
        "a tool result gives you an exact reply, begin your reply with exactly: \"I can't save that from chat.\" "
        "Then say it goes in the fitness section of their daily note, which imports when they open Fitness, Daily. "
        "Never say it was noted, added, logged or recorded."
    )


def _n(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _day_name(iso: str) -> str:
    on = date.fromisoformat(iso)
    ago = (planner_db._today() - on).days
    near = " (today)" if ago == 0 else " (yesterday)" if ago == 1 else ""
    return f"{on:%A %B %-d}{near}"


def _balance(value: float) -> str:
    return "even" if value == 0 else f"{_n(abs(value))} {'deficit' if value < 0 else 'surplus'}"


def _day(day: dict) -> str:
    parts = []
    for key, name in (("weight", "home weight"), ("weight_pf", "gym (PF) weight")):
        if day[key] is not None:
            parts.append(f"{name} {_n(day[key])} lb")
    food = [
        f"{name} {_n(day[key])}"
        for key, name in (
            ("calories_in", "eaten"), ("burned_total", "burned"), ("burned_active", "active"),
            ("carbs_g", "carbs g"), ("fat_g", "fat g"), ("protein_g", "protein g"),
        )
        if day[key] is not None
    ]
    if day["balance"] is not None:
        food.append(_balance(day["balance"]))
    if food:
        sofar = ""
        if day["calories_partial"]:
            at = f" as of {day['calories_as_of']}" if day["calories_as_of"] else ""
            sofar = f" (SO FAR{at}, not the day's final numbers)"
        parts.append(", ".join(food) + sofar)
    return f"{_day_name(day['date'])}: {'; '.join(parts) or 'notes only'}."


def _averages(summary: dict) -> str:
    average, counts = summary["average"], summary["counts"]
    parts = [
        f"{name} {_balance(average[key]) if key == 'balance' else _n(average[key])} ({counts[key]} day{'s' if counts[key] != 1 else ''})"
        for key, name in (
            ("weight", "home weight lb"), ("weight_pf", "gym (PF) weight lb"), ("calories_in", "eaten"),
            ("burned_total", "burned"), ("burned_active", "active"), ("balance", "balance"),
            ("carbs_g", "carbs g"), ("fat_g", "fat g"), ("protein_g", "protein g"),
        )
        if average[key] is not None
    ]
    return "; ".join(parts) or "nothing finished to average"


def _change(first: float, last: float) -> str:
    change = round(last - first, 1)
    return "no change" if change == 0 else f"{'down' if change < 0 else 'up'} {_n(abs(change))} lb"


def _range(period: str, today: date) -> tuple[date, date] | None:
    span = workout_chat._range(period, today)
    if span:
        return span
    try:
        on = chore_chat.parse_when(period, today)
    except ValueError:
        return None
    return on, on


def numbers(period: str | None = None) -> str:
    today = planner_db._today()
    monday = today - timedelta(days=today.weekday())
    asked = " ".join((period or "").split())
    span = _range(asked, today) if asked else None
    with planner_db._connect() as conn:
        days = daily_log.between(conn, date(2000, 1, 1), today)
    if not days:
        return "Nothing is in the daily log yet. Opening Fitness, Daily imports the daily notes."

    if span:
        start, end = span
        inside = [d for d in days if start.isoformat() <= d["date"] <= end.isoformat()]
        label = f"{start:%B %-d}" if start == end else f"{start:%B %-d} to {end:%B %-d}"
        if not inside:
            return (f"Nothing is logged for {asked} ({label}). The latest logged day is "
                    f"{_day_name(days[-1]['date'])}. Don't guess any numbers.")
        if start == end:
            return _day(inside[0])
        lines = [f"{asked.capitalize()} ({label}), daily averages over finished days: "
                 f"{_averages(daily_log.summary(days, start, end))}."]
        for key, name in (("weight", "Home weight"), ("weight_pf", "Gym (PF) weight")):
            weighed = [d for d in inside if d[key] is not None]
            if len(weighed) > 1:
                first, last = weighed[0], weighed[-1]
                lines.append(f"{name} went from {_n(first[key])} lb ({_day_name(first['date'])}) to "
                             f"{_n(last[key])} lb ({_day_name(last['date'])}): {_change(first[key], last[key])}.")
        if len(inside) <= _LISTED_DAYS:
            lines += ["Day by day:", *map(_day, inside)]
        return "\n".join(lines)

    lines = []
    if asked:
        lines.append(f"I couldn't read \"{asked}\" as a period, so here is the overview.")
    for key, name in (("weight", "home"), ("weight_pf", "gym (PF)")):
        weighed = [d for d in days if d[key] is not None]
        if weighed:
            lines.append(f"Latest {name} weigh-in: {_n(weighed[-1][key])} lb on {_day_name(weighed[-1]['date'])}.")
    lines.append(f"This week so far (from Monday), daily averages: {_averages(daily_log.week_summary(days, monday))}.")
    lines.append(f"Last week: {_averages(daily_log.week_summary(days, monday - timedelta(weeks=1)))}.")
    trend = []
    weeks = [daily_log.week_summary(days, monday - timedelta(weeks=n)) for n in range(_TREND_WEEKS - 1, -1, -1)]
    for key, name in (("weight", "Home"), ("weight_pf", "Gym (PF)")):
        points = [(w["start"], w["average"][key]) for w in weeks if w["average"][key] is not None]
        if len(points) > 1:
            listed = ", ".join(f"week of {date.fromisoformat(s):%b %-d}: {_n(v)}" for s, v in points)
            trend.append(f"{name} weight, weekly averages in lb: {listed}. Overall {_change(points[0][1], points[-1][1])}.")
    lines += trend
    lines += ["Most recent days:", *map(_day, days[-3:])]
    return "\n".join(lines)
