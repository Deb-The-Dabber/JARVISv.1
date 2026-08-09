"""Per-fine-class confidence threshold calibration for the two-stage router.

Sweeps a threshold per fine class over a seeded held-out split of the bucket
training data, and recommends the lowest gate that keeps precision above the
floor while retaining acceptable recall.

Usage:
    python -m jarvis_local_nn.training.calibrate_fine [--bucket BUCKET] [--all]
"""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np

from ..integration.specialist_router import predict_fine
from .taxonomy_data import fine_classes

PRECISION_FLOOR = float(
    __import__("os").getenv("JARVIS_FINE_CALIBRATE_PRECISION", "0.90")
)
MIN_SAMPLES = int(__import__("os").getenv("JARVIS_FINE_CALIBRATE_MIN_SAMPLES", "8"))
HOLD_OUT = 0.25

SWEEP_FLOOR = float(__import__("os").getenv("JARVIS_FINE_CALIBRATE_MIN_THRESHOLD", "0.50"))

THRESHOLDS_PATH = (
    Path(__file__).resolve().parent.parent / "weights" / "specialists" / "thresholds.json"
)


def calibrate_bucket(bucket: str, precision_floor: float = PRECISION_FLOOR) -> dict:
    from .taxonomy_data import build_dataset

    texts, labels = build_dataset(bucket, synth_per_class=50, seed=42, include_real=True)
    rng = random.Random(7)
    pairs = list(zip(texts, labels))
    rng.shuffle(pairs)
    split = int(len(pairs) * HOLD_OUT)
    holdout = pairs[:split]
    if len(holdout) < MIN_SAMPLES * len(fine_classes(bucket)):
        holdout = pairs
        note_all = "too few samples — used full set"
    else:
        note_all = f"holdout n={len(holdout)}"
    if not holdout:
        return {"error": f"no data for {bucket}"}

    preds = [predict_fine(bucket, t) for t, _ in holdout]
    confs = np.array([c for _, c in preds], dtype=np.float64)
    pred_labels = np.array([p if p is not None else "" for p, _ in preds])

    recommendations = {}
    for cls in fine_classes(bucket):
        y = np.array([label == cls for _, label in holdout])
        p = pred_labels == cls
        n_true = int(y.sum())
        if n_true < MIN_SAMPLES:
            recommendations[cls] = {
                "threshold": None,
                "precision": None,
                "recall": None,
                "samples": n_true,
                "note": "insufficient samples — keep bucket default",
            }
            continue
        best = None
        for t in np.arange(SWEEP_FLOOR, 0.99, 0.01):
            pos = p & (confs >= t)
            tp = int((pos & y).sum())
            fp = int((pos & ~y).sum())
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / n_true if n_true else 0.0
            if precision >= precision_floor and recall >= 0.30:
                best = {
                    "threshold": round(float(t), 2),
                    "precision": precision,
                    "recall": recall,
                }
                break
        if best is None:
            recommendations[cls] = {
                "threshold": None,
                "precision": 0.0,
                "recall": 0.0,
                "samples": n_true,
                "note": f"never hit precision {precision_floor:.2f}@recall>=0.30 — keep bucket default",
            }
        else:
            recommendations[cls] = {"samples": n_true, **best}
    return {"total": len(holdout), "note": note_all, "recommendations": recommendations}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", choices=["chat", "coding", "tool_use", "reasoning", "self_mod", "automation"])
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.all:
        from .taxonomy_data import get_taxonomy

        buckets = list(get_taxonomy()["coarse_intents"])
    else:
        buckets = [args.bucket]
    if args.bucket is None and not args.all:
        print("Pass --bucket BUCKET or --all")
        return 1

    all_recs: dict[str, dict] = {}
    for bucket in buckets:
        summary = calibrate_bucket(bucket)
        if "error" in summary:
            print(f"[{bucket}] {summary['error']}")
            continue
        print(f"\n=== {bucket} ({summary['note']}) ===")
        print(f"{'fine class':24s} {'threshold':>10s} {'precision':>10s} {'recall':>8s}  note")
        for cls, rec in summary["recommendations"].items():
            t = f"{rec['threshold']:.2f}" if rec["threshold"] is not None else "-"
            p = f"{rec['precision']:.3f}" if rec.get("precision") is not None else "-"
            r = f"{rec['recall']:.3f}" if rec.get("recall") is not None else "-"
            note = rec.get("note", f"n={rec['samples']}")
            print(f"{cls:24s} {t:>10s} {p:>10s} {r:>8s}  {note}")
        all_recs[bucket] = summary["recommendations"]

    out: dict[str, dict[str, float]] = {
        bucket: {
            cls: rec["threshold"]
            for cls, rec in recs.items()
            if rec.get("threshold") is not None
        }
        for bucket, recs in all_recs.items()
    }
    THRESHOLDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    THRESHOLDS_PATH.write_text(json.dumps(out, indent=2) + "\n")
    print(f"\nWrote {THRESHOLDS_PATH}")

    print("\nEnv vars to apply (overrides thresholds.json):")
    for bucket, recs in all_recs.items():
        for cls, rec in recs.items():
            if rec["threshold"] is not None:
                print(f"  JARVIS_FINE_CONFIDENCE_{cls.upper()}={rec['threshold']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
