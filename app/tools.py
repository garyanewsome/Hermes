"""Tool registry. `search_vault` (semantic) and `list_notes` (structural
folder listing) are deliberately separate tools, not one merged tool —
they answer different question shapes ("what do my notes say about X"
vs. "what files exist under folder X") and RAG can't reliably do the
second one. Adding a third tool later is just adding another dict here
and a handler function, not restructuring anything."""

import httpx

from app.config import ATHENAEUM_HOST_HEADER, ATHENAEUM_URL, HINDSIGHT_BANK_ID, HINDSIGHT_URL, IRIS_URL
from app import planner_db


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


def log_habit(name: str) -> str:
    planner_db.log_habit(name)
    streak = planner_db.habit_streak(name)
    day = "day" if streak == 1 else "days"
    return f"Logged \"{name}\" for today. Current streak: {streak} {day}."


def _format_last_7_days(days: list[dict]) -> str:
    return ", ".join(f"{d['date']}: {'done' if d['logged'] else 'missed'}" for d in days)


def habit_status(name: str | None = None) -> str:
    habits = planner_db.list_habits_with_streaks()
    if not habits:
        return "No habits being tracked yet."
    if name:
        match = next((h for h in habits if h["name"] == name), None)
        if not match:
            return f"No habit named \"{name}\" found."
        habits = [match]
    return "\n".join(
        f"{h['name']}: {h['streak']} day streak. Last 7 days — {_format_last_7_days(h['last_7_days'])}."
        for h in habits
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
                "Log today's occurrence of a habit and report the current streak. "
                "Use when the user mentions doing something they track as a habit "
                "(e.g. 'went for a run today', 'meditated this morning')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The habit's name, e.g. 'meditate' or 'run'"}
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
                "Report streak(s) and the last 7 days' actual logged/missed dates "
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
}
