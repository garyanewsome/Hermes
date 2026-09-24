import json
import logging

import httpx

from app.config import CHAT_MODEL, CODEBASE_SEARCHER_URL, IRIS_URL, OLLAMA_HOST, SYSTEM_PROMPT
from app.tools import TOOL_HANDLERS, TOOLS

MAX_TOOL_ITERATIONS = 5

logger = logging.getLogger("hermes")


async def _unload_ollama_model(model: str) -> None:
    """Force Ollama to free VRAM immediately instead of waiting out its own
    idle timeout. generate_image fires in the same turn that just used this
    same model to decide to call it, so there's no idle gap for Ollama's
    own unload to have kicked in — Iris then contends for VRAM against a
    still-resident chat model and OOMs trying to load its own pipeline
    (same class of problem already solved for Selene/images-after-dark).
    Best-effort: if this fails, still let the generate_image attempt
    proceed rather than blocking it on a diagnostic step."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{OLLAMA_HOST}/api/generate", json={"model": model, "keep_alive": 0})
            response.raise_for_status()
    except Exception:
        logger.exception("Failed to unload Ollama model %s before generate_image", model)


async def _unload_iris() -> None:
    """The other half of the handoff: free Iris's SDXL pipeline right after
    a successful generate, before the very next step in this same turn
    (Ollama reloading the chat model for the follow-up reply) needs the GPU
    back. Without this, Iris's passive 5-minute idle-unload leaves the
    pipeline resident long enough to contend with that reload. Best-effort,
    same reasoning as _unload_ollama_model."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{IRIS_URL}/unload")
            response.raise_for_status()
    except Exception:
        logger.exception("Failed to unload Iris pipeline after generate_image")


async def _unload_codebase_searcher() -> None:
    """Same handoff as _unload_iris, for CodebaseSearcher's embedding model
    — it moved to bare-metal/GPU after a CPU-only run took 9+ minutes on a
    real repo. Frees the embedding model right after research_repo returns,
    before Ollama reloads the chat model for the follow-up reply."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{CODEBASE_SEARCHER_URL}/unload")
            response.raise_for_status()
    except Exception:
        logger.exception("Failed to unload CodebaseSearcher model after research_repo")


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
    """Async generator yielding (kind, text) pairs as they arrive. Tool-call
    turns produce no visible output themselves (matches Ollama's own
    behavior — tool_calls come with empty content) — the loop just executes
    them and continues to the next streamed turn.

    kind is "content" for anything that should also be persisted into
    conversation history (normal model text, error notices), or "image" for
    the raw generate_image markdown — display it now, but never persist it:
    a saved copy would re-enter the model's own context on the next message
    in this conversation, and a model handed its own exact prior image URL
    doesn't reliably treat "make another one" as a request to actually call
    the tool again — it can just reference or half-retype the old one
    instead (confirmed live: asking again in the same chat produced garbled
    text plus the literal previous image, not a new generation).

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

        try:
            async for event_type, data in _stream_ollama(messages, model, think):
                if event_type == "content":
                    accumulated_content += data
                    yield ("content", data)
                elif event_type == "tool_calls":
                    tool_calls = data
        except Exception as exc:
            # A broken connection to Ollama (GPU OOM on reload, timeout,
            # restart, ...) must never kill the HTTP stream outright — the
            # client sees that as an opaque "Error in input stream" with no
            # way to tell what happened. Surface it in-chat and end the
            # turn cleanly instead. Whatever content already streamed this
            # turn is unaffected — it was already yielded above.
            logger.exception("Ollama stream failed")
            yield ("content", f"\n\n*Lost connection to the model: {exc}*")
            return

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
                    await _unload_ollama_model(model)
                    try:
                        result = handler(**arguments, conversation_id=conversation_id)
                    finally:
                        # finally, not inline after the call: a raise from
                        # the handler (Iris down, SDXL OOM, ...) must still
                        # free whatever Iris did manage to allocate, or the
                        # next generate_image starts from an already-full
                        # GPU instead of a clean one.
                        await _unload_iris()
                elif name == "research_repo":
                    await _unload_ollama_model(model)
                    try:
                        result = handler(**arguments)
                    finally:
                        # Same reasoning as generate_image above — confirmed
                        # needed for real: a failed embed left CodebaseSearcher
                        # holding ~9GB of stale CUDA allocator cache because
                        # this unload never ran on the exception path.
                        await _unload_codebase_searcher()
                elif name in ("write_vault_note", "read_attachment"):
                    # No GPU handoff needed for either — just needs
                    # conversation_id: write_vault_note to pull the last
                    # assistant message when content is omitted, read_attachment
                    # to scope its lookup to this conversation's own uploads.
                    result = handler(**arguments, conversation_id=conversation_id)
                else:
                    result = handler(**arguments)
            except Exception as exc:
                # A tool failure (Athenaeum/Iris down, GPU OOM, timeout, ...)
                # must never crash the stream — that drops the connection
                # mid-response with no visible reason. Surface it in-chat
                # instead and let the model continue from there.
                if name == "generate_image":
                    yield ("content", f"\n\n*Image generation failed: {exc}*")
                messages.append({"role": "tool", "content": f"Tool '{name}' failed: {exc}"})
                continue

            if name == "generate_image":
                # Never let the model retype the image URL itself — models
                # reliably corrupt long exact strings when regenerating them
                # token-by-token (verified: got "192.168.1.1.157" back from
                # a real run, an extra "1." inserted mid-string). Emit the
                # guaranteed-correct markdown directly as a display-only
                # chunk — never persisted into history, see this function's
                # own docstring for why (the same corruption risk, just on
                # a later turn instead of this one).
                yield ("image", f"\n\n{result}")
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

    yield ("content", "\n\nI wasn't able to finish that — too many tool calls in a row.")
