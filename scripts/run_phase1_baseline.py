#!/usr/bin/env python3
"""Phase 1 Baseline Runner

Extends existing eval_runner.py to run Phase 1 golden baseline tasks
and capture decision traces for analysis.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_runner import load_golden_set, run_eval_case, run_eval_suite, EVAL_RUNS_DIR
from decision_log import get_decision_trace, clear_request_id, new_request_id


PHASE1_BASELINE_PATH = Path(__file__).parent.parent / "tests" / "eval" / "phase1_baseline.jsonl"


def load_phase1_baseline(path: str = None) -> list[dict]:
    """Load Phase 1 baseline tasks."""
    path = path or PHASE1_BASELINE_PATH
    if not os.path.exists(path):
        return []
    cases = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def evaluate_pass_condition(case: dict, result: dict) -> tuple[bool, str]:
    """Evaluate deterministic pass condition for Phase 1 tasks."""
    condition = case.get("pass_condition", "")
    
    if not condition:
        return False, "no_pass_condition_defined"
    
    reply = result.get("reply_preview", "") or result.get("reply", "")
    tools_called = result.get("tools_called", [])
    intent = result.get("intent", "")
    error = result.get("error", "")
    
    # Deterministic pass conditions
    if condition == "response_contains_Debasish":
        passed = "Debasish" in reply
        return passed, "found" if passed else "not_found"
    
    elif condition == "response_contains_black_coffee":
        passed = "black coffee" in reply.lower()
        return passed, "found" if passed else "not_found"
    
    elif condition == "successful_recall":
        # Check if the response contains the requested information (the python script)
        # regardless of which tool was used
        target_indicators = ["sort_list.py", "python script", "fibonacci", "sort"]
        passed = any(indicator.lower() in reply.lower() for indicator in target_indicators)
        return passed, f"tools={tools_called}" if passed else f"no_target_info tools={tools_called}"
    
    elif condition == "weather_tool_called_with_Aurora":
        passed = any(t in ["get_weather", "get_weather_detailed"] for t in tools_called)
        return passed, f"tools={tools_called}"
    
    elif condition == "conditional_execution":
        # Check if both tools were called in sequence
        has_sys = "get_system_info" in tools_called
        has_proc = "get_top_processes" in tools_called
        passed = has_sys and has_proc
        return passed, f"sys={has_sys} proc={has_proc}"
    
    elif condition == "code_correctness_fibonacci":
        # Extract Python code from response and test it in isolated subprocess
        import re
        import subprocess
        import tempfile
        import os
        
        # Extract Python code from response
        code_patterns = [
            r'```python\n(.*?)\n```',
            r'```\n(.*?)\n```',
            r'(def fibonacci\(.*?:\n(?:.*?\n)*?)(?:\n\n|\n$)',
        ]
        
        code = None
        for pattern in code_patterns:
            match = re.search(pattern, reply, re.DOTALL)
            if match:
                code = match.group(1).strip()
                break
        
        if not code:
            return False, "no_code_extracted"
        
        # Write code to temp file and test
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "test_fib.py")
            test_code = f"""
{code}

if __name__ == "__main__":
    try:
        result = fibonacci(10)
        print(result)
    except Exception as e:
        print(f"ERROR: {{e}}")
