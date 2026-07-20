#!/usr/bin/env python3
"""Run evaluation suite and exit non-zero on regression.

Usage:
    source venv/bin/activate
    python scripts/run_eval.py                 # full eval (requires API keys)
    python scripts/run_eval.py --no-api         # intent-only (no API calls)
    python scripts/run_eval.py --verbose        # show per-case results
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from eval_runner import is_regression, run_eval_suite


def main():
    parser = argparse.ArgumentParser(description="Run Jarvis evaluation suite")
    parser.add_argument("--no-api", action="store_true", help="Skip cases requiring API calls")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-case results")
    args = parser.parse_args()

    print("=" * 56)
    print("  Jarvis Evaluation Suite")
    print("=" * 56)

    report = run_eval_suite(require_no_api=args.no_api)

    if "error" in report:
        print(f"\n  Error: {report['error']}")
        sys.exit(1)

    total = report["total"]
    passed = report["passed"]
    failed = report["failed"]
    skipped = report["skipped"]

    print(f"\n  Total cases: {total}")
    print(f"  Passed:      {passed}")
    print(f"  Failed:      {failed}")
    print(f"  Skipped:     {skipped}")
    print(f"  Pass rate:   {report['pass_rate']:.1%}")
    print(f"  Intent acc:  {report['avg_intent_accuracy']:.1%}")
    print(f"  Tool acc:    {report['avg_tool_accuracy']:.1%}")
    print(f"  Keyword rec: {report['avg_keyword_recall']:.1%}")
    print(f"  Avg latency: {report['avg_latency_seconds']:.2f}s")

    if args.verbose:
        print("\n  --- Per-case results ---")
        for r in report.get("results", []):
            status = "PASS" if r.get("passed") else "SKIP" if r.get("skipped") else "FAIL"
            prompt_short = r.get("prompt", "")[:50]
            print(f"  [{status}] {prompt_short}")

    if failed > 0:
        print(f"\n  FAIL: {failed} case(s) failed regression threshold.")
        sys.exit(1)

    regression = is_regression()
    if regression:
        print("\n  FAIL: Regression detected compared to previous run.")
        sys.exit(1)

    print("\n  OK: All checks passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
