"""Parser for the workout paste format (see docs/workout-format.md).

Pure code, no model: the same text always parses the same way. Strict on
purpose — a line that isn't understood is reported, never guessed at."""

import re
from datetime import date, timedelta

MAX_TEXT_LENGTH = 100_000
MAX_SETS = 50

_NUMBER = r"(\d{1,6}(?:\.\d{1,2})?)"
_HEADER = re.compile(r"workout\s+(\d{4}-\d{2}-\d{2})", re.IGNORECASE)
_WEIGHT = re.compile(rf"(?:(bw)(?:\s*\+\s*{_NUMBER}\s*(lbs?|kg))?|{_NUMBER}\s*(lbs?|kg))", re.IGNORECASE)
_SETS_BY_REPS = re.compile(r"(\d{1,3})\s*x\s*(\d{1,4})", re.IGNORECASE)
_DISTANCE = re.compile(rf"{_NUMBER}\s*(mi|km)", re.IGNORECASE)
_MINUTES = re.compile(rf"{_NUMBER}\s*min", re.IGNORECASE)
_CLOCK = re.compile(r"(?:(\d{1,2}):)?(\d{1,3}):([0-5]\d)")


def _unit(value: str) -> str:
    value = value.lower()
    return "lb" if value == "lbs" else value


def _parse_weight(value: str) -> dict:
    match = _WEIGHT.fullmatch(value)
    if not match:
        raise ValueError(f"weight '{value}' should look like '135 lb', '60 kg', 'bw' or 'bw+25 lb'")
    bodyweight, extra, extra_unit, plain, plain_unit = match.groups()
    number = extra if bodyweight else plain
    unit = extra_unit if bodyweight else plain_unit
    weight = float(number) if number else None
    if weight is not None and weight > 2000:
        raise ValueError(f"weight '{value}' is too large")
    return {"bodyweight": bool(bodyweight), "weight": weight, "unit": _unit(unit) if unit else None}


def _parse_reps(value: str) -> list[int]:
    shorthand = _SETS_BY_REPS.fullmatch(value)
    if shorthand:
        sets, count = int(shorthand.group(1)), int(shorthand.group(2))
        if not 1 <= sets <= MAX_SETS:
            raise ValueError(f"'{value}' needs between 1 and {MAX_SETS} sets")
        reps = [count] * sets
    else:
        parts = [part.strip() for part in value.split(",")]
        if not all(re.fullmatch(r"\d{1,4}", part) for part in parts):
            raise ValueError(f"reps '{value}' should look like '8, 8, 7' or '3x8'")
        reps = [int(part) for part in parts]
    if len(reps) > MAX_SETS:
        raise ValueError(f"more than {MAX_SETS} sets on one line")
    if not all(1 <= count <= 1000 for count in reps):
        raise ValueError(f"reps '{value}' must each be between 1 and 1000")
    return reps


def _parse_walk_amounts(values: list[str]) -> dict:
    walk = {"distance": None, "distance_unit": None, "duration_seconds": None}
    for value in values:
        distance = _DISTANCE.fullmatch(value)
        minutes = _MINUTES.fullmatch(value)
        clock = _CLOCK.fullmatch(value)
        if distance:
            if walk["distance"] is not None:
                raise ValueError("distance given twice")
            walk["distance"] = float(distance.group(1))
            walk["distance_unit"] = distance.group(2).lower()
            if not 0 < walk["distance"] <= 1000:
                raise ValueError(f"distance '{value}' is out of range")
        elif minutes or clock:
            if walk["duration_seconds"] is not None:
                raise ValueError("time given twice")
            if minutes:
                seconds = round(float(minutes.group(1)) * 60)
            else:
                hours, mins, secs = (int(part or 0) for part in clock.groups())
                seconds = hours * 3600 + mins * 60 + secs
            if not 0 < seconds <= 86400:
                raise ValueError(f"time '{value}' is out of range")
            walk["duration_seconds"] = seconds
        else:
            raise ValueError(f"'{value}' should be a distance ('1.5 mi', '2 km') or a time ('30 min', '28:30')")
    return walk


def parse(text: str, today: date) -> dict:
    """Returns {"days": [{"date", "lifts", "walks"}], "errors": [{"line", "message"}]}.

    Repeated headers for one date are merged. Callers must not save anything
    when errors is non-empty."""
    if len(text) > MAX_TEXT_LENGTH:
        return {"days": [], "errors": [{"line": 0, "message": "Paste is too long; split it into smaller pieces"}]}

    days: dict[str, dict] = {}
    errors: list[dict] = []
    current = None
    # A bad header leaves its lines with nowhere to go; report the header once.
    skipping = False

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        # Code fences come along when copying a block out of a chat.
        if not line or line.startswith("```"):
            continue
        try:
            header = _HEADER.fullmatch(line)
            if header or line.lower().startswith("workout"):
                current, skipping = None, True
                if not header:
                    raise ValueError("header should look like 'WORKOUT 2026-11-26'")
                try:
                    day = date.fromisoformat(header.group(1))
                except ValueError:
                    raise ValueError(f"'{header.group(1)}' isn't a real date")
                if day > today + timedelta(days=1):
                    raise ValueError(f"'{day}' is in the future")
                current = days.setdefault(day.isoformat(), {"date": day.isoformat(), "lifts": [], "walks": []})
                skipping = False
                continue

            if skipping:
                continue
            parts = [part.strip() for part in line.split("|")]
            kind = parts[0].lower()
            if kind not in ("lift", "walk"):
                raise ValueError("line should start with 'lift |' or 'walk |'")
            if current is None:
                raise ValueError("needs a 'WORKOUT <date>' line above it")
            if kind == "lift":
                if len(parts) != 4 or not all(parts[1:]):
                    raise ValueError("lift lines look like 'lift | Bench Press | 135 lb | 8, 8, 7'")
                current["lifts"].append(
                    {"exercise": " ".join(parts[1].split()), **_parse_weight(parts[2]), "reps": _parse_reps(parts[3])}
                )
            else:
                if len(parts) not in (3, 4) or not all(parts[1:]):
                    raise ValueError("walk lines look like 'walk | walking pad | 1.5 mi | 30 min' (distance or time optional)")
                current["walks"].append({"activity": " ".join(parts[1].split()), **_parse_walk_amounts(parts[2:])})
        except ValueError as exc:
            errors.append({"line": number, "message": str(exc)})

    for day in days.values():
        if not day["lifts"] and not day["walks"] and not errors:
            errors.append({"line": 0, "message": f"{day['date']} has no lift or walk lines"})
    if not days and not errors:
        errors.append({"line": 0, "message": "Nothing to read; start with 'WORKOUT <date>'"})

    return {"days": [days[key] for key in sorted(days)], "errors": errors}
