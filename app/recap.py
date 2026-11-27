"""The Sunday recap: facts from recap_facts.py, laid out by code, with a few
sentences from the chat model on top.

Generated for the week (Monday to Sunday) on Sunday at 8pm, saved to the
vault once, and shown on the Today page. If Hermes was down then, it catches
up the next time it's running. The model only writes words: a summary with
any number that isn't in the facts is thrown away."""

import logging
import re
import threading
import time
from datetime import date, datetime, timedelta

import httpx
from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb

from app import planner_db, recap_facts
from app.config import CHAT_MODEL, OLLAMA_HOST, OLLAMA_NUM_CTX, RECAP_FOLDER, VAULT_KEEPER_URL
from app.trends import monday_of

logger = logging.getLogger("hermes")
router = APIRouter()

RECAP_HOUR = 20  # Sunday, app time
CHECK_SECONDS = 600
MAX_LISTED = 25
_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(planner_db._TZ)


def due_week(now: datetime) -> date:
    """The Monday of the latest week whose recap time has passed."""
    this_monday = monday_of(now.date())
    if now.weekday() == 6 and now.hour >= RECAP_HOUR:
        return this_monday
    return this_monday - timedelta(weeks=1)


# ---- Words and layout ------------------------------------------------------


def _day(iso: str) -> str:
    return f"{date.fromisoformat(iso):%a %b %-d}"


def _plural(count: int, word: str, many: str | None = None) -> str:
    return f"{count} {word if count == 1 else many or word + 's'}"


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def _listed(lines: list[str]) -> list[str]:
    more = len(lines) - MAX_LISTED
    return lines[:MAX_LISTED] + ([f"- …and {more} more"] if more > 0 else [])


def _set(item: dict) -> str:
    if item["weight"] is None:
        return f"{item['reps']} reps"
    side = "" if item["per_side"] is None else f" ({item['per_side']:g} a side)"
    return f"{item['weight']:g} {item['unit'] or 'lb'}{side} × {item['reps']}"


def _amount(value: float) -> str:
    return f"{value:,.1f}".removesuffix(".0")


def _balance(value: float) -> str:
    return "even" if value == 0 else f"{_amount(abs(value))} {'deficit' if value < 0 else 'surplus'}"


def _daily_lines(daily: dict | None) -> list[str]:
    """Weigh-ins, calories and macros: daily averages beside the week before.
    Recaps made before these were tracked have none."""
    if not daily or not daily["week"]["days"]:
        return []
    week, before = daily["week"], daily["previous"]
    now, old, counts = week["average"], before["average"], week["counts"]
    lines = []
    for key, name in (("weight", "Home weight"), ("weight_pf", "PF weight")):
        if now[key] is None:
            continue
        line = f"- {name}: average {_amount(now[key])} lb over {_plural(counts[key], 'weigh-in')}"
        if old[key] is not None:
            change = round(now[key] - old[key], 1)
            moved = "no change" if change == 0 else f"{'down' if change < 0 else 'up'} {_amount(abs(change))} lb"
            line += f", {moved} from the week before ({_amount(old[key])} lb)"
        lines.append(line)
    eaten = [
        f"{label} {_amount(now[key])} (over {_plural(counts[key], 'day')})"
        for key, label in (("calories_in", "eaten"), ("burned_total", "burned"), ("burned_active", "active"))
        if now[key] is not None
    ]
    if eaten:
        lines.append(f"- Calories a day: {', '.join(eaten)}")
    if now["balance"] is not None:
        line = f"- Balance a day: {_balance(now['balance'])} (over {_plural(counts['balance'], 'day')})"
        if old["balance"] is not None:
            line += f"; week before: {_balance(old['balance'])}"
        lines.append(line)
    macros = []
    for key, name in (("carbs_g", "carbs"), ("fat_g", "fat"), ("protein_g", "protein")):
        if now[key] is not None:
            was = "" if old[key] is None else f" (week before: {_amount(old[key])} g)"
            macros.append(f"{name} {_amount(now[key])} g{was}")
    if macros:
        lines.append(f"- Macros a day: {', '.join(macros)}")
    return lines


