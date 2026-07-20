"""XML tool call parser for model outputs that don't use structured API format.

Also includes FormatDetector for auto-logging and hot-reloading parsers
for new Nemotron tool-call formats.
"""

import json
import os
import re
import threading
import time
from typing import Callable, List, Tuple

from config import FORMAT_LOG_PATH, PARSERS_DIR

DEBUG = os.getenv("JARVIS_DEBUG", "0").lower() in ("1", "true", "yes", "on")


def _debug(message: str):
    if DEBUG:
        print(f"  [DEBUG] {message}")


# Global log lock for thread-safe appends
_format_log_lock = threading.Lock()


def parse_xml_tool_calls(text: str) -> List[Tuple[str, dict]]:
    """Extract XML-style tool calls from model output text.

    Handles formats like:
      <tool_name>create_file</tool_name><tool_args>{"filename":"test.html","content":"hello"}</tool_args>
      <tool_name>open_app</tool_name><tool_args>{"app_name":"Finder"}</tool_args>

    Returns list of (tool_name, args_dict) tuples.
    """
    if not text:
        return []
    calls = []
    pattern = r"<tool_name>\s*(\w+)\s*</tool_name>\s*<tool_args>\s*(\{.*?\})\s*</tool_args>"
    for match in re.finditer(pattern, text, re.DOTALL):
        name, args_json = match.groups()
        try:
            args = json.loads(args_json)
            if isinstance(args, dict):
                calls.append((name, args))
        except json.JSONDecodeError:
            continue
    return calls


def strip_xml_tool_calls(text: str) -> str:
    """Remove XML tool call markup from text, returning clean display text."""
    if not text:
        return ""
    cleaned = re.sub(
        r"<tool_name>\s*\w+\s*</tool_name>\s*<tool_args>\s*\{.*?\}\s*</tool_args>",
        "",
        text,
        flags=re.DOTALL,
    )
    return cleaned.strip()


def parse_markdown_json_tool_calls(text: str) -> List[Tuple[str, dict]]:
    """Extract JSON tool calls from markdown ```json ... ``` fences.

    Handles Nemotron regression where model wraps tool calls like:
      ```json{"name": "open_app", "arguments": {"app_name": "Weather"}}```

    Returns list of (tool_name, args_dict) tuples.
    """
    if not text:
        return []
    calls = []
    # Match ```json ... ``` blocks (with or without newlines)
    fence_pattern = r"```json\s*([\s\S]*?)```"
    for match in re.finditer(fence_pattern, text):
        raw = match.group(1).strip()
        if not raw:
            continue
        # Try parsing entire inner content as JSON
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                fn_name = parsed.get("name") or parsed.get("tool", "")
                fn_args = parsed.get("arguments", {})
                if isinstance(fn_args, dict) and fn_name:
                    calls.append((fn_name, fn_args))
                    continue
        except json.JSONDecodeError:
            pass
        # Try finding { } object within the fence (handles extra whitespace/newlines)
        obj_match = re.search(r"(\{.*\})", raw, re.DOTALL)
        if obj_match:
            try:
                parsed = json.loads(obj_match.group(1))
                if isinstance(parsed, dict):
                    fn_name = parsed.get("name") or parsed.get("tool", "")
                    fn_args = parsed.get("arguments", {})
                    if isinstance(fn_args, dict) and fn_name:
                        calls.append((fn_name, fn_args))
            except json.JSONDecodeError:
                continue
    return calls


