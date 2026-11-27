"""Catches a reply that says something was saved when nothing was.

The chat model sometimes answers "I've added it" without calling any tool,
mostly late in a long conversation full of such replies. Code can see which
tools ran, so it checks the claim: one more try with a short, fresh context,
and if that doesn't save either, the user is told plainly."""

import re

# Tools that save something for the user.
WRITE_TOOLS = {
    "add_task", "complete_task", "log_habit", "log_chore", "add_chore", "add_todo_item", "complete_todo_item",
    "add_scratch_note", "save_scratch_note_to_vault", "update_show", "add_show", "log_to_daily_note",
    "add_to_backlog", "write_vault_note", "suggest_vault_edit", "save_project_memory",
}

NOTHING_SAVED = (
    "**Nothing was saved.** I couldn't run the save for that. Try again in a new chat, or add it on its page."
)

NUDGE = (
    "IMPORTANT: a first attempt at the user's latest request replied that it was saved without calling any tool, "
    "so nothing was saved. Call the right tool now, once for each thing asked. If you can't, say that nothing "
    "was saved. Never say something was saved unless a tool result says so."
)

# How the save tools begin when they didn't save.
_FAILED = ("not ", "no ", "multiple ", "several ", "couldn't")
_VERBS = r"added|logged|saved|updated|recorded|marked|moved|noted|put|checked off|removed|created|completed"
_CLAIMS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        # "I've added", "I have also logged", "I added"
        rf"\bI(?:'ve| have)?(?: (?:just|also|now|gone ahead and|successfully))* (?:{_VERBS})\b",
        # "Logged your practice." / "Noted. You're on..." / "Done, added."
        rf"(?:^|[.!?]\s+|\n)\W*(?:(?:got it|done|okay|ok|great|sure|perfect)[.,!:-]*\s+)?"
        rf"(?:added|logged|saved|marked|updated|recorded|noted)\b[^?\n]*(?:[.!\n]|$)",
        r"\b(?:has|have) been (?:added|logged|saved|updated|marked|recorded|moved)\b",
        r"\b(?:that's|it's|that is) (?:now )?(?:added|logged|saved|noted|recorded)\b",
        r"\byou(?:'re| are) now marked\b",
    )
]
# Without a save tool on offer, a claim only counts if it's about these.
_ABOUT = re.compile(r"\b(list|log|habit|chore|task|to-?do|tracker|backlog|daily note|watch)", re.IGNORECASE)
_SAVE_VERB = re.compile(r"\b(add|log|save|mark|record|track|put)\b", re.IGNORECASE)


def should_check(message: str, offered: set[str]) -> bool:
    """Whether this turn could be asking for a save. Questions aren't."""
    return "?" not in message and bool(offered & WRITE_TOOLS or _SAVE_VERB.search(message))


def saved(tool: str, result) -> bool:
    if tool not in WRITE_TOOLS:
        return False
    text = str(result).strip().lower()
    return not text.startswith(_FAILED) and "nothing was logged" not in text


def claims(reply: str, offered: set[str]) -> bool:
    text = reply.replace("’", "'").replace("*", "")
    if not any(pattern.search(text) for pattern in _CLAIMS):
        return False
    return bool(offered & WRITE_TOOLS or _ABOUT.search(text))


def fresh_context(messages: list[dict]) -> list[dict]:
    """The system prompt with the nudge, and just enough recent talk: the
    latest message, plus the exchange before it when that is a short reply
    like "yes". `messages` is the conversation before the first attempt."""
    system, talk = messages[0], messages[1:]
    keep = 3 if talk and len(talk[-1].get("content", "").split()) <= 4 else 1
    return [{**system, "content": f"{system['content']} {NUDGE}"}, *talk[-keep:]]
