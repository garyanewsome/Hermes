"""Habits by chat, including ones that count something. Code picks the habit,
reads the day and the number, and does the totals; numbers the user didn't type
are never saved."""

import re
from contextvars import ContextVar
from datetime import date

from app import chore_chat, habit_amounts, planner_db

_NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                 "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
                 "nineteen", "twenty")
_TENS = {"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90}
_UNITS = {
    "minute": ("minute", "minutes", "min", "mins"),
    "hour": ("hour", "hours", "hr", "hrs", "h"),
    "pound": ("pound", "pounds", "lb", "lbs"),
    "kilogram": ("kilogram", "kilograms", "kg", "kgs", "kilo", "kilos"),
    "mile": ("mile", "miles", "mi"),
    "page": ("page", "pages", "pg", "pgs"),
}
_MINUTES_IN = {"minute": 1, "hour": 60}

# The user's newest message, and what has been saved while answering it; both
# set by chat for each turn.
latest: ContextVar[str | None] = ContextVar("habit_chat_latest", default=None)
saved: ContextVar[set | None] = ContextVar("habit_chat_saved", default=None)


def _unit_key(unit: str | None) -> str:
    text = (unit or "").strip().casefold().rstrip(".")
    for key, spellings in _UNITS.items():
        if text in spellings:
            return key
    return text.rstrip("s")


def said_numbers(text: str) -> set[float]:
    text = text.casefold().replace(",", "")
    found = {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text)}
    words = re.findall(r"[a-z]+", text)
    for index, word in enumerate(words):
        if word in _NUMBER_WORDS[1:]:
            found.add(float(_NUMBER_WORDS.index(word)))
        if word in _TENS:
            found.add(float(_TENS[word]))
            after = words[index + 1] if index + 1 < len(words) else ""
            if after in _NUMBER_WORDS[1:10]:
                found.add(float(_TENS[word] + _NUMBER_WORDS.index(after)))
    # Everyday ways of saying a time, in hours.
    if re.search(r"half an hour|half hour", text):
        found.add(0.5)
    if re.search(r"an hour and a half|hour and a half", text):
        found.add(1.5)
    elif re.search(r"\ban hour\b", text) and "half an hour" not in text:
        found.add(1.0)
    return found


def _amount(amount, unit: str | None, habit_unit: str) -> float:
    """The number in the habit's unit. Raises ValueError, in words for the
    model, if the user didn't say it or it's in an unrelated unit."""
    try:
        number = float(amount)
    except (TypeError, ValueError):
        raise ValueError(f"The amount has to be a number, not \"{amount}\"")
    given, wanted = _unit_key(unit) or _unit_key(habit_unit), _unit_key(habit_unit)
    text = latest.get()
    # "2 hours" stays hours even if the model labels it minutes.
    if text is not None and wanted == "minute" and (
        re.search(rf"(?<![\d.]){re.escape(f'{number:g}')}\s*(hours?|hrs?)\b", text.casefold())
        or (number == 1 and re.search(r"\ban hour\b(?! and)", text.casefold()) and "half an" not in text.casefold())
    ):
        given = "hour"
    if text is not None:
        stated = said_numbers(text)
        # The model may have already turned "1.5 hours" into 90 minutes.
        converted = given in _MINUTES_IN and any(
            abs(n * 60 - number) < 0.01 for n in stated
        ) and _MINUTES_IN[given] == 1 and re.search(r"\bhour|\bhr", text.casefold())
        if number not in stated and not converted:
            raise ValueError(f"The user didn't say {number:g}. Ask them for the number in {habit_unit}")
    if given != wanted:
        if given in _MINUTES_IN and wanted in _MINUTES_IN:
            return round(number * _MINUTES_IN[given] / _MINUTES_IN[wanted], 2)
        raise ValueError(f"This habit counts {habit_unit}, not {unit}. Ask the user for the number in {habit_unit}")
    return number


def _find(name: str, habits: list[dict]) -> list[dict]:
    matches = chore_chat.find(name, habits)
    if matches:
        return matches
    # "studio" for "Studio time": the words given are all in the name, or the
    # name's words are all in what was given ("bass practice session").
    said = chore_chat._stems(name)
    return [
        h for h in habits
        if chore_chat._stems(h["name"])
        and all(any(chore_chat._same(w, s) for s in said) for w in chore_chat._stems(h["name"]))
    ]


def _fmt(value: float, unit: str) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".") + f" {unit}"


