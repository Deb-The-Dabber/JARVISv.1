"""Structured decision logging for JARVIS cognitive control loop.

Records every decision point with measurable metadata, not post-hoc rationalizations.
"""

from __future__ import annotations

import contextvars
import json
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

# Request-scoped ID using contextvars (works for both threads and async)
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")

# Thread-safe JSONL writer
_LOG_PATH = Path(os.path.expanduser("~/.jarvis/logs/decisions.jsonl"))
_log_lock = threading.Lock()

# A/B bypass switch: JARVIS_INSTRUMENTATION=0 disables ALL decision logging
# without touching routing, providers, memory, tools, or model selection.
INSTRUMENTATION_ENABLED = os.getenv("JARVIS_INSTRUMENTATION", "1").lower() not in (
    "0",
    "false",
    "no",
    "off",
)


def new_request_id() -> str:
    """Generate and set a new request ID for the current context."""
    rid = str(uuid.uuid4())[:12]
    _request_id_var.set(rid)
    return rid


def get_request_id() -> str:
    """Get the current request ID, or empty string if none set."""
    return _request_id_var.get("")


def clear_request_id() -> None:
    """Clear the request ID for the current context."""
    _request_id_var.set("")


@dataclass(order=False)
class DecisionEvent:
    """Single decision event in the cognitive loop.

    Fields ordered to satisfy Python dataclass requirements:
    non-default fields before default fields.
    """

    phase: Literal[
        "understand",
        "plan",
        "act",
        "verify",
        "repair",
        "respond",
        "safety",
    ]
    decision: str

    # Core identifiers
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    request_id: str = field(default_factory=get_request_id)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Decision source: what subsystem/mechanism actually made the decision
    decision_source: str = ""

    # Measurable decision inputs (not post-hoc confidence)
    measurable_inputs: dict[str, Any] = field(default_factory=dict)

    # Optional model-generated explanation (treated as untrusted narrative)
    model_explanation: str | None = None

    # Outcome and latency
    outcome: Literal["success", "failure", "partial", "pending", "skipped"] = "pending"
    latency_ms: int = 0

    # Error if any
    error: str = ""

    def to_jsonl(self) -> str:
        """Serialize to JSONL line."""
        return json.dumps(
            {
                "event_id": self.event_id,
                "request_id": self.request_id,
                "timestamp": self.timestamp,
                "phase": self.phase,
                "decision": self.decision,
                "decision_source": self.decision_source,
                "measurable_inputs": self.measurable_inputs,
                "model_explanation": self.model_explanation,
                "outcome": self.outcome,
                "latency_ms": self.latency_ms,
                "error": self.error,
            },
            separators=(",", ":"),
        )


def _ensure_log_dir() -> None:
    """Ensure log directory exists."""
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def log_event(event: DecisionEvent) -> None:
    """Thread-safe append to JSONL. Never blocks the main loop on failure."""
    if not INSTRUMENTATION_ENABLED:
        return
    if not event.request_id:
        event.request_id = get_request_id()
    try:
        _ensure_log_dir()
        with _log_lock:
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(event.to_jsonl() + "\n")
    except Exception as e:
        # Fail silently — logging must never break the main loop
        try:
            from brain import _debug

            _debug(f"[DecisionLog] write failed: {e}")
        except Exception:
            pass


_PhaseT = Literal["understand", "plan", "act", "verify", "repair", "respond", "safety"]
_OutcomeT = Literal["success", "failure", "partial", "pending", "skipped"]


def log_decision(
    phase: _PhaseT,
    decision: str,
    decision_source: str = "",
    measurable_inputs: dict[str, Any] | None = None,
    model_explanation: str | None = None,
    outcome: _OutcomeT = "pending",
    latency_ms: int = 0,
    error: str = "",
    **extra_metadata,
) -> None:
    """Convenience function for inline decision logging."""
    if not INSTRUMENTATION_ENABLED:
        return
    measurable = measurable_inputs or {}
    if extra_metadata:
        measurable.update(extra_metadata)

    event = DecisionEvent(
        phase=phase,
        decision=decision,
        decision_source=decision_source,
        measurable_inputs=measurable,
        model_explanation=model_explanation,
        outcome=outcome,
        latency_ms=latency_ms,
        error=error,
    )
    log_event(event)


def load_recent_decisions(limit: int = 100, request_id: str | None = None) -> list[dict]:
    """Load recent decision events, optionally filtered by request_id."""
    if not INSTRUMENTATION_ENABLED:
        return []
    if not _LOG_PATH.exists():
        return []
    events = []
    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if request_id is None or event.get("request_id") == request_id:
                        events.append(event)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return events[-limit:]


def get_decision_trace(request_id: str) -> list[dict]:
    """Get full decision trace for a single request, ordered by timestamp."""
    events = load_recent_decisions(limit=1000, request_id=request_id)
    # Sort by timestamp
    events.sort(key=lambda e: e.get("timestamp", ""))
    return events
