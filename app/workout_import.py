"""Saves parsed spreadsheet workouts, and lists and links exercise names.

A workout is identified by (date, tab name). Uploading again replaces the
workouts the file contains and leaves all others alone, so nothing duplicates.
The sheet is the main record for lifting: it replaces pasted lifts on the same
date."""

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

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


def _find_replaced(conn, workout: dict) -> dict:
    """How many stored sets saving this workout would replace."""
    row = conn.execute(
        """
        SELECT count(*) FILTER (WHERE w.session_name = %(session)s) AS sheet,
               count(*) FILTER (WHERE s.workout_id IS NULL) AS pasted
        FROM lift_sets s LEFT JOIN workouts w ON w.id = s.workout_id
        WHERE s.workout_date = %(date)s
        """,
        workout,
    ).fetchone()
    return {"sets": row["sheet"], "pasted_sets": row["pasted"]}


def preview(data: bytes, filename: str | None, program: str | None = None) -> dict:
    result = workout_sheet.parse(data, planner_db._today())
    with planner_db._connect() as conn:
        for workout in result["workouts"]:
            workout["replaces"] = _find_replaced(conn, workout)
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
    """All or nothing: any error means nothing is written."""
    result = workout_sheet.parse(data, planner_db._today())
    name = _program_name(program, filename)
    if result["errors"]:
        return {**result, "program": name, "saved": False}
    columns = ", ".join(SET_COLUMNS)
    placeholders = ", ".join(["%s"] * len(SET_COLUMNS))
    with planner_db._connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('workout_save'))")
        program_id = conn.execute(
            """
            INSERT INTO workout_programs (name) VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id
            """,
            (name,),
        ).fetchone()["id"]
        for workout in result["workouts"]:
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


class LinkRequest(BaseModel):
    name: str
    same_as: str


class UnlinkRequest(BaseModel):
    name: str


@router.get("/workouts/exercises")
def get_exercises():
    return {"exercises": list_exercises()}


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
