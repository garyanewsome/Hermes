"""Tool registry. `search_vault` (semantic) and `list_notes` (structural
folder listing) are deliberately separate tools, not one merged tool —
they answer different question shapes ("what do my notes say about X"
vs. "what files exist under folder X") and RAG can't reliably do the
second one. Adding a third tool later is just adding another dict here
and a handler function, not restructuring anything."""

import logging
import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.config import (
    APP_TIMEZONE,
    ATHENAEUM_HOST_HEADER,
    ATHENAEUM_URL,
    CODEBASE_SEARCHER_URL,
    HINDSIGHT_BANK_ID,
    HINDSIGHT_URL,
    IRIS_URL,
    UPLOADS_DIR,
    VAULT_KEEPER_URL,
)
from app import chore_chat, db, documents, habit_chat, music, planner_db, show_chat, tone_analysis, web, workout_chat
from app.pod_go_reference import AMPS_CLEAN, AMPS_CRUNCH, AMPS_HIGH_GAIN, CABS_COMMON, EFFECTS_SHORT

logger = logging.getLogger("hermes")


def search_vault(query: str) -> str:
    response = httpx.post(
        f"{ATHENAEUM_URL}/search",
        json={"query": query, "top_k": 5},
        headers={"Host": ATHENAEUM_HOST_HEADER},
        timeout=30.0,
    )
    response.raise_for_status()
    matches = response.json()["matches"]
    if not matches:
        return "No relevant notes found."
    return "\n\n".join(f"[{m['source']}]\n{m['text']}" for m in matches)


def list_notes(folder: str) -> str:
    response = httpx.post(
        f"{ATHENAEUM_URL}/browse",
        json={"folder": folder},
        headers={"Host": ATHENAEUM_HOST_HEADER},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("error"):
        return data["error"]

    matched = data.get("matched_folders", [])
    if not matched:
        top_level = ", ".join(data.get("top_level_folders", []))
        return (
            f"No folder matching '{folder}' found. "
            f"Top-level folders in the vault: {top_level}"
        )

    sections = []
    for match in matched:
        files = "\n".join(f"  - {f}" for f in match["files"]) or "  (no .md files)"
        sections.append(f"Folder: {match['folder']}\n{files}")
    return "\n\n".join(sections)


def generate_image(prompt: str, conversation_id: str | None = None) -> str:
    response = httpx.post(
        f"{IRIS_URL}/generate",
        json={"prompt": prompt, "conversation_id": conversation_id},
        timeout=120.0,  # image generation is much slower than a text tool call
    )
    response.raise_for_status()
    image_url = response.json()["image_url"]
    # Markdown image syntax — Hermes' renderer displays this as an actual
    # <img>, not just a link (see static/index.html's renderMarkdown).
    return f"![{prompt}]({image_url})"


def save_project_memory(content: str) -> str:
    response = httpx.post(
        f"{HINDSIGHT_URL}/v1/default/banks/{HINDSIGHT_BANK_ID}/memories",
        json={"items": [{"content": content}]},
        timeout=60.0,
    )
    response.raise_for_status()
    return "Saved to project memory."


def recall_project_memory(query: str) -> str:
    response = httpx.post(
        f"{HINDSIGHT_URL}/v1/default/banks/{HINDSIGHT_BANK_ID}/memories/recall",
        json={"query": query},
        timeout=30.0,
    )
    response.raise_for_status()
    results = response.json()["results"]
    if not results:
        return "No relevant project memory found."
    return "\n\n".join(f"[{r['type']}] {r['text']}" for r in results)


QUADRANT_LABELS = {
    "do": "TODO",
    "schedule": "Schedule / plan",
    "next": "NEXT",
    "backlog": "Backlog",
}


def add_task(title: str, quadrant: str, due_date: str | None = None) -> str:
    task = planner_db.create_task(title, quadrant=quadrant, due_date=due_date)
    return f"Added task #{task['id']}: \"{task['title']}\" ({QUADRANT_LABELS[task['quadrant']]})."


def list_tasks(status: str = "open") -> str:
    tasks = planner_db.list_tasks(status=status)
    if not tasks:
        return f"No {status} tasks."
    lines = []
    for task in tasks:
        due = f" (due {task['due_date']})" if task["due_date"] else ""
        lines.append(f"#{task['id']} {task['title']} [{QUADRANT_LABELS[task['quadrant']]}]{due}")
    return "\n".join(lines)


def complete_task(title: str) -> str:
    matches = planner_db.find_open_tasks_by_title(title)
    if not matches:
        return f"No open task matching \"{title}\" found."
    if len(matches) > 1:
        options = "\n".join(f"#{m['id']} {m['title']}" for m in matches)
        return f"Multiple open tasks match \"{title}\" — which one?\n{options}"
    planner_db.complete_task(matches[0]["id"])
    return f"Marked \"{matches[0]['title']}\" done."


def log_habit(name: str, amount: float | None = None, unit: str | None = None, when: str | None = None) -> str:
    return habit_chat.log(name, amount, unit, when)


def habit_status(name: str | None = None) -> str:
    return habit_chat.status(name)


def log_chore(name: str, when: str | None = None) -> str:
    return chore_chat.log(name, when)


def chore_status(name: str | None = None) -> str:
    return chore_chat.status(name)


def add_chore(name: str, every_days: int | None = None) -> str:
    return chore_chat.add(name, every_days)


def lift_history(exercise: str | None = None) -> str:
    return workout_chat.lifts(exercise)


def activity_totals(activity: str | None = None, period: str | None = None) -> str:
    return workout_chat.activity_totals(activity, period)


def show_status(title: str | None = None) -> str:
    return show_chat.status(title)


def update_show(title: str | None = None, season: int | None = None, episode: int | None = None,
                status: str | None = None, finished_season: int | None = None) -> str:
    return show_chat.update(title, season, episode, status, finished_season)


def add_show(title: str, kind: str = "tv", status: str | None = None, season: int | None = None,
             episode: int | None = None, recommended_by: str | None = None) -> str:
    return show_chat.add(title, kind, status, season, episode, recommended_by)


_WEEKDAY_NAMES = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}


def add_todo_item(
    text: str,
    list_name: str | None = None,
    recurrence_days: int | None = None,
    recurrence_weekdays: str | None = None,
) -> str:
    todo_list = planner_db.get_or_create_todo_list(list_name or "General")
    item = planner_db.create_todo_item(
        todo_list["id"], text, recurrence_days=recurrence_days, recurrence_weekdays=recurrence_weekdays
    )
    if recurrence_days:
        suffix = f" — repeats every {recurrence_days} days"
    elif recurrence_weekdays:
        names = [_WEEKDAY_NAMES[int(d)] for d in recurrence_weekdays.split(",") if d]
        suffix = f" — repeats every {', '.join(names)}"
    else:
        suffix = ""
    return f"Added \"{item['text']}\" to \"{todo_list['name']}\"{suffix}."


def _format_todo_item(item: dict, with_list: bool) -> str:
    due = f" (due {item['due_date']})" if item.get("due_date") else ""
    prefix = f"[{item['list_name']}] " if with_list else ""
    return f"{prefix}{item['text']}{due}"


