import json
import logging
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
    planner_db.update_task(task_id, quadrant=request.quadrant, title=request.title, notes=request.notes)
    return {"status": "ok"}


@app.patch("/tasks/{task_id}/complete")
def patch_task_complete(task_id: int):
    planner_db.complete_task(task_id)
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


# Mounted last so it doesn't shadow the API routes above.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
