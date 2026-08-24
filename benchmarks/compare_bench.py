"""Compare BEFORE/AFTER coding-routing benchmark results (Phase 2A).

Usage: python benchmarks/compare_bench.py before_2a after_2a
Prints the full metric table expected in the Phase 2A report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "benchmarks" / "results"

_METRICS = [
    ("pass_rate", "{:.3f}", "higher better"),
    ("intent_accuracy", "{:.3f}", "higher better"),
    ("provider_class_match_rate", "{:.3f}", "higher better"),
    ("fallback_rate", "{:.3f}", "lower better"),
    ("avg_intent_latency_ms", "{:.1f}", "lower better"),
    ("avg_routing_latency_ms", "{:.1f}", "lower better"),
    ("avg_total_latency_ms", "{:.1f}", "lower better"),
    ("p95_total_latency_ms", "{:.1f}", "lower better"),
    ("avg_cost_usd", "{:.6f}", "lower better"),
    ("cost_usd_total", "{:.6f}", "lower better"),
    ("tokens_input_total", "{:.0f}", "lower better"),
    ("tokens_output_total", "{:.0f}", "lower better"),
]


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare two Phase 2A bench reports")
    ap.add_argument("before", help="tag of BEFORE run (e.g. before_2a)")
    ap.add_argument("after", help="tag of AFTER run (e.g. after_2a)")
    args = ap.parse_args()

    def load(tag: str) -> dict:
        path = RESULTS_DIR / f"{tag}.json"
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            sys.exit(1)
        return json.loads(path.read_text())

    b, a = load(args.before), load(args.after)
    print(f"{'metric':<28} {'before':>14} {'after':>14} {'delta':>12}")
    print("-" * 72)
    for key, fmt, note in _METRICS:
        bv = b.get(key)
        av = a.get(key)
        if bv is None or av is None:
            continue
        delta = av - bv if isinstance(bv, (int, float)) and isinstance(av, (int, float)) else "n/a"
        delta_s = fmt.format(delta)
        if isinstance(delta, (int, float)):
            delta_s = f"{'+' if delta >= 0 else ''}{delta_s}"
        print(f"{key:<28} {fmt.format(bv):>14} {fmt.format(av):>14} {delta_s:>12}  {note}")
    print("-" * 72)
    print(f"errors before={len(b.get('errors', []))} after={len(a.get('errors', []))}")
    print(f"env before={b.get('env')} after={a.get('env')}")


if __name__ == "__main__":
    main()