def list_todo_items(list_name: str | None = None) -> str:
    if list_name:
        todo_list = planner_db.find_todo_list_by_name(list_name)
        if not todo_list:
            return f"No todo list matching \"{list_name}\" found."
        items = [i for i in planner_db.list_todo_items(todo_list["id"]) if not i["done"]]
        if not items:
            return f"Nothing open on \"{todo_list['name']}\"."
        lines = [_format_todo_item({**i, "list_name": todo_list["name"]}, with_list=False) for i in items]
        return f"\"{todo_list['name']}\":\n" + "\n".join(f"- {line}" for line in lines)

    items = planner_db.list_all_open_todo_items()
    if not items:
        return "Nothing on any todo list."
    return "\n".join(f"- {_format_todo_item(i, with_list=True)}" for i in items)


def complete_todo_item(text: str, list_name: str | None = None) -> str:
    list_id = None
    if list_name:
        todo_list = planner_db.find_todo_list_by_name(list_name)
        if not todo_list:
            return f"No todo list matching \"{list_name}\" found."
        list_id = todo_list["id"]

    matches = planner_db.find_open_todo_items_by_text(text, list_id=list_id)
    if not matches:
        return f"No open item matching \"{text}\" found."
    if len(matches) > 1:
        options = "\n".join(f"- {m['text']} [{m['list_name']}]" for m in matches)
        return f"Multiple items match \"{text}\" — which one?\n{options}"
    updated = planner_db.update_todo_item(matches[0]["id"], done=True)
    # A recurring item doesn't stay checked off — it's reset to open with
    # the next due date. Say so, rather than a flat "checked off" that
    # would misleadingly suggest it's gone from the list for good.
    if updated["recurrence_days"]:
        return f"Checked off \"{matches[0]['text']}\" — repeats every {updated['recurrence_days']} days, next due {updated['due_date']}."
    return f"Checked off \"{matches[0]['text']}\" on \"{matches[0]['list_name']}\"."


def _note_title(content: str) -> str:
    first_line = next((line.strip() for line in content.split("\n") if line.strip()), "")
    return first_line or "Untitled note"


def add_scratch_note(content: str) -> str:
    planner_db.create_note_with_content(content)
    return f"Saved note: \"{_note_title(content)}\"."


def search_scratch_notes(query: str) -> str:
    matches = planner_db.search_notes_content(query)
    if not matches:
        return "No matching notes found."
    return "\n".join(f"- {_note_title(m['content'])}" for m in matches)


def list_recent_scratch_notes() -> str:
    notes = planner_db.list_recent_notes(limit=10)
    if not notes:
        return "No notes yet."
    return "\n".join(f"- {_note_title(n['content'])}" for n in notes)


def save_scratch_note_to_vault(query: str, folder: str | None = None) -> str:
    # Copies a Notes-page scratch note into the vault (see app/note_export.py).
    # Found by its text, like search_scratch_notes, because the model never
    # sees note ids; if the words match several notes, ask rather than guess.
    from app import note_export

    matches = planner_db.search_notes_content(query)
    if not matches:
        return f"No scratch note matches \"{query}\"."
    if len(matches) > 1:
        options = "\n".join(f"- {_note_title(m['content'])}" for m in matches)
        return f"Several scratch notes match \"{query}\". Which one?\n{options}"
    try:
        result = note_export.export_note(matches[0]["id"], folder)
    except note_export.ExportRefused as exc:
        return f"Not saved: {exc}"
    title = _note_title(matches[0]["content"])
    if result["already"]:
        return f"\"{title}\" is already in the vault at {result['vault_path']}."
    return f"Copied \"{title}\" to the vault at {result['vault_path']}. The scratch note is still in Notes."


# How long research_repo will keep waiting for a repo analysis. A first-time
# index of a big repo (tens of thousands of chunks on the GPU) can take most
# of an hour; the work continues on the server either way, this only bounds
# how long the chat waits for it.
RESEARCH_MAX_WAIT_SECONDS = 90 * 60
RESEARCH_POLL_SECONDS = 2.0


def _research_result(repo: str, question: str | None, data: dict) -> str:
    lines = [f"Indexed {repo} at commit {data['commit'][:8]}."]
    hits = data.get("hits") or []
    is_overview = data.get("is_overview", not question)
    if hits:
        # Actual content, not just file paths — otherwise there's nothing
        # here for the model to summarize or answer from, and it can only
        # say "I found some files" instead of describing what's in them.
        # Confirmed live: without this, a no-question research_repo call
        # produced no summary at all, just "indexed, note written."
        label = "Representative snippets for a general overview:" if is_overview else f"Relevant snippets for \"{question}\":"
        lines.append(label)
        for hit in hits[:5]:
            content = hit["content"][:800]
            lines.append(f"\n--- {hit['file_path']} ---\n{content}")
    elif question:
        lines.append(f"No snippets matched \"{question}\".")
    if data.get("note_path") and data.get("note_reused"):
        # Same commit as an already-existing overview note — CodebaseSearcher
        # skipped writing a duplicate rather than creating another one.
        lines.append(f"\n(Already have an up-to-date overview of this repo in the vault at: {data['note_path']})")
    elif data.get("note_path"):
        lines.append(f"\nFindings written to the vault at: {data['note_path']}")
    elif data.get("note_error"):
        lines.append(f"\n(Couldn't write the findings note: {data['note_error']})")
    return "\n".join(lines)


def research_repo(repo: str, question: str | None = None, progress=None, **_ignored) -> str:
    """Clones/indexes the repo on the homelab and returns relevant snippets.

    A first look at a big repo takes far longer than one HTTP request should
    stay open, so this starts a background job on CodebaseSearcher and polls
    it, passing each progress message to `progress` (the chat shows it).
    Falls back to the old single blocking call if the service predates the
    job API, so the two can be deployed in either order."""
    start = httpx.post(
        f"{CODEBASE_SEARCHER_URL}/research/start", json={"repo": repo, "question": question}, timeout=30.0
    )
    if start.status_code == 404:
        response = httpx.post(
            f"{CODEBASE_SEARCHER_URL}/research", json={"repo": repo, "question": question}, timeout=300.0
        )
        response.raise_for_status()
        return _research_result(repo, question, response.json())
    start.raise_for_status()
    job = start.json()

    deadline = time.monotonic() + RESEARCH_MAX_WAIT_SECONDS
    last_message = None
    failures = 0
    while True:
        try:
            poll = httpx.get(f"{CODEBASE_SEARCHER_URL}/research/jobs/{job['id']}", timeout=15.0)
            if poll.status_code == 404:
                raise RuntimeError("The analysis service restarted while this was running; ask again to start it over.")
            poll.raise_for_status()
            failures = 0
        except RuntimeError:
            raise
        except httpx.HTTPError as exc:
            # A blip while polling is not a failed analysis; the job keeps going.
            failures += 1
            if failures >= 5:
                raise RuntimeError(f"Lost contact with the analysis service: {exc}")
            time.sleep(RESEARCH_POLL_SECONDS)
            continue

        snap = poll.json()
        if snap["stage"] == "done":
            # Reloading the chat model after the GPU handoff takes a while;
            # say so instead of leaving the last progress line on screen.
            if progress:
                progress("Analysis finished. Writing up the results…")
            return _research_result(repo, question, snap["result"])
        if progress and snap.get("message") and snap["message"] != last_message:
            last_message = snap["message"]
            progress(last_message)
        if snap["stage"] == "error":
            raise RuntimeError(snap.get("error") or "The analysis failed.")
        if time.monotonic() > deadline:
            raise RuntimeError(
                "Still working after 90 minutes. The analysis keeps running on the server; ask again later and it will pick up the finished index."
            )
        time.sleep(RESEARCH_POLL_SECONDS)


