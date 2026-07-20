#!/usr/bin/env python3
"""Patch Jarvis with deep debug logging."""

# ── brain.py ──────────────────────────────────────────
with open("/Users/debasishbeura/Jarvis/brain.py", "r") as f:
    brain = f.read()

# Patch cache read
brain = brain.replace("from perf_router import (\n                semantic_cache_get,\n            )", "from perf_router import semantic_cache_get")

brain = brain.replace(
    'cached = semantic_cache_get(user_message, intent)\n            if cached is not None:\n                _debug(f"[Router] Semantic cache HIT for intent={intent}")',
    '_debug(f"[Cache] Read intent={intent}, checking semantic cache...")\n            cached = semantic_cache_get(user_message, intent)\n            if cached is not None:\n                _debug(f"[Cache] HIT for intent={intent}, returning cached response")',
)

# Patch cache write
brain = brain.replace(
    'if _intent_for_cache == "chat" and not _turn_memo_cache and not has_pending_safe():\n            semantic_cache_set(text, _intent_for_cache, reply)\n        else:\n            _debug(f"[Router] Semantic cache write skipped for intent={_intent_for_cache}")',
    'skip_reason = None\n        if _intent_for_cache != "chat":\n            skip_reason = f"intent={_intent_for_cache} (not chat)"\n        elif _turn_memo_cache:\n            skip_reason = f"tools_called={list(_turn_memo_cache.keys())}"\n        elif has_pending_safe():\n            skip_reason = "pending_safe=true"\n        \n        if skip_reason:\n            _debug(f"[Cache] Write skipped: {skip_reason}")\n        else:\n            semantic_cache_set(text, _intent_for_cache, reply)\n            _debug(f"[Cache] Write intent={_intent_for_cache}")',
)

with open("/Users/debasishbeura/Jarvis/brain.py", "w") as f:
    f.write(brain)

print("Patched brain.py")

# ── tool_parser.py ──────────────────────────────────────
with open("/Users/debasishbeura/Jarvis/tool_parser/tool_parser.py", "r") as f:
    tp = f.read()

tp = tp.replace(
    "        # Try static parsers first\n        for parser in self._static_parsers:\n            result = parser(text)\n            if result:\n                return result",
    '        # Try static parsers first\n        for parser in self._static_parsers:\n            result = parser(text)\n            if result:\n                _debug(f"[Parser] {parser.__name__} matched for provider={provider}")\n                return result',
)

with open("/Users/debasishbeura/Jarvis/tool_parser/tool_parser.py", "w") as f:
    f.write(tp)

print("Patched tool_parser.py")

# ── safety.py ──────────────────────────────────────
with open("/Users/debasishbeura/Jarvis/safety.py", "r") as f:
    safety = f.read()

safety = safety.replace(
    '    if level == SAFE:\n        log_audit(tool, args, level, "ALLOWED")\n        return True',
    '    if level == SAFE:\n        _debug(f"[Safety] {tool}: SAFE -> allowed")\n        log_audit(tool, args, level, "ALLOWED")\n        return True',
)

safety = safety.replace(
    "    if level == WARNING:\n        if is_session_confirmed(tool):",
    '    if level == WARNING:\n        confirmed = is_session_confirmed(tool)\n        _debug(f"[Safety] {tool}: WARNING, session_confirmed={confirmed}")\n        if confirmed:',
)

with open("/Users/debasishbeura/Jarvis/safety.py", "w") as f:
    f.write(safety)

print("Patched safety.py")

# ── computer_tools.py ──────────────────────────────────────
with open("/Users/debasishbeura/Jarvis/tools/computer_tools.py", "r") as f:
    comp = f.read()

comp = comp.replace(
    '    if "ps aux --sort=-%mem" in command:\n        command = "ps axm -o pid,%mem,%cpu,comm | sort -nrk2 | head -20"',
    '    if "ps aux --sort=-%mem" in command:\n        command = "ps axm -o pid,%mem,%cpu,comm | sort -nrk2 | head -20"\n        _debug(f"[Rewrite] Linux ps -> macOS compat: {original_command[:60]}...")',
)

with open("/Users/debasishbeura/Jarvis/tools/computer_tools.py", "w") as f:
    f.write(comp)

print("Patched computer_tools.py")
print("Done!")
