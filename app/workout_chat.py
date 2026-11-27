"""Workouts and activities by chat, read-only: last time, personal bests and
totals. Code finds the exercise and does every sum and date; the model only
words the answer."""

import re
from datetime import date, timedelta

from app import activities, planner_db, workout_charts, workout_import

# Words that don't narrow down which exercise or activity is meant.
_GENERAL = {"workout", "exercise", "activity", "activities", "lift", "lifting", "all"}
_MAX_MATCHES = 6
_FILLER = {"a", "an", "the", "my", "i", "did", "do", "done", "of", "on"}
# The user saying they did something, which chat has no way to record.
_REPORT = re.compile(
    r"\bi (just |also )?(walked|ran|jogged|biked|hiked|lifted|benched|squatted|deadlifted|worked out|"
    r"went (for a|to the) (walk|run|gym))\b",
    re.IGNORECASE,
)
_LIFTING = re.compile(r"lift|bench|squat|worked out|gym", re.IGNORECASE)


def report_note(text: str) -> str | None:
    """An instruction for this turn when the user reports exercise."""
    report = _REPORT.search(text)
    if not report or "?" in text:
        return None
    how = (
        "lifting is added by uploading the workout spreadsheet on the Fitness page"
        if _LIFTING.search(report.group(0))
        else "they can add it with the + button on the Fitness page"
    )
    return (
        "The user is telling you about exercise they did. You cannot record workouts or activities from chat: "
        f"never say you noted, logged or saved it. Say you couldn't save it and that {how} (a habit tool may "
        "still be used if they track it as a habit)."
    )


def _stem(word: str) -> str:
    if len(word) > 5 and word.endswith("ing"):
        word = word[:-3]
    elif word.endswith("sses"):
        word = word[:-2]
    elif len(word) > 2 and word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    return word


def _words(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.casefold()) if w not in _FILLER]


def _same(a: str, b: str) -> bool:
    short, long = sorted((a, b), key=len)
    return short == long or (len(short) >= 4 and long.startswith(short))


def _day(on: date) -> str:
    ago = (planner_db._today() - on).days
    when = "today" if ago == 0 else "yesterday" if ago == 1 else f"{ago} days ago"
    return f"{on:%A %B %-d, %Y} ({when})"


def _number(value: float) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def _set(item: dict) -> str:
    if item["weight"] is None:
        text = f"{item['reps']} reps" + (" at bodyweight" if item.get("bodyweight") else " (no weight recorded)")
    else:
        text = f"{_number(item['weight'])} {item['unit'] or 'lb'} x {item['reps']}"
    if item.get("myo_raw"):
        text += f" (myo {item['myo_raw']})"
    return text


def _matches(said: str, listed: list[dict]) -> list[dict]:
    """`listed` items have "name" and may have "variants". An exact name wins.
    Otherwise every word given must be in the name, or the same letters run
    together ("deadlift" also finds "Dead Lift")."""
    names = [
        (name, item) for item in listed for name in [item["name"], *item.get("variants", [])]
    ]
    wanted = _words(said)
    if "bench" in wanted:  # "bench press" is a bench, whatever the log calls it
        wanted = [w for w in wanted if w != "press"]
    if not wanted:
        return []
    found = [item for name, item in names if _words(name) == wanted]
    if not found:
        squashed = "".join(wanted)
        found = [
            item for name, item in names
            if all(any(_same(w, other) for other in _words(name)) for w in wanted)
            or (len(squashed) >= 5 and squashed in "".join(_words(name)))
        ]
    return list({item["name"]: item for item in found}.values())


def _asked(text: str | None) -> str:
    words = [w for w in (text or "").split() if w.casefold().strip("s?.!") not in _GENERAL]
    return " ".join(words)


def _exercise(name: str) -> str:
    history = workout_import.exercise_history(name)
    last, best = history["days"][0], history["best"]
    lines = [
        f"{name}: done on {len(history['days'])} day{'s' if len(history['days']) != 1 else ''}.",
        f"  Last time: {_day(date.fromisoformat(last['date']))}: {'; '.join(_set(s) for s in last['sets'])}.",
        f"  Personal best set: {_set(best)} on {_day(date.fromisoformat(best['date']))}.",
    ]
    if len(history["days"]) > 1:
        before = history["days"][1]
        lines.append(f"  Time before: {_day(date.fromisoformat(before['date']))}: top set {_set(before['best'])}.")
    return "\n".join(lines)