def forget_repo(repo: str) -> str:
    response = httpx.post(f"{CODEBASE_SEARCHER_URL}/forget", json={"repo": repo}, timeout=30.0)
    response.raise_for_status()
    return f"Deleted the local clone and index for \"{repo}\". Any findings notes already in the vault are untouched."


def write_vault_note(folder: str, filename: str, content: str | None = None, conversation_id: str | None = None) -> str:
    # General-purpose vault write, through vault-keeper (which owns the
    # clone, the write-scoped deploy key and the write limits).
    #
    # content is optional on purpose: the common case ("save that plan
    # you just wrote") would otherwise force the model to retype
    # something it already produced, verbatim, as a JSON tool-call
    # argument — slow (nothing streams to the user until the whole
    # argument is generated, confirmed live: a multi-KB plan blew past
    # the frontend's 45s stall timeout with zero bytes sent) and risky
    # (the same long-string retyping corruption already seen and fixed
    # for generate_image's image URLs, just for text instead of a URL).
    # Omitted content pulls the conversation's own last assistant reply
    # straight from storage instead — instant, and guaranteed byte-exact.
    if not content:
        if not conversation_id:
            raise ValueError("No content given, and no conversation to pull the last message from.")
        content = db.get_last_assistant_message(conversation_id)
        if not content:
            raise ValueError("No previous assistant message found in this conversation to save — pass content explicitly.")

    response = httpx.post(
        f"{VAULT_KEEPER_URL}/write_note",
        json={"folder": folder, "filename": filename, "content": content},
        timeout=30.0,
    )
    # 403 is vault-keeper's policy refusing (wrong folder, too
    # big, daily cap). Its detail says what is allowed, so hand it to the
    # model as the result rather than raising: the model can then tell the
    # user, or retry under an allowed folder.
    if response.status_code == 403:
        return f"Not saved: {response.json().get('detail', 'refused by the vault write limits')}"
    response.raise_for_status()
    note_path = response.json()["note_path"]
    return f"Saved to the vault at: {note_path}"


def read_vault_note(path: str) -> str:
    # The note's whole current text. search_vault only returns snippets, so
    # this is what makes an accurate suggest_vault_edit possible.
    response = httpx.post(f"{VAULT_KEEPER_URL}/read_note", json={"path": path}, timeout=30.0)
    if response.status_code in (403, 404):
        return f"Can't read it: {response.json().get('detail', 'not found')}"
    response.raise_for_status()
    return response.json()["content"]


def suggest_vault_edit(path: str, proposed_content: str, reason: str) -> str:
    # Existing vault notes are never edited directly. This files a suggestion
    # note (diff + full proposed text) under 01 Hermes/Suggestions/ for the
    # user to review in Obsidian. proposed_content is the note's *whole*
    # new text, since vault-keeper diffs it against the current file.
    response = httpx.post(
        f"{VAULT_KEEPER_URL}/suggest_edit",
        json={"path": path, "proposed_content": proposed_content, "reason": reason},
        timeout=30.0,
    )
    if response.status_code == 403:
        return f"Not filed: {response.json().get('detail', 'refused by the vault write limits')}"
    response.raise_for_status()
    note_path = response.json()["note_path"]
    return (
        f"Filed a suggestion at {note_path}. The original note was not changed; "
        f"the user reviews and applies it in Obsidian."
    )


def _local_now() -> datetime:
    return datetime.now(ZoneInfo(APP_TIMEZONE))


def log_to_daily_note(text: str) -> str:
    # One line under the "Hermes" section of today's daily note. Append-only
    # and today-only by construction: vault-keeper enforces that, this just
    # supplies the user's local date and time (it only knows UTC).
    now = _local_now()
    response = httpx.post(
        f"{VAULT_KEEPER_URL}/daily/append",
        json={"text": text, "date": now.date().isoformat(), "time": now.strftime("%H:%M")},
        timeout=60.0,
    )
    if response.status_code == 403:
        return f"Not logged: {response.json().get('detail', 'refused by the vault write limits')}"
    response.raise_for_status()
    data = response.json()
    if data["fallback"]:
        return (
            f"Logged \"{data['entry']}\" in {data['note_path']}. Today's daily note doesn't exist in the vault "
            f"yet (Obsidian creates it when it's opened), so it went to a log note for the day instead."
        )
    return f"Logged to today's daily note: {data['entry']}"


def add_to_backlog(text: str, column: str = "Ideas") -> str:
    # One card on the dev backlog board in the vault (vault-keeper's
    # /backlog/add: add-only, Ideas, Backlog, Ready or Bugs, no duplicates). Moving or
    # finishing cards is not possible from here by design.
    response = httpx.post(
        f"{VAULT_KEEPER_URL}/backlog/add",
        json={"text": text, "column": column or None},
        timeout=60.0,
    )
    if response.status_code in (403, 404, 409):
        return f"Not added: {response.json().get('detail', 'refused by the vault write limits')}"
    response.raise_for_status()
    data = response.json()
    if not data["added"]:
        return f"That card is already on the backlog: {data['card']}"
    return f"Added to the {data['column']} column of the dev backlog: {data['card']}"


def read_daily_note() -> str:
    # Today's whole daily note, so the model can answer from it or avoid
    # logging something that is already there.
    response = httpx.post(
        f"{VAULT_KEEPER_URL}/daily/read", json={"date": _local_now().date().isoformat()}, timeout=30.0
    )
    response.raise_for_status()
    data = response.json()
    if not data["exists"]:
        return "There is no daily note for today in the vault yet (Obsidian creates it when it's opened)."
    return f"--- {data['path']} ---\n{data['content']}\n--- end ---"


def read_attachment(filename: str | None = None, conversation_id: str | None = None) -> str:
    # A document's or voice memo's extracted text is normally only in
    # context for the turn it's attached on (see add_attachment's
    # docstring — deliberately not replayed every turn like images, to
    # avoid resending a whole PDF/transcript on every later message).
    # This is the escape hatch: called on-demand when the user refers
    # back to one instead of eagerly carrying its text forward forever.
    if not conversation_id:
        return "No conversation to look up an attachment in."
    matches = db.find_text_attachments(conversation_id, filename)
    if not matches:
        if filename:
            return f"No document or voice memo matching \"{filename}\" found in this conversation."
        return "No documents or voice memos have been attached in this conversation."
    if len(matches) > 1:
        options = ", ".join(m["original_filename"] or "unnamed" for m in matches)
        return f"Multiple attachments match: {options}. Say which one you mean."
    doc = matches[0]
    return f"--- {doc['original_filename']} ---\n{documents.cap_text(doc['extracted_text'])}\n--- end ---"


