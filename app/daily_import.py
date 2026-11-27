"""Brings daily notes into the Fitness log: reads them through vault-keeper,
shows what each day would change, and saves what the user confirms. The note is
never written to.

There are two ways in. The manual import offers everything the notes say. The
automatic one runs when Daily is opened and only saves what is clear and hasn't
been changed in Naradi."""

import datetime

import httpx
from fastapi import APIRouter, HTTPException, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, ValidationError

from app import daily_log, daily_note, planner_db
from app.config import DAILY_NOTES_FOLDER, VAULT_KEEPER_URL

router = APIRouter()

WALK = "Work walk"
SOURCE = "daily-note"
MAX_DAYS = 400
AUTO_DAYS = 7
_CALORIES = ("burned_total", "burned_active", "calories_in", "protein_g", "carbs_g", "fat_g")


def note_path(day: datetime.date) -> str:
    return f"{DAILY_NOTES_FOLDER}/{day:%Y}/{day:%m}/{day.isoformat()}.md"


def fetch(days: list[datetime.date]) -> dict[datetime.date, str]:
    paths = {note_path(day): day for day in days}
    response = httpx.post(f"{VAULT_KEEPER_URL}/read_notes", json={"paths": list(paths)}, timeout=120.0)
    if response.status_code == 404:
        raise LookupError("vault-keeper needs updating before it can read daily notes")
    if response.status_code == 403:
        raise LookupError(str(response.json().get("detail", "The vault refused that read")))
    response.raise_for_status()
    return {paths[path]: text for path, text in response.json()["notes"].items()}


def gather(notes: dict[datetime.date, str], count_old: bool = False) -> dict[datetime.date, dict]:
    """What the notes say about each date. A note's "yesterday" totals are the
    final numbers for the day before and win over that day's own "so far".
    `count_old` treats the older single-block calories, which had no later
    totals, as final too."""
    days: dict[datetime.date, dict] = {}

    def day(on):
        return days.setdefault(on, {"fields": {}, "weights": {}, "walks": [], "warnings": []})

    for on in sorted(notes):
        parsed = daily_note.parse(notes[on])
        for key, column in (("home", "weight"), ("pf", "weight_pf")):
            found = parsed[key]
            if not found:
                continue
            entry = day(on)
            entry["fields"][f"{column}_note"] = found["note"][:2000]
            if found["weight"] is not None:
                entry["fields"][column] = found["weight"]
            if found["unsure"]:
                entry["weights"][column] = found["candidates"]
        for name in ("body_note", "gym_session", "gym_note"):
            if parsed[name]:
                day(on)["fields"][name] = parsed[name][:2000]
        if parsed["walks"]:
            day(on)["walks"] = parsed["walks"]
        if parsed["warnings"]:
            day(on)["warnings"] += parsed["warnings"]
        so_far = parsed["calories"].get("today")
        # A final already read from the next day's note stays.
        if so_far and day(on)["fields"].get("calories_partial") is not False:
            final_enough = count_old and not parsed["dated"]
            day(on)["fields"].update(
                so_far, calories_partial=not final_enough, calories_as_of=None if final_enough else parsed["as_of"]
            )
        final = parsed["calories"].get("yesterday")
        if final:
            entry = day(on - datetime.timedelta(days=1))
            entry["fields"].update(final, calories_partial=False, calories_as_of=None)
    return {on: entry for on, entry in days.items() if entry["fields"] or entry["walks"] or entry["warnings"]}


def _usable(fields: dict, stored: dict | None, warnings: list[str]) -> dict:
    """Leaves out numbers the log would refuse, saying why, so one typo in a
    note can't stop the rest from importing."""
    fields = dict(fields)
    for name in daily_log.NUMBERS:
        if name in fields:
            try:
                daily_log.DayRequest(**{name: fields[name]})
            except ValidationError:
                warnings.append(f"{name.replace('_', ' ').capitalize()} {fields.pop(name):g} is out of range, so it's left out")
    merged = {**(stored or {}), **fields}
    total, active = merged.get("burned_total"), merged.get("burned_active")
    if total is not None and active is not None and active > total:
        warnings.append(f"Active calories ({active:g}) are more than the total burned ({total:g}), so neither is imported")
        fields.pop("burned_total", None)
        fields.pop("burned_active", None)
    return fields


def _same_walk(walk: dict, row: dict) -> bool:
    miles = lambda distance, unit: None if distance is None else round(distance / (1.609344 if unit == "km" else 1), 2)
    return (
        abs((row["duration_seconds"] or 0) - walk["seconds"]) < 60
        and miles(walk["distance"], walk["unit"]) == miles(row["distance"], row["distance_unit"])
    )


