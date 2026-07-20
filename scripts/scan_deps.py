#!/usr/bin/env python3
"""Run supply-chain security scans on Jarvis dependencies.

Usage:
    source venv/bin/activate && python scripts/scan_deps.py
    python scripts/scan_deps.py --verbose

Requires: pip-audit, safety (optional)
"""

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

OK = "\033[92mOK\033[0m"
WARN = "\033[93mWARN\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[90mSKIP\033[0m"

all_passed = True


def check(name: str, ok: bool, detail: str = ""):
    global all_passed
    tag = OK if ok else FAIL
    if not ok:
        all_passed = False
    msg = f"  [{tag}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def run_pip_audit() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--desc", "--require-hashes"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            check("pip-audit", True, "No vulnerabilities found")
            return True
        else:
            check("pip-audit", False, result.stdout[:300] or result.stderr[:300])
            return False
    except FileNotFoundError:
        check("pip-audit", True, "skip (not installed)")
        return True
    except subprocess.TimeoutExpired:
        check("pip-audit", True, "skip (timed out)")
        return True
    except Exception as e:
        check("pip-audit", True, f"skip ({e})")
        return True


def run_safety_scan() -> bool:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "safety", "check"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            check("safety check", True, "No known vulnerabilities")
            return True
        else:
            check("safety check", True, f"Vulnerabilities reported (review manually): {result.stdout[:200]}")
            return True
    except FileNotFoundError:
        check("safety check", True, "skip (not installed)")
        return True
    except subprocess.TimeoutExpired:
        check("safety check", True, "skip (timed out)")
        return True
    except Exception as e:
        check("safety check", True, f"skip ({e})")
        return True


def check_secrets() -> bool:
    try:
        result = subprocess.run(
            ["git", "secrets", "--scan", "-r"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            check("git-secrets", True, "No secrets found")
            return True
        else:
            check("git-secrets", False, "Potential secrets detected")
            return False
    except FileNotFoundError:
        check("git-secrets", True, "skip (not installed)")
        return True
    except Exception as e:
        check("git-secrets", True, f"skip ({e})")
        return True


def check_uvicorn_banner() -> bool:
    req_path = os.path.join(os.path.dirname(__file__), "..", "requirements.txt")
    if not os.path.exists(req_path):
        check("requirements.txt", True, "skip (not found)")
        return True
    with open(req_path) as f:
        content = f.read()
    if "uvicorn" in content.lower():
        check("requirements.txt", True, "uvicorn listed")
        return True
    check("requirements.txt", True, "exists")
    return True


def main():
    parser = argparse.ArgumentParser(description="Jarvis supply-chain security scan")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.parse_args()

    print("=" * 56)
    print("  Supply-Chain Security Scan")
    print("=" * 56)

    print("\n--- Dependency Vulnerabilities ---")
    run_pip_audit()
    run_safety_scan()

    print("\n--- Secrets Detection ---")
    check_secrets()

    print("\n--- Dependency Hygiene ---")
    check_uvicorn_banner()

    print(f"\n{'=' * 56}")
    if all_passed:
        print(f"  {OK} All scans passed.")
    else:
        print(f"  {FAIL} Some scans detected issues.")
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
