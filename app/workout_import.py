"""Saves parsed spreadsheet workouts, and lists and links exercise names.

A workout is identified by (date, tab name). Uploading again saves only the
workouts that are new or differ from what is stored, replacing those and
leaving all others alone, so nothing duplicates.
The sheet is the main record for lifting: it replaces pasted lifts on the same
date."""

from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app import planner_db, workout_sheet

router = APIRouter()

SET_COLUMNS = (
    "exercise", "exercise_order", "set_type", "target", "planned_sets", "superset",
    "weight", "per_side", "base_weight", "base_kind", "reps", "reps_raw", "myo", "note",
    "myo_raw", "full_reps", "rest_pause_reps", "partial_reps",
)


def exercise_key(name: str) -> str:
    return " ".join(name.split()).casefold()


def _aliases(conn) -> dict[str, str]:
    rows = conn.execute("SELECT alias_key, canonical FROM exercise_aliases").fetchall()
    return {row["alias_key"]: row["canonical"] for row in rows}


def list_exercises() -> list[dict]:
    """One entry per unique exercise: capitals, spacing and linked names fold
    together. Recorded names are never rewritten."""
    with planner_db._connect() as conn:
        aliases = _aliases(conn)
        rows = conn.execute(
            """
            SELECT exercise, count(*) AS sets, max(workout_date) AS last_done
            FROM lift_sets GROUP BY exercise ORDER BY max(workout_date), exercise
            """
        ).fetchall()
    found: dict[str, dict] = {}
    for row in rows:
        key = exercise_key(row["exercise"])
        name = aliases.get(key, row["exercise"])
        entry = found.setdefault(exercise_key(name), {"name": name, "sets": 0, "last_done": None, "variants": []})
        # Rows come oldest first, so an unlinked name shows its newest spelling.
        if key not in aliases:
            entry["name"] = row["exercise"]
        entry["sets"] += row["sets"]
        entry["last_done"] = max(filter(None, (entry["last_done"], row["last_done"].isoformat())))
        if row["exercise"] not in entry["variants"]:
            entry["variants"].append(row["exercise"])
    return sorted(found.values(), key=lambda e: e["name"].casefold())


LB_PER_KG = 2.20462


def best_set(sets: list[dict]) -> dict:
    """Heaviest weight, then most reps at it; with no weights recorded, most
    reps. Ties go to the most recent. Expects newest first."""
    def rank(item):
        weight = item["weight"]
        if weight is None:
            return (0, 0, item["reps"])
        return (1, weight * (LB_PER_KG if item["unit"] == "kg" else 1), item["reps"])

    return max(sets, key=rank)


def exercise_history(name: str) -> dict | None:
    """Every set of one exercise, including linked names, newest day first.
    Returns None if nothing has been logged under it."""
    with planner_db._connect() as conn:
        aliases = _aliases(conn)

        def resolved(recorded):
            return exercise_key(aliases.get(exercise_key(recorded), recorded))

        wanted = resolved(name)
        names = [
            row["exercise"]
            for row in conn.execute("SELECT DISTINCT exercise FROM lift_sets").fetchall()
            if resolved(row["exercise"]) == wanted
        ]
        if not names:
            return None
        rows = conn.execute(
            """
            SELECT s.workout_date, w.session_name AS session, s.exercise, s.bodyweight,
                   s.weight::float8 AS weight, s.weight_unit AS unit, s.per_side::float8 AS per_side,
                   s.reps, s.set_type, s.target, s.myo, s.myo_raw, s.note
            FROM lift_sets s LEFT JOIN workouts w ON w.id = s.workout_id
            WHERE s.exercise = ANY(%s)
            ORDER BY s.workout_date DESC, w.session_name, s.position
            """,
            (names,),
        ).fetchall()
    days: list[dict] = []
    sets = []
    for row in rows:
        item = dict(row)
        day = item.pop("workout_date").isoformat()
        session = item.pop("session")
        if not days or days[-1]["date"] != day:
            days.append({"date": day, "sessions": [], "sets": []})
        if session and session not in days[-1]["sessions"]:
            days[-1]["sessions"].append(session)
        days[-1]["sets"].append(item)
        sets.append({**item, "date": day})
    # Each day's top set, for the weight-over-time chart.
    for day in days:
        day["best"] = best_set(day["sets"])
    return {"days": days, "best": best_set(sets)}


