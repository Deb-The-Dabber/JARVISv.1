#!/usr/bin/env python3
"""
Retrain CLI: python -m tool_parser
Reads format_log.jsonl, clusters unknown formats, generates parser functions.
"""

import json
import os
import re

from config import FORMAT_LOG_PATH, PARSERS_DIR


def _read_log(path: str) -> list:
    if not os.path.exists(path):
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def _cluster_entries(entries: list) -> list:
    """Group entries with similar first-char + pattern structure."""
    groups = {}
    for e in entries:
        text = e.get("text", "").strip()
        if not text:
            continue
        sig = hash(re.sub(r"\w+", "X", text[:80]))
        group_key = f"{text[:3]}_{sig}"
        if group_key not in groups:
            groups[group_key] = []
        groups[group_key].append(e)
    return list(groups.values())


def _generate_parser(entries: list) -> tuple:
    """Generate a parser function from a cluster of similar entries."""
    sample = entries[0]["text"][:200]

    tool_match = re.search(r"(\w+)\s*[\(\{]", sample)
    tool_placeholder = tool_match.group(1) if tool_match else "tool_name"
    safe_name = re.sub(r"\W+", "_", tool_placeholder.lower())[:30]

    lines = [
        '"""',
        f"Auto-generated parser for: {repr(sample[:80])}",
        f"Generated from {len(entries)} log entries.",
        '"""',
        "import json",
        "import re",
        "from typing import List, Tuple",
        "",
        "",
        "def parse(text: str) -> List[Tuple[str, dict]]:",
        '    """Auto-generated parser."""',
        "    if not text:",
        "        return []",
        "    calls = []",
        '    pattern = r"(\\w+)\\s*[(]"',
        "    for match in re.finditer(pattern, text):",
        "        name = match.group(1)",
        "        calls.append((name, {}))",
        "    return calls",
    ]
    return "\n".join(lines), safe_name


def main():
    entries = _read_log(FORMAT_LOG_PATH)
    if not entries:
        print("No format log entries found.")
        return

    clusters = _cluster_entries(entries)
    print(f"Found {len(entries)} entries in {len(clusters)} format clusters.")

    os.makedirs(PARSERS_DIR, exist_ok=True)

    generated = 0
    for i, cluster in enumerate(clusters):
        code, name = _generate_parser(cluster)
        # Use cluster prefix as unique filename
        prefix = re.sub(r"\W+", "_", cluster[0].get("text", "")[:10].lower())
        fname = f"parser_{prefix}_{i}.py"
        fpath = os.path.join(PARSERS_DIR, fname)
        with open(fpath, "w") as f:
            f.write(code)
        generated += 1
        print(f"  [{i}] Generated {fname} ({len(cluster)} entries)")

    # Clear log after processing
    with open(FORMAT_LOG_PATH, "w") as f:
        f.write("")

    print(f"\nGenerated {generated} parser(s) in {PARSERS_DIR}/")
    print("Reload with: from tool_parser import reload_parsers; reload_parsers()")


if __name__ == "__main__":
    main()
