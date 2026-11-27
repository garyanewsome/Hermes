"""The entertainment log by chat: finding the title someone means and saving
where they are in it. Code decides which entry and what changes; the model
only passes the words along."""

import re
from contextvars import ContextVar
from datetime import date

from app import entertainment

_NUMBERS = {w: str(n) for n, w in enumerate(
    ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"))}
_ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth")
# Words that mean "finished" covers the whole show, not just one season.
_WHOLE_SHOW = re.compile(r"\b(whole|entire|series|all of|the show|finale|final season|last season|last one)\b")

# What the user typed in their last few messages, set by chat. The model
# fills in numbers nobody said, so only ones found here are saved.
said: ContextVar[str | None] = ContextVar("show_chat_said", default=None)
# Just the newest message: "another episode" must only count once.
latest: ContextVar[str] = ContextVar("show_chat_latest", default="")
_ONE_MORE = re.compile(r"\b(another|next|one more) (episode|ep)\b", re.IGNORECASE)


def _was_said(number: int) -> bool:
    text = said.get()
    if text is None:
        return True
    text = text.casefold()
    numbers = {int(n) for n in re.findall(r"\d+", text)}
    numbers |= {int(w) for w in _words(text) if w.isdigit()}  # includes "two"
    numbers |= {n for n, word in enumerate(_ORDINALS, start=1) if re.search(rf"\b{word}\b", text)}
    # "S1E5" and "the pilot" are ways of saying a number too.
    if "pilot" in text:
        numbers.add(1)
    return number in numbers
_STATUS_WORDS = {
    "watching": "watching", "paused": "paused", "done": "finished", "want": "on the want-to-watch list",
    "waiting": "waiting for more",
}


def _words(text: str) -> list[str]:
    return [_NUMBERS.get(w, w) for w in re.findall(r"[a-z0-9]+", text.casefold().replace("'", ""))]


def find(title: str, listed: list[dict]) -> list[dict]:
    """An exact title wins; otherwise every word given must be in the title
    ("strange new worlds"), or the same letters run together or apart
    ("spider-verse")."""
    wanted = _words(title)
    if not wanted:
        return []
    exact = [e for e in listed if _words(e["title"]) == wanted]
    if exact:
        return exact
    some = [e for e in listed if all(w in _words(e["title"]) for w in wanted)]
    joined = "".join(wanted)
    return some or [e for e in listed if len(joined) >= 5 and joined in "".join(_words(e["title"]))]


def mentions_a_title(text: str) -> bool:
    """Whether the text names something on the list, used to decide when to
    offer these tools. A title or a good chunk of one ("lower decks") counts.
    A short single word ("You", "Devs") is too easy to say by accident, so it
    only counts straight after a word like "finished"."""
    said = f" {' '.join(_words(text))} "
    for entry in entertainment.list_entries()["entries"]:
        words = _words(entry["title"])
        if not words:
            continue
        whole = " ".join(words)
        if len(words) == 1 and len(whole) < 6:
            if re.search(rf" (finished|started|starting|paused|pausing|dropped|watch) {whole} ", said):
                return True
        elif f" {whole} " in said:
            return True
        # Runs of two or more words, long enough not to be everyday talk.
        for start in range(len(words) - 1):
            for end in range(start + 2, len(words) + 1):
                run = words[start:end]
                if len("".join(run)) >= 10 and f" {' '.join(run)} " in said:
                    return True
    return False


def _describe(entry: dict) -> str:
    kind = "movie" if entry["kind"] == "movie" else "TV"
    parts = [_STATUS_WORDS[entry["status"]]]
    waiting_for_season = entry["status"] == "waiting" and entry["season"]
    if waiting_for_season:
        parts = [f"waiting for season {entry['season']}"]
    elif entry["season"]:
        parts.append(f"season {entry['season']}")
    if entry["episode"]:
        parts.append(f"watched through episode {entry['episode']}")
    if entry["return_date"]:
        days = entry["days_until"]
        when = "today" if days == 0 else f"in {days} days" if days > 0 else "already out"
        verb = "which comes out" if waiting_for_season else "comes out"
        parts.append(f"{verb} {_long(entry['return_date'])} ({when})")
    if entry["where_to_watch"]:
        parts.append(f"on {entry['where_to_watch']}")
    return f"{entry['title']} ({kind}): {', '.join(parts)}."


def _long(iso: str) -> str:
    return f"{date.fromisoformat(iso):%A %B %-d, %Y}"


def _names(entries: list[dict]) -> str:
    return ", ".join(e["title"] for e in entries)


def status(title: str | None = None) -> str:
    listed = entertainment.list_entries()["entries"]
    if title:
        matches = find(title, listed)
        if matches:
            return "\n".join(_describe(e) for e in matches)
        return f"\"{title}\" isn't on the list."
    if not listed:
        return "Nothing is on the entertainment list yet."
    by = {s: [e for e in listed if e["status"] == s] for s in _STATUS_WORDS}
    lines = ["Currently watching:"]
    lines += [_describe(e) for e in by["watching"]] or ["Nothing."]
    for name, heading in (("waiting", "Waiting for more:"), ("paused", "Paused:")):
        if by[name]:
            lines += [heading, *map(_describe, by[name])]
    for kind, name in (("tv", "TV"), ("movie", "movies")):
        want = [e for e in by["want"] if e["kind"] == kind]
        if want:
            lines.append(f"Want to watch, {name} ({len(want)}): {_names(want)}.")
    if by["done"]:
        lines.append(f"Finished ({len(by['done'])}): {_names(by['done'])}.")
    return "\n".join(lines)


def _number(value, name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"The {name} has to be a number, not \"{value}\"")
    return number or None


def update(title: str | None = None, season=None, episode=None, status: str | None = None,
           finished_season=None) -> str:
    listed = entertainment.list_entries()["entries"]
    title = " ".join((title or "").split())
    if title:
        matches = find(title, listed)
        if not matches:
            # Worded bluntly: a softer message had the model claiming a save
            # that never happened (see chore_chat).
            return (
                f"NOT SAVED. Nothing changed and nothing was added, because \"{title}\" isn't on the list. "
                f"On the list: {_names(listed) or 'nothing yet'}. If the user clearly means one of these, call "
                f"the tool again with that exact title. Otherwise reply with exactly this and nothing else: "
                f"\"I didn't save that, because {title} isn't on your watch list. Want me to add it?\""
            )
    else:
        matches = [e for e in listed if e["status"] == "watching"]
        if not matches:
            return "NOT SAVED. Nothing is marked as being watched. Ask the user which title they mean."
    if len(matches) > 1:
        return (f"NOT SAVED. Nothing changed, because it could be any of: {_names(matches)}. "
                f"Ask the user which one they mean.")
    entry = matches[0]

    status = (status or "").strip().lower() or None
    if status and status not in _STATUS_WORDS:
        return f"NOT SAVED. \"{status}\" isn't a status; use one of: {', '.join(_STATUS_WORDS)}."
    try:
        season, episode = _number(season, "season"), _number(episode, "episode")
        finished_season = _number(finished_season, "season")
        season, episode, finished_season = (
            n if n is None or _was_said(n) else None for n in (season, episode, finished_season)
        )
        if entry["kind"] == "movie":
            season = episode = finished_season = None
        # "Finished season 4" is not finishing the show, whatever the model says.
        if status == "done" and season and not _WHOLE_SHOW.search((said.get() or "").casefold()):
            finished_season = finished_season or season
        if finished_season:
            season, episode, status = finished_season + 1, None, "waiting"
        one_more = entry["kind"] == "tv" and episode is None and not finished_season
        if one_more and status in (None, "watching") and _ONE_MORE.search(latest.get()):
            episode = (entry["episode"] or 0) + 1
        if season is None and episode is None and status is None:
            return (
                f"NOT SAVED. Nothing changed. Reply with exactly this and nothing else: \"I didn't save that. "
                f"Which episode of {entry['title']} are you on?\""
            )
        values = {name: entry[name] for name in entertainment.FIELDS}
        if season is not None and season != entry["season"]:
            values["season"], values["episode"] = season, None
        if episode is not None:
            values["episode"] = episode
        # Saying where you are in something means you're watching it.
        if status is None and (season is not None or episode is not None):
            status = "watching"
        if status:
            values["status"] = status
        if finished_season:
            values["episode"] = None
        # A date belongs to what was being waited for.
        if values["status"] in ("watching", "done") or (finished_season and values["season"] != entry["season"]):
            values["return_date"] = None
        if not entertainment.update(entry["id"], entertainment.Entry(**values)):
            return "NOT SAVED. That entry is no longer on the list."
    except ValueError as exc:
        return f"NOT SAVED. {exc}"
    after = next(e for e in entertainment.list_entries()["entries"] if e["id"] == entry["id"])
    reply = f"Saved. {_describe(after)} Tell the user this, including any season and episode number."
    if finished_season:
        reply += (f" Season {finished_season} is finished. Tell the user it's now waiting for season "
                  f"{finished_season + 1}, and to say so if that was the last season.")
    return reply


def add(title: str, kind: str = "tv", status: str | None = None, season=None, episode=None) -> str:
    kind = "movie" if str(kind).strip().lower() in ("movie", "film") else "tv"
    status = (status or "want").strip().lower()
    if status not in _STATUS_WORDS:
        status = "want"
    try:
        season, episode = (
            n if n is None or _was_said(n) else None
            for n in (_number(season, "season"), _number(episode, "episode"))
        )
        if kind == "movie":
            season = episode = None
        elif episode:
            status = "watching"
        entry = entertainment.Entry(title=title, kind=kind, status=status, season=season, episode=episode)
        entertainment.add(entry)
    except ValueError as exc:
        return f"NOT ADDED. {exc}"
    place = "".join(f", {name} {n}" for name, n in (("season", season), ("watched through episode", episode)) if n)
    return f"Added \"{' '.join(title.split())}\" ({'movie' if kind == 'movie' else 'TV'}), {_STATUS_WORDS[status]}{place}."
