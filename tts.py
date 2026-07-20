import asyncio
import os
import shutil
import subprocess
import tempfile
import threading
import time

from dotenv import load_dotenv

from config import EDGE_TTS_VOICE, EDGE_TTS_VOICES

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_NAME = os.getenv("ELEVENLABS_VOICE_NAME", "Sarah")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_turbo_v2")

_tts_process = None
_tts_lock = threading.Lock()
_quota_warned = threading.Event()


class _SpeechJob:
    def __init__(self, target, args=()):
        self._stop = threading.Event()
        self._process = None
        self._thread = threading.Thread(target=target, args=(self, *args), daemon=True)
        self._thread.start()

    def set_process(self, process):
        self._process = process

    def stopped(self):
        return self._stop.is_set()

    def terminate(self):
        self._stop.set()
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=2)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass

    def wait(self):
        self._thread.join()

    def poll(self):
        return None if self._thread.is_alive() else 0


def _speak_with_say(text: str, job: _SpeechJob = None):
    process = subprocess.Popen(["say", "-v", "Samantha", text])
    if job:
        job.set_process(process)
    process.wait()


def _play_with_afplay(audio: bytes, job: _SpeechJob):
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio)
        path = f.name

    try:
        process = subprocess.Popen(["afplay", path])
        job.set_process(process)
        process.wait()
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def _stream_with_mpv(audio_stream, job: _SpeechJob):
    process = subprocess.Popen(
        ["mpv", "--no-terminal", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    job.set_process(process)

    try:
        for chunk in audio_stream:
            if job.stopped():
                break
            if chunk:
                process.stdin.write(chunk)
                process.stdin.flush()
    finally:
        if process.stdin:
            try:
                process.stdin.close()
            except Exception:
                pass
        if process.poll() is None:
            process.wait()


def _speak_with_elevenlabs(job: _SpeechJob, text: str):
    from config import TTS_RETRY_BASE_DELAY, TTS_RETRY_MAX_ATTEMPTS
    for attempt in range(1, TTS_RETRY_MAX_ATTEMPTS + 1):
        try:
            from elevenlabs import ElevenLabs

            if attempt > 1:
                delay = TTS_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(f"  ElevenLabs retry {attempt}/{TTS_RETRY_MAX_ATTEMPTS} in {delay:.0f}s")
                if job.stopped():
                    return
                time.sleep(delay)

            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            audio_stream = client.text_to_speech.stream(
                voice_id=ELEVENLABS_VOICE_ID,
                text=text,
                model_id=ELEVENLABS_MODEL,
                output_format="mp3_44100_128",
                optimize_streaming_latency=4,
            )

            if shutil.which("mpv"):
                _stream_with_mpv(audio_stream, job)
                return

            audio = b"".join(chunk for chunk in audio_stream if chunk)
            if not job.stopped():
                _play_with_afplay(audio, job)
            return
        except Exception as e:
            err = str(e).lower()
            quota_keys = ("quota", "exceeded", "rate limit", "429", "too many requests", "payment required")
            is_quota = any(k in err for k in quota_keys)
            if is_quota:
                if not _quota_warned.is_set():
                    print("  ElevenLabs TTS quota exceeded — falling back. (This will only print once per session.)")
                    _quota_warned.set()
                break
            if not is_quota and attempt < TTS_RETRY_MAX_ATTEMPTS:
                print(f"  ElevenLabs TTS attempt {attempt} failed: {e}")

    # Fall through to Edge-TTS
    try:
        _speak_with_edge_tts_inner(job, text)
        return
    except Exception:
        pass

    # Final fallback: macOS say
    if not job.stopped():
        _speak_with_say(text, job)


def _speak_with_edge_tts_inner(job: _SpeechJob, text: str):
    import edge_tts

    voice = EDGE_TTS_VOICE
    if voice not in EDGE_TTS_VOICES:
        voice = "en-US-JennyNeural"
    communicate = edge_tts.Communicate(text, voice)
    audio = asyncio.run(communicate.stream())
    audio_bytes = b"".join(chunk["data"] for chunk in audio if chunk["type"] == "audio")

    if job.stopped():
        return

    if shutil.which("mpv"):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_bytes)
            path = f.name
        try:
            process = subprocess.Popen(["mpv", "--no-terminal", path])
            job.set_process(process)
            process.wait()
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
    else:
        _play_with_afplay(audio_bytes, job)


def speak(text, interrupt=False):
    global _tts_process
    if not text:
        return

    with _tts_lock:
        if _tts_process and _tts_process.poll() is None:
            if interrupt:
                _tts_process.terminate()
                _tts_process.wait()
            else:
                return

        def _elevenlabs_then_edge(j, t):
            if ELEVENLABS_API_KEY:
                _speak_with_elevenlabs(j, t)
            else:
                try:
                    _speak_with_edge_tts_inner(j, t)
                except Exception:
                    pass
                if not j.stopped():
                    _speak_with_say(t, j)

        _tts_process = _SpeechJob(_elevenlabs_then_edge, (text,))


def stop_speaking():
    global _tts_process
    with _tts_lock:
        if _tts_process and _tts_process.poll() is None:
            _tts_process.terminate()
            _tts_process.wait()


def wait_for_speech():
    global _tts_process
    with _tts_lock:
        proc = _tts_process
    if proc:
        proc.wait()


if ELEVENLABS_API_KEY:
    print(f"  TTS: ElevenLabs ({ELEVENLABS_VOICE_NAME}) → Edge-TTS → macOS say")
else:
    print("  TTS: Edge-TTS → macOS say (fallback)")
