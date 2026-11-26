"""Chores by chat: finding the chore someone means and reading dates like
"last Saturday". Code decides both; the model only passes the words along."""

import re
from datetime import date, timedelta

from app import chores, planner_db

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# Words that say nothing about which chore it is.
_FILLER = {"a", "an", "the", "my", "our", "i", "did", "done", "do", "of", "in", "on", "to", "out", "up", "off"}


def _stem(word: str) -> str:
    for ending in ("ing", "ed", "es", "s", "e"):
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            word = word[: -len(ending)]
            break
    # "mopped" -> "mopp" -> "mop"
    if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "ls":
        word = word[:-1]
    return word


def _stems(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.casefold()) if w not in _FILLER]


def _same(a: str, b: str) -> bool:
    short, long = sorted((a, b), key=len)
    return short == long or (len(short) >= 4 and long.startswith(short))


def find(name: str, listed: list[dict]) -> list[dict]:
    """An exact name wins; otherwise every word given must be in the chore's
    name, so "cleaned the oven" never matches "Clean dryer vent"."""
    key = " ".join(name.split()).casefold()
    exact = [c for c in listed if c["name"].casefold() == key]
    if exact:
        return exact
    wanted = _stems(name)
    if not wanted:
        return []
    return [c for c in listed if all(any(_same(w, s) for s in _stems(c["name"])) for w in wanted)]


def mentions_a_chore(text: str) -> bool:
    """Whether the text shares two words with a chore's name (or its only
    word), used to decide when to offer the chore tools."""
    said = _stems(text)
    for chore in chores.list_chores():
        words = _stems(chore["name"])
        hits = sum(any(_same(w, s) for s in said) for w in words)
        if words and hits >= min(2, len(words)):
            return True
    return False


def parse_when(when: str | None, today: date) -> date:
    text = " ".join((when or "today").split()).casefold()
    if text in ("today", "this morning", "this afternoon", "tonight", "just now", "now"):
        return today
    if text in ("yesterday", "last night"):
        return today - timedelta(days=1)
    ago = re.fullmatch(r"(\d{1,4}) (day|week)s? ago", text)
    if ago:
        return today - timedelta(days=int(ago.group(1)) * (7 if ago.group(2) == "week" else 1))
    named = re.fullmatch(r"(last |on )?(" + "|".join(_WEEKDAYS) + ")", text)
    if named:
        back = (today.weekday() - _WEEKDAYS.index(named.group(2))) % 7
        # "last Saturday", said on a Saturday, means a week ago.
        if back == 0 and named.group(1) == "last ":
            back = 7
        return today - timedelta(days=back)
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(f"I can't tell which day \"{when}\" is; use a date like {today.isoformat()}")


def _describe(chore: dict) -> str:
    if chore["last_done"] is None:
        text = "never logged"
    else:
        days = chore["days_ago"]
        ago = "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"
        last = date.fromisoformat(chore["last_done"])
        text = f"last done {ago} ({last:%A %B %-d, %Y}), logged {chore['times']} time{'s' if chore['times'] != 1 else ''}"
    if chore["every_days"]:
        text += f", meant to be every {chore['every_days']} days" + (" and is DUE" if chore["due"] else "")
    return f"{chore['name']}: {text}."


def _one(name: str) -> tuple[dict | None, str, list[str]]:
    """The chore, or what to tell the model instead, plus the names to choose
    between when more than one matched."""
    listed = chores.list_chores()
    matches = find(name, listed)
    if len(matches) == 1:
        return matches[0], "", []
    if matches:
        names = [c["name"] for c in matches]
        return None, (f"NOT LOGGED. Nothing was saved: more than one chore matches \"{name}\": "
                      f"{', '.join(names)}. Ask the user which one they mean."), names
    known = ", ".join(c["name"] for c in listed) or "none yet"
    # Worded this bluntly because a softer message had the model telling the
    # user the chore was logged anyway.
    return None, (
        f"NOT LOGGED. Nothing was saved, because there is no chore matching \"{name}\". "
        f"Existing chores: {known}. If the user clearly means one of these, call the tool again with that exact "
        f"name. Otherwise reply with exactly this and nothing else: \"I didn't log that, because there's no chore "
        f"for it yet. Want me to add it to your chores?\""
    ), []


def log(name: str, when: str | None = None) -> str:
    chore, problem, _ = _one(name)
    if chore is None:
        return problem
    try:
        on = parse_when(when, planner_db._today())
        chores.log_chore(chore["id"], on)
    except ValueError as exc:
        return f"{exc}. Nothing was logged."
    after = next(c for c in chores.list_chores() if c["id"] == chore["id"])
    return f"Logged \"{chore['name']}\" for {on:%A %B %-d, %Y}. Now: {_describe(after)}"


def status(name: str | None = None) -> str:
    if name:
        chore, _, choices = _one(name)
        if chore:
            return _describe(chore)
        if choices:
            return "\n".join(_describe(c) for c in chores.list_chores() if c["name"] in choices)
        known = ", ".join(c["name"] for c in chores.list_chores()) or "none yet"
        return f"There's no chore matching \"{name}\". Existing chores: {known}."
    listed = chores.list_chores()
    if not listed:
        return "No chores have been added yet."
    return ("Chores, longest ago first (only those marked DUE are due):\n"
            + "\n".join(_describe(c) for c in listed))


def add(name: str, every_days: int | None = None) -> str:
    try:
        request = chores.ChoreRequest(name=name, every_days=every_days or None)
        chores.add_chore(request)
    except ValueError as exc:
        return f"Couldn't add that chore: {exc}"
    every = f", every {request.every_days} days" if request.every_days else ""
    return f"Added the chore \"{' '.join(name.split())}\"{every}. It hasn't been logged as done."
