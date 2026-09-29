"""Guitar tone feature extraction for suggest_pod_go_tone — a different
kind of "listening" from app/music.py's chord/pitch analysis: not what
notes are played, but what the signal chain sounds like (bright/dark,
clean/distorted, compressed, modulated, delayed, reverberant).

Plain numpy/scipy math on top of essentia's MonoLoader (already a proven
dependency from the chord/melody work), not more essentia algorithms —
these are well-established DSP proxies (crest factor for distortion,
envelope-spectrum peaks for modulation rate, autocorrelation for echo,
decay-after-onset for reverb tail), not something essentia has a
purpose-built descriptor for, and implementing them directly keeps the
thresholds/reasoning inspectable instead of hidden inside a library call.

Every number here is a rough, heuristic proxy, not a measurement a real
audio engineer would call precise — the whole feature is explicitly a
best-guess starting point (see suggest_pod_go_tone's docstring), and nothing
downstream should treat these labels as exact.
"""

import logging
import tempfile

import httpx
import numpy as np

from app.audio import transcode_to_wav
from app.config import CHAT_MODEL, OLLAMA_HOST
from app.pod_go_reference import AMPS_CLEAN, AMPS_CRUNCH, AMPS_HIGH_GAIN, CABS_COMMON, EFFECTS_SHORT

logger = logging.getLogger("hermes")

SAMPLE_RATE = 44100


