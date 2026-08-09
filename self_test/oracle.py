"""Bug oracle: objective heuristic detectors + optional LLM triage review.

Heuristics are deterministic and high-precision (provider errors, tool-call
errors, timeouts). The LLM review is explicitly a *triage assistant* — it
surfaces "possible issues" for the user to confirm or dismiss, never a verdict.
"""

import datetime
import json
import os
import re
import time

from agent import _sanitize_goal as _redact_pii

from .findings import Finding

TIMEOUT_SECONDS_ENV = "JARVIS_SELF_TEST_TIMEOUT_SECONDS"
DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_EXCERPT_ENTRIES = 150
MAX_EXCERPT_CHARS = 12000
LLM_REVIEW_CATEGORY = "llm_review"


def timeout_threshold() -> float:
    try:
        return float(os.getenv(TIMEOUT_SECONDS_ENV, str(DEFAULT_TIMEOUT_SECONDS)))
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def load_entries(hours: int = 24, limit: int = 5000, path: str | None = None) -> list[dict]:
    """Load request + tool_call entries from jarvis.jsonl within the window."""
    if path is None:
        from jarvis_logger import LOG_FILE

        path = LOG_FILE
    cutoff = time.time() - hours * 3600
    entries = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = e.get("ts", "")
                try:
                    ts_epoch = datetime.datetime.fromisoformat(ts).timestamp()
                except (ValueError, TypeError):
                    continue
                if ts_epoch >= cutoff:
                    entries.append(e)
                if len(entries) >= limit:
                    break
    except OSError:
        pass
    return entries


# ─────────────────────────────────────────────
# HEURISTIC DETECTORS (objective)
# ─────────────────────────────────────────────


def detect_from_entries(entries: list[dict], threshold: float | None = None) -> list[Finding]:
    """Run all heuristic detectors over logged entries."""
    threshold = threshold if threshold is not None else timeout_threshold()
    findings: list[Finding] = []

    for e in entries:
        if e.get("type") == "tool_call":
            err = e.get("error")
            if err:
                findings.append(
                    Finding(
                        severity="warning",
                        category="tool_error",
                        title=f"Tool call failed: {e.get('tool', 'unknown')}",
                        detail=str(err)[:500],
                        source="log",
                        evidence={"tool": e.get("tool", ""), "request_id": e.get("request_id", "")},
                    )
                )
            continue

        # Request entries
        if e.get("error"):
            findings.append(
                Finding(
                    severity="warning",
                    category="provider_error",
                    title=f"Request error: {str(e['error'])[:120]}",
                    detail=str(e["error"])[:500],
                    source="log",
                    evidence={
                        "provider": e.get("provider", ""),
                        "request_id": e.get("request_id", ""),
                        "intent": e.get("intent", ""),
                    },
                )
            )

        latency = e.get("latency_seconds") or 0
        if latency > threshold:
            findings.append(
                Finding(
                    severity="warning",
                    category="timeout",
                    title=f"Slow response: {latency:.0f}s (>{threshold:.0f}s)",
                    detail=f"Request took {latency:.1f}s via {e.get('provider', '?')}",
                    source="log",
                    evidence={
                        "latency_seconds": round(latency, 2),
                        "provider": e.get("provider", ""),
                        "intent": e.get("intent", ""),
                        "tools": e.get("tool_calls", []),
                    },
                )
            )

        if e.get("intent") in ("tool_use", "automation") and not (e.get("reply_preview") or "").strip():
            findings.append(
                Finding(
                    severity="info",
                    category="empty_reply",
                    title="Empty reply for tool request",
                    detail=f"Request '{str(e.get('user_message_preview', ''))[:80]}' produced no visible reply.",
                    source="log",
                    evidence={"request_id": e.get("request_id", "")},
                )
            )

    return findings


# ─────────────────────────────────────────────
# LLM TRIAGE REVIEW (possible issues, needs user confirmation)
# ─────────────────────────────────────────────


def _default_ask(prompt: str) -> str:
    from brain import ask_with_tools

    return ask_with_tools(prompt)


_ask_llm = _default_ask


