"""2B.2 gate calibration — offline sweep over the routing golden set.

Replays the 30 golden cases through the local_nn two-stage router WITHOUT
any cloud calls and evaluates, per intent, how candidate confidence
thresholds trade accepted-correct vs accepted-incorrect vs escalation.

Requirements: JARVIS must have its normal .env (embeddings cache, NN
weights). No API keys are consumed. Determinstic: the NN predictors are
stateless per call.

Usage:
    python benchmarks/classifier_gate_calibrate.py

Writes benchmarks/results/gate_calibration.json and prints the sweep table.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "benchmarks" / "results"

sys.path.insert(0, str(ROOT))
import brain  # noqa: E402

INTENTS = ("chat", "coding", "tool_use", "reasoning", "self_mod")
GRID = (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.92, 0.95, 0.97)
INCORRECT_PENALTY = 2.0


def load_cases() -> list[dict]:
    rows = []
    for line in (ROOT / "tests" / "eval" / "routing_golden.jsonl").read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def main() -> None:
    cases = load_cases()
    per_case = []
    for case in cases:
        text = case["prompt"]
        coarse, conf = brain._local_intent_predict(text)
        fine, fine_conf = None, None
        if coarse is not None:
            fine, fine_conf = brain._local_fine_predict(text, coarse)
        per_case.append(
            {
                "prompt": text,
                "expected": case.get("expected_intent", ""),
                "coarse": coarse,
                "coarse_conf": round(conf, 4) if conf is not None else None,
                "fine": fine,
                "fine_conf": round(fine_conf, 4) if fine_conf is not None else None,
                "fine_withheld_by_gate": fine is None and coarse is not None,
                "golden_fine": case.get("expected_fine_intent", ""),
            }
        )

    print(f"{'T':>5} | {'accept':>6} {'corr':>5} {'incor':>5} {'escal':>5} | {'score':>6}")
    sweep = {}
    best: dict[str, tuple[float, float, float]] = {}
    for intent in INTENTS:
        rows = [r for r in per_case if r["coarse"] == intent]
        if not rows:
            continue
        sweep[intent] = {}
        best_score, best_t = -1e9, None
        for t in GRID:
            accepted = [r for r in rows if r["coarse_conf"] is not None and r["coarse_conf"] >= t]
            correct = sum(1 for r in accepted if r["coarse"] == r["expected"])
            incorrect = len(accepted) - correct
            escalated = len(rows) - len(accepted)
            score = correct - INCORRECT_PENALTY * incorrect
            sweep[intent][t] = {
                "accepted": len(accepted),
                "correct": correct,
                "incorrect": incorrect,
                "escalated": escalated,
            }
            if score > best_score:
                best_score, best_t = score, t
        best[intent] = (best_t, best_score, len(rows))
    for intent in INTENTS:
        if intent not in sweep:
            continue
        print(f"\n== intent={intent} (n={len([r for r in per_case if r['coarse'] == intent])})")
        for t, d in sweep[intent].items():
            mark = " <-- max score" if t == best[intent][0] else ""
            print(
                f"{t:>5} | {d['accepted']:>6} {d['correct']:>5} {d['incorrect']:>5} "
                f"{d['escalated']:>5} | {d['correct'] - INCORRECT_PENALTY * d['incorrect']:>6.1f}{mark}"
            )
        print(f"   BEST: threshold={best[intent][0]} score={best[intent][1]:.1f} n={best[intent][2]}")

    results_dir = RESULTS_DIR
    results_dir.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "gate_calibration.json").write_text(
        json.dumps(
            {
                "per_case": per_case,
                "sweep": sweep,
                "best_per_intent": {k: {"threshold": v[0], "score": v[1], "n": v[2]} for k, v in best.items()},
            },
            indent=2,
            default=str,
        )
    )
    withheld = sum(1 for r in per_case if r["fine_withheld_by_gate"])
    print(f"\n{cases.__len__()} cases; fine withheld by gate in {withheld} ({withheld / len(per_case):.0%})")


results_dir = Path(str(RESULTS_DIR))
if __name__ == "__main__":
    main()
