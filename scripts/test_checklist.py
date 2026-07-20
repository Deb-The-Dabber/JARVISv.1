#!/usr/bin/env python3
"""Full regression test for all Jarvis capabilities.

Starts its own server, runs all checks, stops server.
Usage:
    source venv/bin/activate && python scripts/test_checklist.py
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "PASS"
FAIL = "FAIL"
errors = 0
ran = 0
_server_proc = None


def check(name: str, ok: bool, detail: str = ""):
    global errors, ran
    ran += 1
    tag = PASS if ok else FAIL
    if not ok:
        errors += 1
    msg = f"  [{tag}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def api_get(path: str) -> dict:
    try:
        resp = urllib.request.urlopen(f"http://localhost:8000{path}", timeout=10)
        return json.loads(resp.read())
    except Exception as e:
        return {"_error": str(e)}


def start_server():
    global _server_proc
    _server_proc = subprocess.Popen([sys.executable, "server.py"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for i in range(20):
        try:
            resp = urllib.request.urlopen("http://localhost:8000/health", timeout=3)
            if resp.status == 200:
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Server did not start")


def stop_server():
    global _server_proc
    if _server_proc:
        _server_proc.terminate()
        _server_proc.wait()
        _server_proc = None


# ── Test functions ──


def test_module_imports():
    modules = [
        ("eval_runner", "eval_runner"),
        ("perf_router", "perf_router"),
        ("push_notify", "push_notify"),
        ("agent", "agent"),
        ("graph_memory", "graph_memory"),
        ("safety", "safety"),
        ("config", "config"),
        ("tools.vision_tools", "tools.vision_tools"),
        ("brain", "brain"),
    ]
    for label, mod in modules:
        try:
            __import__(mod)
            check(f"import {label}", True)
        except Exception as e:
            check(f"import {label}", False, str(e))


def test_memory_roundtrip():
    try:
        from memory import forget_memory, get_all_memories, save_memory
        from vector_memory import add_to_vector_memory, search_vector_memory

        test_fact = "test favorite color is chartreuse"
        save_memory(test_fact, "fact")
        memories = get_all_memories()
        found = any(test_fact in m[1] for m in memories)
        check("memory save SQLite", found)

        add_to_vector_memory(test_fact, "fact")
        results = search_vector_memory(test_fact, n_results=5)
        check("memory save vector", len(results) > 0, f"{len(results)}")
        if results:
            check("memory vector content matches", test_fact in results[0][0])

        forget_memory("chartreuse")
        memories_after = get_all_memories()
        still_in_sqlite = any(test_fact in m[1] for m in memories_after)
        check("memory forget SQLite", not still_in_sqlite)

        results_after = search_vector_memory(test_fact, n_results=5)
        still_in_vector = any(test_fact in r[0] for r in results_after)
        check("memory forget vector", not still_in_vector, f"{len(results_after)} matches remain")

    except Exception as e:
        check("memory roundtrip", False, str(e))


def test_graph():
    try:
        from graph_memory import extract_entities_relations, get_graph_summary, hybrid_graph_search, search_neighbors

        summary = get_graph_summary()
        check("graph summary callable", True)

        rels = extract_entities_relations("Alice works at Acme Corp in Seattle")
        check("graph extract_entities", len(rels) > 0, f"{len(rels)} relations")

        neighbors = search_neighbors("Alice")
        check("graph search_neighbors", isinstance(neighbors, list))

        results = hybrid_graph_search("Alice Acme")
        check("graph hybrid_search", isinstance(results, list))
    except Exception as e:
        check("graph module", False, str(e))


def test_agent():
    try:
        from agent import get_agent, list_agents, spawn_agent, stop_agent

        aid = spawn_agent("test automation")
        check("agent spawn", bool(aid))
        agents = list_agents()
        check("agent list", len(agents) > 0)
        a = get_agent(aid)
        check("agent get", a is not None and a.status == "running")
        stop_agent(aid)
        a = get_agent(aid)
        check("agent stop", a is not None and a.status in ("stopped", "completed"))
    except Exception as e:
        check("agent system", False, str(e))


def test_learner():
    try:
        from learner import load_learned_tools

        tools = load_learned_tools()
        check("learner tools loaded", isinstance(tools, dict))
    except Exception as e:
        check("learner module", False, str(e))


def test_perf():
    try:
        from perf_router import get_provider_stats, get_semantic_cache_stats

        ps = get_provider_stats()
        check("perf provider stats", isinstance(ps, dict))
        cs = get_semantic_cache_stats()
        check("perf cache stats", isinstance(cs, dict))
    except Exception as e:
        check("perf module", False, str(e))


def test_capabilities():
    try:
        from safety import CAPABILITY_REGISTRY, get_tool_capability

        check("capabilities registered", len(CAPABILITY_REGISTRY) > 0, f"{len(CAPABILITY_REGISTRY)}")
        cap = get_tool_capability("run_terminal_command")
        check("capability lookup", cap is not None, str(cap))
    except Exception as e:
        check("capability system", False, str(e))


def test_vision():
    try:
        from tools.vision_tools import analyze_image, analyze_video, ocr_document

        check("vision analyze_image callable", callable(analyze_image))
        check("vision ocr_document callable", callable(ocr_document))
        check("vision analyze_video callable", callable(analyze_video))
    except Exception as e:
        check("vision module", False, str(e))


def test_push():
    try:
        from push_notify import enqueue_message, get_devices, get_pending_messages

        devs = get_devices()
        check("push devices", isinstance(devs, list))
        msgs = get_pending_messages()
        check("push pending msgs", isinstance(msgs, list))
        enqueue_message("test notification", priority=1)
        msgs_after = get_pending_messages()
        check("push enqueue", len(msgs_after) >= len(msgs))
    except Exception as e:
        check("push module", False, str(e))


def test_eval():
    try:
        from eval_runner import run_eval_suite

        report = run_eval_suite(require_no_api=True)
        check("eval suite ran", True)
        check("eval total", report["total"] > 0, f"{report['total']} cases")
        check("eval no errors", report["failed"] == 0, f"{report['failed']} failures")
    except Exception as e:
        check("eval module", False, str(e))


def test_api_endpoints():
    endpoints = [
        ("health", "/health", True),
        ("system", "/system", True),
        ("eval/latest", "/eval/latest", True),
        ("eval/history", "/eval/history", True),
        ("learner/stats", "/learner/stats", True),
        ("learner/candidates", "/learner/candidates", True),
        ("graph/stats", "/graph/stats", True),
        ("graph/neighbors", "/graph/neighbors?entity=Alice", True),
        ("graph/search", "/graph/search?query=Alice", True),
        ("perf/providers", "/perf/providers", True),
        ("perf/cache", "/perf/cache", True),
        ("agents", "/agents", True),
        ("mobile/devices", "/mobile/devices", True),
        ("mobile/outbox", "/mobile/outbox", True),
    ]
    for label, path, _ in endpoints:
        data = api_get(path)
        has_error = "_error" in data
        check(f"api {label}", not has_error, data.get("_error", ""))


def test_tool_registry():
    try:
        from tools import TOOL_DEFINITIONS, TOOL_REGISTRY

        check("TOOL_REGISTRY populated", len(TOOL_REGISTRY) > 0, f"{len(TOOL_REGISTRY)} tools")
        check("TOOL_DEFINITIONS populated", len(TOOL_DEFINITIONS) > 0, f"{len(TOOL_DEFINITIONS)} defs")
        check("extract_entities_relations in TOOL_DEFINITIONS", any("extract_entities_relations" in str(d) for d in TOOL_DEFINITIONS))
    except Exception as e:
        check("tool registry", False, str(e))


# ── Main ──


def main():
    global errors, ran
    print("=" * 60)
    print("Jarvis Full Regression Test Checklist")
    print("=" * 60)

    print("\n--- Module Imports ---")
    test_module_imports()

    print("\n--- Tool Registry ---")
    test_tool_registry()

    print("\n--- Capability System ---")
    test_capabilities()

    print("\n--- Memory Round-Trip ---")
    test_memory_roundtrip()

    print("\n--- Graph Module ---")
    test_graph()

    print("\n--- Agent System ---")
    test_agent()

    print("\n--- Learner Module ---")
    test_learner()

    print("\n--- Perf Router ---")
    test_perf()

    print("\n--- Vision Tools ---")
    test_vision()

    print("\n--- Push Notify ---")
    test_push()

    print("\n--- Eval Harness ---")
    test_eval()

    # ── API server tests ──
    print("\n--- Starting Server ---")
    try:
        start_server()
        print("  Server started on :8000")
        print("\n--- API Endpoints ---")
        test_api_endpoints()
    except Exception as e:
        check("server startup", False, str(e))
    finally:
        stop_server()
        print("  Server stopped.")

    print(f"\n{'=' * 60}")
    print(f"Ran {ran} checks, {errors} failure(s)")
    if errors:
        print("SOME CHECKS FAILED")
        sys.exit(1)
    else:
        print("ALL CHECKS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
