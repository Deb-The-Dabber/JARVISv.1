"""Runtime integration for the local intent router — used by brain.py.

Provides a lazy-loaded classifier: embed text with MiniLM, run the tiny MLP
forward pass in pure numpy (no autograd), return (intent, confidence).
"""

from pathlib import Path

import numpy as np

from ..models.router import INTENTS, load_weights

WEIGHTS_PATH = Path(__file__).resolve().parent.parent / "weights" / "intent_router.npz"

_router = None
_embedder = None
_embedder_lock = __import__("threading").Lock()


class LocalIntentRouter:
    def __init__(self, weights_path: Path | str = WEIGHTS_PATH):
        self.state = load_weights(str(weights_path))
        self.hidden = self.state["hidden"]
        self.weights = self.state["weights"]
        self.labels = INTENTS

    def _forward(self, x: np.ndarray) -> np.ndarray:
        """Pure-numpy MLP forward: x (N, 384) -> logits (N, 6)."""
        h = x
        for li in range(len(self.hidden)):
            h = np.maximum(0.0, h @ self.weights[f"layer{li}_w"] + self.weights[f"layer{li}_b"])
        return h @ self.weights["head_w"] + self.weights["head_b"]

    def predict_logits(self, embeddings: np.ndarray) -> np.ndarray:
        return self._forward(np.asarray(embeddings, dtype=np.float64))

    def predict(self, text: str) -> tuple[str, float]:
        """Return (intent, softmax confidence) for a single text."""
        emb = embed_single(text)
        if emb is None:
            return "chat", 0.0
        logits = self._forward(emb.reshape(1, -1))
        exp = np.exp(logits - logits.max())
        probs = exp / exp.sum()
        idx = int(np.argmax(probs))
        return self.labels[idx], float(probs[0, idx])


def embed_single(text: str) -> np.ndarray | None:
    global _embedder
    with _embedder_lock:
        if _embedder is None:
            # Reuse vector_memory's cached MiniLM instance (same model) when available
            try:
                from vector_memory import get_local_embedding_model

                model = get_local_embedding_model()
                _embedder = model
            except Exception:
                _embedder = None
        if _embedder is None:
            try:
                from sentence_transformers import SentenceTransformer

                _embedder = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                return None
        try:
            vec = _embedder.encode(text, normalize_embeddings=True)
            return np.asarray(vec, dtype=np.float64)
        except Exception:
            return None


def get_router() -> LocalIntentRouter | None:
    """Lazily load the router; returns None if weights are missing or unreadable."""
    global _router
    if _router is None:
        if not WEIGHTS_PATH.exists():
            return None
        try:
            _router = LocalIntentRouter(WEIGHTS_PATH)
        except Exception:
            return None
    return _router


def reload_router() -> None:
    """Drop the cached router so the next predict loads fresh weights from disk."""
    global _router
    _router = None


def predict_intent(text: str) -> tuple[str | None, float]:
    """Convenience wrapper: (intent, confidence) or (None, 0.0) when unavailable."""
    try:
        router = get_router()
        if router is None:
            return None, 0.0
        return router.predict(text)
    except Exception:
        return None, 0.0
