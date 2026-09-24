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

# The model is asked to say this exact phrase for non-speech audio (singing,
# an instrumental riff, a whole song) rather than guessing at lyrics or
# refusing — lets main.py recognize and drop it instead of splicing a
# misleading "transcript" into context for what's actually a song upload
# meant for analyze_chords/transcribe_melody, not read back as speech.
NO_SPEECH_MARKER = "[no speech detected]"

TRANSCRIBE_PROMPT = (
    "Transcribe any spoken words in this audio clip exactly, word for word. "
    f"If it's music, singing, or otherwise has no clear spoken words, respond with exactly: {NO_SPEECH_MARKER} "
    "Output only the transcription (or that exact marker), nothing else."
)


def transcode_to_wav(local_path: str, wav_path: str, sample_rate: int = 16000) -> bool:
    """Shared by transcribe() here and app/music.py's chord/melody analysis
    — ffmpeg transcodes whatever container the browser/upload used (webm,
    mp4, ...) to a plain mono wav, since that's the one format confirmed to
    actually work for Ollama's audio input, and the safest common format
    for the music-analysis libraries too."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", local_path, "-ar", str(sample_rate), "-ac", "1", wav_path],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        logger.exception("ffmpeg transcode failed for %s", local_path)
        return False


def transcribe(local_path: str) -> str | None:
    """Best-effort, same contract as documents.extract_text — returns
    None (not an exception) on anything that fails, so one bad recording
    doesn't fail the whole upload."""
    with tempfile.NamedTemporaryFile(suffix=".wav") as wav_file:
        if not transcode_to_wav(local_path, wav_file.name):
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
        text = response.json()["choices"][0]["message"]["content"].strip()
        return None if not text or text == NO_SPEECH_MARKER else text
    except Exception:
        logger.exception("Audio transcription failed for %s", local_path)
        return None