def parse_json_tool_calls(text: str) -> List[Tuple[str, dict]]:
    """Extract bare JSON tool calls from model output text.

    Handles formats like:
      {"tool_calls": [{"name": "open_app", "arguments": {"app_name": "Finder"}}]}
      {"name": "open_app", "arguments": {"app_name": "Finder"}}
      [{"name": "open_app", "arguments": {"app_name": "Finder"}}]

    Does NOT require markdown fences — handles raw JSON the Nemotron model
    sometimes emits as text content.
    """
    if not text:
        return []
    text = text.strip()
    calls = []

    # Try parsing the entire text as JSON
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []

    # {"tool_calls": [...]}
    if isinstance(parsed, dict) and "tool_calls" in parsed:
        tc_list = parsed["tool_calls"]
        if isinstance(tc_list, list):
            for tc in tc_list:
                if isinstance(tc, dict):
                    fn_name = tc.get("name", "")
                    fn_args = tc.get("arguments", {})
                    if isinstance(fn_args, dict) and fn_name:
                        calls.append((fn_name, fn_args))
    # {"name": "...", "arguments": {...}} or {"tool": "...", "args": {...}}
    elif isinstance(parsed, dict):
        fn_name = parsed.get("name") or parsed.get("tool", "")
        fn_args = parsed.get("arguments") or parsed.get("args") or {}
        if isinstance(fn_args, dict) and fn_name:
            calls.append((fn_name, fn_args))
    # [{"name": "...", "arguments": {...}}, ...]
    elif isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                fn_name = item.get("name", "")
                fn_args = item.get("arguments") or item.get("args") or {}
                if isinstance(fn_args, dict) and fn_name:
                    calls.append((fn_name, fn_args))

    return calls


def parse_tool_call_tags(text: str) -> List[Tuple[str, dict]]:
    """Extract <tool_call>function(name)</tool_call> style tool calls.

    Handles formats like:
      <tool_call>
        function(scan_project_structure)
        end function
      </tool_call>
      <tool_call>function(open_app, app_name="Finder")</tool_call>

    The argument parsing is best-effort — extracts simple key=value pairs.
    """
    if not text:
        return []
    calls = []
    # Format with both <tool_call> ... </tool_call> and <tool_call> ... end function
    # Match content between <tool_call> and </tool_call> OR <tool_call> and "end function"
    for match in re.finditer(
        r"<tool_call>\s*(.*?)\s*(?:</tool_call>|end\s+function)",
        text,
        re.DOTALL | re.IGNORECASE,
    ):
        inner = match.group(1).strip()
        # Extract function(name, ...) from inner
        fn_match = re.match(
            r"(?:function|FUNCTION)\s*\(\s*(\w+)\s*(.*?)\s*\)",
            inner,
            re.DOTALL | re.IGNORECASE,
        )
        if fn_match:
            name = fn_match.group(1)
            args_str = fn_match.group(2).strip()
            fn_args = {}
            if args_str:
                for pair in re.split(r",\s*", args_str):
                    pair = pair.strip()
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        fn_args[k] = v
            calls.append((name, fn_args))
    return calls