def link_exercise(name: str, same_as: str) -> None:
    """Counts `name` as `same_as` from now on, including anything already
    linked to `name`."""
    name, same_as = " ".join(name.split()), " ".join(same_as.split())
    if not name or not same_as:
        raise ValueError("Both exercise names are needed")
    with planner_db._connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('exercise_alias'))")
        aliases = _aliases(conn)
        target = aliases.get(exercise_key(same_as), same_as)
        if exercise_key(target) == exercise_key(name):
            raise ValueError("Those are already the same exercise")
        # Keeps links one step deep, so there can be no chains or loops.
        for key, canonical in aliases.items():
            if exercise_key(canonical) == exercise_key(name):
                conn.execute("UPDATE exercise_aliases SET canonical = %s WHERE alias_key = %s", (target, key))
        conn.execute(
            """
            INSERT INTO exercise_aliases (alias_key, canonical) VALUES (%s, %s)
            ON CONFLICT (alias_key) DO UPDATE SET canonical = EXCLUDED.canonical
            """,
            (exercise_key(name), target),
        )


def unlink_exercise(name: str) -> bool:
    with planner_db._connect() as conn:
        return conn.execute(
            "DELETE FROM exercise_aliases WHERE alias_key = %s", (exercise_key(name),)
        ).rowcount > 0


def _program_name(program: str | None, filename: str | None) -> str:
    name = (program or "").strip() or (filename or "").rsplit(".", 1)[0].strip()
    return name[:200] or "Untitled program"


# Stored as NUMERIC(8, 2), so compared at that precision.
_DECIMAL_COLUMNS = {"weight", "per_side", "base_weight"}


def _comparable(item: dict) -> tuple:
    return tuple(
        Decimal(str(item[c])).quantize(Decimal("0.01"), ROUND_HALF_UP)
        if c in _DECIMAL_COLUMNS and item[c] is not None else item[c]
        for c in SET_COLUMNS
    )


def _changed_exercises(old: list[dict], new: list[dict]) -> list[str]:
    """Names whose sets differ, in sheet order. A rename lists both names."""
    def by_name(sets):
        found: dict[str, list[tuple]] = {}
        for item in sets:
            found.setdefault(item["exercise"], []).append(_comparable(item))
        return found

    before, after = by_name(old), by_name(new)
    return [name for name in dict.fromkeys([*after, *before]) if before.get(name) != after.get(name)]


def _compare(conn, workout: dict) -> dict:
    """How a parsed workout differs from what is stored: "new", "changed" or
    "unchanged", how many saved sets saving it would replace, and which
    exercises differ."""
    columns = ", ".join(f"s.{c}" for c in SET_COLUMNS)
    stored = conn.execute(
        f"""
        SELECT {columns} FROM lift_sets s JOIN workouts w ON w.id = s.workout_id
        WHERE s.workout_date = %(date)s AND w.session_name = %(session)s ORDER BY s.position
        """,
        workout,
    ).fetchall()
    pasted = conn.execute(
        "SELECT count(*) AS n FROM lift_sets WHERE workout_id IS NULL AND workout_date = %(date)s", workout
    ).fetchone()["n"]
    changes: list[str] = []
    if not stored and not pasted:
        status = "new"
    elif not pasted and [_comparable(s) for s in stored] == [_comparable(s) for s in workout["sets"]]:
        status = "unchanged"
    else:
        status = "changed"
        if stored:
            changes = _changed_exercises(stored, workout["sets"])
    return {"status": status, "replaces": {"sets": len(stored), "pasted_sets": pasted}, "changes": changes}


def _sort_warnings(conn, result: dict) -> None:
    """Leaves in "warnings" only the ones worth showing. A warning is hidden if
    it was dismissed, or if it's about a workout that is saved and unchanged."""
    dismissed = {r["warning"] for r in conn.execute("SELECT warning FROM sheet_warning_dismissals").fetchall()}
    saved = set()
    for workout in result["workouts"]:
        about = workout.pop("warnings", [])
        if workout["status"] == "unchanged":
            saved.update(about)
    shown, hidden = [], []
    for text in result["warnings"]:
        if text in dismissed:
            hidden.append({"text": text, "reason": "dismissed"})
        elif text in saved:
            hidden.append({"text": text, "reason": "saved"})
        else:
            shown.append(text)
    result["warnings"], result["hidden_warnings"] = shown, hidden


def set_dismissed(warning: str, dismissed: bool) -> None:
    with planner_db._connect() as conn:
        if dismissed:
            conn.execute(
                "INSERT INTO sheet_warning_dismissals (warning) VALUES (%s) ON CONFLICT DO NOTHING", (warning,)
            )
        else:
            conn.execute("DELETE FROM sheet_warning_dismissals WHERE warning = %s", (warning,))