def body(facts: dict) -> str:
    """The recap without its title or summary, as markdown."""
    out: list[str] = []

    def section(title: str, lines: list[str]):
        if lines:
            out.extend([f"## {title}", *lines, ""])

    done = [f"- Task: {_one_line(t)}" for t in facts["tasks_done"]]
    done += [f"- Todo: {_one_line(t['text'])} ({_one_line(t['list'])})" for t in facts["todos_done"]]
    counts = f"{_plural(len(facts['tasks_done']), 'board task')} and {_plural(len(facts['todos_done']), 'todo')} finished."
    section("Done", [counts, *_listed(done)])

    section(
        "Habits",
        [f"- {_one_line(h['name'])}: {h['days']} of 7 days (week before: {h['previous']})" for h in facts["habits"]],
    )

    training = []
    if facts["gym"] or facts["previous_volume"]:
        training.append(
            f"{_plural(len(facts['gym']), 'gym day')}, {facts['volume']:,} lb lifted "
            f"(week before: {_plural(facts['previous_gym_days'], 'gym day')}, {facts['previous_volume']:,} lb)."
        )
    training += [
        f"- {_day(g['date'])}{' ' + g['session'] if g['session'] else ''}: "
        f"{_plural(g['sets'], 'set')}, {g['volume']:,} lb"
        for g in facts["gym"]
    ]
    training += [
        f"- New best, {_one_line(b['exercise'])}: {_set(b['new'])} (was {_set(b['old'])})" for b in facts["new_bests"]
    ]
    training += [
        f"- {_one_line(a['name'])}: {_plural(a['count'], 'time')}, {a['minutes']} min"
        + (f", {a['miles']:g} mi" if a["miles"] else "")
        for a in facts["activities"]
    ]
    section("Training and activity", training)

    section("Body and food", _daily_lines(facts.get("daily")))

    section("Chores", _listed([f"- {_one_line(c['name'])} ({_day(c['date'])})" for c in facts["chores_done"]]))

    slipping = facts["slipping"]
    lines = [f"- Overdue task: {_one_line(t['title'])} (due {_day(t['date'])})" for t in slipping["tasks"]]
    lines += [f"- Overdue todo: {_one_line(t['text'])} (due {_day(t['date'])})" for t in slipping["todos"]]
    lines += [f"- Chore due: {_one_line(name)}" for name in slipping["chores"]]
    lines += [f"- Habit not logged this week: {_one_line(name)}" for name in slipping["habits"]]
    section("Slipping", _listed(lines))

    section("Next week", _listed([f"- {_one_line(u['title'])} ({_day(u['date'])})" for u in facts["upcoming"]]))
    return "\n".join(out).strip()


def render(facts: dict, summary: str | None) -> str:
    start, end = _day(facts["week_start"]), _day(facts["week_end"])
    note = "" if facts["complete"] else f"\n_Week still in progress: as of {_day(facts['as_of'])}._"
    head = f"# Week of {start} to {end}{note}"
    return "\n\n".join(part for part in (head, summary, body(facts)) if part) + "\n"


_NUMBER_WORDS = {
    word: str(value)
    for value, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
        "sixteen seventeen eighteen nineteen twenty".split()
    )
}


def _numbers(text: str) -> set[str]:
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text.lower())
    found = {f"{float(n):g}" for n in re.findall(r"\d+(?:\.\d+)?", text)}
    # "one" is too often not a count ("a good one") to check.
    found |= {v for w, v in _NUMBER_WORDS.items() if v != "1" and re.search(rf"\b{w}\b", text)}
    return found


def check_summary(text: str, source: str) -> str | None:
    """The summary if it's usable, else None."""
    text = " ".join(re.sub(r"<think>.*?</think>", "", text, flags=re.S).split()).strip().strip('"')
    if not text or len(text) > 700 or text.startswith(("#", "-", "*")):
        return None
    invented = _numbers(text) - _numbers(source)
    if invented:
        logger.warning("Recap summary dropped: numbers not in the facts: %s", ", ".join(sorted(invented)))
        return None
    return text


def summarize(facts: dict) -> str | None:
    source = body(facts)
    prompt = (
        "Below is the factual weekly recap for the person you're writing to. Write 2 to 4 short, plain "
        "sentences to them about the week: what went well and what needs attention. Use only what's written "
        "there. Don't calculate or estimate anything; quote numbers exactly or leave them out. No headings, "
        "lists or greeting.\n\n" + source
    )
    try:
        response = httpx.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": CHAT_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "options": {"num_ctx": OLLAMA_NUM_CTX},
            },
            timeout=240.0,
        )
        response.raise_for_status()
        return check_summary(response.json()["message"]["content"], source)
    except Exception:
        # The numbers are the recap; the sentences are a nicety.
        logger.exception("Couldn't write the recap summary")
        return None


