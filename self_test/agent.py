"""SelfTestAgent — runs background self-test scans and reports findings.

Phase 1 scope: log-analysis oracle only. Scans recent runtime logs with
objective heuristic detectors, optionally asks the LLM to surface possible
issues, persists findings, and streams progress to the terminal via the
event bus. No autonomous test execution, no exploration of real tools.

Trigger via chat ("test yourself") or terminal commands (test status, ...).
"""

import os
import re
import threading
import time
import uuid

from event_bus import publish

from . import findings as store
from . import oracle

DEFAULT_LOG_HOURS = 24
LLM_ENABLED_ENV = "JARVIS_SELF_TEST_LLM"
LLM_ENABLED_DEFAULT = True

_START_PATTERNS = [
    r"\btest (yourself|your(?: own)? (code|system|software|self))\b",
    r"\bself[- ]?test(?:ing)?\b",
    r"\b(check|look) (yourself|your (?:own )?code|your system) for bugs\b",
    r"\bfind bugs in (your|the) (code|system)\b",
    r"\b(?:run|start) (?:a )?self[- ]?test\b",
]


def llm_enabled() -> bool:
    return os.getenv(LLM_ENABLED_ENV, "1").lower() in ("1", "true", "yes", "on")


class SelfTestAgent:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._current: dict | None = None
        self._last_finished: dict | None = None

    # ── status / control ─────────────────────

    def is_running(self) -> bool:
        return bool(self._current and not self._current.get("finished_at"))

    def status(self) -> dict:
        with self._lock:
            current = dict(self._current) if self._current else None
        if current and current.get("finished_at"):
            current = None
        return {
            "running": current is not None,
            "current": current,
            "last_run": self._last_finished,
            "open_findings": len(store.list_findings(status=store.STATUS_OPEN, limit=100000)),
            "confirmed_findings": len(store.list_findings(status=store.STATUS_CONFIRMED, limit=100000)),
        }

    def stop(self) -> str:
        if not self.is_running():
            return "No self-test is currently running."
        self._stop.set()
        self._emit("Stop requested — finishing current scan...")
        return "Stop requested. The current scan will wind down."

    # ── run orchestration ────────────────────

    def run(self, hours: int | None = None, use_llm: bool | None = None) -> str:
        if self.is_running():
            rid = (self._current or {}).get("run_id", "?")
            return f"A self-test is already running (run {rid}). Use 'test status' for progress."
        hours = hours or DEFAULT_LOG_HOURS
        use_llm = llm_enabled() if use_llm is None else use_llm
        threading.Thread(target=self._run_scan, args=(hours, use_llm), daemon=True).start()
        return f"Self-test started in the background (window: last {hours}h). Use 'test status' for progress."

    def _emit(self, message: str, phase: str = ""):
        publish(
            "self_test",
            {
                "timestamp": time.time(),
                "message": message,
                "phase": phase,
                "run_id": (self._current or {}).get("run_id", ""),
            },
        )

    def _run_scan(self, hours: int, use_llm: bool):
        run_id = uuid.uuid4().hex[:12]
        self._stop.clear()
        self._current = {"run_id": run_id, "started_at": store._now(), "hours": hours, "use_llm": use_llm}
        self._emit(f"Self-test started (run {run_id}) — scanning last {hours}h of logs...", "scanning")

        heuristic: list[store.Finding] = []
        llm: list[store.Finding] = []
        scanned = 0
        try:
            entries = oracle.load_entries(hours=hours)
            scanned = len(entries)
            if not entries:
                self._emit("No recent logs found — nothing to analyze.", "done")
            else:
                self._emit(f"Loaded {scanned} log entries. Running heuristic detectors...", "scanning")
                heuristic = oracle.detect_from_entries(entries)
                for f in heuristic:
                    if self._stop.is_set():
                        break
                    store.add_finding(f)
                    self._emit(f"[{f.severity}] {f.title} (id {f.id})", "heuristics")
                self._emit(f"Heuristic scan complete: {len(heuristic)} finding(s).", "scanning")

                if use_llm and not self._stop.is_set():
                    self._emit("Asking LLM to review logs for possible issues...", "llm_review")
                    llm = oracle.analyze_with_llm(entries, hours=hours)
                    for f in llm:
                        if self._stop.is_set():
                            break
                        store.add_finding(f)
                        self._emit(f"[{f.severity}] {f.title} (id {f.id})", "llm_review")
        except Exception as e:
            self._emit(f"Self-test failed: {e}", "error")

        total = len(heuristic) + len(llm)
        finished = store._now()
        self._current.update({"finished_at": finished, "entries_scanned": scanned, "findings": total})
        self._last_finished = dict(self._current)
        store.add_run(
            {
                "run_id": run_id,
                "started_at": self._current.get("started_at"),
                "finished_at": finished,
                "hours": hours,
                "use_llm": use_llm,
                "entries_scanned": scanned,
                "findings": total,
                "heuristic": len(heuristic),
                "llm": len(llm),
            }
        )
        self._emit(
            f"Self-test finished: {scanned} entries scanned, {total} finding(s) "
            f"({len(heuristic)} heuristic, {len(llm)} LLM review). Use 'test report' for details.",
            "done",
        )
        self._current = None

    # ── reporting ────────────────────────────

    def status_text(self) -> str:
        st = self.status()
        lines = ["Self-test status:"]
        if st["running"]:
            c = st["current"]
            lines.append(f"  RUNNING — run {c['run_id']} started {c['started_at'][11:19]}")
            lines.append(f"  Window: last {c['hours']}h | LLM review: {'on' if c['use_llm'] else 'off'}")
            lines.append("  Use 'test stop' to halt, 'test findings' to see what's found so far.")
        else:
            lines.append("  Idle.")
        if st["last_run"]:
            lr = st["last_run"]
            lines.append(
                f"  Last run: {lr['run_id']} at {lr.get('started_at', '?')[11:19]} — "
                f"{lr.get('entries_scanned', 0)} entries, {lr.get('findings', 0)} finding(s)"
            )
        lines.append(f"  Open: {st['open_findings']} | Confirmed: {st['confirmed_findings']}")
        return "\n".join(lines)

    def findings_text(self, status: str | None = None, limit: int = 30) -> str:
        items = store.list_findings(status=status, limit=limit)
        if not items:
            return "No findings recorded yet. Run 'test yourself' to scan for bugs."
        lines = [f"Findings ({len(items)}):"]
        for d in items:
            lines.append(
                f"  [{d['status']:9}] [{d['severity']:8}] {d['title'][:90]} (id {d['id']}, {d['created_at'][:16]})"
            )
        lines.append("Use 'test confirm <id>' or 'test dismiss <id>' to review.")
        return "\n".join(lines)

    def report(self, limit: int = 20) -> str:
        all_items = store.list_findings(limit=100000)
        open_items = [d for d in all_items if d["status"] == store.STATUS_OPEN]
        confirmed = [d for d in all_items if d["status"] == store.STATUS_CONFIRMED]
        by_sev = {"critical": 0, "warning": 0, "info": 0}
        for d in open_items + confirmed:
            by_sev[d["severity"]] = by_sev.get(d["severity"], 0) + 1
        lines = ["Self-test report:"]
        lines.append(
            f"  Runs: {len(store.list_runs(limit=100000))} | Open: {len(open_items)} | "
            f"Confirmed: {len(confirmed)} | "
            f"Severity: critical {by_sev['critical']}, warning {by_sev['warning']}, info {by_sev['info']}"
        )
        top = (open_items + confirmed)[:limit]
        for d in top:
            lines.append(f"  [{d['status']:9}] [{d['severity']:8}] {d['title'][:100]} (id {d['id']})")
        if not top:
            lines.append("  No findings to review.")
        return "\n".join(lines)

    def history_text(self, limit: int = 10) -> str:
        runs = store.list_runs(limit=limit)
        if not runs:
            return "No self-test runs yet."
        lines = [f"Last {len(runs)} self-test runs:"]
        for r in runs:
            lines.append(
                f"  {r['run_id']} — {r.get('started_at', '?')[:19]} | {r.get('entries_scanned', 0)} entries | "
                f"{r.get('findings', 0)} findings ({r.get('heuristic', 0)}h/{r.get('llm', 0)}llm)"
            )
        return "\n".join(lines)

    def set_status(self, finding_id: str, action: str) -> str:
        existing = store.get_finding(finding_id)
        if not existing:
            return f"No finding with id {finding_id}. Use 'test findings' to list them."
        new_status = store.STATUS_CONFIRMED if action == "confirm" else store.STATUS_DISMISSED
        if store.update_finding_status(finding_id, new_status):
            self._emit(f"{action.title()}ed finding {finding_id}: {existing.get('title', '')[:60]}")
            return f"Finding {finding_id} {new_status}."
        return "Could not update finding."


