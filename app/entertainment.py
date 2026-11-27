"""The entertainment log: TV and movies to watch, being watched, waited on,
paused or finished. Hermes is where it's edited; the vault note is only read,
for the first import."""

import datetime
import re
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import planner_db
from app.config import ENTERTAINMENT_NOTE, VAULT_KEEPER_URL

router = APIRouter()

Kind = Literal["tv", "movie"]
Status = Literal["want", "watching", "waiting", "paused", "done"]

FIELDS = ("title", "kind", "group_name", "status", "season", "episode", "return_date", "where_to_watch", "note")


class Entry(BaseModel):
    title: str = Field(max_length=200)
    kind: Kind = "tv"
    group_name: str | None = Field(default=None, max_length=100)
    status: Status = "want"
    season: int | None = Field(default=None, ge=1, le=200)
    # The last episode watched in that season.
    episode: int | None = Field(default=None, ge=1, le=2000)
    return_date: datetime.date | None = None
    where_to_watch: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=1000)


class ImportRequest(BaseModel):
    entries: list[Entry] = Field(max_length=1000)


def _tidy(text: str | None) -> str | None:
    return " ".join(text.split()) or None if text else None


def _key(title: str, kind: str) -> tuple[str, str]:
    return " ".join(title.split()).casefold(), kind


def _clean(entry: Entry) -> dict:
    values = entry.model_dump()
    values["title"] = _tidy(entry.title)
    if not values["title"]:
        raise ValueError("Give it a title")
    for name in ("group_name", "where_to_watch"):
        values[name] = _tidy(values[name])
    values["note"] = (entry.note or "").strip() or None
    if entry.kind == "movie":
        values["season"] = values["episode"] = None
    return values


def _existing(conn) -> dict[tuple[str, str], int]:
    rows = conn.execute("SELECT id, title, kind FROM entertainment").fetchall()
    return {_key(r["title"], r["kind"]): r["id"] for r in rows}


def _lock(conn) -> None:
    # One writer at a time, so two saves can't both pass the duplicate check.
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('entertainment'))")


def _insert(conn, values: dict) -> None:
    columns = ", ".join(FIELDS)
    marks = ", ".join(f"%({name})s" for name in FIELDS)
    conn.execute(f"INSERT INTO entertainment ({columns}) VALUES ({marks})", values)


def list_entries() -> dict:
    today = planner_db._today()
    with planner_db._connect() as conn:
        # id order keeps an imported series in the order the note had it.
        rows = conn.execute(f"SELECT id, {', '.join(FIELDS)} FROM entertainment ORDER BY id").fetchall()
    entries = []
    for row in rows:
        item = dict(row)
        on = item["return_date"]
        item["days_until"] = None if on is None else (on - today).days
        item["return_date"] = None if on is None else on.isoformat()
        entries.append(item)
    return {"entries": entries, "today": today.isoformat()}


def add(entry: Entry) -> None:
    values = _clean(entry)
    with planner_db._connect() as conn:
        _lock(conn)
        if _key(values["title"], values["kind"]) in _existing(conn):
            raise ValueError(f"{values['title']} is already on your list")
        _insert(conn, values)


def update(entry_id: int, entry: Entry) -> bool:
    values = _clean(entry)
    with planner_db._connect() as conn:
        _lock(conn)
        if _existing(conn).get(_key(values["title"], values["kind"]), entry_id) != entry_id:
            raise ValueError(f"{values['title']} is already on your list")
        assignments = ", ".join(f"{name} = %({name})s" for name in FIELDS)
        return conn.execute(
            f"UPDATE entertainment SET {assignments}, updated_at = now() WHERE id = %(id)s",
            {**values, "id": entry_id},
        ).rowcount > 0


def delete(entry_id: int) -> bool:
    with planner_db._connect() as conn:
        return conn.execute("DELETE FROM entertainment WHERE id = %s", (entry_id,)).rowcount > 0


# ---- Import from the vault note --------------------------------------------

_SEASON = re.compile(r"season\s+(\d{1,3})", re.IGNORECASE)
_DATE = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")