def _frame_rms(signal: np.ndarray, frame_size: int, hop: int) -> np.ndarray:
    n_frames = max(1, (len(signal) - frame_size) // hop + 1)
    return np.array(
        [np.sqrt(np.mean(signal[i * hop : i * hop + frame_size] ** 2) + 1e-12) for i in range(n_frames)]
    )


def _brightness(signal: np.ndarray, sr: int) -> tuple[float, str]:
    frame_size, hop = 4096, 2048
    freqs = np.fft.rfftfreq(frame_size, d=1 / sr)
    centroids, weights = [], []
    for i in range(0, len(signal) - frame_size, hop):
        frame = signal[i : i + frame_size]
        mag = np.abs(np.fft.rfft(frame * np.hanning(frame_size)))
        energy = mag.sum()
        if energy < 1e-6:
            continue
        centroids.append((freqs * mag).sum() / energy)
        weights.append(energy)
    if not centroids:
        return 0.0, "unknown"
    centroid_hz = float(np.average(centroids, weights=weights))
    # Thresholds are a rough guitar-tone heuristic, not a studied standard.
    if centroid_hz < 700:
        label = "dark / bassy (bass-heavy amp, or the tone/presence rolled off)"
    elif centroid_hz < 1600:
        label = "warm / balanced"
    elif centroid_hz < 3200:
        label = "bright"
    else:
        label = "very bright / harsh (lots of high-end energy, or digital fizz)"
    return centroid_hz, label


def _gain_character(signal: np.ndarray) -> tuple[float, str]:
    # What fraction of samples sit above 85% of the signal's own peak
    # amplitude. A sine-like clean tone only grazes its peak briefly each
    # cycle; clipping/saturation flattens the waveform's top, so a
    # distorted signal spends much more of its time pinned up near peak.
    # Tried plain peak/RMS crest factor first — confirmed live it doesn't
    # work: a sustained clean tone is inherently low-crest (~3dB for a pure
    # sine) regardless of distortion, so it can't tell "held clean note"
    # from "fuzzed out." This time-near-peak measure cleanly separated a
    # clean synthesized tone (0.19) from a heavily clipped one (0.84).
    peak = np.max(np.abs(signal))
    if peak < 1e-9:
        return 0.0, "unknown (too quiet to measure)"
    frac_near_peak = float(np.mean(np.abs(signal) > 0.85 * peak))
    if frac_near_peak < 0.15:
        label = "clean to light breakup — low gain"
    elif frac_near_peak < 0.35:
        label = "moderate gain / crunch"
    elif frac_near_peak < 0.6:
        label = "high gain / distortion"
    else:
        label = "very high gain, fuzz, or heavily clipped/saturated"
    return frac_near_peak, label


def _dynamics(signal: np.ndarray, sr: int) -> str:
    rms_env = _frame_rms(signal, frame_size=int(sr * 0.1), hop=int(sr * 0.05))
    active = rms_env[rms_env > rms_env.max() * 0.05]
    if len(active) < 4:
        return "unknown"
    ratio_db = float(20 * np.log10(active.max() / (active.min() + 1e-9)))
    # A small range between the loudest and quietest active moments is what
    # a compressor/limiter (or a heavily-gained amp's own compression) does.
    if ratio_db < 8:
        return "heavily compressed/limited (very even level throughout)"
    if ratio_db < 16:
        return "moderately compressed"
    return "dynamic / uncompressed (natural level variation)"


def _modulation(signal: np.ndarray, sr: int) -> str | None:
    hop = int(sr * 0.01)  # 10ms envelope frames — fine enough to resolve up to ~8Hz modulation
    env = _frame_rms(signal, frame_size=hop * 2, hop=hop)
    if len(env) < 32:
        return None
    env = env - env.mean()
    env_sr = sr / hop
    spectrum = np.abs(np.fft.rfft(env * np.hanning(len(env))))
    freqs = np.fft.rfftfreq(len(env), d=1 / env_sr)
    # Chorus/flange/tremolo/vibrato LFOs live in ~0.5-8Hz; below that is just
    # the note's own volume envelope (attack/decay), not modulation.
    band = (freqs >= 0.5) & (freqs <= 8.0)
    if not band.any():
        return None
    band_spectrum = spectrum[band]
    peak_idx = int(np.argmax(band_spectrum))
    peak_freq = freqs[band][peak_idx]
    peak_val = band_spectrum[peak_idx]
    # A real LFO concentrates nearly all its energy in one narrow bin; a
    # plain note attack/decay (or several notes in a row) produces a broad
    # low-frequency hump instead. Comparing the peak to the *rest of the
    # same band's* median (not just energy above 8Hz) catches that — a
    # broad hump's own median is close to its peak, a narrow spike's isn't.
    # Confirmed live: a genuine tremolo test signal scored ~1500x on this
    # ratio; three plain notes in a row (no modulation at all) scored ~5x.
    band_median = np.median(band_spectrum) + 1e-9
    out_of_band_floor = np.median(spectrum[freqs > 8.0]) + 1e-9
    if peak_val < band_median * 15 or peak_val < out_of_band_floor * 15:
        return None
    # Guard against a spurious single-bin blip on a short clip — a real LFO
    # should complete at least a few cycles within the analyzed audio.
    duration_s = len(signal) / sr
    if peak_freq * duration_s < 3:
        return None
    return f"periodic modulation detected around {peak_freq:.1f} Hz (chorus/flanger/tremolo/vibrato territory)"


def _echo(signal: np.ndarray, sr: int) -> str | None:
    # Autocorrelation on the amplitude envelope, not the raw waveform — the
    # raw signal's own pitch periodicity (a low E string repeats every
    # ~12ms) would otherwise swamp anything a real delay pedal produces.
    hop = int(sr * 0.005)
    env = _frame_rms(signal, frame_size=hop * 2, hop=hop)
    if len(env) < 40:
        return None
    env = env - env.mean()
    if np.allclose(env, 0):
        return None
    corr = np.correlate(env, env, mode="full")[len(env) - 1 :]
    corr = corr / (corr[0] + 1e-9)
    # Autocorrelation is highest right next to zero-lag for ANY signal (a
    # single note's own envelope has a "main lobe" as wide as the note
    # itself) — confirmed live: with a single ~300ms pluck, that lobe alone
    # produces a >0.7 correlation clear out to 60ms with no real echo
    # present, so just excluding a fixed 60ms and taking the global max
    # (the original approach here) picked up the main lobe's tail, not the
    # actual echo three notes away. Guarding out to 150ms and requiring a
    # genuine LOCAL peak (a bump higher than both neighbors, not just "the
    # least-decayed point yet") separates a real repeat from that lobe.
    min_lag = max(int(0.15 / (hop / sr)), 2)
    if min_lag >= len(corr) - 2:
        return None
    search = corr[min_lag:]
    local_peaks = [i for i in range(1, len(search) - 1) if search[i] > search[i - 1] and search[i] > search[i + 1]]
    if not local_peaks:
        return None
    best = max(local_peaks, key=lambda i: search[i])
    if search[best] < 0.35:
        return None
    delay_ms = (min_lag + best) * hop / sr * 1000
    # Hedged deliberately: this only measures amplitude-envelope
    # periodicity, which a delay pedal produces but so does, say, several
    # evenly-timed notes played in a row — confirmed live, a plain 3-note
    # phrase with no effect at all can trigger this. Can't tell the two
    # apart from envelope shape alone without much heavier analysis.
    return (
        f"a repeating pattern around {delay_ms:.0f}ms found in the signal's volume envelope — likely a delay/echo, "
        f"but could also just be an evenly-timed rhythm in the playing itself"
    )


def _reverb_tail(signal: np.ndarray, sr: int) -> str | None:
    # Measured from the very end of the clip backward, not from "the last
    # loud moment forward" — a multi-note clip's last note re-triggers the
    # envelope partway through the earlier approach's measurement window,
    # making it measure that note's own (short) natural decay instead of
    # whatever's actually still ringing at the tail of the recording.
    # Simpler and more robust: is there still meaningful, gently-decaying
    # energy in the closing stretch of the clip, well below the peak but
    # well above the noise floor? That's what a reverb tail looks like;
    # a dry signal just goes quiet.
    frame, hop = int(sr * 0.02), int(sr * 0.01)
    env = _frame_rms(signal, frame_size=frame, hop=hop)
    if len(env) < 30:
        return None
    env_db = 20 * np.log10(env / (env.max() + 1e-9) + 1e-9)
    tail_window = max(10, len(env_db) // 6)  # last ~1/6th of the clip
    tail = env_db[-tail_window:]
    # A fixed absolute floor, not a percentile of this same signal — a
    # percentile is circular here since the tail we're inspecting often *is*
    # the quietest stretch of the clip, so it ends up compared to itself.
    # -60dB relative to peak is comfortably above where genuine digital
    # silence sits (confirmed live: a silent stretch read at -113dB) and
    # comfortably below a real trailing decay (confirmed live: a reverb-like
    # tail held around -44 to -51dB).
    above_floor = tail.max() > -60
    below_peak = tail.max() < -8
    not_freshly_attacked = tail[-1] < tail[0] + 3  # not still climbing at the very end
    if not (above_floor and below_peak and not_freshly_attacked):
        return None
    tail_ms = tail_window * hop / sr * 1000
    label = "a long, spacious decay tail" if tail_ms > 500 else "a short-to-medium decay tail"
    return f"{label} (~{tail_ms:.0f}ms of trailing decay at the end of the clip) — some reverb/room ambience present"


def analyze_tone(local_path: str) -> str | None:
    """Best-effort, same contract as documents.extract_text/music.py's
    analysis functions — returns None on anything that fails."""
    with tempfile.NamedTemporaryFile(suffix=".wav") as wav_file:
        if not transcode_to_wav(local_path, wav_file.name, sample_rate=SAMPLE_RATE):
            return None
        try:
            import essentia.standard as es

            signal = es.MonoLoader(filename=wav_file.name, sampleRate=SAMPLE_RATE)()
        except Exception:
            logger.exception("Failed to load audio for tone analysis: %s", local_path)
            return None

    if len(signal) < SAMPLE_RATE // 2:
        return None

    signal = np.asarray(signal, dtype=np.float64)
    _, brightness_label = _brightness(signal, SAMPLE_RATE)
    gain_val, gain_label = _gain_character(signal)
    dynamics_label = _dynamics(signal, SAMPLE_RATE)
    modulation = _modulation(signal, SAMPLE_RATE)
    echo = _echo(signal, SAMPLE_RATE)
    reverb = _reverb_tail(signal, SAMPLE_RATE)

    # A short, gain-matched amp list, not the full ~100-model catalog —
    # confirmed live that handing gemma4:12b the complete lists on top of
    # this app's full tool schema broke it (see pod_go_reference.py's
    # comment on AMPS_CLEAN for what that actually looked like: at one
    # size it gave up and greeted the user instead of answering, at
    # another it hallucinated an unrelated tool call to a fake GitHub
    # repo). Boundary gain values include the adjacent tier too, since the
    # thresholds are approximate.
    if gain_val < 0.15:
        amps = AMPS_CLEAN
    elif gain_val < 0.25:
        amps = AMPS_CLEAN + "\n" + AMPS_CRUNCH
    elif gain_val < 0.6:
        amps = AMPS_CRUNCH
    else:
        amps = AMPS_HIGH_GAIN

    lines = [
        "Measured acoustic characteristics (rough heuristic proxies, not exact measurements):",
        f"- Tonal brightness: {brightness_label}",
        f"- Gain/distortion character: {gain_label}",
        f"- Dynamics/compression: {dynamics_label}",
        f"- Modulation: {modulation or 'no clear periodic modulation detected'}",
        f"- Delay/echo: {echo or 'no repeating echo detected'}",
        f"- Reverb/decay: {reverb or 'no notable decay tail detected — sounds dry'}",
        "",
        "Real POD Go amp models to choose from (pick the closest-sounding real amp, never invent a name; "
        "this is a short representative list, not the full catalog):",
        amps,
        "",
        "Real POD Go cab models to choose from:",
        CABS_COMMON,
    ]
    if gain_label != "clean to light breakup — low gain":
        lines += ["", "Real POD Go distortion/drive models to choose from:", EFFECTS_SHORT["distortion"]]
    if modulation:
        lines += ["", "Real POD Go modulation models to choose from:", EFFECTS_SHORT["modulation"]]
    if echo:
        lines += ["", "Real POD Go delay models to choose from:", EFFECTS_SHORT["delay"]]
    if reverb:
        lines += ["", "Real POD Go reverb models to choose from:", EFFECTS_SHORT["reverb"]]
    measurements = "\n".join(lines)

    recommendation = _synthesize_recommendation(measurements)
    return recommendation or measurements


def _synthesize_recommendation(measurements: str) -> str | None:
    """Does the actual "reasoning from measurements to a signal chain" step
    itself, as its own plain call to Ollama with no tools attached, instead
    of handing the raw measurements+reference lists back as the tool result
    for the main chat loop to reason over. Confirmed live this distinction
    matters a lot: with this app's full ~9-tool schema attached (which every
    call in the main chat loop always carries), gemma4:12b reliably lost
    the thread after a tool result of this size — 4 separate runs of the
    exact same conversation either replied with a generic "here's what I
    can help with" greeting, or hallucinated a call to a completely
    unrelated tool (once to a nonexistent GitHub repo, twice to this app's
    own todo-list tools). The identical prompt with only one tool (or zero)
    in scope answered correctly every time. Isolating the actual reasoning
    into its own tools-free call sidesteps that rather than fighting it."""
    prompt = (
        "A user recorded a guitar/bass tone and wants to recreate it on their Line 6 POD Go. "
        "Below are measured acoustic characteristics of their recording and a short list of real "
        "POD Go models to choose from. In 2-3 short sentences, name ONE specific amp, ONE cab, and "
        "any one or two relevant effects from the real names given — no headers, no bullet list, no "
        "restating the measurements back. Never invent a model name that isn't in the lists given.\n\n"
        + measurements
    )
    try:
        response = httpx.post(
            f"{OLLAMA_HOST}/api/chat",
            json={"model": CHAT_MODEL, "messages": [{"role": "user", "content": prompt}], "stream": False},
            timeout=120.0,
        )
        response.raise_for_status()
        text = response.json()["message"]["content"].strip()
        if not text:
            return None
        # Defensive cap, not just a prompt instruction — confirmed live that
        # this app's main chat loop (which always carries its full ~9-tool
        # schema) reliably loses track of the conversation once a tool
        # result gets much past this size, regardless of how well-formed
        # the text is, while a short result (comparable to analyze_chords')
        # stays reliable. A verbose reply here is still better cut down
        # than handed back whole and risking the whole turn.
        return text if len(text) <= 600 else text[:600].rsplit(".", 1)[0] + "."
    except Exception:
        logger.exception("Tone recommendation synthesis failed")
        return None
