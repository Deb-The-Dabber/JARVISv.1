"""Self-test: JARVIS analyzes its own runtime logs for bugs and reports back.

Phase 1 scope: log-analysis oracle (heuristic detectors + optional LLM
triage review), findings store, background runs, terminal/chat reporting.
Exploration / autonomous test execution is intentionally out of scope.
"""

from .agent import get_agent, handle_command

__all__ = ["get_agent", "handle_command"]
