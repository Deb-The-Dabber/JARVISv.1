"""Startup health check: verify JARVIS dependencies before going live.

Checks (all cheap — no model loads): watchlog DB writable, Chroma vector DB
present, trained NN weights present, at least one primary API key set, RAG
folder exists, self-test store writable, internet reachable.
"""

import os
import sqlite3
import threading
import time

import requests

import watchlog
from config import RAG_FOLDER
from vector_memory import VECTOR_DB_PATH

CACHE_SECONDS = 30

WEIGHTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_local_nn", "weights")
SPECIALIST_BUCKETS = ["tool_use", "chat", "coding", "reasoning", "self_mod", "automation"]

_PRIMARY_KEYS = [
    "NVIDIA_NEMOTRON_API_KEY",
    "NVIDIA_API_KEY",
    "GOOGLE_GENAI_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
]

_cache: dict = {"ts": 0.0, "result": None}
_lock = threading.Lock()


def run_healthcheck() -> dict:
    """Run all checks. Results are cached for CACHE_SECONDS to stay cheap."""
    with _lock:
        if time.time() - _cache["ts"] < CACHE_SECONDS and _cache["result"]:
            return _cache["result"]

        checks = [
            _check_watchlog(),
            _check_vector_db(),
            _check_weights(),
            _check_api_keys(),
            _check_rag_folder(),
            _check_self_test_store(),
            _check_internet(),
        ]
        result = {
            "ok": all(c["ok"] for c in checks),
            "checked_at": time.time(),
            "checks": checks,
        }
        _cache.update({"ts": time.time(), "result": result})
        return result


def _check_watchlog() -> dict:
    try:
        conn = sqlite3.connect(watchlog.DB_PATH)
        conn.execute("SELECT COUNT(*) FROM events")
        conn.close()
        return {"name": "watchlog_db", "ok": True, "detail": watchlog.DB_PATH}
    except Exception as e:
        return {"name": "watchlog_db", "ok": False, "detail": str(e)[:120]}


def _check_vector_db() -> dict:
    if not os.path.isdir(VECTOR_DB_PATH):
        return {"name": "vector_db", "ok": False, "detail": f"missing: {VECTOR_DB_PATH}"}
    chroma = os.path.join(VECTOR_DB_PATH, "chroma.sqlite3")
    detail = "present" if os.path.exists(chroma) else "dir present, no chroma.sqlite3 (will be created)"
    return {"name": "vector_db", "ok": True, "detail": detail}


def _check_weights() -> dict:
    router = os.path.join(WEIGHTS_DIR, "intent_router.npz")
    if not os.path.exists(router):
        return {"name": "nn_weights", "ok": False, "detail": "intent_router.npz missing — run training"}
    missing = [
        f"{b}.npz"
        for b in SPECIALIST_BUCKETS
        if not os.path.exists(os.path.join(WEIGHTS_DIR, "specialists", f"{b}.npz"))
    ]
    if missing:
        return {"name": "nn_weights", "ok": False, "detail": f"specialists missing: {', '.join(missing)}"}
    return {"name": "nn_weights", "ok": True, "detail": "intent_router.npz + 6 specialists"}


def _check_api_keys() -> dict:
    present = [k for k in _PRIMARY_KEYS if (os.getenv(k) or "").strip()]
    if not present:
        return {"name": "api_keys", "ok": False, "detail": "no primary provider keys set"}
    return {"name": "api_keys", "ok": True, "detail": f"{len(present)}/{len(_PRIMARY_KEYS)} primary keys set"}


def _check_rag_folder() -> dict:
    if os.path.isdir(RAG_FOLDER):
        return {"name": "rag_folder", "ok": True, "detail": RAG_FOLDER}
    return {"name": "rag_folder", "ok": False, "detail": f"missing: {RAG_FOLDER}"}


def _check_self_test_store() -> dict:
    try:
        os.makedirs(os.path.join(os.path.expanduser("~"), ".jarvis", "self_test"), exist_ok=True)
        probe = os.path.join(os.path.expanduser("~"), ".jarvis", "self_test", ".probe")
        with open(probe, "w") as f:
            f.write("ok")
        os.unlink(probe)
        return {"name": "self_test_store", "ok": True, "detail": "writable"}
    except Exception as e:
        return {"name": "self_test_store", "ok": False, "detail": str(e)[:120]}


def _check_internet() -> dict:
    try:
        requests.get("https://www.google.com", timeout=3)
        return {"name": "internet", "ok": True, "detail": "reachable"}
    except Exception:
        return {"name": "internet", "ok": False, "detail": "offline (cloud providers unavailable)"}


def report_text() -> str:
    result = run_healthcheck()
    header = "Health check: ALL OK" if result["ok"] else "Health check: ISSUES FOUND"
    lines = [header]
    for c in result["checks"]:
        marker = "[OK]   " if c["ok"] else "[FAIL] "
        lines.append(f"  {marker} {c['name']:<14} {c['detail'][:80]}")
    return "\n".join(lines)
