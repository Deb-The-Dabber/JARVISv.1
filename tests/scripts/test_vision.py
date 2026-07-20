#!/usr/bin/env python3
"""Integration test for vision tools (requires NVIDIA_API_KEY).

Usage:
    NVIDIA_API_KEY=... python tests/scripts/test_vision.py

Exits with 1 on any failure (CI-friendly).
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tools.vision_tools import find_on_screen, read_screen, summarize_screen


def test_read_screen():
    result = read_screen()
    assert result, f"read_screen returned empty: {result!r}"
    assert "Frontmost app:" in result, f"Missing 'Frontmost app:' in: {result}"
    print(f"[PASS] test_read_screen: {result[:80]}...")


def test_summarize_screen():
    result = summarize_screen()
    assert result, f"summarize_screen returned empty: {result!r}"
    print(f"[PASS] test_summarize_screen: {result[:80]}...")


def test_find_on_screen():
    result = find_on_screen("something visible on screen")
    assert result, f"find_on_screen returned empty: {result!r}"
    print(f"[PASS] test_find_on_screen: {result[:80]}...")


if __name__ == "__main__":
    results = 0
    tests = [test_read_screen, test_summarize_screen, test_find_on_screen]
    for t in tests:
        name = t.__name__
        try:
            t()
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            results += 1
    sys.exit(results)