def _resolve_audio_attachment(filename: str | None, conversation_id: str | None) -> tuple[str | None, str | None]:
    """Shared by analyze_chords/transcribe_melody: looks up the raw audio
    file itself (unlike find_text_attachments, doesn't require an existing
    transcript — a song upload has no reason to have gone through speech
    transcription). Returns (local_path, None) on a single match, or
    (None, message) to hand straight back as the tool's result."""
    if not conversation_id:
        return None, "No conversation to look up an attached audio file in."
    matches = db.find_audio_attachments(conversation_id, filename)
    if not matches:
        if filename:
            return None, f"No audio file matching \"{filename}\" found in this conversation."
        return None, "No audio has been attached in this conversation."
    if len(matches) > 1:
        options = ", ".join(m["original_filename"] or "unnamed" for m in matches)
        return None, f"Multiple audio files match: {options}. Say which one you mean."
    return os.path.join(UPLOADS_DIR, matches[0]["path"]), None


def analyze_chords(filename: str | None = None, conversation_id: str | None = None) -> str:
    local_path, error = _resolve_audio_attachment(filename, conversation_id)
    if error:
        return error
    result = music.detect_chords(local_path)
    return result or (
        "Couldn't detect a clear chord progression in that audio — it may be too short, too quiet, "
        "or not tonal/harmonic content (e.g. pure drums or noise)."
    )



def suggest_pod_go_tone(filename: str | None = None, conversation_id: str | None = None) -> str:
    # A best-guess starting point, not a precise match — measures real
    # acoustic characteristics (brightness, gain, compression, modulation,
    # echo, reverb tail) from the audio and hands them to you alongside
    # real POD Go model names so you reason from measured data to a real
    # signal chain, instead of guessing blind or inventing plausible-
    # sounding fake model names.
    local_path, error = _resolve_audio_attachment(filename, conversation_id)
    if error:
        return error
    result = tone_analysis.analyze_tone(local_path)
    return result or (
        "Couldn't extract usable tone characteristics from that audio — it may be too short, too quiet, "
        "or too noisy to measure."
    )


def pod_go_models(gain: str = "crunch", **_ignored) -> str:
    """The no-audio counterpart to suggest_pod_go_tone: the model has worked
    out roughly how much gain the target tone has (from what it knows about
    the artist, a web search, or the user's own description) and asks for the
    real POD Go model names that fit, instead of inventing plausible-sounding
    ones. Always includes the modulation/delay/reverb lists (a short ~650
    characters in total) rather than asking the model which it wants: when it
    was asked, it recommended effects it hadn't requested a list for. Kept to
    a short, gain-matched amp list for the same reason as tone_analysis —
    handing gemma the full catalog broke it."""
    gain = (gain or "crunch").strip().lower().replace(" ", "_").replace("-", "_")
    if gain in ("lead", "heavy", "metal", "distorted"):
        gain = "high_gain"
    amps = {"clean": AMPS_CLEAN, "crunch": AMPS_CRUNCH, "high_gain": AMPS_HIGH_GAIN}.get(gain)
    if amps is None:
        gain, amps = "crunch", AMPS_CRUNCH

    lines = [
        f"Real POD Go models for a {gain.replace('_', ' ')} tone. This is a best guess from a description, "
        "not measured from audio — say so. Choose ONLY from these names; never invent one.",
        "",
        "Amp models (pick the closest-sounding real amp):",
        amps,
        "",
        "Cab models:",
        CABS_COMMON,
    ]
    # Gain pedals only matter if the tone isn't already clean.
    if gain != "clean":
        lines += ["", "Distortion/drive models:", EFFECTS_SHORT["distortion"]]
    lines += [
        "",
        "Modulation models (chorus/flanger/phaser/tremolo):",
        EFFECTS_SHORT["modulation"],
        "",
        "Delay models:",
        EFFECTS_SHORT["delay"],
        "",
        "Reverb models:",
        EFFECTS_SHORT["reverb"],
    ]
    return "\n".join(lines)


def web_search(query: str, max_results: int = 5, **_ignored) -> str:
    return web.search(query, max_results)


def read_webpage(url: str, **_ignored) -> str:
    return web.read_page(url)


