# Hermes

General personal assistant — not scoped to just Obsidian. Athenaeum's
vault search is the first tool in a growing tool registry; more tools
(calendar, etc.) get added the same way later, without restructuring
anything.

Backend/API first, on purpose — no UI yet. (Lesson from a past
project: build UI speculatively and it tends not to match what was
actually pictured. Get the logic right, decide on UI shape later,
once there's something real to react to.)

## What it does

`POST /chat` with one message + a `conversation_id` (or `null` to
start a new one) → streams the reply back as NDJSON lines while Ollama
generates it. When the model decides a tool would help, Hermes
executes it (currently just `search_vault`, which calls the live
Athenaeum API) and feeds the result back to the model — transparent to
the client, tool-call turns just produce no visible tokens. Server
owns conversation history now (SQLite-backed, see below), not the
client.

## Status — scaffolded, tested against real live services

Tested against the actual deployed Athenaeum API (`athenaeum.home.local`,
not a mock) and real Ollama, with genuine questions about the real
vault:
- "What do my notes say about house tasks?" → correctly called
  `search_vault`, answered based on real daily notes
- "Search my notes for anything about Spanish learning" → found
  related-but-not-exact content, and **correctly said so** rather than
  fabricating a direct answer — good sign for tool-calling honesty
  with `qwen2.5:7b`

## Deployed — live on the LAN

`k8s/hermes-api.yaml` — Deployment + Service + Ingress
(`hermes.home.local`). Talks to Athenaeum over in-cluster service DNS
(`http://athenaeum-api:8000`) now that both run in K3s — no
IP/Host-header trick needed for that hop (that trick's still used by
local-dev instances reaching Athenaeum through its Ingress from
outside the cluster).

Verified through the real Ingress path (not localhost) with a genuine
question — correctly retrieved and named specific real Songbook
entries from the vault.

## UI — built, dependency-free

Single static page (`static/index.html`), served by the same FastAPI
app at `/` — vanilla HTML/CSS/JS, no framework, no build step,
matching the "backend is proven, don't over-invest in a build
pipeline for one simple page" reasoning. React was considered and
deliberately skipped — no real component/state complexity here that
would justify it.

Chat bubbles, Enter-to-send (Shift+Enter for newline), and a small
hand-rolled markdown renderer (bold, italic, inline code, headers,
ordered/unordered lists) — added after noticing real model responses
came back with markdown formatting that rendered as literal asterisks
otherwise. Escapes raw content before rendering, so nothing from the
model or vault content can inject real HTML.

One real bug caught and fixed during testing: list items separated by
blank lines (a common LLM output style) were each becoming their own
single-item list and restarting numbering at 1 — fixed by treating
blank lines as no-ops rather than list-flush triggers.

## Model selection + chat history — built, deployed

**Model dropdown**: `GET /models` queries Ollama and returns only
models with the **`tools` capability** (checked via `/api/show`'s real
`capabilities` field, not a name-based guess) — Hermes requires
tool-calling to reach Athenaeum, so an incompatible model would
silently break mid-conversation if selectable. Model is now a
per-request parameter instead of a hardcoded constant.

**Chat history**: real server-side persistence via SQLite (stdlib,
no new dependency), on its own PVC (`hermes-data`,
`/mnt/storage/hermes-data`) so it survives pod restarts — deliberately
server-side rather than browser localStorage, so history is
consistent regardless of which device hits `hermes.home.local`. API
shape changed accordingly: client sends one new message +
`conversation_id` (server loads/appends/persists), rather than
resending full history each time. Sidebar lists past conversations
(auto-titled from the first message), click to reopen, "+ New chat"
to start fresh.

Verified through the real deployed Ingress path: conversation
persisted across a page reload, correctly restored full message
history including markdown rendering, model list correctly excluded
the embedding-only model.

## Rename, delete, and real Stop — built, deployed

**Rename/delete**: right-click a sidebar conversation for a small
context menu. Rename edits inline (Enter/blur to commit, Escape to
cancel); delete confirms first (`window.confirm`) since it's
unrecoverable.

**Stop button**: the Send button becomes a red "Stop" while a reply is
generating. This required switching `/chat` to a real streaming
response (NDJSON lines over `StreamingResponse`, Ollama called with
`stream: true`) — with the earlier non-streaming design, aborting only
ever unstuck the *client*; Ollama kept generating server-side
regardless, since the entire reply had to exist before anything could
be returned. With streaming, an aborted `fetch` closes the response
body reader, which closes Hermes's own streaming connection to Ollama,
which **actually stops Ollama generating** — verified by checking GPU
utilization drop to 0% within ~1-2 seconds of hitting Stop (both via a
scripted test and a real UI click), not just "the browser stopped
listening." Whatever was generated before the stop is still persisted
to conversation history (a `finally` block saves accumulated text even
on client disconnect) — a stopped reply isn't just discarded.

Tool-calling verified working through the streaming path too: Ollama
sends tool_calls as one complete chunk with empty content (not
streamed token-by-token themselves), so the loop executes the tool
silently and continues streaming the model's actual answer once it
has the tool's result.

## `list_notes` tool + honesty fix — built + image ready, not yet live

Added after a real conversation exposed two real problems at once:
asked for files in a specific folder, got back results from three
unrelated folders (RAG has no concept of "list files under this exact
path" — see Athenaeum's README for the full diagnosis); then, when
directly asked "you don't have direct access to the folder structure,
do you," the model dodged the question and just re-ran the same
search instead of answering honestly.

Two fixes:
1. **New `list_notes` tool** — calls Athenaeum's new `/browse`
   endpoint (structural folder listing, not semantic search).
   `search_vault` and `list_notes` are kept as separate tools on
   purpose, with descriptions that tell the model which one fits which
   question shape, rather than one merged tool trying to do both.
2. **System prompt fix** — added an explicit instruction to answer
   honestly when asked about capabilities/limitations rather than
   deflecting by just running a tool again.

**Deployment status:** image built (includes both fixes) and sitting
as a tarball on the server (`/tmp/hermes.tar`), not yet imported —
needs the `sudo k3s ctr images import` step, same as Athenaeum's. Both
need to go out together (Hermes' new tool calls Athenaeum's new
endpoint). After importing both:
```bash
sudo k3s ctr images import /tmp/athenaeum.tar
sudo k3s ctr images import /tmp/hermes.tar
```
then (no sudo needed):
```bash
kubectl rollout restart deployment/athenaeum-api deployment/hermes-api
```
Verify with the actual query that surfaced this: ask Hermes to list
files in "Burn St Productions" — should now return real matching
folder(s)/files instead of unrelated semantic-search results.

## Not yet decided / open

- More tools beyond `search_vault` / `list_notes`

## Running it locally
```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8001
# then: curl -N -X POST localhost:8001/chat -d '{"message": "...", "conversation_id": null}'
```
Talks to Athenaeum directly via IP + `Host` header
(`athenaeum.home.local`) rather than needing local DNS — see
`app/config.py`.