# ---- Storing ---------------------------------------------------------------


def _public(row) -> dict | None:
    if row is None:
        return None
    return {
        "week_start": row["week_start"].isoformat(),
        "markdown": row["markdown"],
        "summary": row["summary"],
        "generated_at": row["generated_at"].isoformat(),
        "vault_path": row["vault_path"],
        "vault_error": row["vault_error"],
        # Updated since the vault copy was written.
        "vault_stale": row["vault_path"] is not None and row["vault_markdown"] != row["markdown"],
    }


def get(week_start: date) -> dict | None:
    with planner_db._connect() as conn:
        return _public(conn.execute("SELECT * FROM recaps WHERE week_start = %s", (week_start,)).fetchone())


def latest() -> dict | None:
    with planner_db._connect() as conn:
        return _public(conn.execute("SELECT * FROM recaps ORDER BY week_start DESC LIMIT 1").fetchone())


def generate(week_start: date) -> dict:
    """Builds (or rebuilds) a week's recap. Doesn't touch the vault."""
    facts = recap_facts.week_facts(week_start)
    summary = summarize(facts)
    with planner_db._connect() as conn:
        conn.execute(
            """
            INSERT INTO recaps (week_start, facts, summary, markdown) VALUES (%s, %s, %s, %s)
            ON CONFLICT (week_start) DO UPDATE
                SET facts = EXCLUDED.facts, summary = EXCLUDED.summary, markdown = EXCLUDED.markdown,
                    generated_at = now()
            """,
            (week_start, Jsonb(facts), summary, render(facts, summary)),
        )
    return get(week_start)


def save_to_vault(week_start: date) -> dict:
    """Writes the recap as a new note. vault-keeper never overwrites, so a
    second save becomes a second note."""
    stored = get(week_start)
    if stored is None:
        raise LookupError("There's no recap for that week")
    path = error = None
    try:
        response = httpx.post(
            f"{VAULT_KEEPER_URL}/write_note",
            json={
                "folder": RECAP_FOLDER,
                "filename": f"Week of {week_start.isoformat()}.md",
                "content": stored["markdown"],
                "kind": "weekly-recap",
            },
            timeout=60.0,
        )
        if response.status_code == 403:
            error = str(response.json().get("detail", "The vault write limits refused it."))
        else:
            response.raise_for_status()
            path = response.json()["note_path"]
    except Exception as exc:
        logger.warning("Saving the recap to the vault failed: %s", exc)
        error = f"The vault couldn't be reached ({type(exc).__name__})"
    with planner_db._connect() as conn:
        if path:
            conn.execute(
                "UPDATE recaps SET vault_path = %s, vault_markdown = %s, vault_error = NULL WHERE week_start = %s",
                (path, stored["markdown"], week_start),
            )
        else:
            conn.execute("UPDATE recaps SET vault_error = %s WHERE week_start = %s", (error, week_start))
    return get(week_start)


def run_scheduled(now: datetime | None = None) -> None:
    """Makes the due week's recap if it's missing, and gets it into the vault
    if that hasn't worked yet. Safe to call as often as you like."""
    week = due_week(now or _now())
    with _lock:
        stored = get(week) or generate(week)
        if stored["vault_path"] is None:
            save_to_vault(week)


def _loop() -> None:
    # Let the app and the database settle after a restart.
    time.sleep(60)
    while True:
        try:
            run_scheduled()
        except Exception:
            logger.exception("Scheduled weekly recap failed")
        time.sleep(CHECK_SECONDS)


def start_background() -> None:
    threading.Thread(target=_loop, name="weekly-recap", daemon=True).start()


# ---- Routes ----------------------------------------------------------------


@router.get("/recaps/latest")
def get_latest():
    return {"recap": latest()}


@router.post("/recaps/{week_start}")
def post_recap(week_start: date):
    """Rebuild a week's recap with whatever has been logged since."""
    if week_start.weekday() != 0 or week_start > planner_db._today():
        raise HTTPException(status_code=400, detail="A week is named by a Monday that has started")
    with _lock:
        return {"recap": generate(week_start)}


@router.post("/recaps/{week_start}/vault")
def post_recap_to_vault(week_start: date):
    with _lock:
        try:
            return {"recap": save_to_vault(week_start)}
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
