#!/usr/bin/env python3
"""A local MCP server that lets the Claude desktop app read lifting from
Naradi. Standard library only, so there is nothing to install.

It runs on your computer, talks to Claude over stdin/stdout, and calls three
read-only routes on Naradi. The token comes from the macOS Keychain
(service "naradi-connector"), never from Claude's config or the chat.
Set NARADI_URL to Naradi's address, for example http://192.168.1.157:30080.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

KEYCHAIN_SERVICE = "naradi-connector"
PROTOCOL = "2025-06-18"

READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}
TOOLS = [
    {
        "name": "lift_session",
        "description": (
            "The user's weight lifting on one day from Naradi: every set with weight and reps. Omit `date` for "
            "today's lift. If nothing is logged that day, it says so and returns the latest earlier workout; "
            "don't present that as the day asked about."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"date": {"type": "string", "description": "YYYY-MM-DD; omit for today"}},
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "exercise_history",
        "description": "When the user last did an exercise, what they lifted, and their best set, from Naradi.",
        "inputSchema": {
            "type": "object",
            "properties": {"exercise": {"type": "string", "description": "e.g. 'bench' or 'leg extensions'"}},
            "required": ["exercise"],
        },
        "annotations": READ_ONLY,
    },
    {
        "name": "personal_bests",
        "description": "The user's latest gym days and the best set for every exercise, from Naradi.",
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": READ_ONLY,
    },
]


class Problem(Exception):
    """Told to Claude as the tool's error."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # A redirect would carry the token somewhere else.
    def redirect_request(self, *args, **kwargs):
        return None


def token() -> str:
    try:
        found = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise Problem("The Keychain couldn't be read")
    if found.returncode != 0 or not found.stdout.strip():
        raise Problem(f"No token in the Keychain under \"{KEYCHAIN_SERVICE}\"; see docs/claude-connector.md")
    return found.stdout.strip()


def fetch(path: str, params: dict) -> str:
    base = os.environ.get("NARADI_URL", "").rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise Problem("NARADI_URL isn't set to Naradi's address")
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    request = urllib.request.Request(base + path + query, headers={"Authorization": f"Bearer {token()}"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    try:
        with opener.open(request, timeout=30) as response:
            return json.load(response)["text"]
    except urllib.error.HTTPError as error:
        reasons = {
            401: "Naradi refused the token; the Keychain and the homelab secret don't match",
            404: "Naradi's connector isn't set up (no token on the homelab), or the address is wrong",
            422: "Naradi didn't understand that request; dates are YYYY-MM-DD",
        }
        raise Problem(reasons.get(error.code, f"Naradi answered with error {error.code}"))
    except (OSError, ValueError, KeyError):
        raise Problem(f"Couldn't reach Naradi at {base}. Is this computer on the home network or Tailscale?")


def call(name: str, arguments: dict) -> str:
    if name == "lift_session":
        on = str(arguments.get("date") or "").strip()
        return fetch("/connector/session", {"on": on} if on else {})
    if name == "exercise_history":
        exercise = str(arguments.get("exercise") or "").strip()
        if not exercise:
            raise Problem("Say which exercise")
        return fetch("/connector/exercise", {"name": exercise})
    if name == "personal_bests":
        return fetch("/connector/bests", {})
    raise Problem(f"There's no tool called {name}")


def handle(message: dict):
    """The reply to one JSON-RPC message, or None when none is due."""
    method, ident = message.get("method"), message.get("id")
    if ident is None or method is None:
        return None  # a notification, or a reply to something
    params = message.get("params") or {}
    if method == "initialize":
        result = {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "naradi", "version": "1.0.0"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        try:
            text, failed = call(params.get("name"), params.get("arguments") or {}), False
        except Problem as problem:
            text, failed = str(problem), True
        result = {"content": [{"type": "text", "text": text}], "isError": failed}
    else:
        return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": f"Unknown method {method}"}}
    return {"jsonrpc": "2.0", "id": ident, "result": result}


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Not valid JSON-RPC"}}
        else:
            try:
                reply = handle(message)
            except Exception as error:  # never let one bad message end the server
                print(f"naradi connector: {type(error).__name__}", file=sys.stderr)
                reply = {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": -32603, "message": "Internal error"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
