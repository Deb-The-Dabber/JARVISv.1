"""2B.3 report helper — E (frozen B + cheap) vs frozen B comparison table.

Reads benchmarks/results/gate_bench_B.json (frozen at e923422) and
benchmarks/results/gate_bench_E.json (config E run). Prints a side-by-side
table plus per-case route deltas. Pure offline, no API.
"""
import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "benchmarks" / "results"

KEYS = [
    ("accuracy", "accuracy"),
    ("correct", "correct"),
    ("incorrect", "incorrect"),
    ("routed_without_llm", "routed w/o LLM"),
    ("local_nn_accepted", "local_nn accepts"),
    ("cheap_routed", "cheap accepts"),
    ("local_nn_incorrect_accepts", "wrong accepts"),
    ("escalations", "escalations"),
    ("llm_classify_calls_saved", "LLM calls saved"),
    ("cheap_calls", "cheap calls"),
    ("cheap_errors", "cheap errors"),
    ("mean_latency_ms", "mean latency ms"),
]


def main() -> Path:
    b = json.loads((RESULTS / "gate_bench_B.json").read_text())
    e = json.loads((RESULTS / "gate_bench_E.json").read_text())
    print(f"{'metric':<24}{'B (frozen)':>14}{'E (cheap)':>14}")
    print("-" * 52)
    for key, label in KEYS:
        print(f"{label:<24}{b.get(key, '-'):>14}{e.get(key, '-'):>14}")

    b_cases = {r["prompt"]: r for r in b["per_case"]}
    print("\nper-case route delta (B -> E):")
    for r in e["per_case"]:
        p = r["prompt"]
        bpath = b_cases.get(p, {}).get("path")
        if bpath != r["path"]:
            print(f"  {r['path']:12s} (was {bpath:12s}) got={r['got']} exp={r['expected']}  {p[:44]}")
    return RESULTS / "gate_bench_E.json"


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