def build_excerpt(
    entries: list[dict],
    max_entries: int = MAX_EXCERPT_ENTRIES,
    max_chars: int = MAX_EXCERPT_CHARS,
) -> str:
    """Build a redacted, compact excerpt of log entries for LLM review."""
    lines = []
    for e in entries:
        if e.get("type") == "tool_call":
            if e.get("error"):
                lines.append(f"[tool_call] {e.get('tool', '?')} error: {str(e.get('error', ''))[:200]}")
            continue
        parts = [f"[{str(e.get('ts', ''))[11:19]}] intent={e.get('intent', '?')}"]
        parts.append(f"provider={e.get('provider', '?')}")
        parts.append(f"latency={e.get('latency_seconds', 0)}s")
        if e.get("tool_calls"):
            parts.append(f"tools={e.get('tool_calls')}")
        if e.get("error"):
            parts.append(f"error={str(e['error'])[:200]}")
        user = str(e.get("user_message_preview", ""))[:160]
        if user:
            parts.append(f'user="{user}"')
        reply = str(e.get("reply_preview", ""))[:160]
        if reply:
            parts.append(f'reply="{reply}"')
        lines.append(" ".join(parts))
        if len(lines) >= max_entries:
            break

    excerpt = "\n".join(_redact_pii(line) for line in lines)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars] + "\n...truncated"
    return excerpt


_ISSUE_LINE_RE = re.compile(
    r"^\s*[-*]?\s*\[?(critical|warning|info|high|medium|low)\]?\s*[:.)]?\s*(.{5,})$",
    re.IGNORECASE,
)


def analyze_with_llm(entries: list[dict], hours: int = 24) -> list[Finding]:
    """Ask the LLM to review redacted logs and surface possible issues.

    Findings are labeled ``llm_review`` and start ``open`` — they are triage
    suggestions that the user confirms or dismisses.
    """
    excerpt = build_excerpt(entries)
    if not excerpt.strip():
        return []
    prompt = (
        "You are JARVIS's quality reviewer. Below is a redacted excerpt of JARVIS's own runtime logs "
        f"(recent {hours}h window).\n"
        "Find genuine bugs: crashes, exceptions, tool failures, timeouts, empty replies for tool requests, "
        "provider errors, or safety anomalies.\n"
        "Do NOT report routine things (normal weather checks, ordinary chat, expected latency).\n"
        "Reply with issues, one per line, in exactly this format:\n"
        "[severity: critical|warning|info] <short title> — <evidence from the log>\n"
        "If you find nothing, reply exactly: NO ISSUES\n\n"
        f"LOGS:\n{excerpt}"
    )
    try:
        reply = _ask_llm(prompt)
    except Exception as e:
        return [
            Finding(
                severity="info",
                category=LLM_REVIEW_CATEGORY,
                title="LLM review unavailable",
                detail=f"Could not run log review: {e}",
                source="llm",
            )
        ]

    findings = []
    sev_map = {
        "critical": "critical",
        "warning": "warning",
        "high": "warning",
        "medium": "info",
        "low": "info",
        "info": "info",
    }
    for line in (reply or "").splitlines():
        m = _ISSUE_LINE_RE.match(line)
        if not m:
            continue
        severity = sev_map.get(m.group(1).lower(), "info")
        title = m.group(2).strip()
        if title:
            findings.append(
                Finding(
                    severity=severity,
                    category=LLM_REVIEW_CATEGORY,
                    title=title[:160],
                    detail=line.strip()[:500],
                    source="llm",
                )
            )

    if not findings and (reply or "").strip().upper() != "NO ISSUES":
        findings.append(
            Finding(
                severity="info",
                category=LLM_REVIEW_CATEGORY,
                title="LLM review: unparsed response",
                detail=(reply or "")[:400],
                source="llm",
            )
        )
    return findings


def scan(hours: int = 24, use_llm: bool = True, path: str | None = None) -> tuple[list[Finding], list[Finding], int]:
    """Run heuristic + optional LLM scan. Returns (heuristic_findings, llm_findings, entries_scanned)."""
    entries = load_entries(hours=hours, path=path)
    if not entries:
        return [], [], 0
    heuristic = detect_from_entries(entries)
    llm = analyze_with_llm(entries, hours=hours) if use_llm else []
    return heuristic, llm, len(entries)
