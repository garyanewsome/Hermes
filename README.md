# Hermes

General-purpose personal assistant with a growing tool registry — not scoped to any single tool.

## What it does

`POST /chat {"message": "...", "conversation_id": "...", "model": "...", "think": false}` — streams the reply back as NDJSON lines while the model generates. `conversation_id` can be `null` to start a new conversation; server owns and persists conversation history (SQLite). `think` toggles Ollama's hybrid-reasoning mode (relevant for Qwen3-family models) — defaults off, since the hidden chain-of-thought pass streams under a field Hermes doesn't surface, making a request look stuck until it finishes; has no effect on models without a thinking mode.

When the model decides a tool would help, Hermes executes it and feeds the result back — transparent to the client, tool-call turns just produce no visible tokens until the model's actual answer streams.

**Tools:**
- `search_vault` — semantic search over the vault (calls Athenaeum's `/search`)
- `list_notes` — structural folder listing (calls Athenaeum's `/browse`)
- `generate_image` — image generation (calls Iris's `/generate`). Bidirectional GPU handoff around the call: unloads the chat model from Ollama (`keep_alive: 0`) right before calling Iris, and calls Iris's own `/unload` right after — generate_image fires mid-turn with zero idle gap on either side, so without this, Iris's pipeline load could OOM against a still-resident chat model, and the very next Ollama reload (for the follow-up reply) could just as easily OOM against a still-resident Iris pipeline. Same class of problem already solved for Selene/images-after-dark, just never applied to this path. Both unload calls are best-effort (logged, not fatal) and now check the response status instead of assuming success. The raw image markdown (with its real URL) is streamed to the client for display but deliberately never persisted into conversation history — a saved copy would re-enter the model's own context on the next message in that chat, and asking for "another one" of the same thing would get the model referencing/half-retyping the old URL instead of generating a new image (confirmed live). The system prompt also explicitly tells the model to always call the tool again for a repeated image request, not just claim in text that it already did.
- The chat loop never lets a broken connection to Ollama (GPU OOM on reload, timeout, restart, ...) kill the HTTP stream outright — that surfaced to clients as an opaque "Error in input stream" with no indication of what happened. It's caught and surfaced as a normal in-chat message instead, ending that turn cleanly.
- `save_project_memory` / `recall_project_memory` — persistent memory for VST/audio plugin development work (calls a self-hosted Hindsight instance). Scoped deliberately narrow via the tool description — most messages should not trigger a save, only durable decisions/facts worth recalling later.
- `add_task` / `list_tasks` / `complete_task` — to-dos filed directly into one of four quadrants (`do` / `schedule` / `next` / `backlog`), backed by a dedicated `planner` Postgres database (see below).
- `log_habit` / `habit_status` — daily habit tracking, same `planner` database. `habit_status` returns each of the last 7 days' actual logged/missed dates (not just the streak number), so you can ask Hermes things like "how'd I do this week" or "did I miss Tuesday" and it has real data to answer from. "Today" for logging/streaks is computed in `APP_TIMEZONE` (`America/New_York` by default), not the pod's system clock — K3s containers run UTC regardless of the host's actual local time, so a naive `date.today()` rolled over to the next day hours before it actually was tomorrow locally (confirmed live: still showing today's log as done at 7:39pm Eastern, because UTC had already ticked past midnight).
- `add_todo_item` / `list_todo_items` / `complete_todo_item` — the plain everyday Todo lists (see UI section), deliberately a separate tool set from `add_task`/etc. so the model doesn't conflate "add milk to my grocery list" with the music-production/dev Tasks board. Naming a list that doesn't exist yet creates it (same as `log_habit`); omitting one uses/creates "General". Fuzzy-matched by name/text throughout, and `complete_todo_item` returns a disambiguation prompt instead of guessing when more than one item matches.
- `add_scratch_note` / `search_scratch_notes` / `list_recent_scratch_notes` — the Notes scratchpad (see UI section). Named with a `scratch_note`/`scratch_notes` prefix specifically to avoid colliding with the existing `list_notes` tool, which is Athenaeum's vault folder browser — an unrelated feature that happens to share the word "notes". Deliberately looser-firing than `save_project_memory`: this is meant to catch anything the user explicitly asks to jot down, not just durable VST/audio decisions.
- `research_repo` / `forget_repo` — calls a separate [CodebaseSearcher](https://github.com/garyanewsome/CodebaseSearcher) service (`CODEBASE_SEARCHER_URL`) to look at one of the user's GitHub repos on demand: clone/pull, semantic-search its code for a question, write the findings into the Obsidian vault as a note. On-demand, not a background sync like `search_vault`'s Athenaeum — re-indexes only if the repo's commit actually moved since the last time it was asked about. `forget_repo` deletes the local clone/index (disposable, regenerable) without touching any findings note already written to the vault.

**Other endpoints:**
- `GET /models` — chat-capable models available (filtered to Ollama's `tools`-capability models only)
- `GET /conversations`, `GET /conversations/{id}`, `PATCH /conversations/{id}` (rename), `DELETE /conversations/{id}`
- `GET /tasks`, `POST /tasks`, `PATCH /tasks/{id}` (partial update: quadrant/title/notes/position, any subset), `PATCH /tasks/{id}/complete`, `PATCH /tasks/{id}/reopen`, `DELETE /tasks/{id}`
- `GET /habits`, `POST /habits/log`, `PATCH /habits/{id}/log` (set/unset a specific day, for the dot tracker's undo), `DELETE /habits/{id}` — same data the tools use, for a future dashboard UI
- `GET /todo-lists`, `POST /todo-lists`, `PATCH /todo-lists/{id}` (rename), `DELETE /todo-lists/{id}` (cascades to its items); `GET /todo-lists/{id}/items`, `POST /todo-lists/{id}/items`, `PATCH /todo-items/{id}` (partial update: `text`/`done`/`due_date`, any subset — same omitted-vs-clear convention as `PATCH /tasks/{id}`), `DELETE /todo-items/{id}`
- `GET /notes`, `POST /notes` (creates a blank note), `PATCH /notes/{id}` `{"content": "..."}`, `DELETE /notes/{id}`
- `GET /sketches`, `POST /sketches` `{"width": ..., "height": ...}` (creates a blank canvas at that logical size), `PATCH /sketches/{id}` (partial: `strokes`/`title`, any subset), `DELETE /sketches/{id}`
- `GET /health`
- `POST /login {"password": "..."}` — sets a signed session cookie; `POST /logout` clears it; `GET /auth/check` (200 if the cookie is valid, 401 otherwise, used by the frontend on load)

## Auth

A single shared password gates the whole app — no accounts, this is a personal single-user tool. A FastAPI middleware (not per-route `Depends`) enforces this deny-by-default: everything needs a valid signed session cookie *unless* explicitly public (`/login`, `/logout`, `/health`, and the static SPA shell — index.html, the JS/CSS bundle, icons, the manifest — since the shell is just code and can't fetch anything real without logging in first). An earlier version did the opposite — an allow-list of *protected* prefixes — which meant a new API route was unprotected by default unless someone remembered to add it there; that's backwards for a security check, and the kind of gap that stays invisible until something new ships through it. The frontend checks `/auth/check` on load and shows a login screen if it 401s; any other API call that gets a 401 (session expired mid-use) fires a `hermes:unauthorized` window event that does the same, so a stale session doesn't just leave views silently failing.

Deliberately app-level rather than a Traefik `BasicAuth` middleware on the Ingress: Hermes is also reachable via a NodePort (see Deployment) which routes straight to the pod, bypassing Traefik entirely, so ingress-level auth would only ever cover the hostname path and leave the NodePort one wide open. One check inside the app covers both.

Session cookie is `HttpOnly` + `SameSite=Lax`, signed (HMAC-SHA256 over an expiry timestamp, `SESSION_SECRET`) rather than random+server-stored, since there's no session store to look one up in. No `Secure` flag — this runs over plain HTTP on the LAN, not HTTPS, and `Secure` would silently stop the cookie from being set at all. `AUTH_PASSWORD` and `SESSION_SECRET` come from a K8s secret in deployment (see Deployment); both have insecure dev-only defaults in `app/config.py` so local dev doesn't need a `.env` just to log in.

## UI

React app in `frontend/`, built to `static/` and served by the same FastAPI app at `/` (`static/` is generated — not committed, see Deployment). Black background with a per-view neon accent (blue for Chat, green for Tasks, pink for Habits, purple for Todo, Matrix/terminal green for Notes, orange for Sketch), switched via a hamburger menu that opens an overlay nav drawer. Installable as a home-screen app on Android/Chrome (`manifest.webmanifest`, standalone display) with a little grey Asgard-style alien as the icon and browser favicon (`public/icons/`) — matches the app's own name. All views stay mounted at all times (hidden with `display:none`/shown with `display:contents` in `App.jsx`, never conditionally rendered) — the earlier conditional-render approach unmounted whichever view you left, silently wiping its state, so switching away from an open conversation and back showed an empty chat with nothing selected until a full page reload. Views:
- **Chat** — bubbles, streaming responses, a model dropdown (defaults to `qwen3:14b` when present, not just whatever Ollama's `/api/tags` happens to list first), a persistent conversation sidebar on the right (right-click to rename/delete — delete goes through an in-app confirm modal, not the browser's native `confirm()`, whose Enter-key behavior isn't reliably wired to its own default button across browsers), Enter-to-send, and a Stop button that genuinely halts generation server-side. The sidebar lives on the right specifically so the hamburger menu stays in the same top-left spot across every view — it used to sit on the left and shift the whole layout, the only view where the hamburger wasn't where you'd expect it. Small dependency-free markdown renderer (bold, italic, code, headers, lists, images — images are capped to the bubble's own width, not their natural size).
- **Tasks** — four quadrants, each just a plain category (**TODO**, **Schedule / plan**, **NEXT**, **Backlog**), each with its own neon color (black card background, colored border/glow) — a task belongs to exactly the quadrant it's filed under, tracked as `quadrant` + a per-quadrant `position` (fractional, so reordering never has to renumber siblings). Each quadrant has its own inline `+` to add a task directly into it — adds are optimistic (shown immediately, not after a create-then-refetch round trip); drag a card onto another card to reorder within a box, or onto empty space in a different box to refile it; a checkbox marks it done, a trash icon deletes it — both optimistic too, no visible round trip. Cards stay a single line — clicking the title (not the checkbox or trash) opens a modal to edit the title, an optional description (`notes`, most tasks won't have one — a small icon shows when set), and a due date (settable/clearable there; shows as a badge on the card when set). A **Board / Done** toggle switches to a flat, most-recently-finished-first list of completed tasks (they no longer just vanish) — each with a reopen button (back to its original quadrant/position, not lost) and a trash icon for permanent cleanup.
- **Habits** — streak per habit with a 7-day dot tracker backed by real per-day history (each dot is its own logged/not-logged date, not derived from the streak count); click a dot to toggle that specific day — undo an accidental log, or backfill a day you forgot; "Log today" for the common case; add a new habit; delete one via an in-app confirm modal (its whole log history goes with it — `habit_logs` cascades on delete).
- **Todo** — a plain everyday checklist, deliberately kept apart from Tasks (which stays for music-production/dev whiteboarding — Todo is for everything else; Tasks may get renamed to something less easily confused with Todo, e.g. "Studio", still undecided): multiple named lists (a list picker on the right, same responsive pattern as Chat's conversation sidebar — a permanent column on desktop, an off-canvas overlay on mobile), each holding a flat set of items. Open items stay in the order added; checking one off sinks it below the still-open ones (optimistic update matches the server's own `ORDER BY (done, created_at)`, so nothing reshuffles on refresh). A list's open-item count badges its row in the picker. Click an item's text to rename it inline (Enter commits, Escape cancels); a calendar icon sets an optional due date, shown as a small badge with its own clear (×) once set. Rename a list via the pencil icon; delete a list (in-app confirm — its items cascade with it) or an item any time.
- **Notes** — a Simplenote-style plain-text scratchpad, meant for jotting something down (from anywhere, now that Tailscale's set up) to move into Obsidian later, not to replace it. No titles — the first line of a note's text serves as its title in the list, same idea as Simplenote. Autosaves on a 600ms debounce after you stop typing (not on every keystroke, and not on an explicit save action); switching notes or creating a new one flushes any pending save first, so nothing in progress gets lost. The note list (right sidebar, same responsive column/overlay pattern as Todo and Chat) sorts by most-recently-edited and has a plain substring search box. Delete via an in-app confirm modal.
- **Sketch** — a freehand canvas for drawing/writing with a stylus (or mouse/touch — everything's built on the Pointer Events API, which unifies all three; a pen reports real pressure via `event.pressure`, a mouse reports a flat 0.5). Drawings are stored as *vector* stroke data (`{tool, color, width, points: [{x, y, pressure}]}` per stroke, in a `strokes` JSONB column), not a flattened raster image — same rationale as everywhere else in this app: keeps it editable/resizable rather than a dead pixel blob. Each sketch has a fixed logical canvas size (1000×1400) independent of whatever device it's viewed on, so coordinates — and exports — stay consistent whether it was started on the tablet or reopened on a phone. A handful of preset colors and pen widths (thin/medium/thick), an eraser (implemented as drawing in white, not true alpha transparency — the canvas is always opaque anyway, and it keeps SVG export simple since an erase stroke needs no special masking), undo/redo (pure in-memory stroke-array slicing, not server round trips), and a destructive clear (in-app confirm). **Export** buttons regenerate a PNG (straight off the live canvas via `canvas.toBlob`) or an SVG (hand-built from the same stroke data — each stroke becomes a `<polyline>`, sized/colored/widthed to match) on demand, so a sketch never has to "choose" an export format up front. List sidebar (same responsive pattern as Todo/Notes) shows a live thumbnail per sketch, rendered from its actual stroke data at a smaller size, not a cached snapshot.

**Mobile layout** (`useIsMobile.js`, a `matchMedia` hook at a 700px breakpoint — below phone width, above the small-tablet width the app actually targets): the conversation sidebar and nav drawer become off-canvas overlays instead of permanent columns; the Tasks board stacks into one scrollable column instead of a 2×2 grid; the Habits row wraps instead of overflowing; `TopBar` wraps its controls onto a second line. Dragging a task card between quadrants uses the HTML5 drag API, which never fires from touch input at all — as the only way to recategorize a task on a phone/tablet, the task detail modal has a "Move to" button per other quadrant, doing the same append-to-end-of-quadrant move as a drag drop. Safe-area insets (`env(safe-area-inset-*)`) pad the top bar and chat input so content doesn't sit under a phone's notch or gesture bar when installed as a home-screen app.

## Stack

- Python + FastAPI, async throughout the chat path (needed for real streaming cancellation)
- SQLite for conversation history (stdlib, no new dependency)
- Postgres (`psycopg`) for tasks/habits/todo lists/notes/sketches — a separate `planner` database, not Hindsight's. Hindsight is semantic recall over durable facts; this is mutable structured state that doesn't belong in a recall-by-similarity store.
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
Opens on `http://localhost:5173` and proxies `/chat`, `/models`, `/conversations`, `/tasks`, `/habits`, `/todo-lists`, `/todo-items`, `/notes`, `/sketches`, `/login`, `/logout`, `/auth`, `/health` to the backend on port 8001 (see `vite.config.js`) — run both at once for a working dev setup.

## Deployment

`static/` is generated by the frontend build, not committed — the Dockerfile's first stage runs `npm run build` and copies its output in, so `./deploy.sh` builds both without any extra steps.

Runs in K3s:
- `k8s/hermes-api.yaml` — Deployment + two Services + Ingress. The `hermes-api` Service backs the `hermes.home.local` Ingress (needs per-device `/etc/hosts`, fine on computers you control); `hermes-api-nodeport` is a NodePort on `30080` reachable as `http://<any-node-ip>:30080` from any device on the LAN with zero setup — this is the one to bookmark on a phone or tablet, since editing hosts files isn't practically possible there.
- `k8s/hermes-pv.yaml` — PersistentVolume/Claim for the conversation database
- `k8s/planner-postgres.yaml` — Deployment + Service + PersistentVolume/Claim for the `planner` Postgres (tasks/habits)
- `k8s/planner-postgres-backup-cronjob.yaml` — daily `pg_dump` of the planner Postgres to `/mnt/storage/planner-backups`, keeping the last 7 (plain `.sql` files, not `pg_dump`'s custom format — a backup should be a file you can read and `psql <` without needing `pg_restore`). Exists because a bad migration guard once silently dropped the tasks table on a routine deploy with nothing to recover from — see git history on `planner_db.py` if curious. Has explicit `activeDeadlineSeconds` + history limits from the start, learned from the vault-sync incident (a hung CronJob run with neither will pile up stuck job objects forever instead of just failing).

Reaches Athenaeum over in-cluster service DNS (`http://athenaeum-api:8000`) and Iris directly by host IP:port (Iris runs bare-metal, not in K3s — see Iris' own README). Reaches `planner-postgres` over in-cluster DNS too.

**One-time setup before the first deploy with planner support:** create the Secret both `hermes-api` and `planner-postgres` read from (not stored in the yaml — this needs `kubectl`, which only works from the homelab's own terminal, not over the `homelab-agent` SSH connection):
```bash
kubectl create secret generic planner-postgres-secret \
  --from-literal=password='<pick a password>' \
  --from-literal=hermes-db-url='postgresql://hermes:<same password>@planner-postgres:5432/planner'
kubectl apply -f k8s/planner-postgres.yaml
kubectl apply -f k8s/planner-postgres-backup-cronjob.yaml
```

**One-time setup before the first deploy with auth enabled:** create the Secret `hermes-api` reads `AUTH_PASSWORD`/`SESSION_SECRET` from:
```bash
kubectl create secret generic hermes-auth-secret \
  --from-literal=auth-password='<pick a login password>' \
  --from-literal=session-secret="$(openssl rand -hex 32)"
```
Without this secret the pod falls back to `app/config.py`'s dev defaults (`AUTH_PASSWORD=hermes`, a fixed `SESSION_SECRET`) — fine for local dev, not for anything reachable on the LAN, so create this before exposing the NodePort.

**Restoring from a backup:**
```bash
kubectl exec -i deploy/planner-postgres -- sh -c \
  'PGPASSWORD=$POSTGRES_PASSWORD psql -U hermes -d planner' < /mnt/storage/planner-backups/planner-<timestamp>.sql
```
`-i` (not `-it`) is deliberate — piping a file into stdin needs no tty, and `-t` fights it. Run from the homelab host, where that path is a real file; `kubectl cp` it out of the CronJob's PV first if running this from elsewhere.

To redeploy after a code change: `./deploy.sh` — builds the image, reimports it into K3s, and restarts the deployment.

## Reliability

Reported live: "every page... if idle too long or sometimes on a restart it just seems stuck," fixed with two changes on either side of the connection:

- **`k8s/hermes-api.yaml`** now has a `readinessProbe`/`livenessProbe` against `/health`. Without them, a rolling restart had no way to know the new pod could actually serve traffic yet — Kubernetes' default is to treat "container process started" as "ready," so requests could land on a pod mid-`init_planner_db()`, before Uvicorn was even listening. A genuinely wedged app (hung event loop, exhausted connection pool) also had no way to get detected or auto-restarted — it would just sit broken until someone noticed and manually restarted it.
- **`frontend/src/api.js`** — no fetch anywhere had a timeout, so a stale connection (a browser-cached keep-alive left over from a long-idle tab, or the backend pod mid-restart) just hung forever with no recovery short of a manual page refresh. Every regular API call now times out at 15s and retries once automatically on a fresh connection — a hang is essentially always a dead connection, not a slow server, so the retry succeeds silently rather than surfacing an error. `checkAuth()` gets the same treatment despite bypassing the shared `apiFetch` wrapper (it runs before login, so it can't dispatch the same "session expired" event) — and `App.jsx` now catches a `checkAuth()` that fails even after the retry, falling to the login screen instead of leaving the blank "still checking" state up forever, which is exactly what an uncaught rejection there used to do.
- **`ChatView.jsx`**'s streaming `/chat` fetch gets its own stall-timeout (45s of receiving nothing at all, reset on every chunk so an actively-streaming reply is never cut short) — a normal request timeout doesn't apply to a stream that's supposed to stay open, so this needed its own mechanism rather than reusing `apiFetch`.

Verified live: simulated a completely hung backend (a fake server that never responds) and confirmed the app times out, retries once, and falls back to a working state (the login screen) instead of hanging indefinitely — then confirmed a real backend afterward recovers cleanly with no lingering broken state from the failed attempt.

## Status

- [x] Streaming chat with real mid-generation cancellation
- [x] Tool-calling: `search_vault`, `list_notes`, `generate_image`, `save_project_memory`/`recall_project_memory`
- [x] Server-side conversation history with rename/delete
- [x] Tasks (four-quadrant board, tracked by which quadrant a task is filed under) and habit tracking, backed by a dedicated `planner` Postgres
- [x] React UI: black + per-view neon theme, hamburger view switcher, Chat/Tasks/Habits — verified end to end locally (real Ollama model, real Postgres) before this landed
- [x] Deployed, verified against real live services (not mocks)
- [x] Single-password login gating the whole app (session cookie, `app/auth.py`) — needed once the NodePort made Hermes reachable from more than just hosts-file-configured computers
- [x] NodePort (`30080`) for zero-setup LAN access from phones/tablets, alongside the existing hostname Ingress
- [x] Mobile layout pass (overlay drawers, stacked Tasks board, wrapping Habits rows, touch-friendly quadrant moves) — verified against real phone/tablet widths, not just resized-desktop-window guessing
- [x] Home-screen install with a custom icon/favicon (little grey alien)
- [x] Todo view — separate multi-list checklist, deliberately kept simpler than the Tasks board (see UI section)
- [x] Auth middleware fixed to deny-by-default (was an allow-list of protected routes — backwards; a new route needs no special handling now to be covered)
- [x] Remote access via Tailscale (the homelab and phone/tablet are on the same tailnet) — reaches Hermes from anywhere, not just the home LAN, with no port-forwarding and no public exposure; set up on the homelab side (`sudo tailscale up`), not tracked in this repo
- [x] Notes view — Simplenote-style plain-text scratchpad with debounced autosave, meant to feed ideas into Obsidian later (see UI section)
- [x] Sketch view — freehand drawing with real stylus pressure support, stored as vector strokes (JSONB, not a raster blob), with PNG/SVG export (see UI section)
- [x] Chat tool access for Todo (`add_todo_item`/`list_todo_items`/`complete_todo_item`) and Notes (`add_scratch_note`/`search_scratch_notes`/`list_recent_scratch_notes`) — verified end to end through the real chat tool-call pipeline (fake-Ollama-driven, not just direct handler calls), not just the REST API. Sketch deliberately has no chat tools — no clear value in a model calling a drawing canvas.
- [x] Habit "today" fixed to use `APP_TIMEZONE` instead of the pod's UTC system clock — was rolling over to the next day hours before it actually was tomorrow locally (see Tools section)
- [x] Fixed the whole app hanging indefinitely on a stale connection (long-idle tab, or a pod restart) with no recovery but a manual refresh — request timeouts + one automatic retry everywhere, plus K8s readiness/liveness probes so a restart can't route traffic to a not-yet-ready pod (see Reliability section)
- [x] `research_repo`/`forget_repo` tools added, calling the new CodebaseSearcher service (see Tools section) — CodebaseSearcher itself is built and verified but not yet deployed, so these tools will fail until it's up and `CODEBASE_SEARCHER_URL` is set

## Not yet decided / open

- No HTTPS — login password and session cookie travel as plaintext HTTP, both on the LAN and over Tailscale's own encrypted tunnel (which wraps the plaintext HTTP but doesn't change what Hermes itself speaks). Acceptable given Tailscale's tunnel is itself encrypted end-to-end, but worth revisiting if that assumption ever changes
