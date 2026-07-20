#!/usr/bin/env python3
"""Integration test for computer tools (requires NVIDIA_API_KEY for vision).

Usage:
    NVIDIA_API_KEY=... python tests/scripts/test_computer.py

Exits with 1 on any failure (CI-friendly).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tools.computer_tools import take_screenshot


def test_take_screenshot():
    result = take_screenshot()
    assert result, f"take_screenshot returned empty: {result!r}"
    # Extract the path from the result string
    path_prefix = "Screenshot saved to "
    assert result.startswith(path_prefix), f"Unexpected result format: {result}"
    path = result[len(path_prefix):]
    assert os.path.isfile(path), f"Screenshot file not found: {path}"
    os.remove(path)
    print("[PASS] test_take_screenshot")


if __name__ == "__main__":
    results = 0
    tests = [test_take_screenshot]
    for t in tests:
        name = t.__name__
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            results += 1
    sys.exit(results)
