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
- `add_task` / `list_tasks` / `complete_task` — to-dos classified on the Eisenhower matrix (urgent × important), backed by a dedicated `planner` Postgres database (see below).
- `log_habit` / `habit_status` — daily habit tracking with streak counting, same `planner` database.

**Other endpoints:**
- `GET /models` — chat-capable models available (filtered to Ollama's `tools`-capability models only)
- `GET /conversations`, `GET /conversations/{id}`, `PATCH /conversations/{id}` (rename), `DELETE /conversations/{id}`
- `GET /tasks`, `POST /tasks`, `PATCH /tasks/{id}/complete`, `DELETE /tasks/{id}`
- `GET /habits`, `POST /habits/log` — same data the tools use, for a future dashboard UI
- `GET /health`

## UI

Single static page (`static/index.html`) served by the same FastAPI app at `/` — vanilla HTML/CSS/JS, no framework, no build step. Chat bubbles, streaming responses, a model dropdown, a conversation sidebar (right-click to rename/delete), Enter-to-send, and a Stop button that genuinely halts generation server-side (not just the UI). Includes a small dependency-free markdown renderer (bold, italic, code, headers, lists, images).

## Stack

- Python + FastAPI, async throughout the chat path (needed for real streaming cancellation)
- SQLite for conversation history (stdlib, no new dependency)
- Postgres (`psycopg`) for tasks/habits — a separate `planner` database, not Hindsight's. Hindsight is semantic recall over durable facts; tasks and habit streaks are mutable structured state that doesn't belong in a recall-by-similarity store.
- Talks to Ollama directly for chat completions, and to Athenaeum/Iris as tools

## Running it locally

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8001
# then: curl -N -X POST localhost:8001/chat -d '{"message": "...", "conversation_id": null}'
```

## Deployment

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
- [x] Tasks (Eisenhower matrix) and habit tracking, backed by a dedicated `planner` Postgres
- [x] Deployed, verified against real live services (not mocks)

## Not yet decided / open

- A real UI for tasks/habits beyond the chat tools and raw REST endpoints (`/tasks`, `/habits`) — candidate for a separate React dashboard hitting this API
- Task editing (change urgency/importance/due date after creation) — currently create/list/complete/delete only