_agent = SelfTestAgent()


def get_agent() -> SelfTestAgent:
    return _agent


def handle_command(text: str) -> str:
    """Route natural-language self-test commands to the agent."""
    t = (text or "").strip().lower()

    m = re.search(r"\b(confirm|dismiss)\s+(?:bug\s+|finding\s+|issue\s+)?([a-f0-9]{12})\b", t)
    if m:
        return _agent.set_status(m.group(2), m.group(1))

    if any(re.search(p, t) for p in _START_PATTERNS) or t in ("test", "test run", "run self test"):
        return _agent.run()
    if t in ("test logs", "test heuristics", "test scan"):
        return _agent.run(use_llm=False)
    if t in ("test stop", "stop self test", "cancel self test"):
        return _agent.stop()
    if t in ("test status", "test progress", "self test status"):
        return _agent.status_text()
    if t in ("test report", "bug report", "self test report"):
        return _agent.report()
    if t in ("test findings", "list findings", "self test findings", "test bugs"):
        return _agent.findings_text()
    if t in ("test history", "self test history"):
        return _agent.history_text()

    return (
        "Self-test commands: 'test yourself' (full scan), 'test logs' (heuristics only), "
        "'test status', 'test report', 'test findings', 'test history', 'test stop', "
        "'test confirm <id>', 'test dismiss <id>'."
    )
