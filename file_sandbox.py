"""File-write sandbox: Jarvis proposes file changes, the user approves before any write happens.

When Jarvis calls a write tool (create_file, write_file, append_file), brain._execute_tool
intercepts the call, simulates the change, renders a unified diff, and queues it here as a
pending write. The actual write only happens after the user says yes (terminal) or confirms
via the API (/confirm). Saying no discards the change.

Disable with JARVIS_FILE_SANDBOX=0. Eval mode (JARVIS_EVAL_MODE=1) bypasses the sandbox so
tests can run unattended.
"""
import difflib
import os
import threading
import time

WRITE_TOOLS = {"create_file", "write_file", "append_file"}

PENDING_TTL = 300  # seconds before a staged change expires

_pending: dict = {}
_lock = threading.Lock()


def enabled() -> bool:
    return os.getenv("JARVIS_FILE_SANDBOX", "1").lower() in ("1", "true", "yes", "on")


def eval_mode() -> bool:
    return os.getenv("JARVIS_EVAL_MODE", "0").lower() in ("1", "true", "yes", "on")


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def simulate(tool_name: str, args: dict):
    """Return (full_path, old_content, new_content) for a write tool, or None."""
    if tool_name not in WRITE_TOOLS:
        return None
    args = args or {}
    try:
        if tool_name == "create_file":
            folder = args.get("path") or os.path.join(os.path.expanduser("~"), "Desktop")
            folder = os.path.expanduser(folder)
            full = os.path.realpath(os.path.join(folder, args.get("filename", "")))
        else:
            full = os.path.realpath(os.path.expanduser(args.get("path", "")))
        if not full:
            return None
        content = args.get("content", "")
        if isinstance(content, str) and "\x00" in content:
            return None  # binary content — skip sandboxing
        old = _read(full) if os.path.isfile(full) else ""
        new = old + content if tool_name == "append_file" else content
        return full, old, new
    except Exception:
        return None


def make_diff(path: str, old: str, new: str) -> str:
    if old == new:
        return ""
    rel = os.path.basename(path) or path
    diff = "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{rel}",
            tofile=f"b/{rel}",
            n=3,
        )
    )
    return diff


def counts(diff: str) -> tuple:
    lines = diff.splitlines()
    ins = sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++"))
    dels = sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---"))
    return ins, dels


def stage(tool_name: str, args: dict, path: str, old: str, new: str, diff: str):
    with _lock:
        _pending["tool"] = tool_name
        _pending["args"] = dict(args or {})
        _pending["path"] = path
        _pending["old"] = old
        _pending["new"] = new
        _pending["diff"] = diff
        _pending["expires_at"] = time.time() + PENDING_TTL


def get_pending() -> dict | None:
    with _lock:
        if not _pending:
            return None
        if time.time() > _pending.get("expires_at", 0):
            return None
        return {k: _pending[k] for k in ("tool", "path", "diff", "old", "new")}


def has_pending() -> bool:
    return get_pending() is not None


def clear_pending():
    with _lock:
        _pending.clear()
