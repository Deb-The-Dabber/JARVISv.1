"""Latency policy — effort-aware, provider-agnostic routing (vNext).

Answers the question: "How much intelligence does this request actually
need?" It maps a request to a *task profile* (effort level, thinking budget,
latency/cost/capability constraints) — never to a concrete provider. The
shared scorer (``routing_policy.score_candidates``) then picks the cheapest
capable model from the ``PROVIDER_PROFILES`` registry, so adding or removing
models later requires registry edits only.

Provider names are FORBIDDEN in this module by design. All routing decisions
are made from profile metadata and the request itself.
"""

from __future__ import annotations

# Effort -> (capability, latency, cost, health) scoring weights.
# "low" favors fast/cheap capable providers; "high" favors raw capability.
EFFORT_WEIGHTS: dict[str, dict[str, float]] = {
    "low": {"capability": 0.30, "latency": 0.50, "cost": 0.10, "health": 0.10},
    "normal": {"capability": 0.50, "latency": 0.20, "cost": 0.20, "health": 0.10},
    "high": {"capability": 0.60, "latency": 0.15, "cost": 0.15, "health": 0.10},
}

# Thinking/CoT budget by effort level (0 = thinking off).
THINKING_BUDGETS: dict[str, int] = {"low": 0, "normal": 512, "high": 2048}

# Long-thought questions — never treated as idle chatter.
REASONING_HINTS = (
    "why ", "why's", "explain", "analyze", "compare", "evaluate", "strategy",
    "design ", "pros and cons", "how do i ", "how can i ", "how does ",
    "how would ", "write me a", "write a ", "build a ", "create a ",
    "fix the", "debug the",
)

# Imperative task verbs — "open X" is work, not chatter.
TASK_VERBS = (
    "open", "launch", "play", "send", "run", "create", "write", "install",
    "fix", "build", "deploy", "commit", "push", "quit", "click", "type",
    "search", "remind", "timer",
)

# Tool-able topics that can short-circuit from local data (0 LLM calls).
SIMPLE_TOOL_HINTS = (
    "weather", "temperature", "humidity", "rain", "snow", "forecast",
    "my ip", "time is it", "what time", "date", "cpu", "ram", "disk",
    "system usage", "spotify", "calendar", "timers", "my timers",
)

# A simple tool hint alongside research intent is NOT simple.
RESEARCH_HINTS = (
    "search", "look up", "research", "history", "trends", "patterns",
    "analysis", "compare",
)


def task_profile(intent: str, text: str, complexity: int) -> dict:
    """Map a request to a provider-agnostic task profile.

    Returns: {effort, thinking_budget, latency_cap_ms, capability_floor,
    short_circuit}.
    """
    t = (text or "").strip().lower()

    if intent == "chat":
        is_task = any(v in t for v in TASK_VERBS)
        is_reasoning = any(p in t for p in REASONING_HINTS)
        if len(t) <= 80 and not is_task and not is_reasoning:
            return dict(
                effort="low",
                thinking_budget=THINKING_BUDGETS["low"],
                latency_cap_ms=1200,
                capability_floor=0.60,
                short_circuit=False,
            )
        return dict(
            effort="normal",
            thinking_budget=THINKING_BUDGETS["normal"],
            latency_cap_ms=None,
            capability_floor=None,
            short_circuit=False,
        )

    if intent == "tool_use":
        simple = any(k in t for k in SIMPLE_TOOL_HINTS)
        is_research = any(p in t for p in RESEARCH_HINTS)
        if simple and not is_research and complexity <= 4:
            return dict(
                effort="low",
                thinking_budget=THINKING_BUDGETS["low"],
                latency_cap_ms=1200,
                capability_floor=0.60,
                short_circuit=True,
            )
        return dict(
            effort="normal",
            thinking_budget=THINKING_BUDGETS["normal"],
            latency_cap_ms=None,
            capability_floor=None,
            short_circuit=False,
        )

    if intent in ("coding", "self_mod", "automation") or complexity >= 8:
        return dict(
            effort="high",
            thinking_budget=THINKING_BUDGETS["high"],
            latency_cap_ms=None,
            capability_floor=None,
            short_circuit=False,
        )

    return dict(
        effort="normal",
        thinking_budget=THINKING_BUDGETS["normal"],
        latency_cap_ms=None,
        capability_floor=None,
        short_circuit=False,
    )
