"""Voice-memo transcription (Phase 3 of the chat-attachments plan).

Ollama's own native /api/chat (what app/chat.py's streaming pipeline uses
for the actual conversation) silently ignores an audio field — confirmed
live, it just answers as if no audio were attached at all. Real audio
input only works through Ollama's OpenAI-compatible /v1/chat/completions
endpoint, as a content-array `input_audio` block, and only in "wav" or
"mp3" format — confirmed live that "webm" (what browsers actually record)
is rejected outright with "Failed to load image or audio file".

Rather than reworking the whole streaming chat pipeline onto that
different endpoint just for audio, this module does one non-streaming
call at upload time — ffmpeg transcodes whatever the browser recorded to
wav, that gets sent once to get a transcript, and the transcript is then
treated exactly like a document attachment's extracted_text (see
app/documents.py and the /chat handler's splice logic): injected into
context on the turn it's attached, not replayed on every later turn.
"""

import base64
import logging
import os
import subprocess
import tempfile

import httpx

from app.config import AUDIO_MODEL, OLLAMA_HOST

logger = logging.getLogger("hermes")

TRANSCRIBE_PROMPT = "Transcribe this audio clip exactly, word for word. Output only the transcription, nothing else."


def transcribe(local_path: str) -> str | None:
    """Best-effort, same contract as documents.extract_text — returns
    None (not an exception) on anything that fails, so one bad recording
    doesn't fail the whole upload."""
    with tempfile.NamedTemporaryFile(suffix=".wav") as wav_file:
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", local_path, "-ar", "16000", "-ac", "1", wav_file.name],
                check=True,
                capture_output=True,
                timeout=60,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            logger.exception("ffmpeg transcode failed for %s", local_path)
            return None

        try:
            audio_b64 = base64.b64encode(wav_file.read()).decode("ascii")
        except OSError:
            return None

    try:
        response = httpx.post(
            f"{OLLAMA_HOST}/v1/chat/completions",
            json={
                "model": AUDIO_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": TRANSCRIBE_PROMPT},
                            {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
                        ],
                    }
                ],
            },
            timeout=120.0,  # a real voice memo is much slower to transcribe than a normal tool call
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
        return text.strip() or None
    except Exception:
        logger.exception("Audio transcription failed for %s", local_path)
        return None
