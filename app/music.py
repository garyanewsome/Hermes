"""Chord and melody analysis for music/riff audio attachments — distinct
from app/audio.py's speech transcription (a different kind of "listening":
harmonic/pitch analysis, not language). Runs entirely on CPU inside this
container, not on the shared homelab GPU — essentia and basic-pitch are
lightweight classical-DSP/small-CNN tools, not LLM-scale, so no GPU
handoff dance is needed the way generate_image/research_repo need one.
"""

import logging
import tempfile

from app.audio import transcode_to_wav

logger = logging.getLogger("hermes")

CHORD_SAMPLE_RATE = 44100


def detect_chords(local_path: str) -> str | None:
    """Best-effort, same contract as documents.extract_text — returns
    None on anything that fails or yields nothing usable."""
    import essentia.standard as es

    with tempfile.NamedTemporaryFile(suffix=".wav") as wav_file:
        if not transcode_to_wav(local_path, wav_file.name, sample_rate=CHORD_SAMPLE_RATE):
            return None
        try:
            audio = es.MonoLoader(filename=wav_file.name, sampleRate=CHORD_SAMPLE_RATE)()
        except Exception:
            logger.exception("Failed to load audio for chord detection: %s", local_path)
            return None

    if len(audio) < CHORD_SAMPLE_RATE:  # under ~1s, not enough to analyze
        return None

    try:
        hop_size = 2048
        frame_size = 4096
        windowing = es.Windowing(type="blackmanharris62")
        spectrum = es.Spectrum()
        spectral_peaks = es.SpectralPeaks(sampleRate=CHORD_SAMPLE_RATE)
        hpcp = es.HPCP()
        chords_detection = es.ChordsDetection(sampleRate=CHORD_SAMPLE_RATE, hopSize=hop_size)

        pcp_frames = []
        for frame in es.FrameGenerator(audio, frameSize=frame_size, hopSize=hop_size, startFromZero=True):
            spectrum_frame = spectrum(windowing(frame))
            frequencies, magnitudes = spectral_peaks(spectrum_frame)
            pcp_frames.append(hpcp(frequencies, magnitudes))

        if not pcp_frames:
            return None

        chords, strengths = chords_detection(pcp_frames)
    except Exception:
        logger.exception("Chord detection failed for %s", local_path)
        return None

    return _format_chord_progression(chords, hop_size, CHORD_SAMPLE_RATE)


def _format_chord_progression(chords: list[str], hop_size: int, sample_rate: int) -> str | None:
    # Collapse consecutive repeats into (chord, start_time, duration)
    # segments — the model shouldn't see 200 frame-by-frame "C C C C G G
    # G..." entries, it should see the actual progression with rough
    # timing, similar to how research_repo trims raw hits to something a
    # model can actually summarize from.
    segments = []
    for i, chord in enumerate(chords):
        t = i * hop_size / sample_rate
        if segments and segments[-1][0] == chord:
            segments[-1][2] = t  # extend the running segment's end time
        else:
            segments.append([chord, t, t])

    segments = [s for s in segments if s[0] != "N" and (s[2] - s[1]) >= 0.3]
    if not segments:
        return None

    lines = [f"{chord} ({start:.1f}s–{end:.1f}s)" for chord, start, end in segments]
    progression = " → ".join(chord for chord, _, _ in segments)
    return f"Chord progression: {progression}\n\nWith rough timing:\n" + "\n".join(lines)


def transcribe_melody(local_path: str) -> str | None:
    """Best-effort — returns None on anything that fails or yields no
    notes. Uses Spotify's basic-pitch (a small CNN, not an LLM) for
    polyphonic-aware audio-to-note transcription."""
    from basic_pitch.inference import predict

    with tempfile.NamedTemporaryFile(suffix=".wav") as wav_file:
        if not transcode_to_wav(local_path, wav_file.name, sample_rate=22050):
            return None
        try:
            _, _, note_events = predict(wav_file.name)
        except Exception:
            logger.exception("Melody transcription failed for %s", local_path)
            return None

    if not note_events:
        return None

    return _format_note_events(note_events)


_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _midi_to_note_name(midi_pitch: int) -> str:
    octave = midi_pitch // 12 - 1
    return f"{_NOTE_NAMES[midi_pitch % 12]}{octave}"


def _format_note_events(note_events: list) -> str | None:
    # note_events entries: (start_time_s, end_time_s, pitch_midi, amplitude, [bends])
    # Cap the count, same reasoning as documents.cap_text — a long clip
    # shouldn't dump hundreds of note events into the model's context.
    notes = sorted(note_events, key=lambda n: n[0])[:80]
    if not notes:
        return None
    lines = [f"{_midi_to_note_name(round(pitch))} ({start:.2f}s–{end:.2f}s)" for start, end, pitch, *_ in notes]
    sequence = " ".join(_midi_to_note_name(round(pitch)) for start, end, pitch, *_ in notes)
    suffix = "" if len(note_events) <= 80 else f"\n\n[... {len(note_events) - 80} more notes not shown ...]"
    return f"Note sequence: {sequence}\n\nWith timing:\n" + "\n".join(lines) + suffix