def preview(data: bytes, filename: str | None, program: str | None = None) -> dict:
    result = workout_sheet.parse(data, planner_db._today())
    with planner_db._connect() as conn:
        for workout in result["workouts"]:
            workout.update(_compare(conn, workout))
        _sort_warnings(conn, result)
    known = set()
    for entry in list_exercises():
        known.update(exercise_key(v) for v in [entry["name"], *entry["variants"]])
    with planner_db._connect() as conn:
        known.update(_aliases(conn))
    new = {}
    for workout in result["workouts"]:
        for item in workout["sets"]:
            key = exercise_key(item["exercise"])
            if key not in known:
                new.setdefault(key, item["exercise"])
    return {**result, "program": _program_name(program, filename), "new_exercises": sorted(new.values(), key=str.casefold)}


def save(data: bytes, filename: str | None, program: str | None = None) -> dict:
    """All or nothing: any error means nothing is written. Unchanged workouts
    are left as they are."""
    result = workout_sheet.parse(data, planner_db._today())
    name = _program_name(program, filename)
    if result["errors"]:
        return {**result, "program": name, "saved": False}
    columns = ", ".join(SET_COLUMNS)
    placeholders = ", ".join(["%s"] * len(SET_COLUMNS))
    with planner_db._connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('workout_save'))")
        for workout in result["workouts"]:
            workout.update(_compare(conn, workout))
        writing = [w for w in result["workouts"] if w["status"] != "unchanged"]
        program_id = None
        if writing:
            program_id = conn.execute(
                """
                INSERT INTO workout_programs (name) VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id
                """,
                (name,),
            ).fetchone()["id"]
        for workout in writing:
            workout_id = conn.execute(
                """
                INSERT INTO workouts (program_id, session_name, workout_date, source_file)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (workout_date, session_name) DO UPDATE
                    SET program_id = EXCLUDED.program_id, source_file = EXCLUDED.source_file, imported_at = now()
                RETURNING id
                """,
                (program_id, workout["session"], workout["date"], filename),
            ).fetchone()["id"]
            conn.execute(
                "DELETE FROM lift_sets WHERE workout_id = %s OR (workout_id IS NULL AND workout_date = %s)",
                (workout_id, workout["date"]),
            )
            for position, item in enumerate(workout["sets"], start=1):
                conn.execute(
                    f"""
                    INSERT INTO lift_sets (workout_id, workout_date, position, weight_unit, {columns})
                    VALUES (%s, %s, %s, 'lb', {placeholders})
                    """,
                    (workout_id, workout["date"], position, *(item[c] for c in SET_COLUMNS)),
                )
    return {**result, "program": name, "saved": True}


async def _read(file: UploadFile) -> bytes:
    return await file.read(workout_sheet.MAX_FILE_BYTES + 1)


@router.post("/workouts/import/preview")
async def post_import_preview(file: UploadFile, program: str | None = None):
    try:
        return await run_in_threadpool(preview, await _read(file), file.filename, program)
    except workout_sheet.SheetError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/workouts/import")
async def post_import(file: UploadFile, program: str | None = None):
    try:
        result = await run_in_threadpool(save, await _read(file), file.filename, program)
    except workout_sheet.SheetError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not result["saved"]:
        raise HTTPException(status_code=422, detail=result["errors"])
    return result


class WarningRequest(BaseModel):
    warning: str = Field(min_length=1, max_length=1000)
    dismissed: bool


@router.post("/workouts/import/warnings")
def post_warning(request: WarningRequest):
    set_dismissed(request.warning, request.dismissed)
    return {"status": "ok"}


class LinkRequest(BaseModel):
    name: str
    same_as: str


class UnlinkRequest(BaseModel):
    name: str


@router.get("/workouts/exercises")
def get_exercises():
    return {"exercises": list_exercises()}


@router.get("/workouts/exercises/history")
def get_exercise_history(name: str):
    result = exercise_history(name)
    if result is None:
        raise HTTPException(status_code=404, detail="Nothing logged for that exercise")
    return result


@router.post("/workouts/exercises/link")
def post_link(request: LinkRequest):
    try:
        link_exercise(request.name, request.same_as)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"exercises": list_exercises()}


@router.post("/workouts/exercises/unlink")
def post_unlink(request: UnlinkRequest):
    if not unlink_exercise(request.name):
        raise HTTPException(status_code=404, detail="That name isn't linked")
    return {"exercises": list_exercises()}
