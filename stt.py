import os
import tempfile
import threading

SAMPLE_RATE = 16000

_model = None
_model_kind = None
_model_lock = threading.Lock()

# VAD
_vad = None


def _load_vad():
    global _vad
    if _vad is not None:
        return _vad
    try:
        import webrtcvad

        from config import VAD_AGGRESSIVENESS
        _vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
    except Exception:
        _vad = False
    return _vad


def vad_is_available() -> bool:
    v = _load_vad()
    return v is not False


def vad_filter(audio: bytes, sample_rate: int = 16000) -> bool:
    v = _load_vad()
    if v is False:
        return True
    from config import VAD_FRAME_MS
    frame_size = int(sample_rate * VAD_FRAME_MS / 1000) * 2
    if len(audio) < frame_size:
        return False
    try:
        return v.is_speech(audio[:frame_size], sample_rate)
    except Exception:
        return True


def _load_model():
    global _model, _model_kind
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel
            _model = WhisperModel("base", device="cpu", compute_type="int8")
            _model_kind = "faster-whisper"
            print("  STT: faster-whisper (base, int8)")
        except Exception as e:
            print(f"  faster-whisper failed ({e}), falling back to openai-whisper...")
            import whisper
            _model = whisper.load_model("base")
            _model_kind = "openai-whisper"
            print("  STT: openai-whisper (fallback)")
        return _model


def get_model():
    if _model is None:
        return _load_model()
    return _model


def transcribe_file(path: str) -> str:
    """Transcribe a wav/audio file. Returns text."""
    model = get_model()
    try:
        if _model_kind == "faster-whisper":
            segments, _ = model.transcribe(path)
            return " ".join(segment.text for segment in segments).strip()
        result = model.transcribe(path)
        if isinstance(result, dict):
            return result.get("text", "").strip()
        return str(result).strip()
    except Exception as e:
        print(f"  Transcription error: {e}")
        return ""


def transcribe_audio_data(audio_bytes: bytes) -> str:
    """Transcribe raw audio bytes. Saves to temp file first."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        tmp = f.name
    try:
        return transcribe_file(tmp)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


def transcribe_numpy(audio, sample_rate: int = SAMPLE_RATE) -> str:
    """Transcribe numpy audio array."""
    import scipy.io.wavfile as wav
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav.write(f.name, sample_rate, audio)
        tmp = f.name
    try:
        return transcribe_file(tmp)
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass


threading.Thread(target=_load_model, daemon=True).start()