def lifts(exercise: str | None = None) -> str:
    listed = workout_import.list_exercises()
    if not listed:
        return "No lifting has been logged yet."
    wanted = _asked(exercise)
    if wanted:
        matches = _matches(wanted, listed)
        if not matches:
            words = set(_words(wanted))
            close = [e["name"] for e in listed if words & set(_words(e["name"]))]
            return (f"No logged exercise matches \"{wanted}\". Don't guess any numbers. "
                    + (f"Similar names: {', '.join(close)}." if close
                       else f"Logged exercises: {', '.join(e['name'] for e in listed)}."))
        matches.sort(key=lambda e: e["last_done"], reverse=True)
        text = "\n".join(_exercise(e["name"]) for e in matches[:_MAX_MATCHES])
        if len(matches) > 1:
            text = f"{len(matches)} exercises match \"{wanted}\":\n{text}"
        if len(matches) > _MAX_MATCHES:
            text += "\nAlso: " + ", ".join(e["name"] for e in matches[_MAX_MATCHES:])
        return text

    # Nothing named: the last few gym days, then every personal best.
    with planner_db._connect() as conn:
        rows = conn.execute(
            """
            SELECT s.workout_date, s.exercise, w.session_name AS session
            FROM lift_sets s LEFT JOIN workouts w ON w.id = s.workout_id
            WHERE s.workout_date IN (SELECT DISTINCT workout_date FROM lift_sets ORDER BY 1 DESC LIMIT 3)
            ORDER BY s.workout_date DESC, w.session_name, s.position
            """
        ).fetchall()
        bests = workout_charts.personal_bests(conn)
    days: dict[date, dict] = {}
    for row in rows:
        day = days.setdefault(row["workout_date"], {"sessions": {}, "exercises": {}})
        if row["session"]:
            day["sessions"][row["session"]] = None
        day["exercises"][row["exercise"]] = None
    lines = ["Latest gym days:"]
    for on, day in days.items():
        session = f" {', '.join(day['sessions'])}:" if day["sessions"] else ":"
        lines.append(f"{_day(on)}{session} {', '.join(day['exercises'])}.")
    lines.append("Personal best set for each exercise (all time):")
    lines += [f"{b['exercise']}: {_set(b)} on {date.fromisoformat(b['date']):%B %-d, %Y}." for b in bests]
    return "\n".join(lines)


def periods(today: date) -> dict[str, tuple[date, date]]:
    """Weeks run Monday to Sunday, as on the charts."""
    monday = today - timedelta(days=today.weekday())
    month = today.replace(day=1)
    last_month_end = month - timedelta(days=1)
    return {
        "today": (today, today),
        "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
        "this week": (monday, today),
        "last week": (monday - timedelta(days=7), monday - timedelta(days=1)),
        "this month": (month, today),
        "last month": (last_month_end.replace(day=1), last_month_end),
        "this year": (today.replace(month=1, day=1), today),
    }


def _range(period: str, today: date) -> tuple[date, date] | None:
    text = " ".join(period.casefold().replace("_", " ").split())
    named = periods(today)
    if text in named:
        return named[text]
    back = re.fullmatch(r"(?:the )?(?:last|past) (\d{1,4}) (day|week)s?", text)
    if back:
        days = int(back.group(1)) * (7 if back.group(2) == "week" else 1)
        return today - timedelta(days=max(days, 1) - 1), today
    return None


def _total(rows: list[dict]) -> str:
    if not rows:
        return "none"
    seconds = sum(r["duration_seconds"] or 0 for r in rows)
    miles = sum(
        r["distance"] / 1.609344 if r["distance_unit"] == "km" else r["distance"]
        for r in rows if r["distance"] is not None
    )
    hours, minutes = divmod(round(seconds / 60), 60)
    time = f"{hours} h {minutes} min" if hours else f"{minutes} min"
    text = f"{len(rows)} entr{'ies' if len(rows) != 1 else 'y'} on {len({r['activity_date'] for r in rows})} day(s), {time}"
    return text + (f", {_number(miles)} miles" if miles else "")


def activity_totals(activity: str | None = None, period: str | None = None) -> str:
    with planner_db._connect() as conn:
        logged = activities.entries(conn)
    if not logged:
        return "No activities have been logged yet."
    names = list(dict.fromkeys(r["activity"] for r in logged))
    wanted = _asked(activity)
    chosen = names
    if wanted:
        chosen = [m["name"] for m in _matches(wanted, [{"name": n} for n in names])]
        if not chosen:
            return (f"No logged activity matches \"{wanted}\". Don't guess any numbers. "
                    f"Logged activities: {', '.join(names)}.")
    rows = [r for r in logged if r["activity"] in chosen]
    today = planner_db._today()
    spans = periods(today)
    show = ["this week", "last week", "this month", "last month"]
    asked = (period or "").strip()
    if asked and asked.casefold() not in ("all", "all time", "ever", "total"):
        span = _range(asked, today)
        if span:
            spans[asked.casefold()] = span
            show = [asked.casefold()]
    lines = [f"Activity: {', '.join(chosen)}."]
    for name in show:
        start, end = spans[name]
        inside = [r for r in rows if start <= r["activity_date"] <= end]
        lines.append(f"{name.capitalize()} ({start:%b %-d} to {end:%b %-d}): {_total(inside)}.")
        if len(chosen) > 1:
            for each in chosen:
                part = [r for r in inside if r["activity"] == each]
                if part:
                    lines.append(f"  {each}: {_total(part)}.")
    lines.append(f"All time: {_total(rows)}.")
    last = rows[-1]
    lines.append(f"Most recent: {last['activity']} on {_day(last['activity_date'])}: {_total([last])}.")
    return "\n".join(lines)


def mentions(text: str) -> bool:
    """Whether the text names a logged exercise or activity: two words of its
    name, or its only word."""
    said = _words(text)
    names = [e["name"] for e in workout_import.list_exercises()]
    with planner_db._connect() as conn:
        names += [r["activity"] for r in conn.execute("SELECT DISTINCT activity FROM activities").fetchall()]
    for name in names:
        words = _words(name)
        hits = sum(any(_same(w, s) for s in said) for w in words)
        if words and hits >= min(2, len(words)):
            return True
    return False
