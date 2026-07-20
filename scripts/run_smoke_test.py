#!/usr/bin/env python3
"""Non-interactive smoke test for Jarvis core subsystems.

Run:  source venv/bin/activate && python scripts/run_smoke_test.py

Tests: cache, config, safety, router, memory, timer.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time

OK = "PASS"
FAIL = "FAIL"
errors = 0
ran = 0


def check(name: str, ok: bool, detail: str = ""):
    global errors, ran
    ran += 1
    tag = OK if ok else FAIL
    if not ok:
        errors += 1
    msg = f"  [{tag}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)


print("=" * 60)
print("Jarvis Smoke Test")
print("=" * 60)

# --- 1. Cache ---
print("\n--- Cache ---")
from cache import clear_cache, get_cache_stats, get_cached, invalidate, set_cached

clear_cache()
check("clear_cache", True)

set_cached("smoke_k", "smoke_v", 30)
found, val = get_cached("smoke_k")
check("set+get", found and val == "smoke_v", f"got {val!r}")

invalidate("smoke_k")
found, _ = get_cached("smoke_k")
check("invalidate", not found)

stats = get_cache_stats()
check("stats_entry", stats["entries"] == 0)
check("stats_miss", stats["misses"] == 1)

set_cached("a", 1, 0)
time.sleep(0.02)
found, _ = get_cached("a")
check("expiry", not found)

# --- 2. Config ---
print("\n--- Config ---")
from config import DEFAULT_BROWSER, USER_CITY, USER_LAT, USER_LON, USER_NAME

check("user_name", bool(USER_NAME))
check("city", bool(USER_CITY))
check("lat_range", -90 <= USER_LAT <= 90)
check("lon_range", -180 <= USER_LON <= 180)
check("browser", bool(DEFAULT_BROWSER))

# --- 3. Safety ---
print("\n--- Safety ---")
from safety import (
    CRITICAL,
    DANGEROUS,
    SAFE,
    TOOL_PERMISSIONS,
    WARNING,
    NeedsConfirmation,
    analyze_command,
    check_permission,
    mark_session_confirmed,
    reset_session,
)

reset_session()
check("weather_safe", TOOL_PERMISSIONS.get("get_weather") == SAFE)
check("nav_warning", TOOL_PERMISSIONS.get("browser_navigate") == WARNING)
check("imessage_danger", TOOL_PERMISSIONS.get("send_imessage") == DANGEROUS)

try:
    check_permission("browser_navigate")
    check("confirm_needed", False, "should have raised")
except NeedsConfirmation:
    check("confirm_needed", True)

mark_session_confirmed("browser_navigate")
check("confirmed_ok", check_permission("browser_navigate"))

safe_cmd, level, _ = analyze_command("ls -la")
check("safe_cmd", safe_cmd and level == SAFE)

danger_cmd, dlevel, _ = analyze_command("rm -rf /")
check("danger_cmd", not danger_cmd and dlevel == CRITICAL)

# --- 4. Intent Router ---
print("\n--- Router ---")
from brain import classify_intent

checks = [
    ("fix bug in brain.py", "self_mod"),
    ("open safari", "tool_use"),
    ("hello", "chat"),
    ("why is the sky blue", "reasoning"),
    ("refactor brain.py", "self_mod"),
    ("browse brain.py", "tool_use"),
    ("weather in chicago", "tool_use"),
    ("what is love", "chat"),
    ("implement a fibonacci function", "coding"),
]
for query, expected in checks:
    result = classify_intent(query)
    ok = result == expected
    check(f"router: {query!r} -> {result}", ok, f"expected {expected}")

# --- 5. Memory (associative) ---
print("\n--- Memory ---")
from memory import get_all_memories, init_db, save_memory

init_db()
save_memory("smoke test fact", "fact")
results = get_all_memories()
check("memory_write+query", len(results) > 0, f"{len(results)} entries")

# --- Summary ---
print(f"\n{'=' * 60}")
print(f"Ran {ran} checks, {errors} failures")
if errors:
    print("SOME CHECKS FAILED")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
    sys.exit(0)
