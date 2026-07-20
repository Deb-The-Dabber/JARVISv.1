import logging
import os
import resource
import shutil
import signal
import subprocess
import tempfile
import threading
import time

_LOG = logging.getLogger("sandbox")

SANDBOX_DIR = os.path.join(tempfile.gettempdir(), "jarvis_sandbox")


def _use_sandbox() -> bool:
    return os.getenv("JARVIS_SANDBOX_ENABLED", "1").lower() in ("1", "true", "yes")


DEFAULT_TIMEOUT = 30
DEFAULT_MEMORY_MB = 256
DEFAULT_CPU_SECONDS = 30

_sandbox_dir_created = False
_sandbox_lock = threading.Lock()
_run_counter = 0


def _ensure_sandbox_dir() -> str:
    global _sandbox_dir_created
    if not _sandbox_dir_created:
        with _sandbox_lock:
            if not _sandbox_dir_created:
                os.makedirs(SANDBOX_DIR, exist_ok=True)
                _sandbox_dir_created = True
    return SANDBOX_DIR


def _make_run_dir() -> str:
    global _run_counter
    base = _ensure_sandbox_dir()
    with _sandbox_lock:
        _run_counter += 1
        c = _run_counter
    run_dir = os.path.join(base, f"run_{int(time.time())}_{os.getpid()}_{c}")
    os.makedirs(run_dir, exist_ok=True)
    return os.path.realpath(run_dir)


def _cleanup_run_dir(run_dir: str):
    try:
        shutil.rmtree(run_dir, ignore_errors=True)
    except Exception:
        pass


def _apply_limits(memory_mb: int, cpu_seconds: int):
    try:
        if memory_mb > 0:
            mem_bytes = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        if cpu_seconds > 0:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    except Exception:
        pass


def _kill_process_group(pid: int):
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except Exception:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass


def _build_sandbox_exec_args(base_args: list, run_dir: str, allow_network: bool) -> list | None:
    sb_path = os.path.join(_ensure_sandbox_dir(), f"profile_{os.getpid()}_{int(time.time())}.sb")
    real_dir = os.path.realpath(run_dir)
    esc_dir = real_dir.replace('"', '\\"')
    esc_jarvis = os.path.realpath(os.path.expanduser("~/.jarvis")).replace('"', '\\"')

    write_rules = "\n".join(
        [
            f'(allow file-write* (subpath "{esc_dir}"))',
            '(allow file-write* (subpath "/tmp"))',
            '(allow file-write* (subpath "/private/tmp"))',
            f'(allow file-write* (subpath "{esc_jarvis}"))',
        ]
    )

    net = "(allow network*)" if allow_network else "(deny network*)"

    profile = f"""(version 1)
(deny default)
(allow file-read*)
{write_rules}
(allow process-exec)
(allow process-fork)
(allow sysctl-read)
(allow signal (target self))
(allow ipc-posix*)
(allow mach*)
{net}
"""
    try:
        with open(sb_path, "w") as f:
            f.write(profile)
        return ["sandbox-exec", "-f", sb_path] + base_args
    except Exception:
        return None


def _try_sandbox_exec(args: list, run_dir: str, allow_network: bool) -> list | None:
    sb = shutil.which("sandbox-exec")
    if not sb:
        return None
    return _build_sandbox_exec_args(args, run_dir, allow_network)


def run_sandboxed(
    args: list | str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    memory_mb: int = DEFAULT_MEMORY_MB,
    cpu_seconds: int = DEFAULT_CPU_SECONDS,
    allow_network: bool = False,
    shell: bool = False,
    cwd: str | None = None,
    env: dict | None = None,
) -> dict:
    started = time.time()
    run_dir = _make_run_dir()
    result = {"ok": False, "stdout": "", "stderr": "", "exit_code": -1, "duration_ms": 0, "error": "", "sandboxed": False, "run_dir": run_dir}

    enable_sandbox = _use_sandbox()
    final_args = args
    if enable_sandbox and not shell and isinstance(args, list):
        sb_args = _try_sandbox_exec(args, run_dir, allow_network)
        if sb_args is not None:
            final_args = sb_args
            result["sandboxed"] = True

    try:
        proc = subprocess.Popen(
            final_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=shell,
            cwd=cwd or run_dir,
            env=env,
            preexec_fn=None if (shell or result["sandboxed"]) else (lambda: _apply_limits(memory_mb, cpu_seconds)),
            start_new_session=True,
        )

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            result["exit_code"] = proc.returncode
            result["stdout"] = stdout or ""
            result["stderr"] = stderr or ""
            result["ok"] = proc.returncode == 0
        except subprocess.TimeoutExpired:
            _kill_process_group(proc.pid)
            result["error"] = f"Timed out after {timeout}s"
            try:
                stdout, stderr = proc.communicate(timeout=3)
                result["stdout"] = stdout or ""
                result["stderr"] = stderr or ""
            except Exception:
                pass
    except FileNotFoundError as e:
        result["error"] = f"Command not found: {e}"
    except Exception as e:
        result["error"] = str(e)

    result["duration_ms"] = int((time.time() - started) * 1000)
    return result


def run_sandboxed_python(code: str, *, timeout: int = DEFAULT_TIMEOUT, memory_mb: int = DEFAULT_MEMORY_MB, cpu_seconds: int = DEFAULT_CPU_SECONDS) -> dict:
    run_dir = _make_run_dir()
    script_path = os.path.join(run_dir, "script.py")
    try:
        with open(script_path, "w") as f:
            f.write(code)
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": "", "exit_code": -1, "duration_ms": 0, "error": f"Could not write script: {e}", "sandboxed": False, "run_dir": run_dir}

    result = run_sandboxed(
        ["python", script_path],
        timeout=timeout,
        memory_mb=memory_mb,
        cpu_seconds=cpu_seconds,
        allow_network=False,
        cwd=run_dir,
    )
    # Clean up the temp script
    try:
        os.remove(script_path)
    except Exception:
        pass
    return result


def run_sandboxed_command(command: str, *, timeout: int = DEFAULT_TIMEOUT, memory_mb: int = DEFAULT_MEMORY_MB, cpu_seconds: int = DEFAULT_CPU_SECONDS, allow_network: bool = False) -> dict:
    return run_sandboxed(
        command,
        timeout=timeout,
        memory_mb=memory_mb,
        cpu_seconds=cpu_seconds,
        allow_network=allow_network,
        shell=True,
    )
