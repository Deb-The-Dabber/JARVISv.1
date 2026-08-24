"""Coding-routing benchmark harness for Phase 2A.

Runs a fixed golden set through the REAL default routing path
(JARVIS_LLM_FIRST=1, local intent router enabled) and captures
routing-quality + latency + cost metrics. Used to produce a legitimate
BEFORE (policy off) / AFTER (policy on) baseline comparison with an
identical request set.

Usage:
    source venv/bin/activate && export PATH="$(pwd)/venv/bin:$PATH"
    python benchmarks/coding_routing_bench.py --tag before_2a
    python benchmarks/coding_routing_bench.py --tag after_2a [--limit N]

Output: benchmarks/results/<tag>.json + benchmarks/results/latest.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Setup BEFORE importing brain: eval-mode bypasses sandbox confirmations
# (eval_runner convention); TTS is silenced in-process so the bench never speaks.
os.environ.setdefault("JARVIS_EVAL_MODE", "1")
# MiniLM embedder init pings HF for updates (timeout-less SSL read can stall
# the whole run). Cache-only + no telemetry keeps embedding OUT of routing
# metrics and identical across runs.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

import signal  # noqa: E402

import tts  # noqa: E402

tts.speak = lambda *args, **kwargs: None  # noqa: E731 — bench has no mouth
tts.stop_speaking = lambda *args, **kwargs: None  # noqa: E731

import brain as brain_mod  # noqa: E402
from brain import classify_intent, get_last_tool_calls, process  # noqa: E402
from decision_log import get_decision_trace, get_request_id  # noqa: E402
from jarvis_logger import get_cost_summary  # noqa: E402

CHEAP_PROVIDERS = {"groq", "pollinations"}
RESULTS_DIR = ROOT / "benchmarks" / "results"

_COST_KEYS = ("tokens_input_total", "tokens_output_total", "cost_usd_total")


def _iso_to_epoch(ts: str) -> float | None:
    try:
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return None


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, int(0.95 * (len(s) - 1) + 0.5))
    return s[idx]


def _cost_delta(before: dict, after: dict) -> dict:
    return {k: round(after.get(k, 0) - before.get(k, 0), 6) for k in _COST_KEYS}


def load_cases(path: str) -> list[dict]:
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            if not case.get("prompt"):
                raise ValueError(f"case missing prompt: {line[:80]}")
            cases.append(case)
    if not cases:
        raise ValueError(f"no cases in {path}")
    return cases


def run_case(case: dict) -> dict:
    prompt = case["prompt"]
    cost_before = get_cost_summary()

    class _CaseTimeout(Exception):
        pass

    def _alarm(sig, frame):
        raise _CaseTimeout()

    old_handler = signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(max(90, int(case.get("max_latency", 180)) + 60))
    try:
        return _run_case_inner(case, prompt, cost_before)
    except _CaseTimeout:
        return {
            "prompt": prompt,
            "error": f"case watchdog: exceeded {case.get('max_latency', 180) + 60}s",
            "latency": case.get("max_latency", 180) + 60,
        }
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def _run_case_inner(case: dict, prompt: str, cost_before: dict) -> dict:
    t0 = time.time()
    try:
        intent = classify_intent(prompt)
    except Exception as e:
        return {"prompt": prompt, "error": f"classify_intent: {e}", "latency": time.time() - t0}
    intent_ms = round((time.time() - t0) * 1000, 1)

    classifier_path = None
    try:
        classifier_path = brain_mod.get_last_classifier_path()
    except Exception:
        pass
    fine_actual = None
    try:
        fine_actual = brain_mod.get_last_fine_intent()
    except Exception:
        pass

    t0_total = time.time()
    try:
        reply = process(prompt)
    except Exception as e:
        return {
            "prompt": prompt,
            "intent": intent,
            "intent_latency_ms": intent_ms,
            "error": f"process: {e}",
            "latency": time.time() - t0_total,
        }
    total_ms = round((time.time() - t0_total) * 1000, 1)

    request_id = get_request_id()
    trace = get_decision_trace(request_id)

    routing_ms = None
    attempted = []
    for ev in trace:
        decision = ev.get("decision", "")
        if "provider" in decision:
            ts = _iso_to_epoch(ev.get("timestamp", ""))
            if ts:
                routing_ms = round((ts - t0) * 1000, 1)
                break
        if decision.startswith("fallback_provider_"):
            attempted.append(ev.get("measurable_inputs", {}).get("provider"))

    final_provider = getattr(brain_mod, "_last_provider_used", "unknown")

    called_tools = []
    try:
        called_tools = get_last_tool_calls()
    except Exception:
        pass

    expected_tools = case.get("expected_tools", [])
    expected_keywords = case.get("expected_keywords", [])
    expected_intent = case.get("expected_intent", "")
    expected_class = case.get("expected_provider_class", "")

    tool_acc = 1.0
    if expected_tools:
        called_lower = {t.lower() for t in called_tools or []}
        tool_acc = sum(1 for t in expected_tools if t.lower() in called_lower) / len(expected_tools)

    kw_recall = 0.0
    if expected_keywords:
        kw_recall = sum(1 for kw in expected_keywords if kw.lower() in (reply or "").lower()) / len(
            expected_keywords
        )

    intent_acc = 1.0 if intent == expected_intent else 0.0

    class_match = None
    if expected_class and final_provider and final_provider != "unknown":
        if expected_class == "cheap":
            class_match = final_provider in CHEAP_PROVIDERS
        elif expected_class == "reasoning":
            class_match = final_provider not in CHEAP_PROVIDERS

    latency_ok = total_ms / 1000.0 <= case.get("max_latency", 180)
    passed = (
        intent_acc == 1.0
        and bool(reply)
        and latency_ok
        and "couldn" not in reply[:120].lower()
    )

    return {
        "prompt": prompt,
        "intent": intent,
        "expected_intent": expected_intent,
        "intent_accuracy": intent_acc,
        "fine_intent": case.get("expected_fine_intent", ""),
        "expected_provider_class": expected_class,
        "final_provider": final_provider,
        "provider_class_match": class_match,
        "tools_called": called_tools,
        "tool_accuracy": round(tool_acc, 3),
        "keyword_recall": round(kw_recall, 3),
        "intent_latency_ms": intent_ms,
        "routing_latency_ms": routing_ms,
        "total_latency_ms": total_ms,
        "max_latency_s": case.get("max_latency", 180),
        "latency_ok": latency_ok,
        "providers_attempted": attempted,
        "fallback_count": max(0, len(set(attempted)) - 1),
        "cost": _cost_delta(cost_before, get_cost_summary()),
        "passed": passed,
        "reply_preview": (reply or "")[:160],
        "request_id": request_id,
        "classifier_path": (classifier_path or {}).get("path"),
        "classifier_confidence": (classifier_path or {}).get("confidence"),
        "classifier_raw": (classifier_path or {}).get("raw"),
        "fine_intent_actual": (fine_actual or (None, None))[0],
        "fine_confidence_actual": (fine_actual or (None, None))[1],
    }


def _spawn_case(case: dict, index: int, set_path: str, isolation: dict) -> dict:
    """Run one case in a subprocess with a hard wall-clock kill.

    The routing path can block inside C-level TLS reads that skip SDK
    timeouts (observed: NVIDIA NIM endpoint stalls), so a hung case MUST
    die without taking the whole suite down. Subprocess startup (~20s:
    MiniLM + vector memory + router weights) is identical for every case
    and for both BEFORE/AFTER runs.

    isolation: env additions (health snapshot, fresh gemini usage) that
    keep the suite deterministic and off the live ~/.jarvis state.
    """
    timeout_s = int(case.get("max_latency", 180)) + 90
    env = os.environ.copy()
    env.update(isolation)
    env["JARVIS_BENCH_CASE"] = str(index)
    env["JARVIS_BENCH_SET"] = set_path
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "benchmarks" / "coding_routing_bench.py"), "--one"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            cwd=str(ROOT),
        )
        if proc.returncode != 0:
            return {
                "prompt": case["prompt"],
                "error": f"case subprocess exit {proc.returncode}: {proc.stderr[-400:]}",
                "latency": timeout_s,
            }
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except subprocess.TimeoutExpired:
        return {
            "prompt": case["prompt"],
            "error": f"case killed after {timeout_s}s (provider stall)",
            "latency": timeout_s,
        }
    except Exception as e:
        return {"prompt": case["prompt"], "error": f"subprocess wrapper: {e}", "latency": timeout_s}


def _make_isolation(health_seed: str | None, name: str) -> dict:
    """Return env additions that isolate a suite run from live ~/.jarvis state.

    health_seed: path to a static provider-health JSON (same file for every
    case -> no cross-case poisoning, no clobbering of the live file).
    Fresh per-suite gemini usage counter (the daily cap is daily-life, not
    a routing property; a mid-suite cap hit would skew AFTER vs BEFORE).
    """
    iso: dict = {}
    if health_seed and Path(health_seed).exists():
        iso["JARVIS_PROVIDER_HEALTH_FILE"] = str(Path(health_seed).resolve())
    usage = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "count": 0,
    }
    usage_path = RESULTS_DIR / f"gemini_usage_{name}.json"
    usage_path.write_text(json.dumps(usage))
    iso["JARVIS_GEMINI_USAGE_FILE"] = str(usage_path.resolve())
    return iso


def run_suite(cases: list[dict], tag: str, health_seed: str | None = None) -> dict:
    isolation = _make_isolation(health_seed, tag)
    results = []
    for i, case in enumerate(cases, 1):
        print(f"[{tag}] case {i}/{len(cases)}: {case['prompt'][:60]}...", flush=True)
        r = _spawn_case(case, i - 1, str(ROOT / "tests" / "eval" / "routing_golden.jsonl"), isolation)
        results.append(r)
        cases_dir = RESULTS_DIR / "cases"
        cases_dir.mkdir(parents=True, exist_ok=True)
        (cases_dir / f"{tag}_{i:02d}.json").write_text(
            json.dumps({"case": case, "result": r}, indent=2, default=str)
        )
        status = "PASS" if r.get("passed") else "FAIL/ERR"
        print(
            f"    -> {status} intent={r.get('intent')} provider={r.get('final_provider')} "
            f"total={r.get('total_latency_ms')}ms cost=${r.get('cost', {}).get('cost_usd_total', 0)}",
            flush=True,
        )

    ok = [r for r in results if not r.get("error")]
    totals = [
        r.get("total_latency_ms", 0) for r in ok
    ]
    intents = [r.get("intent_latency_ms", 0) for r in ok]
    routings = [r.get("routing_latency_ms") for r in ok if r.get("routing_latency_ms") is not None]
    costs = [r.get("cost", {}).get("cost_usd_total", 0) for r in ok]
    fallbacks = sum(1 for r in ok if (r.get("fallback_count") or 0) > 0)

    report = {
        "tag": tag,
        "timestamp": datetime.now().isoformat(),
        "env": {
            "JARVIS_ROUTER_POLICY": os.getenv("JARVIS_ROUTER_POLICY", "0"),
            "JARVIS_ROUTER_CHEAP": os.getenv("JARVIS_ROUTER_CHEAP", "0"),
            "JARVIS_LLM_FIRST": os.getenv("JARVIS_LLM_FIRST", "1"),
            "health_seed": os.getenv("JARVIS_BENCH_HEALTH_SEED", ""),
            "gemini_usage_isolated": "1",
        },
        "total": len(results),
        "errors": [r.get("error") for r in results if r.get("error")],
        "passed": sum(1 for r in ok if r.get("passed")),
        "pass_rate": round(sum(1 for r in ok if r.get("passed")) / max(len(ok), 1), 3),
        "intent_accuracy": round(
            sum(r.get("intent_accuracy", 0) for r in ok) / max(len(ok), 1), 3
        ),
        "avg_intent_latency_ms": round(statistics.mean(intents), 1) if intents else 0,
        "avg_routing_latency_ms": round(statistics.mean(routings), 1) if routings else None,
        "avg_total_latency_ms": round(statistics.mean(totals), 1) if totals else 0,
        "p95_total_latency_ms": round(_p95(totals), 1) if totals else 0,
        "avg_cost_usd": round(statistics.mean(costs), 6) if costs else 0,
        "cost_usd_total": round(sum(costs), 6),
        "tokens_input_total": sum(r.get("cost", {}).get("tokens_input_total", 0) for r in ok),
        "tokens_output_total": sum(r.get("cost", {}).get("tokens_output_total", 0) for r in ok),
        "fallback_rate": round(fallbacks / max(len(ok), 1), 3),
        "provider_class_match_rate": round(
            sum(
                1
                for r in ok
                if r.get("expected_provider_class") and r.get("provider_class_match") is True
            )
            / max(sum(1 for r in ok if r.get("expected_provider_class")), 1),
            3,
        ),
        "results": results,
    }
    _save(report, tag)
    _print_table(report)
    return report


def _save(report: dict, tag: str) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{tag}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    with open(RESULTS_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nSaved: {path}")


def _print_table(report: dict) -> None:
    print("\n=== routing bench report ===")
    print(
        f"pass_rate={report['pass_rate']}  intent_acc={report['intent_accuracy']}  "
        f"class_match={report['provider_class_match_rate']}  fallback_rate={report['fallback_rate']}"
    )
    print(
        f"avg intent latency={report['avg_intent_latency_ms']}ms  "
        f"avg routing latency={report['avg_routing_latency_ms']}ms  "
        f"avg total={report['avg_total_latency_ms']}ms  p95 total={report['p95_total_latency_ms']}ms"
    )
    print(
        f"cost total=${report['cost_usd_total']}  avg/req=${report['avg_cost_usd']}  "
        f"tokens in={report['tokens_input_total']} out={report['tokens_output_total']}"
    )
    hdr = f"{'prompt':<46} {'intent':<10} {'provider':<18} {'total ms':>9} {'$':>7} {'pass':<5}"
    print(hdr)
    for r in report["results"]:
        if r.get("error"):
            print(f"{r['prompt'][:44]:<46} ERROR: {r['error'][:60]}")
            continue
        print(
            f"{r['prompt'][:44]:<46} {r['intent']:<10} {str(r['final_provider'])[:18]:<18} "
            f"{r['total_latency_ms']:>9} {r['cost']['cost_usd_total']:>7.4f} "
            f"{'PASS' if r['passed'] else 'FAIL'}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="Coding routing benchmark (Phase 2A)")
    ap.add_argument("--set", default=str(ROOT / "tests/eval/routing_golden.jsonl"))
    ap.add_argument("--tag", default="run")
    ap.add_argument("--limit", type=int, default=0, help="run only first N cases (0 = all)")
    ap.add_argument(
        "--health",
        default="",
        help="static provider-health JSON used for every case (suite isolation)",
    )
    ap.add_argument("--one", action="store_true", help="internal: run single case from env, print JSON")
    args = ap.parse_args()

    cases = load_cases(args.set)
    if args.one:
        index = int(os.environ.get("JARVIS_BENCH_CASE", "0"))
        case = cases[index]
        print(json.dumps(run_case(case), default=str))
        sys.exit(0)

    if args.limit > 0:
        cases = cases[: args.limit]
    print(f"Loaded {len(cases)} cases from {args.set}")
    os.environ["JARVIS_BENCH_HEALTH_SEED"] = args.health
    report = run_suite(cases, args.tag, health_seed=args.health or None)
    sys.exit(0 if report["errors"] == [] else 2)


if __name__ == "__main__":
    main()
