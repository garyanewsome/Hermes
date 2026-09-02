"""Tool registry. `search_vault` (semantic) and `list_notes` (structural
folder listing) are deliberately separate tools, not one merged tool —
they answer different question shapes ("what do my notes say about X"
vs. "what files exist under folder X") and RAG can't reliably do the
second one. Adding a third tool later is just adding another dict here
and a handler function, not restructuring anything."""

import httpx

from app.config import ATHENAEUM_HOST_HEADER, ATHENAEUM_URL


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
]

TOOL_HANDLERS = {"search_vault": search_vault, "list_notes": list_notes}
