import json

import httpx

from app.config import CHAT_MODEL, OLLAMA_HOST, SYSTEM_PROMPT
from app.tools import TOOL_HANDLERS, TOOLS

MAX_TOOL_ITERATIONS = 5


async def _stream_ollama(messages: list[dict], model: str, think: bool):
    """Yields ('content', str) for each text chunk, and ('tool_calls', list)
    once a message carrying tool calls completes. Streaming a closed/
    cancelled consumer (client aborts) closes this httpx stream too, via
    the `async with` — which stops Ollama's own generation, not just our
    read of it.

    `think` controls Ollama's hybrid-reasoning mode (Qwen3 and similar):
    when on, the model runs a hidden chain-of-thought pass that streams
    under `thinking`, not `content` — Hermes never surfaces that field, so
    the request looks silently stuck until it finishes (measured: ~10s for
    a one-sentence reply, far worse under a real tool-decision prompt).
    Ignored harmlessly by models with no thinking mode (verified against
    qwen2.5), so it's safe to pass regardless of which model is active."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_HOST}/api/chat",
            json={"model": model, "messages": messages, "tools": TOOLS, "stream": True, "think": think},
        ) as response:
            response.raise_for_status()
            tool_calls = None
            async for line in response.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                message = chunk.get("message", {})
                if message.get("tool_calls"):
                    tool_calls = message["tool_calls"]
                content = message.get("content")
                if content:
                    yield ("content", content)
                if chunk.get("done"):
                    break
            if tool_calls:
                yield ("tool_calls", tool_calls)


def list_models() -> list[str]:
    """Only models with Ollama's "tools" capability — Hermes requires
    tool-calling to reach Athenaeum, so anything else (embedding models,
    older completion-only models) would silently break mid-conversation
    if selected."""
    response = httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=10.0)
    response.raise_for_status()
    names = [m["name"] for m in response.json().get("models", [])]

    tool_capable = []
    for name in names:
        show_response = httpx.post(f"{OLLAMA_HOST}/api/show", json={"name": name}, timeout=10.0)
        show_response.raise_for_status()
        if "tools" in show_response.json().get("capabilities", []):
            tool_capable.append(name)
    return tool_capable


async def run_chat_stream(
    messages: list[dict],
    model: str | None = None,
    conversation_id: str | None = None,
    think: bool = False,
):
    """Async generator yielding assistant-visible text chunks as they
    arrive. Tool-call turns produce no visible output themselves (matches
    Ollama's own behavior — tool_calls come with empty content) — the
    loop just executes them and continues to the next streamed turn.

    conversation_id isn't a model-controlled tool argument (the model
    doesn't know or manage it) — it's injected here specifically for
    generate_image, so Iris can organize output per-conversation."""
    model = model or CHAT_MODEL

    if not messages or messages[0].get("role") != "system":
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
    else:
        messages = list(messages)

    for _ in range(MAX_TOOL_ITERATIONS):
        accumulated_content = ""
        tool_calls = None

        async for event_type, data in _stream_ollama(messages, model, think):
            if event_type == "content":
                accumulated_content += data
                yield data
            elif event_type == "tool_calls":
                tool_calls = data

        assistant_message = {"role": "assistant", "content": accumulated_content}
        if tool_calls:
            assistant_message["tool_calls"] = tool_calls
        messages.append(assistant_message)

        if not tool_calls:
            return

        for call in tool_calls:
            name = call["function"]["name"]
            arguments = call["function"]["arguments"]
            handler = TOOL_HANDLERS.get(name)

            if not handler:
                messages.append({"role": "tool", "content": f"Unknown tool: {name}"})
                continue

            try:
                if name == "generate_image":
                    result = handler(**arguments, conversation_id=conversation_id)
                else:
                    result = handler(**arguments)
            except Exception as exc:
                # A tool failure (Athenaeum/Iris down, GPU OOM, timeout, ...)
                # must never crash the stream — that drops the connection
                # mid-response with no visible reason. Surface it in-chat
                # instead and let the model continue from there.
                if name == "generate_image":
                    yield f"\n\n*Image generation failed: {exc}*"
                messages.append({"role": "tool", "content": f"Tool '{name}' failed: {exc}"})
                continue

            if name == "generate_image":
                # Never let the model retype the image URL itself — models
                # reliably corrupt long exact strings when regenerating them
                # token-by-token (verified: got "192.168.1.1.157" back from
                # a real run, an extra "1." inserted mid-string). Emit the
                # guaranteed-correct markdown directly as a content chunk,
                # and give the model a URL-free placeholder so it has
                # nothing to accidentally mangle in its own reply.
                yield f"\n\n{result}"
                messages.append(
                    {
                        "role": "tool",
                        "content": (
                            "Image generated and already displayed to the user directly "
                            "above this message. Do not include any image markdown, URL, "
                            "or image data in your reply — you don't have the actual URL "
                            "and inventing one (including fake base64 data) would be "
                            "wrong. Just briefly acknowledge it in plain text."
                        ),
                    }
                )
            else:
                messages.append({"role": "tool", "content": result})

    yield "\n\nI wasn't able to finish that — too many tool calls in a row."