def parse_tool_call_json_tags(text: str) -> List[Tuple[str, dict]]:
    """Extract <tool_call>{...JSON...}</tool_call> or unterminated tag JSON calls."""
    if not text:
        return []
    calls = []
    for match in re.finditer(
        r"<tool_call>\s*(.*?)(?:</tool_call>|$)",
        text,
        re.DOTALL | re.IGNORECASE,
    ):
        inner = match.group(1).strip()
        if not inner:
            continue
        json_match = re.search(r"(\{.*\})", inner, re.DOTALL)
        if not json_match:
            continue
        try:
            parsed = json.loads(json_match.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            fn_name = parsed.get("name") or parsed.get("tool", "")
            fn_args = parsed.get("arguments") or parsed.get("args") or {}
            if isinstance(fn_args, dict) and fn_name:
                calls.append((fn_name, fn_args))
    return calls


def strip_tool_call_tags(text: str) -> str:
    """Remove <tool_call> and ...end function markup, including hybrid JSON-in-tag format."""
    if not text:
        return ""
    cleaned = re.sub(
        r"<tool_call>.*?(?:</tool_call>|end\s+function)",
        "",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    cleaned = re.sub(
        r"<tool_call>\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}",
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return cleaned.strip()


def strip_json_tool_calls(text: str) -> str:
    """Remove bare JSON tool calls from text, returning clean display text."""
    if not text:
        return ""
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return text

    # If the whole text is a tool call JSON, return empty
    if isinstance(parsed, dict):
        if "tool_calls" in parsed:
            return ""
        if parsed.get("name") or parsed.get("tool"):
            return ""
    if isinstance(parsed, list) and any(isinstance(i, dict) and (i.get("name") or i.get("tool")) for i in parsed):
        return ""

    return text


def strip_markdown_json_tool_calls(text: str) -> str:
    """Remove ```json ... ``` tool-call fences from text."""
    if not text:
        return ""
    cleaned = re.sub(r"```json\s*[\s\S]*?```", "", text)
    # Also handle leftover raw JSON tool calls: {"name":"...", "arguments":{...}}
    # that may not be in fences
    lines = cleaned.strip().splitlines()
    filtered = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("{") and ('"name"' in stripped or '"tool"' in stripped):
            # Only skip if it actually parses as a tool call
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict) and (parsed.get("name") or parsed.get("tool")):
                    continue
            except Exception:
                pass
        filtered.append(line)
    return "\n".join(filtered).strip()


# ─────────────────────────────────────────────
# FORMAT DETECTOR — self-learning parser
# ─────────────────────────────────────────────


class FormatDetector:
    """Detects known tool-call formats, logs unknown ones, hot-reloads new parsers."""

    def __init__(self):
        self._static_parsers: List[Callable] = [
            parse_xml_tool_calls,
            parse_markdown_json_tool_calls,
            parse_json_tool_calls,
            parse_tool_call_json_tags,
            parse_tool_call_tags,
        ]
        self._dynamic_parsers: List[Callable] = []
        self._lock = threading.Lock()
        self._load_dynamic_parsers()

    # ── Public API ──

    def detect_and_parse(self, text: str, provider: str = "unknown") -> List[Tuple[str, dict]]:
        """Run all known + dynamic parsers. Logs unknown formats for later retraining."""
        if not text:
            return []

        # Try static parsers first
        for parser in self._static_parsers:
            result = parser(text)
            if result:
                _debug(f"[Parser] {parser.__name__} matched for provider={provider}")
                return result

        # Try dynamic (hot-reloaded) parsers
        with self._lock:
            for parser in self._dynamic_parsers:
                try:
                    result = parser(text)
                    if result:
                        return result
                except Exception:
                    continue

        # No parser matched — log for self-learning
        self._log_failed_format(text, provider)
        return []

    def reload(self) -> int:
        """Reload all dynamic parsers from disk. Returns count loaded."""
        with self._lock:
            self._dynamic_parsers.clear()
            self._load_dynamic_parsers()
            return len(self._dynamic_parsers)

    # ── Internal ──

    def _log_failed_format(self, text: str, provider: str):
        try:
            os.makedirs(os.path.dirname(FORMAT_LOG_PATH), exist_ok=True)
            entry = {
                "timestamp": time.time(),
                "provider": provider,
                "text": text[:2000],
            }
            with _format_log_lock:
                with open(FORMAT_LOG_PATH, "a") as f:
                    f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def _load_dynamic_parsers(self):
        """Import parser modules from PARSERS_DIR/*.py"""
        if not os.path.isdir(PARSERS_DIR):
            return
        for fname in sorted(os.listdir(PARSERS_DIR)):
            if fname.startswith("parser_") and fname.endswith(".py"):
                mod_name = fname[:-3]
                try:
                    mod = __import__(f"parsers.{mod_name}", fromlist=["parse"])
                    if hasattr(mod, "parse"):
                        self._dynamic_parsers.append(mod.parse)
                except Exception:
                    pass


# Global singleton
_detector = FormatDetector()


def detect_and_parse(text: str, provider: str = "unknown") -> List[Tuple[str, dict]]:
    """Convenience wrapper around FormatDetector.detect_and_parse."""
    return _detector.detect_and_parse(text, provider)


def reload_parsers() -> int:
    """Reload dynamic parsers from disk. Returns count loaded."""
    return _detector.reload()


def add_dynamic_parser(parser_fn: Callable) -> None:
    """Hot-reload a new parser function at runtime."""
    _detector._dynamic_parsers.append(parser_fn)
