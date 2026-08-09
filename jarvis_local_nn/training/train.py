"""Train the coarse 6-way intent router and export weights to .npz.

Usage:
    python -m jarvis_local_nn.training.train [--synth 50] [--epochs 30]
"""

import argparse
import random
import time
from pathlib import Path

import numpy as np

from ..models.router import INTENTS, build_router, export_weights
from ..tensor import Adam, Tensor, cross_entropy
from .data import build_dataset, embed_texts, load_real_examples

WEIGHTS_PATH = Path(__file__).resolve().parent.parent / "weights" / "intent_router.npz"


def _split(examples: list[tuple[str, str]], val_frac: float = 0.15, seed: int = 0):
    rng = random.Random(seed)
    shuffled = list(examples)
    rng.shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * val_frac))
    return shuffled[n_val:], shuffled[:n_val]


def _deep_copy_state(state):
    """Deep-copy a state tree (dicts/lists of {'w','b'} ndarrays) so best-checkpoint
    weights aren't mutated in place by later optimizer steps."""
    if isinstance(state, dict):
        return {k: _deep_copy_state(v) for k, v in state.items()}
    if isinstance(state, list):
        return [_deep_copy_state(v) for v in state]
    return state.copy() if hasattr(state, "copy") else state


def train(
    synth_per_class: int = 50,
    epochs: int = 30,
    batch_size: int = 64,
    lr: float = 1e-3,
    patience: int = 5,
    seed: int = 0,
    verbose: bool = True,
    include_learned: bool = False,
) -> dict:
    real = load_real_examples()
    texts, intents = build_dataset(real, synth_per_class=synth_per_class, seed=seed, include_learned=include_learned)
    examples = list(zip(texts, intents))
    train_ex, val_ex = _split(examples, seed=seed)

    n_train, n_val = len(train_ex), len(val_ex)
    if verbose:
        print(f"Dataset: {n_train} train / {n_val} val (real={len(real)}, synth={len(texts) - len(real)})")
        from collections import Counter

        for intent, count in Counter(intents).most_common():
            print(f"  {intent:12s}: {count}")

    train_texts = [t for t, _ in train_ex]
    val_texts = [t for t, _ in val_ex]
    if verbose:
        print("Embedding texts (MiniLM, 384-dim)...")
    t0 = time.time()
    train_X = np.array(embed_texts(train_texts), dtype=np.float64)
    val_X = np.array(embed_texts(val_texts), dtype=np.float64)
    if verbose:
        print(f"  embedded in {time.time() - t0:.1f}s")

    train_y = np.array([INTENTS.index(i) for _, i in train_ex])
    val_y = np.array([INTENTS.index(i) for _, i in val_ex])

    mlp = build_router(seed=seed)
    opt = Adam(mlp.parameters(), lr=lr)
    rng = np.random.default_rng(seed)

    best_val_acc, best_state, best_epoch = 0.0, None, -1
    epochs_without_improvement = 0

    for epoch in range(1, epochs + 1):
        perm = rng.permutation(n_train)
        total_loss = 0.0
        n_batches = 0
        for start in range(0, n_train, batch_size):
            idx = perm[start : start + batch_size]
            opt.zero_grad()
            logits = mlp(Tensor(train_X[idx]), training=True)
            loss = cross_entropy(logits, train_y[idx])
            loss.backward()
            opt.step()
            total_loss += float(loss.data.item())
            n_batches += 1

        val_logits = mlp(Tensor(val_X))
        val_pred = np.argmax(val_logits.data, axis=1)
        val_acc = float(np.mean(val_pred == val_y))
        train_loss = total_loss / max(n_batches, 1)

        if verbose:
            print(f"epoch {epoch:2d}: loss={train_loss:.4f} val_acc={val_acc:.3f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_epoch = epoch
            best_state = {k: _deep_copy_state(v) for k, v in mlp.to_numpy().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                if verbose:
                    print(f"Early stop at epoch {epoch} (best {best_epoch}: acc={best_val_acc:.3f})")
                break

    mlp.load_numpy(best_state)
    return {
        "mlp": mlp,
        "val_acc": best_val_acc,
        "best_epoch": best_epoch,
        "n_train": n_train,
        "n_val": n_val,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--synth", type=int, default=50, help="synthetic examples per long-tail class (0=off)")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--out", type=str, default=str(WEIGHTS_PATH))
    parser.add_argument(
        "--retrain", action="store_true", help="retrain from accumulated logs; compare val accuracy vs existing weights"
    )
    parser.add_argument(
        "--include-learned", action="store_true", help="add learner.py task descriptions as tool_use examples"
    )
    args = parser.parse_args()

    if args.retrain:
        old_acc = _evaluate_existing_weights(args.out)
        print(f"Existing weights ({args.out}): val accuracy = {old_acc:.3f}")

    result = train(
        synth_per_class=args.synth,
        epochs=args.epochs,
        batch_size=args.batch,
        lr=args.lr,
        include_learned=args.include_learned,
    )
    export_weights(result["mlp"], args.out)
    print(f"\nBest val accuracy: {result['val_acc']:.3f} (epoch {result['best_epoch']})")
    print(f"Weights exported to: {args.out}")
    if args.retrain and old_acc is not None:
        delta = result["val_acc"] - old_acc
        trend = "improved" if delta > 0.005 else "declined" if delta < -0.005 else "stable"
        print(f"Retrain delta: {delta:+.3f} ({trend})")


def _evaluate_existing_weights(path: str) -> float | None:
    """Evaluate the current .npz weights on the same train/val split; returns val accuracy."""
    import random

    from ..models.router import INTENTS, load_weights
    from .data import build_dataset, embed_texts, load_real_examples

    real = load_real_examples()
    texts, intents = build_dataset(real, synth_per_class=50, seed=0)
    examples = list(zip(texts, intents))
    rng = random.Random(0)
    shuffled = list(examples)
    rng.shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * 0.15))
    val_ex = shuffled[:n_val]
    try:
        state = load_weights(path)
        weights = state["weights"]
        hidden = state["hidden"]
        val_X = np.array(embed_texts([t for t, _ in val_ex]), dtype=np.float64)
        val_y = np.array([INTENTS.index(i) for _, i in val_ex])
        h = val_X
        for li in range(len(hidden)):
            h = np.maximum(0.0, h @ weights[f"layer{li}_w"] + weights[f"layer{li}_b"])
        logits = h @ weights["head_w"] + weights["head_b"]
        preds = np.argmax(logits, axis=1)
        return float(np.mean(preds == val_y))
    except Exception:
        return None


if __name__ == "__main__":
    main()
