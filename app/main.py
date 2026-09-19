import json
import logging
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import auth
from app.chat import list_models, run_chat_stream
from app.db import (
    add_message,
    create_conversation,
    delete_conversation,
    get_messages,
    init_db,
    list_conversations,
    maybe_set_title,
    rename_conversation,
)
from app import planner_db

logger = logging.getLogger("hermes")

app = FastAPI(title="Hermes")
init_db()

try:
    planner_db.init_planner_db()
except Exception:
    # The planner Postgres is a separate, optional dependency — chat and
    # every other tool must keep working even if it's unreachable at
    # startup. Individual /tasks, /habits, and tool calls will still fail
    # (and report why) the moment they're actually used.
    logger.exception("planner_db.init_planner_db() failed — tasks/habits will be unavailable until this is fixed")


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    model: str | None = None
    think: bool = False


class RenameRequest(BaseModel):
    title: str


Quadrant = Literal["do", "schedule", "next", "backlog"]


class TaskRequest(BaseModel):
    title: str
    quadrant: Quadrant
    due_date: str | None = None
    notes: str | None = None


class HabitLogRequest(BaseModel):
    name: str


class HabitDayRequest(BaseModel):
    date: str
    logged: bool


class TaskUpdateRequest(BaseModel):
    quadrant: Quadrant | None = None
    title: str | None = None
    notes: str | None = None
    position: float | None = None
    # Distinguishing "omitted" (None, don't touch) from "clear it" needs a
    # value that isn't None but also isn't a real date — "" means clear,
    # matching how title/notes already treat an empty-but-present string as
    # a real value, not "field not sent". See update_task's due_date arg.
    due_date: str | None = None


class LoginRequest(BaseModel):
    password: str


class TodoListRequest(BaseModel):
    name: str


class TodoItemRequest(BaseModel):
    text: str


class TodoItemUpdateRequest(BaseModel):
    text: str | None = None
    done: bool | None = None
    due_date: str | None = None


class NoteUpdateRequest(BaseModel):
    content: str


class SketchCreateRequest(BaseModel):
    width: int
    height: int


class SketchUpdateRequest(BaseModel):
    strokes: list | None = None
    title: str | None = None


# Deny-by-default: every request needs a valid session cookie UNLESS it's
# explicitly public. /login, /logout, /health, and the static SPA shell
# (index.html, the JS/CSS bundle, icons, the manifest) stay public — the
# shell itself is harmless without a session, it's just code, and the login
# screen is part of it. Everything else — including any future API route —
# is protected automatically just by not being on this list. An earlier
# version of this did the opposite (an allow-list of PROTECTED prefixes),
# which meant a new route was unprotected by default unless someone
# remembered to add it — exactly backwards for a security check, and the
# kind of gap that's invisible until something new ships through it.
_PUBLIC_PATHS = {"/login", "/logout", "/health", "/", "/manifest.webmanifest"}
_PUBLIC_PREFIXES = ("/assets/", "/icons/")


@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    if path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES):
        return await call_next(request)
    if not auth.verify_session_token(request.cookies.get(auth.COOKIE_NAME)):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return await call_next(request)


@app.post("/login")
def login(request: LoginRequest):
    if not auth.check_password(request.password):
        raise HTTPException(status_code=401, detail="Incorrect password")
    response = JSONResponse({"status": "ok"})
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.create_session_token(),
        max_age=auth.SESSION_LIFETIME_SECONDS,
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/logout")
def logout():
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(auth.COOKIE_NAME)
    return response


@app.get("/auth/check")
def auth_check():
    # Reaching this handler at all means the middleware already validated
    # the session cookie, so there's nothing left to check.
    return {"authenticated": True}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/models")
def models():
    return {"models": list_models()}


@app.get("/conversations")
def conversations():
    return {"conversations": list_conversations()}


@app.get("/conversations/{conversation_id}")
def conversation(conversation_id: str):
    messages = get_messages(conversation_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"id": conversation_id, "messages": messages}


@app.patch("/conversations/{conversation_id}")
def rename(conversation_id: str, request: RenameRequest):
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title can't be empty")
    rename_conversation(conversation_id, title)
    return {"status": "ok"}


@app.delete("/conversations/{conversation_id}")
def remove_conversation(conversation_id: str):
    delete_conversation(conversation_id)
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: ChatRequest):
    conversation_id = request.conversation_id
    is_new = conversation_id is None
    if is_new:
        conversation_id = create_conversation()

    history = get_messages(conversation_id)
    history.append({"role": "user", "content": request.message})

    add_message(conversation_id, "user", request.message)
    if is_new:
        maybe_set_title(conversation_id, request.message)

    async def event_stream():
        accumulated = ""
        yield json.dumps({"type": "conversation_id", "conversation_id": conversation_id}) + "\n"
        try:
            async for kind, chunk in run_chat_stream(
                history, model=request.model, conversation_id=conversation_id, think=request.think
            ):
                # "image" chunks (the raw generate_image markdown/URL) are
                # sent to the client like any other chunk, but deliberately
                # excluded from what gets persisted — see run_chat_stream's
                # docstring. A saved copy would re-enter the model's own
                # context on the next message in this conversation and get
                # echoed/half-retyped instead of a fresh image being made.
                if kind == "content":
                    accumulated += chunk
                yield json.dumps({"type": "token", "content": chunk}) + "\n"
        finally:
            # Persist whatever was generated even on client abort/error —
            # a stopped-partway reply is still worth keeping in history.
            if accumulated:
                add_message(conversation_id, "assistant", accumulated)

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.get("/tasks")
def get_tasks(status: str | None = "open"):
    return {"tasks": planner_db.list_tasks(status=status)}


