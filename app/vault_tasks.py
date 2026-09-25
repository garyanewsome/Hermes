"""Nightly Obsidian -> Todo import: pulls open `- [ ]` tasks from
Athenaeum's /tasks (which scans the synced vault clone) and adds any it
hasn't imported before to a dedicated todo list.

One-way and additive on purpose: it only ever creates items. Checking a
task off in Hermes does not write back to the vault (Athenaeum's deploy key
is read-only), and a task you complete or delete here is never re-imported
even though its checkbox is still open in Obsidian (see planner_db's
vault_task_imports table).

Run as a K8s CronJob (k8s/vault-tasks-cronjob.yaml), or by hand:
    python -m app.vault_tasks --dry-run
    python -m app.vault_tasks --also "00 System/Tasks/Tasks.md"   # one-off extra file
"""

import argparse
import hashlib

import httpx

from app import planner_db
from app.config import ATHENAEUM_HOST_HEADER, ATHENAEUM_URL

LIST_NAME = "Inbox"

# get_or_create_todo_list matches list names fuzzily (ILIKE %name%), so if
# you already have a list with "inbox" in its name, tasks land there rather
# than in a second one.


def _task_key(text: str) -> str:
    return hashlib.sha1(" ".join(text.lower().split()).encode("utf-8")).hexdigest()


def fetch_vault_tasks(extra_files: list[str]) -> list[dict]:
    response = httpx.get(
        f"{ATHENAEUM_URL}/tasks",
        params={"extra": extra_files},
        headers={"Host": ATHENAEUM_HOST_HEADER},
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data["tasks"]


def sync(dry_run: bool = False, extra_files: list[str] | None = None) -> dict:
    tasks = fetch_vault_tasks(extra_files or [])
    already = planner_db.get_imported_vault_task_keys()
    new = [t for t in tasks if _task_key(t["text"]) not in already]

    if dry_run:
        return {"scanned": len(tasks), "new": len(new), "added": 0, "sample": [t["text"] for t in new[:10]]}

    todo_list = planner_db.get_or_create_todo_list(LIST_NAME) if new else None
    for task in new:
        item = planner_db.create_todo_item(todo_list["id"], task["text"])
        if task.get("due"):
            planner_db.update_todo_item(item["id"], due_date=task["due"])
        planner_db.record_vault_task_import(_task_key(task["text"]), item["id"])
    return {
        "scanned": len(tasks),
        "new": len(new),
        "added": len(new),
        "list": todo_list["name"] if todo_list else None,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--also", action="append", default=[], metavar="PATH",
        help="also scan this vault-relative .md file, for a one-off import (repeatable)",
    )
    args = parser.parse_args()
    print(sync(dry_run=args.dry_run, extra_files=args.also))
