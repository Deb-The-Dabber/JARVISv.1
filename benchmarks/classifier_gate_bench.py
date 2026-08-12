"""2B.2 gate evaluation — replay the golden intent set under 4 gate configs.

Evaluates the local_nn classifier + escalation under:
  A baseline            (stock thresholds from .env, no gates)
  B confidence          (calibrated per-intent thresholds from gate_calibration.json)
  C agreement           (coarse confident + specialist withheld -> escalate)
  D confidence + agreement

Runs classify_intent ONLY (no tool execution, no process()) — measures the
routing decision layer. Escalated cases fall through to the Nemotron
classify round-trip (replaced by keyword fallback when unavailable).

Each config runs in a FRESH subprocess so import-time env (per-intent
thresholds, gates) applies correctly and no intent cache leaks between
configs. --config NAME runs one config in-process (child mode); default
runs all four as children.

Usage:
    python benchmarks/classifier_gate_bench.py            # all four
    python benchmarks/classifier_gate_bench.py --config C # one config

Writes benchmarks/results/gate_bench_{config}.json per config plus
benchmarks/results/gate_bench_summary.json (parent mode).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "benchmarks" / "results"

CONFIGS: dict[str, dict[str, str]] = {
    "A": {},
    "B": {
        "JARVIS_LOCAL_INTENT_CONFIDENCE_CHAT": "0.92",
        "JARVIS_LOCAL_INTENT_CONFIDENCE_TOOL_USE": "0.92",
        "JARVIS_LOCAL_INTENT_CONFIDENCE_CODING": "0.5",
    },
    "C": {
        "JARVIS_LOCAL_AGREEMENT_GATE": "1",
    },
    "D": {
        "JARVIS_LOCAL_INTENT_CONFIDENCE_CHAT": "0.92",
        "JARVIS_LOCAL_INTENT_CONFIDENCE_TOOL_USE": "0.92",
        "JARVIS_LOCAL_INTENT_CONFIDENCE_CODING": "0.5",
        "JARVIS_LOCAL_AGREEMENT_GATE": "1",
    },
}


def load_cases() -> list[dict]:
    rows = []
    for line in (ROOT / "tests" / "eval" / "routing_golden.jsonl").read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def run_config(name: str, cases: list[dict]) -> dict:
    sys.path.insert(0, str(ROOT))
    from brain import (  # noqa: E402
        _clear_fine_intent,
        classify_intent,
        conversation_context,
        get_last_classifier_path,
        get_last_fine_intent,
    )

    per_case = []
    for case in cases:
        text = case["prompt"]
        expected = case.get("expected_intent", "")
        conversation_context.intent_cache.clear()
        _clear_fine_intent()
        row = {"prompt": text, "expected": expected}
        try:
            got = classify_intent(text)
            cp = get_last_classifier_path() or {}
            row.update(
                {
                    "got": got,
                    "path": cp.get("path"),
                    "confidence": cp.get("confidence"),
                    "raw": cp.get("raw"),
                    "fine_actual": (get_last_fine_intent() or (None, None))[0],
                    "correct": got == expected,
                }
            )
        except Exception as e:
            row.update({"got": None, "path": "error", "error": f"{type(e).__name__}: {e}", "correct": False})
        per_case.append(row)

    ok = [r for r in per_case if r.get("path") != "error"]
    accepts = [r for r in ok if r.get("path") == "local_nn"]
    escalations = [r for r in ok if r.get("path") != "local_nn"]
    wrong_accepts = [r for r in accepts if not r["correct"]]
    total = len(per_case)
    correct = sum(1 for r in ok if r["correct"])
    summary = {
        "config": name,
        "env": CONFIGS.get(name, {}),
        "total_cases": total,
        "errors": total - len(ok),
        "error_rows": [r for r in per_case if r.get("path") == "error"],
        "correct": correct,
        "incorrect": len(ok) - correct,
        "accuracy": round(correct / total, 4) if total else 0,
        "local_nn_accepted": len(accepts),
        "local_nn_correct_accepts": len(accepts) - len(wrong_accepts),
        "local_nn_incorrect_accepts": len(wrong_accepts),
        "escalations": len(escalations),
        "escalation_rate": round(len(escalations) / total, 4) if total else 0,
        "llm_classify_calls_saved": len(accepts),
        "escalation_paths": {
            p: sum(1 for r in escalations if r.get("path") == p)
            for p in sorted({r.get("path") for r in escalations if r.get("path")})
        },
        "per_case": per_case,
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"gate_bench_{name}.json").write_text(json.dumps(summary, indent=2, default=str))
    return summary


def run_all(cases: list[dict]) -> None:
    summaries = []
    for name in sorted(CONFIGS):
        env = os.environ.copy()
        env["JARVIS_LLM_FIRST"] = "1"
        env["JARVIS_ROUTER_CHEAP"] = "0"
        env["JARVIS_ROUTER_POLICY"] = "0"
        env.update(CONFIGS[name])
        print(f"=== config {name}: env={CONFIGS[name]}", flush=True)
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--config", name],
            capture_output=True,
            text=True,
            timeout=1800,
            env=env,
            cwd=str(ROOT),
        )
        if proc.returncode != 0:
            print(f"    FAILED exit={proc.returncode}: {proc.stderr[-300:]}", flush=True)
            continue
        line = proc.stdout.strip().splitlines()[-1]
        print(f"    {line}", flush=True)
        summary_file = RESULTS_DIR / f"gate_bench_{name}.json"
        if summary_file.exists():
            summaries.append(json.loads(summary_file.read_text()))
    if summaries:
        (RESULTS_DIR / "gate_bench_summary.json").write_text(json.dumps(summaries, indent=2, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", choices=sorted(CONFIGS))
    args = ap.parse_args()
    cases = load_cases()
    if args.config:
        s = run_config(args.config, cases)
        print(
            f"total={s['total_cases']} correct={s['correct']} incorrect={s['incorrect']} "
            f"acc={s['accuracy']} accepts={s['local_nn_accepted']} "
            f"wrong_accepts={s['local_nn_incorrect_accepts']} escalations={s['escalations']} "
            f"saved={s['llm_classify_calls_saved']}"
        )
    else:
        run_all(cases)


if __name__ == "__main__":
    main()