def _describe(habit: dict) -> str:
    today = habit["last_7_days"][-1]
    parts = [f"{habit['name']}: {'logged' if today['logged'] else 'not logged'} today"]
    totals = habit["totals"]
    if totals and habit["unit"]:
        unit = habit["unit"]
        if habit["add_up"]:
            parts.append(f"today {_fmt(totals['today'] or 0, unit)}, this week (from Monday) "
                         f"{_fmt(totals['this_week'], unit)}, last week {_fmt(totals['last_week'], unit)}")
        elif totals["latest"]:
            on = date.fromisoformat(totals["latest"]["date"])
            parts.append(f"latest {_fmt(totals['latest']['amount'], unit)} on {on:%A %B %-d}")
            earlier = [d for d in habit["last_7_days"] if d["amount"] is not None and d["date"] < on.isoformat()]
            if earlier:
                before = date.fromisoformat(earlier[-1]["date"])
                parts.append(f"before that {_fmt(earlier[-1]['amount'], unit)} on {before:%A %B %-d}")
        else:
            parts.append(f"no {unit} recorded yet")
    if not habit["hide_streak"]:
        streak = habit["streak"]
        parts.append(f"{streak} day streak")
        week = ", ".join(f"{d['date']}: {'done' if d['logged'] else 'missed'}" for d in habit["last_7_days"])
        parts.append(f"last 7 days: {week}")
    return "; ".join(parts) + "."


def log(name: str, amount=None, unit: str | None = None, when: str | None = None) -> str:
    name = " ".join((name or "").split())
    habits = planner_db.list_habits_with_streaks()
    matches = _find(name, habits) if name else []
    if len(matches) > 1:
        return (f"NOT SAVED. \"{name}\" could be any of: {', '.join(h['name'] for h in matches)}. "
                "Ask the user which one.")
    if amount in ("", 0):
        amount = None
    if not matches and "weigh" in name.casefold():
        # Weigh-ins belong to the Fitness log unless there's a habit for them.
        return (
            "NOT SAVED. Nothing was recorded anywhere. Reply with exactly this and nothing else: \"I didn't save "
            "that. Weigh-ins go in the fitness section of your daily note, which imports when you open Fitness, "
            "Daily. You can also type it on that page.\""
        )
    if not matches:
        known = ", ".join(h["name"] for h in habits) or "none yet"
        if amount is not None or not name:
            return (f"NOT SAVED. There's no habit called \"{name}\". Existing habits: {known}. If the user clearly "
                    "means one of these, call again with that name. Otherwise tell them nothing was saved and that "
                    "they can add it, with its unit, on the Habits page; you can't create it with a number from chat, so "
                    "don't offer to.")
    try:
        on = chore_chat.parse_when(when, planner_db._today())
        if on > planner_db._today():
            raise ValueError("That date is in the future")
        habit = matches[0] if matches else None
        if habit is None:
            planner_db.log_habit(name, on)
        else:
            key = (habit["id"], on)
            done = saved.get()
            if done is not None and key in done:
                return f"Already saved for this message. {_describe(habit)}"
            if amount is not None and habit["unit"]:
                habit_amounts.log_amount(habit["id"], on, _amount(amount, unit, habit["unit"]))
            else:
                planner_db.set_habit_log(habit["id"], on, True)
            if done is not None:
                done.add(key)
    except ValueError as exc:
        return f"NOT SAVED. {exc}."
    shown = habit["name"] if habit else name
    after = next(h for h in planner_db.list_habits_with_streaks() if h["name"] == shown)
    day = "today" if on == planner_db._today() else f"{on:%A %B %-d}"
    reply = f"Saved the habit \"{shown}\" for {day}. {_describe(after)}"
    if after["unit"] and amount is None:
        reply += f" No number was saved. Ask how many {after['unit']} it was."
    elif amount is not None and not after["unit"]:
        reply += (" This habit doesn't track a number, so only the check-off was saved. Say so, and that a unit "
                  "can be set on the Habits page.")
    return reply


def status(name: str | None = None) -> str:
    habits = planner_db.list_habits_with_streaks()
    if not habits:
        return "No habits being tracked yet."
    if name:
        matches = _find(name, habits)
        if not matches:
            return f"No habit matches \"{name}\". Habits: {', '.join(h['name'] for h in habits)}."
        habits = matches
    return "\n".join(map(_describe, habits))


def mentions(text: str) -> bool:
    """Whether the text uses a habit's name. For habits that count something,
    one longer word of the name is enough ("studio" for "Studio time")."""
    said = chore_chat._stems(text)
    for habit in planner_db.list_habits_with_streaks():
        hits, words = 0, 0
        long_hit = False
        # Word length is judged before stemming ("bass" stems to "bas").
        for word in re.findall(r"[a-z0-9]+", habit["name"].casefold()):
            for stem in chore_chat._stems(word):
                words += 1
                if any(chore_chat._same(stem, other) for other in said):
                    hits += 1
                    long_hit = long_hit or len(word) >= 4
        if words and (hits >= min(2, words) or (habit["unit"] and long_hit)):
            return True
    return False


_DID = re.compile(r"\b(\w+ed|did|spent|ran|read|swam|wrote|sang|weigh|put in)\b", re.IGNORECASE)
_ASKS = re.compile(r"^\s*(how|what|when|did|do|does|can|could|should|is|am|have|has|show|tell)\b", re.IGNORECASE)


def report_note(text: str) -> str | None:
    """A nudge for a turn that reports a habit; without it the model sometimes
    just chats about it and nothing is saved."""
    if "?" in text or _ASKS.search(text) or not _DID.search(text) or not mentions(text):
        return None
    return (
        "The user seems to be saying they did something they track as a habit. If so, call log_habit now, "
        "with the number and day they gave, before replying."
    )
