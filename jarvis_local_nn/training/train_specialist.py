"""Train a fine-grained specialist MLP for one coarse bucket.

Usage:
    python -m jarvis_local_nn.training.train_specialist --bucket tool_use [--synth 50] [--epochs 40]
    python -m jarvis_local_nn.training.train_specialist --all
"""

import argparse
import random
import time
from pathlib import Path

import numpy as np

from ..models.specialists import build_specialist, export_specialist
from ..tensor import Adam, Tensor, cross_entropy
from .data import embed_texts
from .taxonomy_data import BUCKETS, build_dataset, fine_classes

WEIGHTS_DIR = Path(__file__).resolve().parent.parent / "weights" / "specialists"


def _split(examples: list[tuple[str, str]], val_frac: float = 0.15, seed: int = 0):
    rng = random.Random(seed)
    shuffled = list(examples)
    rng.shuffle(shuffled)
    n_val = max(1, int(len(shuffled) * val_frac))
    return shuffled[n_val:], shuffled[:n_val]


def _deep_copy_state(state):
    if isinstance(state, dict):
        return {k: _deep_copy_state(v) for k, v in state.items()}
    if isinstance(state, list):
        return [_deep_copy_state(v) for v in state]
    return state.copy() if hasattr(state, "copy") else state


def train_specialist(
    bucket: str,
    synth_per_class: int = 50,
    epochs: int = 40,
    batch_size: int = 64,
    lr: float = 1e-3,
    patience: int = 6,
    seed: int = 0,
    verbose: bool = True,
) -> dict:
    """Train one specialist. Returns {'mlp', 'labels', 'val_acc', ...}."""
    classes = fine_classes(bucket)
    texts, intents = build_dataset(bucket, synth_per_class=synth_per_class, seed=seed)
    examples = list(zip(texts, intents))
    train_ex, val_ex = _split(examples, seed=seed)

    n_train, n_val = len(train_ex), len(val_ex)
    if verbose:
        from collections import Counter

        print(f"[{bucket}] {n_train} train / {n_val} val — {len(classes)} classes")
        for intent, count in Counter(intents).most_common():
            print(f"  {intent:22s}: {count}")

    train_texts = [t for t, _ in train_ex]
    val_texts = [t for t, _ in val_ex]
    if verbose:
        print(f"[{bucket}] Embedding texts (MiniLM, 384-dim)...")
    t0 = time.time()
    train_X = np.array(embed_texts(train_texts), dtype=np.float64)
    val_X = np.array(embed_texts(val_texts), dtype=np.float64)
    if verbose:
        print(f"  embedded in {time.time() - t0:.1f}s")

    label_index = {c: i for i, c in enumerate(classes)}
    train_y = np.array([label_index[i] for _, i in train_ex])
    val_y = np.array([label_index[i] for _, i in val_ex])

    mlp = build_specialist(len(classes), seed=seed)
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
            print(f"[{bucket}] epoch {epoch:2d}: loss={train_loss:.4f} val_acc={val_acc:.3f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_epoch = epoch
            best_state = {k: _deep_copy_state(v) for k, v in mlp.to_numpy().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                if verbose:
                    print(f"[{bucket}] Early stop at epoch {epoch} (best {best_epoch}: acc={best_val_acc:.3f})")
                break

    mlp.load_numpy(best_state)
    return {
        "mlp": mlp,
        "labels": classes,
        "val_acc": best_val_acc,
        "best_epoch": best_epoch,
        "n_train": n_train,
        "n_val": n_val,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", type=str, choices=BUCKETS)
    parser.add_argument("--all", action="store_true", help="train all buckets")
    parser.add_argument("--synth", type=int, default=50)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--out", type=str, default="")
    args = parser.parse_args()

    buckets = BUCKETS if args.all else [args.bucket]
    if not buckets or (not args.all and not args.bucket):
        parser.error("specify --bucket or --all")

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    for bucket in buckets:
        result = train_specialist(
            bucket,
            synth_per_class=args.synth,
            epochs=args.epochs,
            batch_size=args.batch,
            lr=args.lr,
        )
        out = args.out or str(WEIGHTS_DIR / f"{bucket}.npz")
        export_specialist(result["mlp"], result["labels"], out)
        print(f"[{bucket}] Best val accuracy: {result['val_acc']:.3f} (epoch {result['best_epoch']})")
        print(f"[{bucket}] Exported to: {out}")


if __name__ == "__main__":
    main()
