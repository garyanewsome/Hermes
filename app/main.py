import base64
import json
import logging
import os
import uuid
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import audio, auth, documents
from app.chat import list_models, run_chat_stream
from app.config import UPLOADS_DIR
from app.db import (
    add_attachment,
    add_message,
    create_conversation,
    delete_conversation,
    delete_message,
    delete_messages_from,
    get_message,
    get_messages,
    init_db,
    list_conversations,
    maybe_set_title,
    rename_conversation,
    update_message_content,
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


class AttachmentRef(BaseModel):
    kind: str = "image"
    path: str
    mime_type: str | None = None
    filename: str | None = None
    extracted_text: str | None = None


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    model: str | None = None
    think: bool = False
    attachments: list[AttachmentRef] | None = None


class RenameRequest(BaseModel):
    title: str


class ResendRequest(BaseModel):
    # Present + non-empty to edit a user message before resending;
    # omitted/None to resend as-is (a plain "regenerate" when targeting
    # the last assistant message, or "retry this exact message" for a user one).
    content: str | None = None
    model: str | None = None
    think: bool = False


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


class TodoListUpdateRequest(BaseModel):
    name: str | None = None
    position: float | None = None


class TodoItemRequest(BaseModel):
    text: str
    recurrence_days: int | None = None
    recurrence_weekdays: str | None = None


class TodoItemUpdateRequest(BaseModel):
    text: str | None = None
    done: bool | None = None
    due_date: str | None = None
    position: float | None = None
    recurrence_days: int | None = None
    recurrence_weekdays: str | None = None


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


def _encode_image_attachments(attachments: list[dict] | None) -> list[str]:
    # Ollama's /api/chat has no server-side image cache — a vision model
    # only "sees" whatever's in the images field of *this* request, so a
    # photo from three turns ago has to be re-read and re-encoded on every
    # subsequent call too, not just the turn it was originally attached
    # to. Missing/unreadable files are skipped rather than failing the
    # whole chat turn over one bad attachment.
    images = []
    for a in attachments or []:
        if a.get("kind") != "image":
            continue
        try:
            with open(os.path.join(UPLOADS_DIR, a["path"]), "rb") as f:
                images.append(base64.b64encode(f.read()).decode("ascii"))
        except OSError:
            logger.exception("Failed to read attachment %s for a chat turn", a.get("path"))
    return images


def _stream_and_persist(conversation_id: str, history: list[dict], model: str | None, think: bool):
    # Shared by /chat and /resend — both send an initial history to Ollama,
    # stream the reply back as ndjson, and persist it the same way on
    # completion or client abort. run_chat_stream gets id-free {role,
    # content} pairs — the message id is our own bookkeeping, not
    # something to hand to Ollama's API.
    clean_history = []
    for m in history:
        entry = {"role": m["role"], "content": m["content"]}
        images = _encode_image_attachments(m.get("attachments"))
        if images:
            entry["images"] = images
        clean_history.append(entry)

    async def event_stream():
        accumulated = ""
        yield json.dumps({"type": "conversation_id", "conversation_id": conversation_id}) + "\n"
        try:
            async for kind, chunk in run_chat_stream(
                clean_history, model=model, conversation_id=conversation_id, think=think
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


@app.post("/chat")
async def chat(request: ChatRequest):
    conversation_id = request.conversation_id
    is_new = conversation_id is None
    if is_new:
        conversation_id = create_conversation()

    history = get_messages(conversation_id)
    # Same {kind, path, ...} shape get_attachments() returns, so
    # _stream_and_persist's clean_history builder treats this turn's
    # not-yet-persisted attachments identically to older, already-stored
    # ones — no separate code path needed for "the newest message."
    pending_attachments = [a.model_dump() for a in request.attachments or []]

    # A document's (or voice memo's) text is spliced into the content sent
    # to Ollama for *this* turn only — not persisted (the DB keeps
    # request.message exactly as typed) and not replayed on later turns
    # the way image attachments are (see documents.py / add_attachment's
    # docstring for why: a large document's full text getting re-sent on
    # every later message in the conversation would be expensive and
    # mostly wasted). Audio's transcript reuses the exact same splice
    # mechanism — by the time it reaches here it's just text, same as a
    # PDF's extracted text.
    ollama_content = request.message
    text_blocks = []
    for a in request.attachments or []:
        if a.kind not in ("document", "audio") or not a.extracted_text:
            continue
        label = "Transcript of voice memo" if a.kind == "audio" else "Document"
        text_blocks.append(f"--- {label}: {a.filename or a.path} ---\n{documents.cap_text(a.extracted_text)}\n--- end ---")
    if text_blocks:
        ollama_content = f"{request.message}\n\n" + "\n\n".join(text_blocks)

    history.append({"role": "user", "content": ollama_content, "attachments": pending_attachments})

    message_id = add_message(conversation_id, "user", request.message)
    for a in request.attachments or []:
        add_attachment(message_id, a.kind, a.path, a.mime_type, a.filename, a.extracted_text)
    if is_new:
        maybe_set_title(conversation_id, request.message)

    return _stream_and_persist(conversation_id, history, request.model, request.think)


@app.delete("/conversations/{conversation_id}/messages/{message_id}")
def remove_message(conversation_id: str, message_id: int):
    message = get_message(message_id)
    if message is None or message["conversation_id"] != conversation_id:
        raise HTTPException(status_code=404, detail="Message not found")
    delete_message(message_id)
    return {"status": "ok"}


@app.post("/conversations/{conversation_id}/messages/{message_id}/resend")
def resend(conversation_id: str, message_id: int, request: ResendRequest):
    message = get_message(message_id)
    if message is None or message["conversation_id"] != conversation_id:
        raise HTTPException(status_code=404, detail="Message not found")

    if message["role"] == "user":
        # Edit-and-resend (content given) or plain retry of this exact
        # message (content omitted) — either way, the old reply (and
        # anything after it) is stale and gets dropped.
        if request.content is not None:
            content = request.content.strip()
            if not content:
                raise HTTPException(status_code=400, detail="content can't be empty")
            update_message_content(message_id, content)
        delete_messages_from(conversation_id, message_id + 1)
    elif message["role"] == "assistant":
        # Regenerate: content doesn't apply to an assistant message here —
        # editing the model's own words isn't what this endpoint is for.
        if request.content is not None:
            raise HTTPException(status_code=400, detail="content only applies when resending a user message")
        delete_messages_from(conversation_id, message_id)
    else:
        raise HTTPException(status_code=400, detail=f"Can't resend a '{message['role']}' message")

    history = get_messages(conversation_id)
    if not history:
        raise HTTPException(status_code=400, detail="Nothing left to resend after truncation")

    return _stream_and_persist(conversation_id, history, request.model, request.think)


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
def patch_todo_list(list_id: int, request: TodoListUpdateRequest):
    planner_db.update_todo_list(list_id, name=request.name, position=request.position)
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
    return planner_db.create_todo_item(
        list_id, request.text, recurrence_days=request.recurrence_days, recurrence_weekdays=request.recurrence_weekdays
    )


@app.patch("/todo-items/{item_id}")
def patch_todo_item(item_id: int, request: TodoItemUpdateRequest):
    # Returns the actual resulting item, not just {"status": "ok"} — a
    # recurring item's "mark done" can turn into "reset to open, due_date
    # advanced" server-side, and the client needs the real outcome to
    # reflect that instead of assuming done=True stuck.
    return planner_db.update_todo_item(
        item_id,
        text=request.text,
        done=request.done,
        due_date=request.due_date,
        position=request.position,
        recurrence_days=request.recurrence_days,
        recurrence_weekdays=request.recurrence_weekdays,
    )


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


class UploadResponse(BaseModel):
    kind: str
    path: str
    mime_type: str
    filename: str
    extracted_text: str | None = None


# Classified by extension, not the browser's Content-Type header — some
# OSes send generic/inconsistent types for .md (application/octet-stream
# is common), so extension is the more reliable signal here.
_UPLOAD_KINDS = {
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".webp": ("image", "image/webp"),
    ".gif": ("image", "image/gif"),
    ".pdf": ("document", "application/pdf"),
    ".txt": ("document", "text/plain"),
    ".md": ("document", "text/plain"),
    # Covers both a live recording (browser MediaRecorder: webm/opus in
    # Chrome/Firefox, mp4/aac in Safari) and a pre-recorded file the user
    # picks directly. The mime_type here is just what gets stored/served
    # back for playback — transcription (app/audio.py) transcodes to wav
    # itself regardless of the original container.
    ".webm": ("audio", "audio/webm"),
    ".m4a": ("audio", "audio/mp4"),
    ".mp4": ("audio", "audio/mp4"),
    ".wav": ("audio", "audio/wav"),
    ".mp3": ("audio", "audio/mpeg"),
    ".ogg": ("audio", "audio/ogg"),
}


@app.post("/uploads")
async def upload(file: UploadFile) -> UploadResponse:
    # Saves the file and hands back a reference only — no DB row yet.
    # /chat creates the actual attachment row once it knows the real
    # message_id this ends up attached to; an attachment picked but never
    # sent just leaves an orphaned file on disk, never an orphaned row.
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _UPLOAD_KINDS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or 'unknown'}")
    kind, mime_type = _UPLOAD_KINDS[ext]

    filename = f"{uuid.uuid4()}{ext}"
    os.makedirs(UPLOADS_DIR, exist_ok=True)
    local_path = os.path.join(UPLOADS_DIR, filename)
    with open(local_path, "wb") as f:
        f.write(await file.read())

    extracted_text = None
    if kind == "document":
        extracted_text = documents.extract_text(local_path, mime_type)
    elif kind == "audio":
        extracted_text = audio.transcribe(local_path)

    return UploadResponse(
        kind=kind, path=filename, mime_type=mime_type, filename=file.filename or filename, extracted_text=extracted_text
    )


# Kept behind the auth middleware (unlike Iris's public /images — see
# _PUBLIC_PATHS/_PUBLIC_PREFIXES above) — the browser already sends the
# session cookie on same-origin <img> requests, so this doesn't break
# rendering. Mounted before the catch-all static mount below so it isn't
# shadowed by it.
os.makedirs(UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

# Mounted last so it doesn't shadow the API routes above.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
