"""Copies a scratch note (the Notes page / add_scratch_note) into the
Obsidian vault as a new note.

A copy, not a move: the scratch note stays where it is. Scratch notes are
quick capture "meant to get copied into Obsidian later" (planner_db), and
deleting someone's note as a side effect of saving it is not a thing to do
by default. The write goes through vault-keeper's /write_note, so it is
subject to the same vault limits as anything else Hermes writes.
"""

import re

import httpx

from app import planner_db
from app.config import VAULT_KEEPER_URL

DEFAULT_FOLDER = "Hermes/Imported"


class ExportRefused(Exception):
    """Shown to the user or the model as-is."""


def _filename(content: str) -> str:
    first_line = next((ln for ln in content.splitlines() if ln.strip()), "")
    title = re.sub(r"^#+\s*", "", first_line.strip())
    slug = re.sub(r'[\\/:*?"<>|]+', " ", title)
    slug = re.sub(r"\s+", " ", slug).strip(" .")[:60]
    return f"{slug or 'Scratch note'}.md"


def export_note(note_id: int, folder: str | None = None, force: bool = False) -> dict:
    """Returns {"vault_path", "already"}. `already` is True when the note had
    been exported before and force was not set, so nothing was written."""
    note = planner_db.get_note(note_id)
    if not note:
        raise ExportRefused("That note doesn't exist any more.")
    if note["vault_path"] and not force:
        return {"vault_path": note["vault_path"], "already": True}
    if not note["content"].strip():
        raise ExportRefused("That note is empty.")

    response = httpx.post(
        f"{VAULT_KEEPER_URL}/write_note",
        json={"folder": folder or DEFAULT_FOLDER, "filename": _filename(note["content"]), "content": note["content"]},
        timeout=30.0,
    )
    if response.status_code == 403:
        raise ExportRefused(response.json().get("detail", "The vault write limits refused it."))
    response.raise_for_status()
    vault_path = response.json()["note_path"]
    planner_db.record_note_export(note_id, vault_path)
    return {"vault_path": vault_path, "already": False}
