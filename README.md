# Hermes

General-purpose personal assistant with a growing tool registry — not scoped to any single tool.

## What it does

`POST /chat {"message": "...", "conversation_id": "...", "model": "...", "think": false}` — streams the reply back as NDJSON lines while the model generates. `conversation_id` can be `null` to start a new conversation; server owns and persists conversation history (SQLite). `think` toggles Ollama's hybrid-reasoning mode (relevant for Qwen3-family models) — defaults off, since the hidden chain-of-thought pass streams under a field Hermes doesn't surface, making a request look stuck until it finishes; has no effect on models without a thinking mode.

When the model decides a tool would help, Hermes executes it and feeds the result back — transparent to the client, tool-call turns just produce no visible tokens until the model's actual answer streams.

**Tools:**
- `search_vault` — semantic search over the vault (calls Athenaeum's `/search`)
- `list_notes` — structural folder listing (calls Athenaeum's `/browse`)
- `generate_image` — image generation (calls Iris's `/generate`)
- `save_project_memory` / `recall_project_memory` — persistent memory for VST/audio plugin development work (calls a self-hosted Hindsight instance). Scoped deliberately narrow via the tool description — most messages should not trigger a save, only durable decisions/facts worth recalling later.
- `add_task` / `list_tasks` / `complete_task` — to-dos filed directly into one of four quadrants (`do` / `schedule` / `next` / `backlog`), backed by a dedicated `planner` Postgres database (see below).
- `log_habit` / `habit_status` — daily habit tracking with streak counting, same `planner` database.

**Other endpoints:**
- `GET /models` — chat-capable models available (filtered to Ollama's `tools`-capability models only)
- `GET /conversations`, `GET /conversations/{id}`, `PATCH /conversations/{id}` (rename), `DELETE /conversations/{id}`
- `GET /tasks`, `POST /tasks`, `PATCH /tasks/{id}` (partial update: quadrant/title/notes, any subset), `PATCH /tasks/{id}/complete`, `DELETE /tasks/{id}`
- `GET /habits`, `POST /habits/log`, `PATCH /habits/{id}/log` (set/unset a specific day, for the dot tracker's undo) — same data the tools use, for a future dashboard UI
- `GET /health`

## UI

React app in `frontend/`, built to `static/` and served by the same FastAPI app at `/` (`static/` is generated — not committed, see Deployment). Black background with a per-view neon accent (blue for Chat, green for Tasks, pink for Habits), switched via a hamburger menu that opens an overlay nav drawer. Views:
- **Chat** — bubbles, streaming responses, a model dropdown, a persistent conversation sidebar (right-click to rename/delete, independent of the view-switching drawer), Enter-to-send, and a Stop button that genuinely halts generation server-side. Small dependency-free markdown renderer (bold, italic, code, headers, lists, images).
- **Tasks** — four quadrants, each just a plain category (**TODO**, **Schedule / plan**, **NEXT**, **Backlog**), each with its own neon color (black card background, colored border/glow) — a task belongs to exactly the quadrant it's filed under, tracked as one `quadrant` field, no urgent/important flags underneath. Each quadrant has its own inline `+` to add a task directly into it; drag a card between quadrants to refile it (native HTML5 drag and drop, straight to the REST API — no LLM involved); a checkbox marks it done, a trash icon deletes it. Cards stay a single line — clicking the title (not the checkbox or trash) opens a modal to edit the title and an optional description (`notes`), which most tasks won't have; a small icon on the card shows when one's set.
- **Habits** — streak per habit with a 7-day dot tracker backed by real per-day history (each dot is its own logged/not-logged date, not derived from the streak count); click a dot to toggle that specific day — undo an accidental log, or backfill a day you forgot; "Log today" for the common case; add a new habit.

## Stack

- Python + FastAPI, async throughout the chat path (needed for real streaming cancellation)
- SQLite for conversation history (stdlib, no new dependency)
- Postgres (`psycopg`) for tasks/habits — a separate `planner` database, not Hindsight's. Hindsight is semantic recall over durable facts; tasks and habit streaks are mutable structured state that doesn't belong in a recall-by-similarity store.
- React + Vite for the UI (`frontend/`) — plain inline styles, no CSS framework, no component library
- Talks to Ollama directly for chat completions, and to Athenaeum/Iris as tools

## Running it locally

Backend:
```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
PLANNER_DB_URL=postgresql://hermes@localhost:5432/planner .venv/bin/uvicorn app.main:app --reload --port 8001
```
Needs a local Postgres with a `planner` database (`createdb planner`) — `init_planner_db()` creates the tables on startup.

Frontend (separate terminal):
```bash
cd frontend && npm install && npm run dev
```
Opens on `http://localhost:5173` and proxies `/chat`, `/models`, `/conversations`, `/tasks`, `/habits` to the backend on port 8001 (see `vite.config.js`) — run both at once for a working dev setup.

## Deployment

`static/` is generated by the frontend build, not committed — the Dockerfile's first stage runs `npm run build` and copies its output in, so `./deploy.sh` builds both without any extra steps.

Runs in K3s:
- `k8s/hermes-api.yaml` — Deployment + Service + Ingress (`hermes.home.local`)
- `k8s/hermes-pv.yaml` — PersistentVolume/Claim for the conversation database
- `k8s/planner-postgres.yaml` — Deployment + Service + PersistentVolume/Claim for the `planner` Postgres (tasks/habits)

Reaches Athenaeum over in-cluster service DNS (`http://athenaeum-api:8000`) and Iris directly by host IP:port (Iris runs bare-metal, not in K3s — see Iris' own README). Reaches `planner-postgres` over in-cluster DNS too.

**One-time setup before the first deploy with planner support:** create the Secret both `hermes-api` and `planner-postgres` read from (not stored in the yaml — this needs `kubectl`, which only works from the homelab's own terminal, not over the `homelab-agent` SSH connection):
```bash
kubectl create secret generic planner-postgres-secret \
  --from-literal=password='<pick a password>' \
  --from-literal=hermes-db-url='postgresql://hermes:<same password>@planner-postgres:5432/planner'
kubectl apply -f k8s/planner-postgres.yaml
```

To redeploy after a code change: `./deploy.sh` — builds the image, reimports it into K3s, and restarts the deployment.

## Status

- [x] Streaming chat with real mid-generation cancellation
- [x] Tool-calling: `search_vault`, `list_notes`, `generate_image`, `save_project_memory`/`recall_project_memory`
- [x] Server-side conversation history with rename/delete
- [x] Tasks (four-quadrant board, tracked by which quadrant a task is filed under) and habit tracking, backed by a dedicated `planner` Postgres
- [x] React UI: black + per-view neon theme, hamburger view switcher, Chat/Tasks/Habits — verified end to end locally (real Ollama model, real Postgres) before this landed
- [x] Deployed, verified against real live services (not mocks)

## Not yet decided / open

- Due date isn't editable after task creation, and isn't settable at all from the UI (only via the `add_task` tool) — no due-date field anywhere in the Tasks view yet
- No mobile layout pass yet — drawer and quadrant grid are fixed-ish widths, untested below ~900px
