"""Per-intent confidence threshold calibration for the local intent router.

Runs the trained router over the golden eval set plus the real labeled log
data, sweeps the confidence threshold per intent, and recommends a gate for
each: the lowest threshold that keeps precision >= PRECISION_FLOOR.

Usage:
    python -m jarvis_local_nn.training.calibrate
"""

import json
import sys

import numpy as np

from ..integration.local_router import get_router
from ..models.router import INTENTS
from .data import load_real_examples
from .evaluate import GOLDEN_PATH

PRECISION_FLOOR = float(
    __import__("os").getenv("JARVIS_LOCAL_CALIBRATE_PRECISION", "0.95")
)
MIN_SAMPLES = int(__import__("os").getenv("JARVIS_LOCAL_CALIBRATE_MIN_SAMPLES", "15"))


def _load_eval_cases() -> list[tuple[str, str]]:
    """[(text, intent)] from golden set + real labeled log data (deduped)."""
    cases: list[tuple[str, str]] = []
    seen = set()
    with open(GOLDEN_PATH) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            intent = entry.get("expected_intent")
            text = (entry.get("prompt") or "").strip()
            if intent in INTENTS and text and text not in seen:
                seen.add(text)
                cases.append((text, intent))
    for text, intent in load_real_examples():
        if text not in seen:
            seen.add(text)
            cases.append((text, intent))
    return cases


def calibrate(precision_floor: float = PRECISION_FLOOR) -> dict:
    """Return {intent: {"threshold": float|None, "precision": float, "recall": float}}."""
    router = get_router()
    if router is None:
        return {"error": "no weights"}

    cases = _load_eval_cases()
    preds = [router.predict(text) for text, _ in cases]
    labels = np.array([INTENTS.index(intent) for _, intent in cases])
    pred_idx = np.array([INTENTS.index(intent) for intent, _ in preds])
    confs = np.array([c for _, c in preds], dtype=np.float64)

    recommendations = {}
    for intent in INTENTS:
        i = INTENTS.index(intent)
        y = labels == i
        p = pred_idx == i
        n_true = int(y.sum())
        if n_true < MIN_SAMPLES:
            recommendations[intent] = {
                "threshold": None,
                "precision": None,
                "recall": None,
                "samples": n_true,
                "note": f"only {n_true} samples — keep global default",
            }
            continue
        best = None
        for t in np.arange(0.50, 1.00, 0.01):
            pos = p & (confs >= t)
            tp = int((pos & y).sum())
            fp = int((pos & ~y).sum())
            precision = tp / (tp + fp) if (tp + fp) else 0.0
            recall = tp / n_true if n_true else 0.0
            if precision >= precision_floor:
                best = {"threshold": round(float(t), 2), "precision": precision, "recall": recall}
                break
        if best is None:
            recommendations[intent] = {
                "threshold": None,
                "precision": 0.0,
                "recall": 0.0,
                "samples": n_true,
                "note": f"precision never reached {precision_floor:.2f} — keep global default",
            }
        else:
            recommendations[intent] = {"samples": n_true, **best}
    return {"total": len(cases), "recommendations": recommendations}


def main() -> int:
    summary = calibrate()
    if "error" in summary:
        print(f"Calibration failed: {summary['error']}")
        return 1
    print(f"Calibration over {summary['total']} examples "
          f"(precision floor >= {PRECISION_FLOOR:.2f}):\n")
    print(f"{'intent':12s} {'threshold':>10s} {'precision':>10s} {'recall':>8s}  note")
    for intent, rec in summary["recommendations"].items():
        t = f"{rec['threshold']:.2f}" if rec["threshold"] is not None else "-"
        p = f"{rec['precision']:.3f}" if rec.get("precision") is not None else "-"
        r = f"{rec['recall']:.3f}" if rec.get("recall") is not None else "-"
        note = rec.get("note", "n={}".format(rec["samples"]))
        print(f"{intent:12s} {t:>10s} {p:>10s} {r:>8s}  {note}")
    print("\nEnv vars to apply:")
    for intent, rec in summary["recommendations"].items():
        if rec["threshold"] is not None:
            print(f"  JARVIS_LOCAL_INTENT_CONFIDENCE_{intent.upper()}={rec['threshold']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
