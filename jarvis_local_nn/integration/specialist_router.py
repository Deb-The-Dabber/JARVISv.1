"""Runtime two-stage fine intent classification.

Stage 1: coarse 6-way router (local_router.py) picks the bucket.
Stage 2: the bucket's specialist MLP picks the fine-grained intent.

Lazy-loaded per specialist; shares the same MiniLM embedder as the coarse
router via embed_single.
"""

import json
import os
import threading
from pathlib import Path

import numpy as np

from ..models.specialists import load_specialist_weights
from .local_router import embed_single

WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "weights" / "specialists"
THRESHOLDS_PATH = WEIGHTS_DIR / "thresholds.json"

DEFAULT_BUCKET_GATES = {
    "chat": 0.85,
    "coding": 0.85,
    "tool_use": 0.85,
    "reasoning": 0.85,
    "self_mod": 0.90,
    "automation": 0.90,
}

_specialists = {}
_specialists_lock = threading.Lock()
_thresholds: dict[str, float] | None = None
_thresholds_lock = threading.Lock()


def _load_thresholds() -> dict[str, float]:
    """Per-fine-class gates from thresholds.json, with env overrides on top."""
    global _thresholds
    with _thresholds_lock:
        if _thresholds is not None:
            return _thresholds
        merged: dict[str, float] = {}
        if THRESHOLDS_PATH.exists():
            try:
                data = json.loads(THRESHOLDS_PATH.read_text())
                for bucket, classes in data.items():
                    merged.update({str(c): float(t) for c, t in classes.items()})
            except Exception:
                pass
        # env overrides: JARVIS_FINE_CONFIDENCE_<CLASS>
        for key, val in os.environ.items():
            if key.startswith("JARVIS_FINE_CONFIDENCE_"):
                cls = key[len("JARVIS_FINE_CONFIDENCE_"):].lower()
                try:
                    merged[cls] = float(val)
                except ValueError:
                    pass
        _thresholds = merged
        return _thresholds


def reload_specialists() -> None:
    """Drop cached specialists and thresholds so the next call reloads fresh."""
    global _specialists, _thresholds
    with _specialists_lock:
        _specialists.clear()
    with _thresholds_lock:
        _thresholds = None


def fine_threshold(bucket: str, fine_intent: str) -> float:
    """Per-class gate, falling back to the bucket default when uncalibrated."""
    return _load_thresholds().get(
        fine_intent, DEFAULT_BUCKET_GATES.get(bucket, 0.85)
    )


class SpecialistRouter:
    def __init__(self, weights_path: Path | str):
        state = load_specialist_weights(str(weights_path))
        self.hidden = state["hidden"]
        self.weights = state["weights"]
        self.labels = state["labels"]

    def predict(self, text: str) -> tuple[str, float]:
        emb = embed_single(text)
        if emb is None:
            return self.labels[0], 0.0
        logits = self._forward(emb.reshape(1, -1))
        exp = np.exp(logits - logits.max())
        probs = exp / exp.sum()
        idx = int(np.argmax(probs))
        return self.labels[idx], float(probs[0, idx])

    def _forward(self, x: np.ndarray) -> np.ndarray:
        h = x
        for li in range(len(self.hidden)):
            h = np.maximum(0.0, h @ self.weights[f"layer{li}_w"] + self.weights[f"layer{li}_b"])
        return h @ self.weights["head_w"] + self.weights["head_b"]


def get_specialist(bucket: str) -> SpecialistRouter | None:
    """Lazily load a bucket's specialist; None if weights missing/unreadable."""
    global _specialists
    with _specialists_lock:
        if bucket not in _specialists:
            path = WEIGHTS_DIR / f"{bucket}.npz"
            if not path.exists():
                return None
            try:
                _specialists[bucket] = SpecialistRouter(path)
            except Exception:
                return None
    return _specialists[bucket]


def predict_fine(bucket: str, text: str) -> tuple[str | None, float]:
    """Raw (fine_intent, confidence) or (None, 0.0) when the specialist is unavailable."""
    try:
        specialist = get_specialist(bucket)
        if specialist is None:
            return None, 0.0
        return specialist.predict(text)
    except Exception:
        return None, 0.0


def predict_fine_gated(bucket: str, text: str) -> tuple[str | None, float]:
    """(fine_intent, confidence) with the per-class confidence gate applied.

    Below the gate the fine label is withheld — (None, conf) — so callers fall
    through to LLM routing instead of trusting a weak prediction.
    """
    try:
        fine, conf = predict_fine(bucket, text)
        if fine is None or conf < fine_threshold(bucket, fine):
            return None, conf
        return fine, conf
    except Exception:
        return None, 0.0
