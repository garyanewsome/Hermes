"""The entertainment log: TV and movies to watch, being watched, waited on,
paused or finished. Hermes is where it's edited, and after changes it rewrites
a copy in the vault to read in Obsidian."""

import datetime
import logging
import threading
import time
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import planner_db
from app.config import ENTERTAINMENT_NOTE, VAULT_KEEPER_URL

router = APIRouter()
logger = logging.getLogger("hermes.entertainment")

# The note is written once changes stop for a bit, so a run of taps is one write.
QUIET_SECONDS = 20
RETRY_SECONDS = 300
STARTUP_SECONDS = 45
_changed = threading.Event()
_vault_error: str | None = None

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
    _changed.set()


def update(entry_id: int, entry: Entry) -> bool:
    values = _clean(entry)
    with planner_db._connect() as conn:
        _lock(conn)
        if _existing(conn).get(_key(values["title"], values["kind"]), entry_id) != entry_id:
            raise ValueError(f"{values['title']} is already on your list")
        assignments = ", ".join(f"{name} = %({name})s" for name in FIELDS)
        found = conn.execute(
            f"UPDATE entertainment SET {assignments}, updated_at = now() WHERE id = %(id)s",
            {**values, "id": entry_id},
        ).rowcount > 0
    _changed.set()  # after the commit
    return found


def delete(entry_id: int) -> bool:
    with planner_db._connect() as conn:
        found = conn.execute("DELETE FROM entertainment WHERE id = %s", (entry_id,)).rowcount > 0
    _changed.set()
    return found


# ---- The copy in the vault -------------------------------------------------


def _line(entry: dict) -> str:
    parts = [entry["title"]]
    place = [
        entry["season"] and f"Season {entry['season']}",
        entry["episode"] and f"watched E{entry['episode']}",
    ]
    if any(place):
        parts.append(", ".join(p for p in place if p))
    if entry["return_date"]:
        parts.append(entry["return_date"].replace("-", "."))
    if entry["where_to_watch"]:
        parts.append(f"on {entry['where_to_watch']}")
    mark = {"watching": "▶️ watching", "paused": "⏸️ paused", "done": "✅"}.get(entry["status"])
    if entry["status"] == "waiting" and not entry["return_date"]:
        mark = "⏳ waiting"
    if mark:
        parts.append(mark)
    line = "- " + " - ".join(parts)
    note = " ".join((entry["note"] or "").split())
    return f"{line}\n    - {note}" if note else line


def render(entries: list[dict]) -> str:
    """The list in the style of the hand-written note: TV then movies, named
    groups first, then the rest."""
    out = ["> Written by Hermes from its Entertainment page. Anything typed here is replaced."]
    for kind, heading in (("tv", "TV"), ("movie", "Movies")):
        mine = [e for e in entries if e["kind"] == kind]
        if not mine:
            continue
        out += ["", f"## {heading}"]
        groups: dict[str, list[dict]] = {}
        for entry in mine:
            groups.setdefault(entry["group_name"] or "", []).append(entry)
        loose = groups.pop("", [])
        for name, members in groups.items():
            out += ["", f"### {name}", *map(_line, members)]
        if loose:
            out += ["", *(["### Others"] if groups else []), *map(_line, loose)]
    return "\n".join(out) + "\n"


def write_note(skip_empty: bool = False) -> bool:
    """Rewrites the vault copy. False means it failed, and the page says why.
    `skip_empty` leaves the note alone when there is nothing listed, so a
    fresh or unreadable database can't blank it on startup."""
    global _vault_error
    try:
        entries = list_entries()["entries"]
        if skip_empty and not entries:
            return True
        response = httpx.post(
            f"{VAULT_KEEPER_URL}/owned/write",
            json={
                "path": ENTERTAINMENT_NOTE,
                "content": render(entries),
                # Its own source, so these don't use up chat's daily writes.
                "source": "hermes-sync",
                "kind": "entertainment",
            },
            timeout=60.0,
        )
        if response.status_code == 403:
            _vault_error = str(response.json().get("detail", "The vault write limits refused it."))
        elif response.status_code == 404:
            _vault_error = "vault-keeper needs updating before it can rewrite notes."
        else:
            response.raise_for_status()
            _vault_error = None
    except Exception as exc:  # a vault problem must never end the writer thread
        _vault_error = f"The vault couldn't be reached ({type(exc).__name__})."
    if _vault_error:
        logger.warning("entertainment note not written: %s", _vault_error)
    return _vault_error is None


def _loop() -> None:
    # Let the app and the database settle, then bring the note up to date.
    time.sleep(STARTUP_SECONDS)
    changed_since_start = False
    ok = write_note(skip_empty=True)
    while True:
        if _changed.wait(timeout=None if ok else RETRY_SECONDS):
            changed_since_start = True
            _changed.clear()
            while _changed.wait(timeout=QUIET_SECONDS):
                _changed.clear()
        ok = write_note(skip_empty=not changed_since_start)


def start_background() -> None:
    threading.Thread(target=_loop, name="entertainment-note", daemon=True).start()


# ---- Routes ----------------------------------------------------------------


def _refuse(action):
    try:
        return action()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _found(result):
    if not result:
        raise HTTPException(status_code=404, detail="That's no longer on your list")


def _page() -> dict:
    return {**list_entries(), "vault": {"path": ENTERTAINMENT_NOTE, "error": _vault_error}}


@router.get("/entertainment")
def get_entertainment():
    return _page()


@router.post("/entertainment")
def post_entry(entry: Entry):
    _refuse(lambda: add(entry))
    return _page()


@router.put("/entertainment/{entry_id}")
def put_entry(entry_id: int, entry: Entry):
    _found(_refuse(lambda: update(entry_id, entry)))
    return _page()


@router.delete("/entertainment/{entry_id}")
def remove_entry(entry_id: int):
    _found(delete(entry_id))
    return _page()
