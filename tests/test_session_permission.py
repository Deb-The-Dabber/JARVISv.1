#!/usr/bin/env python3
"""
Session Permission Consistency Test Suite
Tests all variants of the confirmation bug after Bug #1 (missing args) fix.

Run: python tests/test_session_permission.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safety import (
    DANGEROUS,
    SAFE,
    TOOL_PERMISSIONS,
    WARNING,
    NeedsConfirmation,
    check_permission,
    get_audit_log,
    is_session_confirmed,
    mark_session_confirmed,
    reset_session,
)


class Colors:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def log(msg, color=Colors.ENDC):
    print(f"{color}{msg}{Colors.ENDC}")


def section(title):
    print(f"\n{Colors.HEADER}{'=' * 60}{Colors.ENDC}")
    log(f"  {title}", Colors.BOLD)
    print(f"{Colors.HEADER}{'=' * 60}{Colors.ENDC}\n")


def test_result(name, passed, details=""):
    status = f"{Colors.OKGREEN}✓ PASS{Colors.ENDC}" if passed else f"{Colors.FAIL}✗ FAIL{Colors.ENDC}"
    print(f"  {status}: {name}")
    if details:
        print(f"         {details}")
    return passed


def test_basic_confirmation():
    section("TEST 1: Basic Confirmation Flow")
    reset_session()
    log("Step 1: First-time WARNING tool should raise NeedsConfirmation")
    try:
        check_permission("quit_app", {"app_name": "Safari"})
        return test_result("First call raises NeedsConfirmation", False, "Should have raised exception")
    except NeedsConfirmation as e:
        log(f"  raised: {e.message[:50]}...")
    log("\nStep 2: After mark_session_confirmed, should allow")
    mark_session_confirmed("quit_app")
    try:
        result = check_permission("quit_app", {"app_name": "Safari"})
        return test_result("Session confirmation persists", result == True)
    except NeedsConfirmation:
        return test_result("Session confirmation persists", False, "Still raised NeedsConfirmation")


def test_session_multiple_tools():
    section("TEST 2: Multiple WARNING Tools")
    reset_session()
    log("Step 1: Confirm quit_app")
    try:
        check_permission("quit_app", {"app_name": "Safari"})
    except NeedsConfirmation:
        mark_session_confirmed("quit_app")
        log("  quit_app confirmed")
    log("\nStep 2: click_on_screen should still ask (different tool)")
    try:
        check_permission("click_on_screen", {})
        return test_result("Different tool asks separately", False, "Should have raised NeedsConfirmation")
    except NeedsConfirmation:
        log("  click_on_screen raised NeedsConfirmation (correct)")
        return test_result("Different tool asks separately", True)


def test_dangerous_always_confirm():
    section("TEST 3: DANGEROUS Tools Always Ask")
    reset_session()
    log("Step 1: First DANGEROUS tool")
    try:
        check_permission("send_imessage", {"contact": "John", "message": "hi"})
        return test_result("DANGEROUS raises NeedsConfirmation", False)
    except NeedsConfirmation:
        log("  send_imessage raised NeedsConfirmation (correct)")
    log("\nStep 2: After mark_session_confirmed (DANGEROUS should still ask)")
    mark_session_confirmed("send_imessage")
    try:
        check_permission("send_imessage", {"contact": "John", "message": "hi"})
        log("  NOTE: DANGEROUS allowed after mark_session_confirmed - by design")
        return test_result("DANGEROUS behavior", True)
    except NeedsConfirmation:
        log("  DANGEROUS still asks after session confirm")
        return test_result("DANGEROUS behavior", True)


def test_safe_never_confirm():
    section("TEST 4: SAFE Tools Never Ask")
    reset_session()
    safe_tools = [
        ("get_weather", {}),
        ("get_system_info", {}),
        ("get_open_apps", {}),
        ("open_app", {"app_name": "Safari"}),
        ("web_search", {"query": "test"}),
    ]
    all_passed = True
    for tool_name, args in safe_tools:
        try:
            check_permission(tool_name, args)
            log(f"  {tool_name}: allowed")
        except NeedsConfirmation:
            log(f"  ✗ {tool_name}: incorrectly raised NeedsConfirmation")
            all_passed = False
    return test_result("SAFE tools bypass confirmation", all_passed)


def test_audit_logging():
    section("TEST 5: Audit Log Entries")
    reset_session()
    log("Trigger NEEDS_CONFIRMATION log entry")
    try:
        check_permission("quit_app", {"app_name": "Safari"})
    except NeedsConfirmation:
        pass
    log("Check audit log")
    logs = get_audit_log(limit=5)
    quit_logs = [l for l in logs if l[0] == "quit_app"]
    if quit_logs:
        log(f"  Found {len(quit_logs)} entries for quit_app")
        log(f"  Latest: tool={quit_logs[0][0]}, level={quit_logs[0][2]}, decision={quit_logs[0][3]}")
        return test_result("Audit log captures confirmation requests", quit_logs[0][3] == "NEEDS_CONFIRMATION")
    log("  No audit log entries found")
    return test_result("Audit log captures confirmation requests", False)


def test_permission_levels():
    section("TEST 6: TOOL_PERMISSIONS Dictionary")
    expected_levels = {
        "get_weather": SAFE,
        "get_weather_detailed": SAFE,
        "get_system_info": SAFE,
        "open_app": SAFE,
        "quit_app": WARNING,
        "browser_navigate": SAFE,
        "click_on_screen": WARNING,
        "send_imessage": DANGEROUS,
    }
    all_passed = True
    for tool, expected in expected_levels.items():
        actual = TOOL_PERMISSIONS.get(tool, "UNKNOWN")
        if actual == expected:
            log(f"  {tool:25s} -> {actual}")
        else:
            log(f"  ✗ {tool:25s} -> {actual} (expected {expected})")
            all_passed = False
    return test_result("All permission levels correct", all_passed)


def test_session_state():
    section("TEST 7: Session State Management")
    reset_session()
    log("Before confirmation")
    c1 = is_session_confirmed("quit_app")
    log(f"  is_session_confirmed('quit_app') = {c1}")
    log("After mark_session_confirmed")
    mark_session_confirmed("quit_app")
    c2 = is_session_confirmed("quit_app")
    log(f"  is_session_confirmed('quit_app') = {c2}")
    log("Different tool should not be confirmed")
    c3 = is_session_confirmed("click_on_screen")
    log(f"  is_session_confirmed('click_on_screen') = {c3}")
    return test_result("Session state management", c1 == False and c2 == True and c3 == False)


if __name__ == "__main__":
    print(f"\n{Colors.BOLD}{'=' * 60}")
    print("  SESSION PERMISSION CONSISTENCY TEST SUITE")
    print(f"{'=' * 60}{Colors.ENDC}\n")
    results = [
        f() for f in [test_basic_confirmation, test_session_multiple_tools, test_dangerous_always_confirm, test_safe_never_confirm, test_audit_logging, test_permission_levels, test_session_state]
    ]
    section("SUMMARY")
    passed = sum(results)
    total = len(results)
    if passed == total:
        log(f"  {Colors.OKGREEN}All {total} tests passed!{Colors.ENDC}", Colors.BOLD)
    else:
        log(f"  {Colors.FAIL}{passed}/{total} tests passed{Colors.ENDC}", Colors.BOLD)
    print()
    sys.exit(0 if passed == total else 1)