@app.post("/tasks")
def post_task(request: TaskRequest):
    return planner_db.create_task(
        request.title,
        quadrant=request.quadrant,
        due_date=request.due_date,
        notes=request.notes,
    )


@app.patch("/tasks/{task_id}")
def patch_task(task_id: int, request: TaskUpdateRequest):
    planner_db.update_task(
        task_id,
        quadrant=request.quadrant,
        title=request.title,
        notes=request.notes,
        position=request.position,
        due_date=request.due_date,
    )
    return {"status": "ok"}


@app.patch("/tasks/{task_id}/complete")
def patch_task_complete(task_id: int):
    planner_db.complete_task(task_id)
    return {"status": "ok"}


@app.patch("/tasks/{task_id}/reopen")
def patch_task_reopen(task_id: int):
    planner_db.reopen_task(task_id)
    return {"status": "ok"}


@app.delete("/tasks/{task_id}")
def remove_task(task_id: int):
    planner_db.delete_task(task_id)
    return {"status": "ok"}


@app.get("/habits")
def get_habits():
    return {"habits": planner_db.list_habits_with_streaks()}


@app.post("/habits/log")
def post_habit_log(request: HabitLogRequest):
    planner_db.log_habit(request.name)
    return {"streak": planner_db.habit_streak(request.name)}


@app.patch("/habits/{habit_id}/log")
def patch_habit_log(habit_id: int, request: HabitDayRequest):
    planner_db.set_habit_log(habit_id, date.fromisoformat(request.date), request.logged)
    return {"status": "ok"}


@app.delete("/habits/{habit_id}")
def remove_habit(habit_id: int):
    planner_db.delete_habit(habit_id)
    return {"status": "ok"}


@app.get("/todo-lists")
def get_todo_lists():
    return {"lists": planner_db.list_todo_lists()}


@app.post("/todo-lists")
def post_todo_list(request: TodoListRequest):
    return planner_db.create_todo_list(request.name)


@app.patch("/todo-lists/{list_id}")
def patch_todo_list(list_id: int, request: TodoListRequest):
    planner_db.rename_todo_list(list_id, request.name)
    return {"status": "ok"}


@app.delete("/todo-lists/{list_id}")
def remove_todo_list(list_id: int):
    planner_db.delete_todo_list(list_id)
    return {"status": "ok"}


@app.get("/todo-lists/{list_id}/items")
def get_todo_items(list_id: int):
    return {"items": planner_db.list_todo_items(list_id)}


@app.post("/todo-lists/{list_id}/items")
def post_todo_item(list_id: int, request: TodoItemRequest):
    return planner_db.create_todo_item(list_id, request.text)


@app.patch("/todo-items/{item_id}")
def patch_todo_item(item_id: int, request: TodoItemUpdateRequest):
    planner_db.update_todo_item(item_id, text=request.text, done=request.done, due_date=request.due_date)
    return {"status": "ok"}


@app.delete("/todo-items/{item_id}")
def remove_todo_item(item_id: int):
    planner_db.delete_todo_item(item_id)
    return {"status": "ok"}


@app.get("/notes")
def get_notes():
    return {"notes": planner_db.list_notes()}


@app.post("/notes")
def post_note():
    return planner_db.create_note()


@app.patch("/notes/{note_id}")
def patch_note(note_id: int, request: NoteUpdateRequest):
    planner_db.update_note(note_id, request.content)
    return {"status": "ok"}


@app.delete("/notes/{note_id}")
def remove_note(note_id: int):
    planner_db.delete_note(note_id)
    return {"status": "ok"}


@app.get("/sketches")
def get_sketches():
    return {"sketches": planner_db.list_sketches()}


@app.post("/sketches")
def post_sketch(request: SketchCreateRequest):
    return planner_db.create_sketch(request.width, request.height)


@app.patch("/sketches/{sketch_id}")
def patch_sketch(sketch_id: int, request: SketchUpdateRequest):
    planner_db.update_sketch(sketch_id, strokes=request.strokes, title=request.title)
    return {"status": "ok"}


@app.delete("/sketches/{sketch_id}")
def remove_sketch(sketch_id: int):
    planner_db.delete_sketch(sketch_id)
    return {"status": "ok"}


# Mounted last so it doesn't shadow the API routes above.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