def _walk_changes(conn, on: datetime.date, walks: list[dict]) -> tuple[list[dict], int]:
    """The walks that saving would add, and how many earlier imports it would
    take away. Walks entered by hand are left alone and not repeated."""
    rows = conn.execute(
        """
        SELECT activity, distance::float8 AS distance, distance_unit, duration_seconds, source
        FROM activities WHERE activity_date = %s ORDER BY id
        """,
        (on,),
    ).fetchall()
    by_hand = [r for r in rows if r["source"] != SOURCE and r["activity"].casefold() == WALK.casefold()]
    imported = [r for r in rows if r["source"] == SOURCE]
    wanted = []
    for walk in walks:
        match = next((r for r in by_hand if _same_walk(walk, r)), None)
        if match:
            by_hand.remove(match)
        else:
            wanted.append(walk)
    added, left = [], list(imported)
    for walk in wanted:
        match = next((r for r in left if _same_walk(walk, r)), None)
        if match:
            left.remove(match)
        else:
            added.append(walk)
    return added, len(left)


def _compare(conn, on: datetime.date, entry: dict) -> dict:
    row = conn.execute("SELECT * FROM daily_log WHERE log_date = %s", (on,)).fetchone()
    stored = daily_log.public(row) if row else None
    warnings = list(entry["warnings"])
    fields = _usable(entry["fields"], stored, warnings)
    # "So far" numbers never replace a day that is already final.
    if stored and fields.get("calories_partial") and not stored["calories_partial"] and any(
        stored[name] is not None for name in _CALORIES
    ):
        for name in (*_CALORIES, "calories_partial", "calories_as_of"):
            fields.pop(name, None)
    changes = {}
    for name, value in fields.items():
        old = stored[name] if stored else None
        if name == "calories_partial":
            if old != value and any(n in fields for n in _CALORIES):
                changes[name] = [old, value]
        elif old != value:
            changes[name] = [old, value]
    added, removed = _walk_changes(conn, on, entry["walks"]) if entry["walks"] else ([], 0)
    if not changes and not added and not removed:
        status = "unchanged"
    else:
        status = "changed" if stored or removed else "new"
    return {
        "date": on.isoformat(), "status": status, "fields": fields, "changes": changes,
        "weights": entry["weights"], "walks": entry["walks"], "new_walks": len(added), "removed_walks": removed,
        "warnings": warnings,
    }


def preview(days: int, count_old: bool = False) -> dict:
    today = planner_db._today()
    wanted = [today - datetime.timedelta(days=n) for n in range(days)]
    notes = fetch(wanted)
    gathered = gather(notes, count_old)
    with planner_db._connect() as conn:
        found = [_compare(conn, on, gathered[on]) for on in sorted(gathered, reverse=True) if on <= today]
    return {"notes": len(notes), "days": found}


def _normal(name: str, value):
    """A note's value as it would read back once stored."""
    if value is None:
        return None
    stored = daily_log._value(name, value)
    return float(stored) if name in daily_log.NUMBERS and stored is not None else stored


def _seen(conn, on: datetime.date) -> dict:
    rows = conn.execute("SELECT field, value FROM daily_note_seen WHERE log_date = %s", (on,)).fetchall()
    return {row["field"]: row["value"] for row in rows}


def _remember(conn, on: datetime.date, values: dict) -> None:
    for field, value in values.items():
        conn.execute(
            """
            INSERT INTO daily_note_seen (log_date, field, value) VALUES (%s, %s, %s)
            ON CONFLICT (log_date, field) DO UPDATE SET value = EXCLUDED.value
            """,
            (on, field, Jsonb(value)),
        )


