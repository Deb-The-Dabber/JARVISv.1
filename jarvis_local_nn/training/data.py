"""Training data for the coarse intent router.

Sources:
1. Real labeled requests from ~/.jarvis/logs/jarvis.jsonl (intent per request,
   logged by jarvis_logger.log_request).
2. Synthetic template generation for the long tail (reasoning, self_mod,
   automation) which has <50 real examples each.

Embeddings come from the same all-MiniLM-L6-v2 model Jarvis uses for vector
memory (384-dim).
"""

import hashlib
import json
import os
import threading
from pathlib import Path

import numpy as np

from ..models.router import INTENTS

LOG_FILE = Path(os.path.expanduser("~/.jarvis/logs/jarvis.jsonl"))
JARVIS_ROOT = Path(__file__).resolve().parent.parent.parent

_embedder = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


# ── Persistent embedding cache ──
# Keyed by sha256(text)[:16] → 384-dim vector. Full retrains re-embed ~2k texts
# (~10-15s); the cache makes incremental retrains embed only new entries.

CACHE_DIR = Path(os.path.expanduser("~/.jarvis/nn_cache"))
EMBED_CACHE_PATH = CACHE_DIR / "embeddings.npz"

_cache_lock = threading.Lock()
_embed_cache: dict[str, np.ndarray] | None = None


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _load_embed_cache() -> dict[str, np.ndarray]:
    global _embed_cache
    if _embed_cache is None:
        _embed_cache = {}
        if EMBED_CACHE_PATH.exists():
            try:
                with np.load(EMBED_CACHE_PATH, allow_pickle=False) as z:
                    keys = [str(k) for k in z["keys"]]
                    vecs = z["vecs"]
                _embed_cache = dict(zip(keys, vecs))
            except Exception:
                _embed_cache = {}
    return _embed_cache


