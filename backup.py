"""State backup/recovery: snapshots JARVIS persistent state to ~/.jarvis/backups/.

Covers: watchlog DB, Chroma vector DB, trained NN weights, self-test findings,
daily cost ledger. Not covered: ~/.jarvis/nn_cache (re-embeddable cache),
logs, .env (secrets stay out of backups).
"""

import datetime
import os
import shutil

import watchlog
from vector_memory import VECTOR_DB_PATH

BACKUP_ROOT_ENV = "JARVIS_BACKUP_ROOT"
DEFAULT_BACKUP_ROOT = os.path.join(os.path.expanduser("~"), ".jarvis", "backups")
KEEP_ENV = "JARVIS_BACKUP_KEEP"
DEFAULT_KEEP = 7

WEIGHTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_local_nn", "weights")
SELF_TEST_DIR = os.path.join(os.path.expanduser("~"), ".jarvis", "self_test")
COST_FILE = os.path.join(os.path.expanduser("~"), ".jarvis", "cost_daily.jsonl")


def backup_root() -> str:
    return os.getenv(BACKUP_ROOT_ENV) or DEFAULT_BACKUP_ROOT


def keep_count() -> int:
    try:
        return max(1, int(os.getenv(KEEP_ENV, str(DEFAULT_KEEP))))
    except ValueError:
        return DEFAULT_KEEP


def _sources() -> list[tuple[str, str]]:
    """Return (label, path) pairs; missing paths are skipped at runtime."""
    try:
        from rag_memory import RAG_DB_PATH
    except Exception:
        RAG_DB_PATH = ""
    return [
        ("watchlog.db", watchlog.DB_PATH),
        ("vector_db", VECTOR_DB_PATH),
        ("rag_db", RAG_DB_PATH),
        ("nn_weights", WEIGHTS_DIR),
        ("self_test", SELF_TEST_DIR),
        ("cost_daily.jsonl", COST_FILE),
    ]


def run_backup(label: str = "manual") -> dict:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_root(), f"{ts}_{label}")
    os.makedirs(dest, exist_ok=True)

    copied = []
    skipped = []
    for name, src in _sources():
        if not os.path.exists(src):
            skipped.append(name)
            continue
        target = os.path.join(dest, name)
        try:
            if os.path.isdir(src):
                shutil.copytree(src, target, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(src, target)
            copied.append(name)
        except Exception as e:
            skipped.append(f"{name} (error: {e})")

    total_size = 0
    for root, _dirs, files in os.walk(dest):
        for f in files:
            total_size += os.path.getsize(os.path.join(root, f))

    pruned = _prune_old()
    return {
        "backup_dir": dest,
        "created_at": ts,
        "label": label,
        "copied": copied,
        "skipped": skipped,
        "size_bytes": total_size,
        "pruned": pruned,
    }


def list_backups() -> list[dict]:
    root = backup_root()
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root), reverse=True):
        path = os.path.join(root, name)
        if not os.path.isdir(path):
            continue
        size = 0
        for r, _d, files in os.walk(path):
            for f in files:
                size += os.path.getsize(os.path.join(r, f))
        out.append({"name": name, "path": path, "size_bytes": size})
    return out


def _prune_old() -> list[str]:
    keep = keep_count()
    backups = sorted(os.listdir(backup_root())) if os.path.isdir(backup_root()) else []
    pruned = []
    for name in backups[:-keep]:
        path = os.path.join(backup_root(), name)
        if os.path.isdir(path):
            try:
                shutil.rmtree(path)
                pruned.append(name)
            except Exception:
                pass
    return pruned