def _add_walks(conn, on: datetime.date, walks: list[dict]) -> int:
    """Brings the day's imported walks in line with the note. Returns how many
    entries changed."""
    added, removed = _walk_changes(conn, on, walks)
    if removed:
        # The note's list changed: rebuild this day's imported walks.
        conn.execute("DELETE FROM activities WHERE activity_date = %s AND source = %s", (on, SOURCE))
        added, _ = _walk_changes(conn, on, walks)
    for walk in added:
        conn.execute(
            """
            INSERT INTO activities (activity, activity_date, distance, distance_unit, duration_seconds, source)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (WALK, on, walk["distance"], None if walk["distance"] is None else walk["unit"] or "mi",
             walk["seconds"], SOURCE),
        )
    return len(added) + removed


def _walk_list(walks: list[dict]) -> list[list]:
    return [[w["seconds"], w["distance"], w["unit"]] for w in walks]


_LABELS = {
    "weight": "home weight", "weight_pf": "PF weight", "burned_total": "burned", "burned_active": "active",
    "calories_in": "eaten", "carbs_g": "carbs", "fat_g": "fat", "protein_g": "protein",
    "weight_note": "home note", "weight_pf_note": "PF note", "body_note": "body update",
    "gym_session": "gym session", "gym_note": "gym notes",
}


def _auto_day(conn, on: datetime.date, entry: dict) -> tuple[bool, list[str]]:
    """Saves what is safe to save for one day. Returns whether anything was
    saved, and what is left for the user to look at."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('daily_log'))")
    row = conn.execute("SELECT * FROM daily_log WHERE log_date = %s", (on,)).fetchone()
    stored = daily_log.public(row) if row else {}
    seen = _seen(conn, on)
    review = list(entry["warnings"])
    note = _usable(entry["fields"], stored, review)
    partial = note.get("calories_partial")
    # Final totals replace "so far" numbers, whoever typed those.
    finishing = partial is False and stored.get("calories_partial") is True and seen.get("calories_partial") is not False
    has_final = bool(stored) and not stored["calories_partial"] and any(stored[n] is not None for n in _CALORIES)
    apply, remember, left = {}, {}, []
    for name in (*daily_log.NUMBERS, *daily_log.TEXTS):
        if name == "calories_as_of" or name not in note:
            continue
        value, old = _normal(name, note[name]), stored.get(name)
        if name in entry["weights"]:
            if old is None and entry["weights"][name]:
                review.append(f"Pick the {_LABELS[name]}: \"{note[f'{name}_note']}\"")
            continue
        if old == value:
            remember[name] = value
        elif name in _CALORIES and partial and has_final:
            continue
        elif (old is None and name not in seen) or (name in seen and old == seen[name]) or (name in _CALORIES and finishing):
            apply[name] = remember[name] = value
        elif seen.get(name) != value:
            left.append(_LABELS[name])
    calories = any(name in apply for name in _CALORIES)
    if partial is not None and (calories or finishing):
        apply["calories_partial"] = remember["calories_partial"] = partial
        apply["calories_as_of"] = note.get("calories_as_of")
    if left:
        review.append(f"Kept your {', '.join(left)}; the note says something different")
    saved = False
    if apply:
        sent = {k: v for k, v in apply.items() if v is not None or k == "calories_as_of"}
        daily_log.save(on, daily_log.DayRequest(**sent), conn=conn)
        saved = True
    if entry["walks"]:
        walks = _walk_list(entry["walks"])
        # Unchanged since last time: a walk deleted in Naradi stays deleted.
        if seen.get("walks") != walks:
            saved = _add_walks(conn, on, entry["walks"]) > 0 or saved
            remember["walks"] = walks
    _remember(conn, on, remember)
    return saved, review


def auto() -> dict:
    today = planner_db._today()
    notes = fetch([today - datetime.timedelta(days=n) for n in range(AUTO_DAYS)])
    saved, review = [], []
    for on, entry in sorted(gather(notes).items(), reverse=True):
        if on > today:
            continue
        # A transaction each, so one bad day doesn't hold back the rest.
        try:
            with planner_db._connect() as conn:
                changed, notices = _auto_day(conn, on, entry)
        except ValueError as exc:
            changed, notices = False, [str(exc)]
        if changed:
            saved.append(on.isoformat())
        review += [{"date": on.isoformat(), "text": text} for text in notices]
    return {"notes": len(notes), "saved": saved, "review": review}


class Walk(BaseModel):
    seconds: int = Field(ge=1, le=86400)
    distance: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    unit: str | None = Field(default=None, pattern="^(mi|km)$")


class ImportDay(BaseModel):
    date: datetime.date
    fields: daily_log.DayRequest
    walks: list[Walk] = Field(default_factory=list, max_length=50)
    # What the note said, before any edits in the preview.
    note: daily_log.DayRequest | None = None


class ImportRequest(BaseModel):
    days: list[ImportDay] = Field(max_length=MAX_DAYS + 1)


def save(request: ImportRequest) -> int:
    """All or nothing. Blank values in a note never clear what's stored."""
    with planner_db._connect() as conn:
        for item in request.days:
            sent = {k: v for k, v in item.fields.model_dump(exclude_unset=True).items()
                    if v is not None or k == "calories_as_of"}
            if sent:
                daily_log.save(item.date, daily_log.DayRequest(**sent), conn=conn)
            if item.note:
                said = item.note.model_dump(exclude_unset=True)
                _remember(conn, item.date, {k: _normal(k, v) for k, v in said.items() if k != "calories_as_of"})
            if item.walks:
                walks = [w.model_dump() for w in item.walks]
                _add_walks(conn, item.date, walks)
                _remember(conn, item.date, {"walks": _walk_list(walks)})
    return len(request.days)


def _vault(action):
    try:
        return action()
    except LookupError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"The vault couldn't be reached ({type(exc).__name__})")


@router.post("/daily-import/auto")
def post_auto():
    return _vault(auto)


@router.get("/daily-import")
def get_import(days: int = Query(default=7, ge=1, le=MAX_DAYS), count_old: bool = False):
    return _vault(lambda: preview(days, count_old))


@router.post("/daily-import")
def post_import(request: ImportRequest):
    try:
        return {"saved": save(request)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
