"""Evaluate the local intent router against the golden eval set (no API required).

Usage:
    python -m jarvis_local_nn.training.evaluate
"""

import json
import sys
from pathlib import Path

from ..integration.local_router import get_router

GOLDEN_PATH = Path(__file__).resolve().parent.parent.parent / "tests" / "eval" / "golden_set.jsonl"


def evaluate(golden_path: Path = GOLDEN_PATH) -> dict:
    router = get_router()
    if router is None:
        print("Router weights unavailable — train first (python -m jarvis_local_nn.training.train)")
        return {"error": "no weights"}

    cases = []
    with open(golden_path) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("expected_intent"):
                cases.append(entry)

    results = []
    for case in cases:
        prompt = case["prompt"]
        expected = case["expected_intent"]
        intent, conf = router.predict(prompt)
        correct = intent == expected
        fine_expected = case.get("expected_fine")
        fine_pred = None
        fine_conf = 0.0
        fine_correct = None
        if fine_expected:
            from ..integration.specialist_router import predict_fine_gated

            fine_pred, fine_conf = predict_fine_gated(expected, prompt)
            fine_correct = fine_pred == fine_expected
        results.append(
            {
                "prompt": prompt,
                "expected": expected,
                "predicted": intent,
                "confidence": round(conf, 3),
                "correct": correct,
                "fine_expected": fine_expected,
                "fine_predicted": fine_pred,
                "fine_confidence": round(fine_conf, 3),
                "fine_correct": fine_correct,
            }
        )

    n = len(results)
    correct = sum(1 for r in results if r["correct"])
    by_intent = {}
    for r in results:
        bucket = by_intent.setdefault(r["expected"], {"n": 0, "correct": 0, "confidences": []})
        bucket["n"] += 1
        bucket["correct"] += 1 if r["correct"] else 0
        bucket["confidences"].append(r["confidence"])

    fine_cases = [r for r in results if r["fine_correct"] is not None]
    n_fine = len(fine_cases)
    fine_correct = sum(1 for r in fine_cases if r["fine_correct"])
    fine_withheld = sum(
        1 for r in fine_cases if r["fine_predicted"] is None and r["fine_expected"]
    )

    summary = {
        "total": n,
        "correct": correct,
        "accuracy": round(correct / n, 3) if n else 0.0,
        "fine_total": n_fine,
        "fine_correct": fine_correct,
        "fine_accuracy": round(fine_correct / n_fine, 3) if n_fine else 0.0,
        "fine_withheld": fine_withheld,
        "by_intent": {
            intent: {"n": v["n"], "correct": v["correct"], "acc": round(v["correct"] / v["n"], 3)}
            for intent, v in sorted(by_intent.items())
        },
        "results": results,
    }
    return summary


def main():
    summary = evaluate()
    if "error" in summary:
        sys.exit(1)
    print(f"Golden-set intent accuracy (local NN): {summary['accuracy']:.1%} ({summary['correct']}/{summary['total']})")
    for intent, stats in summary["by_intent"].items():
        print(f"  {intent:12s}: {stats['acc']:.1%} ({stats['correct']}/{stats['n']})")
    if summary["fine_total"]:
        print(
            f"Fine-grained accuracy (two-stage): {summary['fine_accuracy']:.1%} "
            f"({summary['fine_correct']}/{summary['fine_total']}, "
            f"{summary['fine_withheld']} withheld by gate)"
        )
    print("\nMismatches:")
    for r in summary["results"]:
        if not r["correct"]:
            prompt = r["prompt"][:42]
            print(
                f"  {prompt!r:45s} expected={r['expected']:10s} got={r['predicted']:10s} conf={r['confidence']:.2f}"
            )
        elif r["fine_correct"] is False:
            prompt = r["prompt"][:42]
            print(
                f"  {prompt!r:45s} fine expected={r['fine_expected']:10s} "
                f"got={r['fine_predicted']} conf={r['fine_confidence']:.2f}"
            )
        elif r["fine_expected"] and r["fine_predicted"] is None:
            prompt = r["prompt"][:42]
            print(f"  {prompt!r:45s} fine withheld (conf {r['fine_confidence']:.2f} < gate)")


if __name__ == "__main__":
    main()
