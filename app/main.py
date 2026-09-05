import json

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

app = FastAPI(title="Hermes")
init_db()


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    model: str | None = None


class RenameRequest(BaseModel):
    title: str


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
            async for chunk in run_chat_stream(history, model=request.model, conversation_id=conversation_id):
                accumulated += chunk
                yield json.dumps({"type": "token", "content": chunk}) + "\n"
        finally:
            # Persist whatever was generated even on client abort/error —
            # a stopped-partway reply is still worth keeping in history.
            if accumulated:
                add_message(conversation_id, "assistant", accumulated)

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


# Mounted last so it doesn't shadow the API routes above.
app.mount("/", StaticFiles(directory="static", html=True), name="static")
