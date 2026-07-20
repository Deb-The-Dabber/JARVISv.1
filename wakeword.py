import threading
import time

import numpy as np
import pyaudio

from terminal import RECORD_SAMPLE_RATE

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
CHUNK_SIZE    = 1280   # OWW expects 80ms chunks at 16kHz
RECORD_SAMPLE_RATE = 44100
SAMPLE_RATE = 16000
CHANNELS      = 1

# Wake words to listen for
WAKE_WORDS = ["hey_jarvis", "jarvis"]

# Sensitivity — higher = more sensitive but more false positives
# 0.3 is a good balance
SENSITIVITY = 0.3

# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────
_running   = False
_thread    = None
_callback  = None   # Called when wake word detected
_model     = None
_model_lock = threading.Lock()


def _resolve_sd_input_device():
    """Resolve a valid SoundDevice input index, avoiding default -1 errors."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
    except Exception:
        return None

    try:
        default_in = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else sd.default.device
        if isinstance(default_in, int) and default_in >= 0:
            info = sd.query_devices(default_in)
            if info.get("max_input_channels", 0) > 0:
                return default_in
    except Exception:
        pass

    for i, info in enumerate(devices):
        if info.get("max_input_channels", 0) > 0:
            return i
    return None


def _resolve_pyaudio_input_device(pa):
    """Resolve a valid PyAudio input index instead of hardcoded device ids."""
    try:
        default_idx = pa.get_default_input_device_info().get("index")
        if isinstance(default_idx, int):
            return default_idx
    except Exception:
        pass

    try:
        count = pa.get_device_count()
    except Exception:
        return None

    for i in range(count):
        try:
            info = pa.get_device_info_by_index(i)
            if int(info.get("maxInputChannels", 0)) > 0:
                return i
        except Exception:
            continue
    return None

# ─────────────────────────────────────────────
# LOAD MODEL
# ─────────────────────────────────────────────
def _load_model():
    global _model
    with _model_lock:
        if _model is not None:
            return _model
        print("  Loading OpenWakeWord model...")
        try:
            from openwakeword.model import Model
            # Try to load hey_jarvis model first
            # OWW will download it automatically on first run
            _model = Model(
                wakeword_models=["hey_jarvis"],
                inference_framework="onnx"
            )
            print("  OpenWakeWord ready — listening for 'Hey Jarvis'")
        except Exception as e:
            print(f"  OWW model load failed: {e}")
            print("  Falling back to 'jarvis' keyword detection via Whisper...")
            _model = None
        return _model

# ─────────────────────────────────────────────
# CONTEXT CHECK (is user talking TO Jarvis?)
# ─────────────────────────────────────────────
def _should_activate(transcript: str) -> bool:
    """
    Decide if user is talking TO Jarvis or just mentioning Jarvis.
    Uses rule-based checks only (no model call).
    """
    t = transcript.lower().strip()

    # Always activate on direct wake words
    if t.startswith("hey jarvis"):
        return True

    # If it's just "jarvis" alone
    if t == "jarvis":
        return True

    # Quick keyword check first (saves LLM call)
    # If followed by a verb or command word → likely talking TO Jarvis
    command_words = ["open","close","play","pause","skip","search","find",
                     "what","how","when","where","why","who","set","turn",
                     "show","tell","run","check","get","make","create","can",
                     "could","would","is","are","do","did","will","help"]
    words = t.replace("jarvis","").strip().split()
    if words and words[0] in command_words:
        return True

    # Talking ABOUT Jarvis patterns
    about_patterns = ["jarvis is","jarvis was","jarvis looks","jarvis seems",
                      "jarvis can","jarvis could","jarvis would","jarvis has",
                      "about jarvis","like jarvis","jarvis so"]
    if any(p in t for p in about_patterns):
        return False

    # For ambiguous cases, prefer activation for responsiveness.
    return True

# ─────────────────────────────────────────────
# AUDIO LISTENER (OWW-based)
# ─────────────────────────────────────────────
def _oww_listener():
    """Main OWW listening loop."""
    global _running

    model = _load_model()
    if model is None:
        print("  OWW not available — using fallback listener")
        _fallback_listener()
        return

    pa = pyaudio.PyAudio()
    input_device_index = _resolve_pyaudio_input_device(pa)
    stream = pa.open(
        rate=SAMPLE_RATE,
        channels=CHANNELS,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
        input_device_index=input_device_index,
    )
    print(f"  OWW input device index: {input_device_index}")

    print("  Wake word active — say 'Hey Jarvis' or 'Jarvis [command]'")
    cooldown_until = 0

    SILENCE_THRESHOLD = 500  # RMS threshold — skip near-silent chunks

    while _running:
        try:
            audio_chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            audio_array = np.frombuffer(audio_chunk, dtype=np.int16)

            # SNR check — skip silent/noisy chunks to reduce false activations
            rms = np.sqrt(np.mean(audio_array.astype(np.float32) ** 2))
            if rms < SILENCE_THRESHOLD:
                continue

            # Run OWW inference
            prediction = model.predict(audio_array)

            # Check all wake word scores
            activated = False
            for wake_word, scores in prediction.items():
                score = scores[-1] if hasattr(scores, '__len__') else scores
                if score > SENSITIVITY:
                    activated = True
                    break

            if activated and time.time() > cooldown_until:
                cooldown_until = time.time() + 2  # 2 second cooldown
                if _callback:
                    threading.Thread(
                        target=_callback,
                        daemon=True
                    ).start()

        except Exception:
            if _running:
                time.sleep(0.1)

    stream.stop_stream()
    stream.close()
    pa.terminate()

# ─────────────────────────────────────────────
# FALLBACK LISTENER (Whisper-based, if OWW fails)
# ─────────────────────────────────────────────
def _fallback_listener():
    """
    Fallback: record 2-second chunks and check for
    'jarvis' using Whisper transcription.
    Slower but reliable.
    """
    import os
    import tempfile

    import scipy.io.wavfile as wav
    import sounddevice as sd

    sd_input_device = _resolve_sd_input_device()
    print(f"  Fallback input device index: {sd_input_device}")
    print("  Fallback wake word active — say 'Jarvis' or 'Hey Jarvis'")
    cooldown_until = 0

    while _running:
        try:
            # Record 2 second chunk
            audio = sd.rec(
                int(2 * RECORD_SAMPLE_RATE),
                samplerate=RECORD_SAMPLE_RATE,
                channels=1,
                dtype='int16',
                device=sd_input_device,
            )
            sd.wait()

            # Quick energy check — skip silent chunks
            energy = np.abs(audio).mean()
            if energy < 100:
                continue

            # Transcribe
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                wav.write(f.name, SAMPLE_RATE, audio)
                tmp = f.name

            try:
                from stt import transcribe_file
                text = transcribe_file(tmp).lower().strip()
            finally:
                try:
                    os.remove(tmp)
                except Exception:
                    pass

            if not text:
                continue

            # Check if jarvis is mentioned
            if "jarvis" in text and time.time() > cooldown_until:
                if _should_activate(text):
                    cooldown_until = time.time() + 3
                    print(f"  Wake word detected: '{text}'")
                    if _callback:
                        threading.Thread(
                            target=_callback,
                            daemon=True
                        ).start()

        except Exception:
            if _running:
                time.sleep(0.5)

# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────
def start(callback):
    """
    Start wake word detection.
    callback() is called whenever wake word is detected.
    """
    global _running, _thread, _callback
    _callback = callback
    _running = True
    _thread = threading.Thread(target=_oww_listener, daemon=True)
    _thread.start()
    print("  Wake word engine started.")

def stop():
    global _running
    _running = False
    print("  Wake word engine stopped.")

def is_running() -> bool:
    return _running