def _save_embed_cache(cache: dict[str, np.ndarray]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = EMBED_CACHE_PATH.with_suffix(".tmp.npz")
        np.savez_compressed(
            tmp,
            keys=np.array(sorted(cache.keys())),
            vecs=np.array([cache[k] for k in sorted(cache.keys())]),
        )
        tmp.replace(EMBED_CACHE_PATH)
    except Exception:
        pass


def embed_texts(texts: list[str], use_cache: bool = True) -> list[list[float]]:
    if not texts:
        return []
    if not use_cache:
        return _get_embedder().encode(texts, normalize_embeddings=True).tolist()
    with _cache_lock:
        cache = _load_embed_cache()
        keys = [_cache_key(t) for t in texts]
        missing = [t for t, k in zip(texts, keys) if k not in cache]
        if missing:
            new_vecs = _get_embedder().encode(missing, normalize_embeddings=True)
            for t, v in zip(missing, new_vecs):
                cache[_cache_key(t)] = np.asarray(v, dtype=np.float64)
            _save_embed_cache(cache)
        return [cache[k].tolist() for k in keys]


# ── Real data from jarvis.jsonl ──


def load_real_examples(path: Path | None = None) -> list[tuple[str, str]]:
    """Return [(text, intent)] from the jarvis_logger request log."""
    path = path or LOG_FILE
    examples = []
    if not path.exists():
        return examples
    with open(path) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") == "tool_call":
                continue
            intent = entry.get("intent")
            text = entry.get("user_message_preview") or entry.get("user_message")
            if intent in INTENTS and text and len(text.strip()) >= 2:
                examples.append((text.strip(), intent))
    return examples


# ── Learned tools (learner.py) as tool_use training examples ──

LEARNED_TOOLS_DIR = Path(os.path.expanduser("~/jarvis_learned_tools"))


def load_learned_tool_tasks(path: Path | None = None) -> list[str]:
    """Return task descriptions from learner.py-generated tools (~/jarvis_learned_tools).

    Each learned tool file has a '# Task: <description>' header; the task
    description is what the user asked Jarvis to learn — a natural tool_use example.
    """
    path = path or LEARNED_TOOLS_DIR
    tasks = []
    if not path.exists():
        return tasks
    for filename in sorted(path.glob("*.py")):
        try:
            with open(filename) as f:
                for _ in range(5):
                    line = f.readline()
                    if line.startswith("# Task:"):
                        task = line.replace("# Task:", "").strip()
                        if task and len(task) >= 3:
                            tasks.append(task)
                        break
        except OSError:
            continue
    return tasks


# ── Synthetic templates for the long tail ──

SYNTHETIC_TEMPLATES: dict[str, list[str]] = {
    "reasoning": [
        "why is the sky blue",
        "why does water boil at 100 degrees",
        "how do neural networks work",
        "how does gravity affect time",
        "explain how the economy works",
        "explain why the stock market went down",
        "analyze the pros and cons of electric cars",
        "compare python and javascript",
        "evaluate which database is best for this project",
        "design a strategy to improve my productivity",
        "what is the meaning of life",
        "why are the seasons changing",
        "how does quantum computing work",
        "think about the best way to organize this codebase",
        "describe the difference between supervised and unsupervised learning",
        "what is the best approach to scale this application",
        "why do we dream",
        "how can i improve my memory",
        "analyze the risks of investing in crypto",
        "explain the theory of relativity in simple terms",
        "what would happen if the moon disappeared",
        "how does photosynthesis work",
        "why is the ocean salty",
        "compare the two architectures we discussed",
        "evaluate whether i should switch to linux",
        "strategy for learning a new language quickly",
        "pros and cons of working remotely",
        "describe how money is created",
        "why does time feel faster as we age",
        "what is the best way to study for exams",
        "analyze this dataset and tell me what you see",
        "how would you solve the traveling salesman problem",
        "explain the butterfly effect",
        "why do we sleep",
        "design an algorithm to find the shortest path",
    ],
    "self_mod": [
        "fix the bug in brain.py",
        "refactor the code in brain.py",
        "update brain.py to handle this better",
        "modify the tool in tools/browser_tools.py",
        "edit safety.py to add a new gate",
        "change terminal.py to add a shortcut",
        "rewrite agent.py to persist agents",
        "improve the code in server.py",
        "debug the issue in brain.py",
        "read brain.py and fix it",
        "modify yourself to be faster",
        "improve yourself",
        "update your code to handle errors better",
        "change your source code",
        "fix the bug in tools/computer_tools.py",
        "refactor the tools in tools/ directory",
        "improve the weather tool in tools/system_tools.py",
        "make brain.py more efficient",
        "rewrite the file sandbox in file_sandbox.py",
        "fix config.py to load the right settings",
        "edit your own source code",
        "add error handling to tools/gmail_tools.py",
        "modify tts.py to use a different voice",
        "update agent.py to support more agents",
        "refactor server.py to add new endpoints",
        "fix the memory bug in memory.py",
        "change the behavior in tools/spotify_tools.py",
        "improve the search in tools/browser_tools.py",
        "debug and fix brain.py line 400",
        "make the code in tools/vision_tools.py more robust",
    ],
    "automation": [
        "automate my downloads folder",
        "set up an automation to organize my files",
        "create a workflow to back up my documents",
        "automate sending a weekly report",
        "set up a script that cleans my desktop every day",
        "create an automation to monitor my system usage",
        "build a workflow that checks my calendar each morning",
        "automate downloading my emails as pdf",
        "create a routine to summarize news every morning",
        "set up automation to track my goals weekly",
        "automate my folder organization on weekends",
        "create a workflow to sync my notes",
        "set up a daily backup automation",
        "automate sorting my screenshots",
        "create an automation that reminds me to stand up",
        "set up a weekly clean of my downloads",
        "automate the process of checking stock prices",
        "build a routine that opens my apps at 9am",
        "create an automation for my morning briefing",
        "set up a script to monitor disk space",
    ],
}


def build_dataset(
    real_examples: list[tuple[str, str]] | None = None,
    synth_per_class: int = 0,
    seed: int = 0,
    include_learned: bool = False,
) -> tuple[list[str], list[str]]:
    """Return (texts, intents) — real examples + sampled synthetic augmentation.

    synth_per_class caps synthetic samples per long-tail class so the model
    doesn't get flooded by templates. Pass 0 to use only real data.
    include_learned adds learner.py task descriptions as tool_use examples.
    """
    rng = __import__("random").Random(seed)
    examples = list(real_examples) if real_examples else load_real_examples()
    texts = [t for t, _ in examples]
    intents = [i for _, i in examples]

    if synth_per_class > 0:
        for intent, templates in SYNTHETIC_TEMPLATES.items():
            if intent in INTENTS:
                pool = [t for t in templates]
                rng.shuffle(pool)
                for t in pool[:synth_per_class]:
                    texts.append(t)
                    intents.append(intent)

    if include_learned:
        for task in load_learned_tool_tasks():
            texts.append(f"can you learn how to {task}")
            intents.append("tool_use")
            texts.append(f"teach yourself to {task}")
            intents.append("tool_use")
    return texts, intents