def parse_note(text: str, today: datetime.date) -> list[dict]:
    """Reads the hand-written list: "## TV" / "## MOVIES" headings, "###"
    groups, and "- Title - Season 2 - 2027.01.14 - ✅" lines. Only recognised
    parts are taken off the end of a title, so "Mission - Impossible" stays
    whole."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                lines = lines[index + 1:]
                break
    kind, group, found = "tv", None, []
    for line in lines:
        line = line.strip()
        heading = re.match(r"(#{1,6})\s+(.*)", line)
        if heading:
            name = heading.group(2).strip()
            if len(heading.group(1)) <= 2:
                kind = "movie" if "movie" in name.lower() or "film" in name.lower() else "tv"
                group = None
            else:
                group = None if name.lower() in ("other", "others") else name
            continue
        bullet = re.match(r"[-*+]\s+(?:\[[ xX]\]\s*)?(.*)", line)
        if not bullet:
            continue
        body = bullet.group(1).strip()
        done = "✅" in body or bool(re.match(r"[-*+]\s+\[[xX]\]", line))
        parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", body.replace("✅", "").strip(" -–—"))]
        season = on = None
        while len(parts) > 1:
            last = parts[-1]
            if not last:
                parts.pop()
            elif season is None and _SEASON.fullmatch(last):
                season = int(_SEASON.fullmatch(parts.pop()).group(1)) or None
            elif on is None and _DATE.fullmatch(last):
                try:
                    on = datetime.date(*map(int, _DATE.fullmatch(last).groups()))
                except ValueError:
                    break
                parts.pop()
            else:
                break
        title = " - ".join(parts).strip()
        if not title:
            continue
        if done:
            status = "done"
        elif on and on > today:
            status = "waiting"
        elif season:
            status = "watching"  # the next season up
        else:
            status = "want"
        found.append(
            {"title": title[:200], "kind": kind, "group_name": group, "status": status,
             "season": season if kind == "tv" and season and season <= 200 else None,
             "return_date": None if on is None else on.isoformat()}
        )
    return found


def preview_import() -> dict:
    response = httpx.post(f"{VAULT_KEEPER_URL}/read_note", json={"path": ENTERTAINMENT_NOTE}, timeout=60.0)
    if response.status_code in (403, 404):
        raise LookupError(str(response.json().get("detail", "The note couldn't be read")))
    response.raise_for_status()
    entries = parse_note(response.json()["content"], planner_db._today())
    with planner_db._connect() as conn:
        seen = set(_existing(conn))
    for entry in entries:
        key = _key(entry["title"], entry["kind"])
        entry["exists"] = key in seen
        seen.add(key)  # a title listed twice counts once
    return {"note": ENTERTAINMENT_NOTE, "entries": entries}


def import_entries(entries: list[Entry]) -> int:
    """Adds the ones not already listed; nothing existing is changed."""
    cleaned = [_clean(entry) for entry in entries]
    added = 0
    with planner_db._connect() as conn:
        _lock(conn)
        seen = set(_existing(conn))
        for values in cleaned:
            key = _key(values["title"], values["kind"])
            if key not in seen:
                _insert(conn, values)
                seen.add(key)
                added += 1
    return added


# ---- Routes ----------------------------------------------------------------


def _refuse(action):
    try:
        return action()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _found(result):
    if not result:
        raise HTTPException(status_code=404, detail="That's no longer on your list")


@router.get("/entertainment")
def get_entertainment():
    return list_entries()


@router.post("/entertainment")
def post_entry(entry: Entry):
    _refuse(lambda: add(entry))
    return list_entries()


@router.put("/entertainment/{entry_id}")
def put_entry(entry_id: int, entry: Entry):
    _found(_refuse(lambda: update(entry_id, entry)))
    return list_entries()


@router.delete("/entertainment/{entry_id}")
def remove_entry(entry_id: int):
    _found(delete(entry_id))
    return list_entries()


@router.get("/entertainment/import")
def get_import_preview():
    try:
        return preview_import()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"The vault couldn't be reached ({type(exc).__name__})")


@router.post("/entertainment/import")
def post_import(request: ImportRequest):
    added = _refuse(lambda: import_entries(request.entries))
    return {**list_entries(), "added": added}