def transcribe_melody(filename: str | None = None, conversation_id: str | None = None) -> str:
    local_path, error = _resolve_audio_attachment(filename, conversation_id)
    if error:
        return error
    result = music.transcribe_melody(local_path)
    return result or (
        "Couldn't pick out a clear melody/riff from that audio — it may be too short, too dense/polyphonic, "
        "or mostly percussive."
    )


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_vault",
            "description": (
                "Semantic search over the user's Obsidian notes — use for questions "
                "about what notes say or contain, e.g. 'what do my notes say about X'. "
                "Not for listing files in a folder — use list_notes for that."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for in the user's notes",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": (
                "List the actual note files that exist under a folder in the user's "
                "Obsidian vault, by folder name (fuzzy/partial match is fine, e.g. "
                "'Burn St Productions'). Use this for 'what files/notes are in folder X' "
                "questions — NOT for questions about note content, use search_vault "
                "for that instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "description": "The folder name to look for (partial match is fine)",
                    }
                },
                "required": ["folder"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": (
                "Generate an image from a text description. Use when the user asks "
                "to create, draw, generate, or make an image/picture of something."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Description of the image to generate",
                    }
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_project_memory",
            "description": (
                "Save a durable fact or decision to persistent project memory — "
                "specifically for VST/audio plugin development work (framework "
                "choices, why something was picked over an alternative, bugs found "
                "and how they were fixed, concrete outcomes of trying something). "
                "Do NOT use this for routine questions, small talk, or anything "
                "that didn't land on an actual decision or fact worth recalling "
                "months from now — most messages should NOT trigger this."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The fact or decision to remember, written as a standalone statement",
                    }
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_project_memory",
            "description": (
                "Search persistent project memory for past VST/audio plugin "
                "development decisions and facts. Use when the user references "
                "earlier project decisions or asks something like 'what did we "
                "decide about X' or 'why did we choose Y' for the VST work."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for in project memory",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": (
                "Add a to-do item to one of four quadrants. Use whenever the user "
                "asks to add/remember a task or to-do, picking the quadrant that "
                "best fits from context if the user doesn't say explicitly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short description of the task"},
                    "quadrant": {
                        "type": "string",
                        "enum": ["do", "schedule", "next", "backlog"],
                        "description": (
                            "'do' = do first, time-sensitive and matters now. "
                            "'schedule' = matters but isn't urgent, plan time for it. "
                            "'next' = urgent but low-stakes, a quick thing to knock out. "
                            "'backlog' = neither urgent nor important, someday/maybe."
                        ),
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Due date in YYYY-MM-DD format, if the user gave one",
                    },
                },
                "required": ["title", "quadrant"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": (
                "List to-do items, with which quadrant each is in. Use for 'what's "
                "on my plate', 'what do I need to do', or questions about the "
                "quadrant board. Defaults to open tasks only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["open", "done"],
                        "description": "Which tasks to list (default: open)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": (
                "Mark a to-do item done, matched by title text (partial match is "
                "fine). Use when the user says they finished, did, or completed "
                "something that sounds like a tracked task."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The task's title, or a fragment of it"}
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_habit",
            "description": (
                "Record that the user did a habit, with a number if they give one, e.g. 'meditated this "
                "morning', 'practiced bass for 45 minutes', 'played bass for an hour yesterday', 'read 20 pages', 'I weigh 182'. Use when they "
                "report something they track as a habit, never for a question. Call it for every report: "
                "nothing is saved unless you do."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The habit's name, e.g. 'meditate' or 'run'"},
                    "amount": {"type": "number", "description": "Only a number the user said"},
                    "unit": {"type": "string", "description": "The unit the user used, e.g. 'minutes' or 'hours'"},
                    "when": {
                        "type": "string",
                        "description": "Only if not today, as said: 'yesterday', 'saturday' or YYYY-MM-DD",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "habit_status",
            "description": (
                "Report habits: totals or latest value for ones that count something (e.g. 'how much did "
                "I practice this week?'), streaks and the last 7 days' actual logged/missed dates "
                "for habits being tracked — use this for anything about recent "
                "consistency or patterns (e.g. 'how did I do this week', 'did I "
                "miss meditating on Tuesday'), not just the current streak number. "
                "Omit `name` to list every tracked habit."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "A specific habit to check, or omit for all"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_chore",
            "description": (
                "Record that the user did a household chore, e.g. 'I dusted the ceiling fans' or "
                "'descaled the coffee maker yesterday'. The chore stays on the list. Only call this "
                "when they say they did it, never for a question about it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The chore, in the user's words or its exact name"},
                    "when": {
                        "type": "string",
                        "description": (
                            "The day it was done, as the user said it: 'today' (default), 'yesterday', "
                            "'saturday', 'last saturday', '3 days ago' or YYYY-MM-DD"
                        ),
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "chore_status",
            "description": (
                "When a household chore was last done and which are due, e.g. 'when did I last descale "
                "the coffee maker?' or 'what chores are due?'. Omit `name` for all chores. Answer with "
                "the dates and day counts returned; don't work them out yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "One chore, or omit for all"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_chore",
            "description": "Add a new chore to the chores list. Only when the user asks for it to be added.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Short chore name, e.g. 'Dust ceiling fans'"},
                    "every_days": {"type": "integer", "description": "How often, in days, only if the user says"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lift_history",
            "description": (
                "The user's logged weight lifting at the gym: when they last did an exercise, what they lifted, "
                "and their personal best, e.g. 'when did I last bench?', 'what's my best leg press?' or 'what "
                "are my PRs?' (PR means personal record here). Use this, not the vault, for lifting. Omit "
                "`exercise` for the latest gym days and all personal bests. Read-only: it can't record "
                "anything. Answer with the dates and numbers returned; don't work any out yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise": {"type": "string", "description": "The exercise in the user's words, or omit"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "activity_totals",
            "description": (
                "Totals for logged activities such as walks: times, minutes and miles, e.g. 'how far have "
                "I walked this week?' or 'when was my last walk?'. Read-only: chat can't record an "
                "activity, so if the user reports one, say to add it with the + button on the Fitness "
                "page. Answer with the totals returned; don't add them up yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "activity": {"type": "string", "description": "e.g. 'walk'. Omit for every activity."},
                    "period": {
                        "type": "string",
                        "description": (
                            "Only if the user names one: 'today', 'yesterday', 'this week', 'last week', "
                            "'this month', 'last month', 'this year', 'all time' or 'last N days'"
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "show_status",
            "description": (
                "The user's TV and movie list: what they're watching, where they are in it, what's coming "
                "back, what others recommended and what they want to watch, e.g. 'what was I watching?' or 'when is 3 Body Problem "
                "back?'. Omit `title` for the whole list. Answer only from what is returned."
            ),
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string", "description": "One title, or omit for all"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_show",
            "description": (
                "Save the user's progress in a TV show or movie, e.g. 'I'm on episode 4', 'finished Dark "
                "Matter', 'I started Silicon Valley', 'pausing Devs', 'watched another episode'. Call it every "
                "time they report watching something, even straight after an earlier update and even with no "
                "title: nothing is saved unless you call it. Also call it to move a title, e.g. 'add it to "
                "my want to watch list' for a recommended one. Never call it for a question."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The title as the user said it. Omit if they didn't name one; don't guess.",
                    },
                    "season": {"type": "integer", "description": "Only if the user says a season number"},
                    "episode": {"type": "integer", "description": "Only if the user says an episode number"},
                    "finished_season": {
                        "type": "integer",
                        "description": "The season they say they finished, when the show isn't over",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["watching", "done", "paused", "want", "waiting", "recommended"],
                        "description": (
                            "'done' means finished the whole show or movie; for one season use "
                            "finished_season instead. Omit when they only give a season or episode."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_show",
            "description": (
                "Add a TV show or movie to the user's watch list. Only for things to watch, and only when "
                "they ask for it to be added or say someone recommended it to them (e.g. 'Sam recommended "
                "Severance' or 'my brother told me to watch Arrival': add those straight away as recommended, "
                "without asking first. Never add your own suggestions. Groceries and to-dos go on to-do lists."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "kind": {"type": "string", "enum": ["tv", "movie"]},
                    "status": {
                        "type": "string",
                        "enum": ["want", "watching", "recommended"],
                        "description": (
                            "'recommended' when someone else suggested it; 'watching' only if they say "
                            "they've started it; otherwise 'want'"
                        ),
                    },
                    "season": {"type": "integer", "description": "Only if the user said where they are"},
                    "episode": {"type": "integer", "description": "Only if the user said where they are"},
                    "recommended_by": {"type": "string", "description": "Who suggested it, only if the user says"},
                },
                "required": ["title", "kind"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_todo_item",
            "description": (
                "Add an item to a plain everyday to-do list (groceries, errands, "
                "life stuff) — a different thing from add_task, which is for "
                "\"The Board\" (the music-production/dev task board). Use this "
                "one for casual 'add X to my list' requests that aren't project "
                "work. If the named list doesn't exist yet it's created; if the user doesn't "
                "name a list, it goes on \"General\". For something that repeats on a "
                "fixed interval ('remind me to take out the trash every 3 days', "
                "'water the plants weekly'), set recurrence_days. For something that "
                "repeats on specific days of the week ('every Monday and Thursday', "
                "'gym on weekdays'), set recurrence_weekdays instead. Only set one of "
                "the two. Either way, checking the item off resets it to open with the "
                "due date pushed to the next occurrence, instead of leaving it checked "
                "off for good."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The item to add"},
                    "list_name": {
                        "type": "string",
                        "description": "Which list, e.g. 'groceries' or 'errands' (fuzzy match; omit for the general list)",
                    },
                    "recurrence_days": {
                        "type": "integer",
                        "description": "Fixed-interval recurrence, in days (1 for daily, 7 for weekly, etc.) — omit for a normal one-off item, or if using recurrence_weekdays instead.",
                    },
                    "recurrence_weekdays": {
                        "type": "string",
                        "description": "Specific-weekday recurrence: comma-separated ISO weekday numbers, 1=Monday through 7=Sunday (e.g. '1,3,5' for Mon/Wed/Fri, '1,2,3,4,5' for weekdays). Omit for a normal one-off item, or if using recurrence_days instead.",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_todo_items",
            "description": (
                "List open (not checked off) items from the everyday to-do lists. "
                "Use for 'what's on my todo/grocery/errands list' — not for "
                "\"The Board\", use list_tasks for that. Omit list_name to see "
                "everything across all lists."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "list_name": {"type": "string", "description": "A specific list to check (fuzzy match), or omit for all"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_todo_item",
            "description": (
                "Check an item off an everyday to-do list, matched by its text "
                "(partial match is fine). Use when the user says they picked up, "
                "did, or finished something that sounds like a todo-list item, "
                "not \"The Board\" — use complete_task for that instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The item's text, or a fragment of it"},
                    "list_name": {"type": "string", "description": "Which list to look in (fuzzy match), if known — helps disambiguate"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_scratch_note",
            "description": (
                "Save a quick freeform note to the user's Notes scratchpad — for "
                "when the user explicitly asks to jot something down, write that "
                "down, or save a note. This is a lightweight, unfiltered capture "
                "spot meant to be copied into Obsidian later, NOT the curated "
                "save_project_memory (which is specifically for durable VST/audio "
                "project decisions) — use whichever the user's request actually "
                "matches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The note's text, exactly as the user wants it captured"}
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_scratch_notes",
            "description": "Search the user's Notes scratchpad by content. Use for 'did I write anything down about X' or similar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for in the user's notes"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_recent_scratch_notes",
            "description": "List the user's most recently edited notes from the Notes scratchpad, most recent first. Use for 'what have I jotted down lately'.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_repo",
            "description": (
                "Look at any GitHub repo on demand — the user's own, or anyone else's public "
                "repo: clones/updates it, semantically searches its code for `question` if "
                "given, and writes the findings as a note in the user's Obsidian vault. Use "
                "when the user says something like 'check out my X repo', 'look into how Y's "
                "repo handles Z', or pastes a GitHub URL — this is a one-shot look, not a "
                "standing index, so call it again if they ask about the same repo later (it "
                "only re-indexes if the repo actually changed since last time, so repeat "
                "calls are cheap)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": (
                            "Pass through exactly what the user gave you — do not shorten or "
                            "rewrite it. A full GitHub URL if they pasted one (e.g. "
                            "'https://github.com/someone/their-repo'), 'owner/repo' if they "
                            "named someone else's repo that way (e.g. 'someone/their-repo'), "
                            "or just the bare name (e.g. 'Hermes') only when it's the user's "
                            "own repo. Stripping a third-party URL down to a bare name is "
                            "wrong — it gets resolved as if it were the user's own repo of "
                            "that name, which will fail."
                        ),
                    },
                    "question": {
                        "type": "string",
                        "description": "What to look for in the repo's code, if the user asked something specific. Omit for a general first look.",
                    },
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_repo",
            "description": (
                "Delete a previously-researched repo's local clone and search index — use "
                "when the user says a repo they had you check out wasn't useful/relevant "
                "and they want it cleaned up. Does not delete any findings note already "
                "written to the vault; only the disposable, regenerable cache."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "The repo's name, matching what was passed to research_repo"}
                },
                "required": ["repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_vault_note",
            "description": (
                "Save a note in the user's Obsidian vault, at whatever folder they specify — "
                "e.g. 'write this up as a note', 'save that plan to my vault', or pasting a "
                "path like '10 Development/Tech Plans'. Not for codebase research findings — "
                "research_repo already writes those itself. Always creates a new file; never "
                "overwrites an existing one (auto-suffixes on a name collision instead). "
                "Notes can go in any vault folder except hidden ones (starting with '.'), "
                "and only as .md files. Changing an existing note is a different "
                "tool: suggest_vault_edit. "
                "Omit `content` whenever you're saving something you (the assistant) already "
                "wrote earlier in this conversation — it saves your actual last message "
                "byte-for-byte, which is faster and safer than retyping it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "folder": {
                        "type": "string",
                        "description": (
                            "Folder path within the vault, e.g. '10 Development/Tech Plans'. "
                            "If the user gave one combined path with the filename at the end "
                            "(e.g. '10 Development/Tech Plans/Audio Analyzer.md'), split it: "
                            "everything before the last '/' is the folder."
                        ),
                    },
                    "filename": {
                        "type": "string",
                        "description": (
                            "Filename including extension, e.g. 'audio-analyzer-plan.md'. If "
                            "the user gave a combined path, use just the last segment (e.g. "
                            "'Audio Analyzer.md'). Pick something short and descriptive if "
                            "they didn't specify a name at all."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "Only set this when writing NEW content the user is dictating or "
                            "you're composing fresh right now. Leave it out entirely when "
                            "saving something you already said earlier in this conversation "
                            "(e.g. 'write that plan to the vault') — omitting it saves your "
                            "actual last message directly, instead of you having to retype a "
                            "long response as this argument, which is slow and risks "
                            "corrupting the text."
                        ),
                    },
                },
                "required": ["folder", "filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_scratch_note_to_vault",
            "description": (
                "Copy one of the user's scratch notes (the quick-capture Notes page) into their "
                "Obsidian vault as a new note, e.g. 'put my CMake note in the vault' or 'move that "
                "scratch note to Obsidian'. It copies: the scratch note is kept. Not for saving "
                "something you wrote in conversation (use write_vault_note for that)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Words from the scratch note's text that identify it.",
                    },
                    "folder": {
                        "type": "string",
                        "description": "Vault folder to put it in. Leave out unless the user names one; the default is '01 Hermes/Imported'.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_to_daily_note",
            "description": (
                "Add one short line to the 'Hermes' section of today's daily note in the user's "
                "Obsidian vault, stamped with the current time. Use it when the user asks to log, "
                "jot down or record something for today ('log that I shelved the burl Intel work', "
                "'note in my daily that the deploy went out'). It only ever adds a line to today's "
                "note; it cannot edit anything else or other days. For anything longer than a "
                "sentence use write_vault_note instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The line to log, one sentence, no leading bullet or timestamp (both are added).",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_to_backlog",
            "description": (
                "Add a card to the DEV backlog: the Kanban board in the user's Obsidian vault that "
                "holds coding and project work for the user's AI assistants (not the personal task "
                "board, habits or todo lists). Use it when the user says to add something to the dev "
                "or coding backlog, asks to queue a code task for later, or reports a bug in one of "
                "their projects. It only adds a card to the Ideas, Backlog, Ready or Bugs column; it cannot move, edit or delete cards, and it skips cards "
                "that already exist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": (
                            "The card, one line, and it MUST start with the project (the repo folder name) and a colon, "
                            "like 'Misnomer: add a stereo width control'. If the user didn't say which project, ask "
                            "before calling this."
                        ),
                    },
                    "column": {
                        "type": "string",
                        "enum": ["Ideas", "Backlog", "Ready", "Bugs"],
                        "description": (
                            "Ideas (default) for rough thoughts that need refining, "
                            "Backlog for scoped work not yet queued, Bugs for something broken, "
                            "Ready only when the user says it is ready to be worked."
                        ),
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_daily_note",
            "description": (
                "Read today's complete daily note from the user's Obsidian vault: tasks, notes, "
                "and anything already logged. Use it for 'what's in my daily note', 'what did I "
                "log today', or before log_to_daily_note to avoid repeating a line."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_vault_note",
            "description": (
                "Read the complete text of one note in the user's Obsidian vault. search_vault "
                "only returns short snippets; use this when you need the whole note, e.g. to "
                "summarise it, answer from all of it, or before proposing a change with "
                "suggest_vault_edit. Get the exact path from search_vault or list_notes first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Vault-relative path of the .md note, e.g. '10 Development/Tech Plans/Audio Analyzer.md'.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_vault_edit",
            "description": (
                "Propose a change to a note that already exists in the user's Obsidian vault. "
                "This never edits the note: it files a suggestion (a diff plus the full proposed "
                "text) for the user to review and apply themselves. Use it for 'fix the typo in "
                "my X note', 'add this to my plan', 'tidy that note up'. Use search_vault or "
                "list_notes to find the note's exact path, then read_vault_note to get its current "
                "text, because proposed_content must be the note's WHOLE text after your change, not "
                "just the changed part. To create a brand-new note use write_vault_note."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Vault-relative path of the existing note, e.g. '10 Development/Tech Plans/Audio Analyzer.md'.",
                    },
                    "proposed_content": {
                        "type": "string",
                        "description": "The complete text the note should have after the change.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "One or two sentences on what changed and why, shown at the top of the suggestion.",
                    },
                },
                "required": ["path", "proposed_content", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_attachment",
            "description": (
                "Re-read the extracted text of a document (PDF/text/markdown) or the "
                "transcript of a voice memo the user attached earlier in this "
                "conversation. Attached documents/voice memos are only visible to you "
                "for the turn they're attached on, not carried forward automatically "
                "— call this when the user refers back to one (e.g. 'what did that "
                "PDF say about X', 'check the invoice again', 'what did I say in that "
                "voice memo') and its content isn't already visible earlier in this "
                "conversation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": (
                            "The attachment's filename, or a fragment of it, if the "
                            "user mentioned or it's otherwise known. Omit to get the "
                            "most recently attached document/voice memo, or a list to "
                            "choose from if more than one is attached in this "
                            "conversation."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_chords",
            "description": (
                "Detect the chord progression in a song or musical audio clip the user "
                "attached — not for a spoken voice memo. Use when the user asks things "
                "like 'what chords is this', 'what's the progression', 'work out the "
                "changes for this song'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": (
                            "The audio file's filename, or a fragment of it, if known. "
                            "Omit to use the most recently attached audio, or a list to "
                            "choose from if more than one is attached in this conversation."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pod_go_models",
            "description": (
                "Get the REAL Line 6 POD Go amp, cab and effect model names that fit a "
                "described guitar tone, so you can recommend a signal chain without an "
                "audio file. Use when the user asks how to get a song's/artist's/style's "
                "tone on their POD Go and no recording is attached: decide from what you "
                "know (or a web search) whether the tone is clean, crunch or high gain, "
                "then call this and pick from the names it returns (amp, cab and "
                "effects). Present the result as a best-guess starting point."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gain": {
                        "type": "string",
                        "enum": ["clean", "crunch", "high_gain"],
                        "description": "How much distortion the target tone has",
                    },
                },
                "required": ["gain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web. Use for things you don't reliably know or that may have "
                "changed: what gear/amp/pedals an artist used on a song, product details, "
                "current facts. Returns titles, links and snippets; use read_webpage on a "
                "result if you need its full text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to search for, e.g. 'The Midnights Heart Worth Breaking guitar amp pedals'"},
                    "max_results": {"type": "integer", "description": "How many results (default 5, max 8)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_webpage",
            "description": "Fetch one web page (a URL from web_search results or given by the user) and return its text.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "The full http(s) URL"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transcribe_melody",
            "description": (
                "Transcribe the melody or riff played in a song or musical audio clip "
                "the user attached, as a sequence of note names — not for a spoken "
                "voice memo. Use when the user asks things like 'what notes is this "
                "riff', 'transcribe this melody', 'what's this lick'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": (
                            "The audio file's filename, or a fragment of it, if known. "
                            "Omit to use the most recently attached audio, or a list to "
                            "choose from if more than one is attached in this conversation."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_pod_go_tone",
            "description": (
                "Analyze a recorded guitar/bass tone the user attached and suggest real "
                "Line 6 POD Go amp, cab, and effect models to get a similar sound — a "
                "best-guess starting point to dial in from, not an exact match. Use when "
                "the user asks things like 'what amp is this', 'how would I get this tone "
                "on my POD Go', 'help me recreate this sound'. Always use the real model "
                "names given in the tool's result — never invent a plausible-sounding one."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {
                        "type": "string",
                        "description": (
                            "The audio file's filename, or a fragment of it, if known. "
                            "Omit to use the most recently attached audio, or a list to "
                            "choose from if more than one is attached in this conversation."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
]

TOOL_HANDLERS = {
    "search_vault": search_vault,
    "list_notes": list_notes,
    "generate_image": generate_image,
    "save_project_memory": save_project_memory,
    "recall_project_memory": recall_project_memory,
    "add_task": add_task,
    "list_tasks": list_tasks,
    "complete_task": complete_task,
    "log_habit": log_habit,
    "habit_status": habit_status,
    "log_chore": log_chore,
    "chore_status": chore_status,
    "add_chore": add_chore,
    "lift_history": lift_history,
    "activity_totals": activity_totals,
    "show_status": show_status,
    "update_show": update_show,
    "add_show": add_show,
    "add_todo_item": add_todo_item,
    "list_todo_items": list_todo_items,
    "complete_todo_item": complete_todo_item,
    "add_scratch_note": add_scratch_note,
    "search_scratch_notes": search_scratch_notes,
    "list_recent_scratch_notes": list_recent_scratch_notes,
    "research_repo": research_repo,
    "forget_repo": forget_repo,
    "write_vault_note": write_vault_note,
    "save_scratch_note_to_vault": save_scratch_note_to_vault,
    "read_vault_note": read_vault_note,
    "log_to_daily_note": log_to_daily_note,
    "add_to_backlog": add_to_backlog,
    "read_daily_note": read_daily_note,
    "suggest_vault_edit": suggest_vault_edit,
    "read_attachment": read_attachment,
    "analyze_chords": analyze_chords,
    "transcribe_melody": transcribe_melody,
    "suggest_pod_go_tone": suggest_pod_go_tone,
    "pod_go_models": pod_go_models,
    "web_search": web_search,
    "read_webpage": read_webpage,
}


# --- Dynamic tool scoping -------------------------------------------------
# Every tool's JSON schema goes into the model's own prompt context on
# every single call — that's how OpenAI-style function calling works
# regardless of whether the tool is implemented here or fetched from an
# MCP server; moving tools to a server doesn't shrink what has to be
# described to the model. At the full 23-tool catalog, confirmed live:
# analyze_chords' short result answers fine, but suggest_pod_go_tone's
# chunkier one reliably broke gemma4:12b's ability to continue the
# conversation (it either fell back to a generic greeting or hallucinated
# a call to an unrelated tool). Cutting the *number of tool schemas
# actually sent on a given turn* is the fix that matters, not where the
# Python code implementing them lives.
#
# Keyword-matched against recent message text, not a second LLM call — a
# router model call would add latency and its own failure mode, ironically
# the same kind of unreliability this exists to work around. False
# negatives (a real request whose wording doesn't hit any keyword) just
# mean the model answers without that tool this turn, same as if the tool
# never existed at all — a much milder failure than the full-catalog
# hallucinated-tool-call behavior this replaces.
TOOL_GROUPS: dict[str, list[str]] = {
    "vault": ["search_vault", "list_notes", "read_vault_note", "write_vault_note", "suggest_vault_edit", "save_scratch_note_to_vault"],
    "daily": ["log_to_daily_note", "read_daily_note"],
    "dev_backlog": ["add_to_backlog"],
    "vst_memory": ["save_project_memory", "recall_project_memory"],
    "board": ["add_task", "list_tasks", "complete_task"],
    "habits": ["log_habit", "habit_status"],
    "chores": ["log_chore", "chore_status"],
    "chore_add": ["add_chore"],
    "workouts": ["lift_history", "activity_totals"],
    "shows": ["show_status", "update_show"],
    "show_add": ["add_show"],
    "todo": ["add_todo_item", "list_todo_items", "complete_todo_item"],
    "scratch_notes": ["add_scratch_note", "search_scratch_notes", "list_recent_scratch_notes", "save_scratch_note_to_vault"],
    "repo_research": ["research_repo", "forget_repo"],
    "image": ["generate_image"],
    "attachments": ["read_attachment", "analyze_chords", "transcribe_melody", "suggest_pod_go_tone"],
    # Guitar-tone questions get the no-audio model lookup plus web search
    # (to find out what an artist actually played through) together.
    "pod_go": ["pod_go_models", "web_search", "read_webpage"],
    "web": ["web_search", "read_webpage"],
}

GROUP_KEYWORDS: dict[str, list[str]] = {
    "vault": ["note", "notes", "vault", "obsidian", "folder"],
    "daily": ["daily", "journal", "log this", "log that", "log it", "log to", "today's note", "todays note"],
    "dev_backlog": ["backlog", "dev task", "coding task", "code task", "bug"],
    "vst_memory": ["vst", "plugin", "project memory"],
    "board": ["board", "task", "quadrant", "backlog"],
    "habits": ["habit", "streak", "meditat", "exercis", "practic", "i weigh"],
    "todo": ["todo", "to-do", "to do", "grocery", "groceries", "errand", "remind me", "checklist"],
    "chores": [
        "chore", "dusted", "dusting", "cleaned", "cleaning", "descale", "vacuum", "mopped", "mopping",
        "scrubbed", "washed the", "changed the filter", "replaced the filter", "when did i last", "last time i",
    ],
    "shows": [
        "episode", "season", "watching", "watched", "to watch", "watch list", "watchlist", "movie", "tv show",
        "series", "entertainment", "my list", "recommend", "should watch",
    ],
    "workouts": [
        "workout", "work out", "worked out", "gym", "lift", "personal best", "personal record", "bench", "squat",
        "deadlift", "dead lift", "curl", "walk", "miles", "my activit", "training volume", "leg press",
        "pull up", "pullup", "push up", "shrug", "lateral raise", "extensions", "my max", "1rm",
    ],
    "scratch_notes": ["scratch", "jot", "write down", "wrote down", "jotted"],
    "repo_research": ["repo", "repository", "github", "codebase", "clone"],
    "image": ["image", "picture", "photo", "draw", "generate a"],
    "attachments": [
        "chord", "melody", "riff", "transcribe", "notes in this", "tab",
        "amp", "tone", "pod go", "attached", "attachment", "voice memo",
        "that pdf", "that document", "that file", "recording", "song",
    ],
    "pod_go": ["pod go", "podgo", "amp model", "guitar tone", "guitar sound", "patch", "preset", "my tone", "this tone", "that tone", "sounds like", "tone similar", "similar tone"],
    "web": [
        "search the web", "search online", "search the internet", "web search", "google", "look up", "look it up",
        "lookup", "online", "internet", "on the web", "find out", "latest", "news about",
    ],
}


def select_tools(recent_texts: list[str], has_attachments: bool) -> list[dict]:
    """Picks the subset of TOOLS whose group matches recent conversation
    text, instead of always sending the full catalog. `recent_texts` is
    typically [previous assistant reply, current user message] — checking
    the prior turn too catches a short follow-up ("yes, add it") that has
    no keywords of its own but responds to something the assistant just
    proposed. `has_attachments` is checked separately (not keyword-based)
    since it's a hard fact about the conversation, not a guess."""
    haystack = " ".join(t.lower() for t in recent_texts if t)
    matched_groups = {group for group, keywords in GROUP_KEYWORDS.items() if any(kw in haystack for kw in keywords)}
    if has_attachments:
        matched_groups.add("attachments")
    # Chores are named by the user, so their own words are keywords too.
    if "chores" not in matched_groups:
        try:
            if chore_chat.mentions_a_chore(haystack):
                matched_groups.add("chores")
        except Exception:
            # The planner database is optional for chat.
            logger.exception("Couldn't check the message against the chore names")
    # Offered only when adding is actually being talked about. With it always
    # available the model added a chore nobody asked for after a failed log.
    if "chores" in matched_groups and re.search(r"\b(add|track)\b|new chore", haystack):
        matched_groups.add("chore_add")
    if "workouts" not in matched_groups:
        try:
            if re.search(r"\b(pr|prs|pb|pbs)\b", haystack) or workout_chat.mentions(haystack):
                matched_groups.add("workouts")
        except Exception:
            logger.exception("Couldn't check the message against the workout log")
    if "habits" not in matched_groups:
        try:
            if habit_chat.mentions(haystack):
                matched_groups.add("habits")
        except Exception:
            logger.exception("Couldn't check the message against the habit names")
    # Titles on the watch list are keywords too ("finished Dark Matter").
    if "shows" not in matched_groups:
        try:
            if show_chat.mentions_a_title(haystack):
                matched_groups.add("shows")
        except Exception:
            logger.exception("Couldn't check the message against the watch list")
    if "shows" in matched_groups and re.search(r"\b(add|put|recommend\w*|suggested)\b|\b(told|says|said)\b.{0,40}\bwatch\b", haystack):
        matched_groups.add("show_add")
    # "Add X to my list" could be either kind of list, so offer both.
    if "show_add" in matched_groups and "my list" in haystack:
        matched_groups.add("todo")
    matched_names = {name for group in matched_groups for name in TOOL_GROUPS[group]}
    return [t for t in TOOLS if t["function"]["name"] in matched_names]
