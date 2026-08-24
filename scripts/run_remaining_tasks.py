#!/usr/bin/env python3
"""Run only the remaining phase1 baseline task(s) and merge with a completed
partial run, producing a full report JSON.

Usage:
  venv/bin/python scripts/run_remaining_tasks.py /tmp/baseline_A4.log ambiguous
"""

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decision_log import clear_request_id, get_decision_trace, new_request_id
from eval_runner import EVAL_RUNS_DIR, run_eval_case
from scripts.run_phase1_baseline import evaluate_pass_condition, load_phase1_baseline

TARGET = sys.argv[2] if len(sys.argv) > 2 else "ambiguous"
PARTIAL_LOG = sys.argv[1] if len(sys.argv) > 1 else "/tmp/baseline_A4.log"


def parse_partial(log_path: str) -> dict:
    """Parse per-task results from a partial run log."""
    results = []
    lines = open(log_path).read().splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"\s*\[(\d+)/10\] (\w+): (.*)\.\.\.", lines[i])
        if m:
            num = int(m.group(1))
            category = m.group(2)
            prompt = m.group(3)
            # next PASS/FAIL line
            j = i + 1
            status_line = None
            while j < len(lines):
                if re.match(r"\s*(PASS|FAIL) \(", lines[j]):
                    status_line = lines[j]
                    break
                j += 1
            entry = {"num": num, "category": category, "prompt": prompt[:60]}
            if status_line:
                m2 = re.match(
                    r"\s*(PASS|FAIL) \(([^)]*)\) - ([\d.]+)s - trace: (\d+) events",
                    status_line,
                )
                if m2:
                    entry["status"] = m2.group(1)
                    entry["condition_detail"] = m2.group(2)
                    entry["latency"] = float(m2.group(3))
                    entry["trace_events"] = int(m2.group(4))
                    if "tools=" in entry["condition_detail"]:
                        tm = re.search(r"tools=\[([^\]]*)\]", entry["condition_detail"])
                        if tm and tm.group(1).strip():
                            entry["tools_called"] = [t.strip().strip("'\"") for t in tm.group(1).split(",")]
                        else:
                            entry["tools_called"] = []
            results.append(entry)
        i += 1
    return {"results": [r for r in results if r.get("status")]}


def main():
    partial = parse_partial(PARTIAL_LOG)
    cases = load_phase1_baseline()
    results = partial["results"]
    done_categories = {r["category"] for r in results}

    print(f"Parsed {len(results)} completed tasks from {PARTIAL_LOG}")
    print(f"Running remaining: {[c['category'] for c in cases if c['category'] not in done_categories]}")

    for case in cases:
        if case["category"] in done_categories:
            continue
        if case["category"] != TARGET:
            continue
        print(f"\nRunning [{case['category']}]: {case['prompt'][:60]}...")
        clear_request_id()
        new_request_id()
        start = time.time()
        result = run_eval_case(case)
        elapsed = time.time() - start
        passed, detail = evaluate_pass_condition(case, result)
        request_id = result.get("request_id", "")
        trace = get_decision_trace(request_id) if request_id else []
        entry = {
            "num": len(results) + 1,
            "category": case["category"],
            "prompt": case["prompt"][:60],
            "status": "PASS" if passed else "FAIL",
            "condition_detail": detail,
            "latency": round(elapsed, 2),
            "trace_events": len(trace),
            "tools_called": result.get("tools_called", []),
            "reply_preview": (result.get("reply_preview") or "")[:200],
            "error": result.get("error", ""),
        }
        results.append(entry)
        print(f"    {entry['status']} ({detail}) - {elapsed:.2f}s - trace: {len(trace)} events")

    results.sort(key=lambda r: r.get("num", 99))
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "PASS")
    report = {
        "timestamp": time.time(),
        "phase": 1,
        "source": f"merged: {os.path.basename(PARTIAL_LOG)} + remaining",
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 3) if total else 0,
        "avg_latency_seconds": round(sum(r.get("latency", 0) for r in results) / total, 3) if total else 0,
        "results": results,
    }
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(EVAL_RUNS_DIR, f"phase1_baseline_{ts}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    latest = os.path.join(EVAL_RUNS_DIR, "phase1_baseline_latest.json")
    with open(latest, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nSaved: {path}")
    print(f"Pass rate: {passed}/{total} ({report['pass_rate'] * 100:.0f}%)")


if __name__ == "__main__":
    main()
