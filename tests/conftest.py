import os
import signal
import subprocess
import sys
import time

import pytest
import requests


def _free_port(port: int = 8000):
    """Kill any process listening on the given port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
        for pid in pids:
            os.kill(int(pid), signal.SIGKILL)
            print(f"  Killed stale process {pid} on port {port}")
        if pids:
            time.sleep(2)
    except Exception:
        pass


def _stop_proc(proc: subprocess.Popen):
    """Terminate a subprocess, with escalation to SIGKILL."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def jarvis_server():
    _free_port(8000)
    env = os.environ.copy()
    env["JARVIS_TTS_SILENT"] = "1"
    proc = subprocess.Popen(
        ["python", "server.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(60):
        try:
            r = requests.get("http://localhost:8000/health", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        _stop_proc(proc)
        raise RuntimeError("Server failed to start within 60s")
    yield "http://localhost:8000"
    _stop_proc(proc)


@pytest.fixture
def api(jarvis_server):
    base = jarvis_server
    session = requests.Session()
    session.post(f"{base}/brain/reset", timeout=10)

    class API:
        def ask(self, text: str, timeout=180):
            return session.post(
                f"{base}/ask",
                json={"text": text},
                timeout=timeout,
            )

        def get(self, endpoint: str):
            return session.get(f"{base}{endpoint}", timeout=30)

        def close(self):
            session.close()

    yield API()
    session.close()


@pytest.fixture
def has_display():
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or (sys.platform == "darwin" and os.environ.get("TERM_PROGRAM")))


@pytest.fixture(autouse=True)
def _silence_tts():
    old = os.environ.get("JARVIS_TTS_SILENT")
    os.environ["JARVIS_TTS_SILENT"] = "1"
    yield
    if old is None:
        os.environ.pop("JARVIS_TTS_SILENT", None)
    else:
        os.environ["JARVIS_TTS_SILENT"] = old


# ── Mock Provider Fixtures ──


@pytest.fixture(scope="session")
def mock_provider_server():
    """Start the mock provider server for the test session."""
    mock_port = int(os.environ.get("MOCK_PROVIDER_PORT", "18889"))
    env = os.environ.copy()
    env["JARVIS_MOCK_PROVIDERS"] = "1"
    env["MOCK_PROVIDER_URL"] = f"http://127.0.0.1:{mock_port}"
    env["MOCK_PROVIDER_PORT"] = str(mock_port)

    # Set dummy API keys so brain.py passes the api_key check
    for key in [
        "NVIDIA_NEMOTRON_API_KEY",
        "NVIDIA_API_KEY",
        "NVIDIA_EMBEDDING_API_KEY",
        "DEEPSEEK_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "KIMI_API_KEY",
        "TAVILY_API_KEY",
        "ELEVENLABS_API_KEY",
    ]:
        env.setdefault(key, "mock-key")

    proc = subprocess.Popen(
        ["python", "-m", "uvicorn", "tests.mock_provider:app", "--host", "127.0.0.1", "--port", str(mock_port), "--log-level", "warning"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            r = requests.get(f"http://127.0.0.1:{mock_port}/health", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        _stop_proc(proc)
        raise RuntimeError("Mock provider failed to start within 30s")

    yield f"http://127.0.0.1:{mock_port}"

    _stop_proc(proc)


@pytest.fixture
def mock_provider(mock_provider_server):
    """Provide a control client for the mock provider."""
    base = mock_provider_server

    class MockClient:
        def fail(self, provider: str, mode: str = "500", duration: int = 30):
            requests.post(f"{base}/mock/fail/{provider}", params={"mode": mode, "duration": duration})

        def unfail(self, provider: str):
            requests.post(f"{base}/mock/unfail/{provider}")

        def rate_limit(self, provider: str, retry_after: int = 60):
            requests.post(f"{base}/mock/rate-limit/{provider}", params={"retry_after": retry_after})

        def latency(self, provider: str, ms: int):
            requests.post(f"{base}/mock/latency/{provider}", params={"ms": ms})

        def reset(self):
            requests.post(f"{base}/mock/reset")

        def health(self, provider: str) -> dict:
            return requests.get(f"{base}/mock/health/{provider}").json()

        def state(self) -> dict:
            return requests.get(f"{base}/mock/state").json()

        @property
        def called_providers(self) -> list[str]:
            state = self.state()
            return [p for p, s in state.items() if s.get("call_count", 0) > 0]

    client = MockClient()
    yield client
    client.reset()


@pytest.fixture
def mock_api(mock_provider_server):
    """API fixture that uses the mock provider server."""
    mock_port = int(os.environ.get("MOCK_PROVIDER_PORT", "18889"))
    env = os.environ.copy()
    env["JARVIS_TTS_SILENT"] = "1"
    env["JARVIS_MOCK_PROVIDERS"] = "1"
    env["MOCK_PROVIDER_URL"] = f"http://127.0.0.1:{mock_port}"
    for key in [
        "NVIDIA_NEMOTRON_API_KEY",
        "NVIDIA_API_KEY",
        "NVIDIA_EMBEDDING_API_KEY",
        "DEEPSEEK_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "KIMI_API_KEY",
        "TAVILY_API_KEY",
        "ELEVENLABS_API_KEY",
    ]:
        env.setdefault(key, "mock-key")

    proc = subprocess.Popen(
        ["python", "server.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(60):
        try:
            r = requests.get("http://localhost:8000/health", timeout=2)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        _stop_proc(proc)
        raise RuntimeError("Server failed to start within 60s")

    session = requests.Session()

    class MockAPI:
        def ask(self, text: str, timeout=180):
            return session.post(
                "http://localhost:8000/ask",
                json={"text": text},
                timeout=timeout,
            )

        def get(self, endpoint: str):
            return session.get(f"http://localhost:8000{endpoint}", timeout=30)

        def close(self):
            session.close()

    yield MockAPI()
    session.close()
    _stop_proc(proc)
