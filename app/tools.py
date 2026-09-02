"""Tool registry. Athenaeum's vault search is the first entry — adding a
second tool later is just adding another dict here and a handler function,
not restructuring anything."""

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


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_vault",
            "description": "Search the user's personal Obsidian notes vault for relevant information.",
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
    }
]

TOOL_HANDLERS = {"search_vault": search_vault}