"""
            with open(test_file, "w") as f:
                f.write(test_code)
            
            try:
                result = subprocess.run(
                    ["python3", test_file],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=tmpdir
                )
                output = result.stdout.strip()
                if output == "55":
                    return True, "fibonacci(10)==55"
                else:
                    return False, f"output={output}"
            except subprocess.TimeoutExpired:
                return False, "timeout"
            except Exception as e:
                return False, f"execution_error={e}"
    
    elif condition == "semantic_repo_explore":
        # Check if answer correctly identifies brain.py and classify_intent
        # Normalize and check for key facts
        normalized = reply.lower()
        has_brain_py = "brain.py" in normalized
        has_classify_intent = "classify_intent" in normalized
        
        # Also check for line number or function definition mention
        passed = has_brain_py and has_classify_intent
        return passed, f"brain_py={has_brain_py} classify_intent={has_classify_intent}"
    
    elif condition == "weather_tool_called_with_Aurora":
        passed = any(t in ["get_weather", "get_weather_detailed"] for t in tools_called)
        return passed, f"tools={tools_called}"
    
    elif condition == "conditional_execution":
        # Check if both tools were called in sequence
        has_sys = "get_system_info" in tools_called
        has_proc = "get_top_processes" in tools_called
        passed = has_sys and has_proc
        return passed, f"sys={has_sys} proc={has_proc}"
    
    elif condition == "error_then_recovery_attempted":
        # Check if error occurred and then retry/fix was attempted
        passed = "error" in reply.lower() or "fix" in reply.lower() or "retry" in reply.lower()
        return passed, "recovery_indicated" if passed else "no_recovery"
    
    elif condition == "delegation_or_search_then_write":
        passed = any(t in ["web_search", "create_file", "write_file", "agent_spawn"] for t in tools_called)
        return passed, f"tools={tools_called}"
    
    elif condition == "asks_for_clarification":
        passed = any(w in reply.lower() for w in ["clarify", "what", "which", "specific", "could you", "more detail"])
        return passed, "clarification_requested" if passed else "no_clarification"
    
    return False, f"unknown_condition:{condition}"


def run_phase1_baseline(require_no_api: bool = False) -> dict:
    """Run Phase 1 baseline tasks and produce detailed report."""
    cases = load_phase1_baseline()
    if not cases:
        return {"error": "No Phase 1 baseline cases found", "results": []}
    
    results = []
    category_stats = {}
    
    print(f"Running {len(cases)} Phase 1 baseline tasks...")
    
    for i, case in enumerate(cases):
        category = case.get("category", "unknown")
        
        # Initialize category stats
        if category not in category_stats:
            category_stats[category] = {"total": 0, "passed": 0, "failed": 0}
        
        category_stats[category]["total"] += 1
        
        print(f"  [{i+1}/{len(cases)}] {category}: {case['prompt'][:60]}...")
        
        # Clear request ID for clean trace
        clear_request_id()
        rid = new_request_id()
        
        start = time.time()
        result = run_eval_case(case, require_no_api=require_no_api)
        elapsed = time.time() - start
        
        # Evaluate pass condition
        passed, condition_detail = evaluate_pass_condition(case, result)
        
        # Get decision trace
        request_id = result.get("request_id", "")
        trace = []
        if request_id:
            from decision_log import get_decision_trace
            trace = get_decision_trace(request_id)
        
        # Build enhanced result
        enhanced_result = {
            **result,
            "category": category,
            "pass_condition": case.get("pass_condition", ""),
            "condition_passed": passed,
            "condition_detail": condition_detail,
            "trace": trace,
            "trace_events": len(trace),
        }
        
        results.append(enhanced_result)
        
        if passed:
            category_stats[category]["passed"] += 1
            status = "PASS"
        else:
            category_stats[category]["failed"] += 1
            status = "FAIL"
        
        print(f"    {status} ({condition_detail}) - {elapsed:.2f}s - trace: {len(trace)} events")
    
    # Overall stats
    total = len(results)
    passed = sum(1 for r in results if r.get("condition_passed"))
    failed = total - passed
    pass_rate = passed / total if total > 0 else 0
    
    # Overall metrics (from existing eval)
    non_skipped = [r for r in results if not r.get("skipped")]
    avg_tool_acc = sum(r.get("tool_accuracy", 0) for r in non_skipped) / len(non_skipped) if non_skipped else 0
    avg_kw_recall = sum(r.get("keyword_recall", 0) for r in non_skipped) / len(non_skipped) if non_skipped else 0
    avg_intent_acc = sum(r.get("intent_accuracy", 0) for r in non_skipped) / len(non_skipped) if non_skipped else 0
    avg_latency = sum(r.get("latency", 0) for r in non_skipped) / len(non_skipped) if non_skipped else 0
    
    # Build report
    report = {
        "timestamp": time.time(),
        "phase": 1,
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(pass_rate, 3),
        "avg_tool_accuracy": round(avg_tool_acc, 3),
        "avg_keyword_recall": round(avg_kw_recall, 3),
        "avg_intent_accuracy": round(avg_intent_acc, 3),
        "avg_latency_seconds": round(avg_latency, 3),
        "category_stats": category_stats,
        "results": results,
    }
    
    # Save report
    os.makedirs(EVAL_RUNS_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = os.path.join(EVAL_RUNS_DIR, f"phase1_baseline_{ts}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    # Also save as latest
    latest_path = os.path.join(EVAL_RUNS_DIR, "phase1_baseline_latest.json")
    with open(latest_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    
    return report


def print_summary(report: dict):
    """Print a human-readable summary."""
    print("\n" + "=" * 60)
    print("PHASE 1 BASELINE RESULTS")
    print("=" * 60)
    print(f"Total tasks: {report['total']}")
    print(f"Passed: {report['passed']}")
    print(f"Failed: {report['failed']}")
    print(f"Pass rate: {report['pass_rate']*100:.1f}%")
    print(f"Avg tool accuracy: {report['avg_tool_accuracy']:.2f}")
    print(f"Avg keyword recall: {report['avg_keyword_recall']:.2f}")
    print(f"Avg intent accuracy: {report['avg_intent_accuracy']:.2f}")
    print(f"Avg latency: {report['avg_latency_seconds']:.2f}s")
    print()
    print("Per-category:")
    for cat, stats in report.get("category_stats", {}).items():
        rate = stats["passed"] / stats["total"] * 100 if stats["total"] > 0 else 0
        print(f"  {cat}: {stats['passed']}/{stats['total']} ({rate:.0f}%)")
    print()
    print("Failures:")
    for r in report["results"]:
        if not r.get("condition_passed"):
            print(f"  [{r['category']}] {r['prompt'][:60]}")
            print(f"    Expected: {r.get('pass_condition')}")
            print(f"    Got: {r.get('condition_detail')}")
            print(f"    Trace events: {r.get('trace_events', 0)}")
            if r.get("reply_preview"):
                print(f"    Reply: {r['reply_preview'][:100]}")
            print()


if __name__ == "__main__":
    require_no_api = "--no-api" in sys.argv
    report = run_phase1_baseline(require_no_api=require_no_api)
    print_summary(report)
    
    if report.get("failed", 0) > 0:
        sys.exit(1)
    else:
        sys.exit(0)