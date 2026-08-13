"""Phase 2A routing policy — deterministic, explainable provider selection.

Pure module (no network, no brain imports): capability profiles, hard
eligibility gates, and an explicit scoring function that produces a
deterministic candidate ordering plus an explanation dict for telemetry.

Design rules (reviewer-locked, Phase 2A):
  * Hard eligibility gates FIRST: unavailable or low-health providers are
    INVALID — they never receive a score. Availability/health are filters,
    not scored dimensions.
  * No magic weights: all weights are named module constants, logged with
    every decision.
  * Capability profiles are LOGGED PRIORS (input priors for the later
    2C learned-router calibration), not hardwired "winner" rules.
  * Deterministic tie-break: score desc, then provider name asc.
"""

from __future__ import annotations

import math
from typing import Any

# ── Capability profiles (0..1 fit per dimension).
# Across-dimension vectors, deliberately NO single "winner" dimension.
# Estimated price per 1M tokens (USD) — update as rates change.
PROVIDER_PROFILES: dict[str, dict[str, float | tuple[float, float]]] = {
    "nemotron_ultra": {
        "coding": 0.92,
        "reasoning": 0.95,
        "tool_use": 0.98,
        "chat": 0.90,
        "chat_fast": 0.40,
        "base_latency_ms": 1500,
        "price": (2.00, 8.00),
    },
    "gemini": {
        "coding": 0.85,
        "reasoning": 0.90,
        "tool_use": 0.96,
        "chat": 0.95,
        "chat_fast": 0.72,
        "base_latency_ms": 900,
        "price": (0.15, 0.60),
    },
    "groq": {
        "coding": 0.78,
        "reasoning": 0.82,
        "tool_use": 0.90,
        "chat": 0.95,
        "chat_fast": 0.98,
        "base_latency_ms": 350,
        "price": (0.80, 0.80),
    },
    "nvidia_nim_tier_5": {
        "coding": 0.80,
        "reasoning": 0.84,
        "tool_use": 0.88,
        "chat": 0.90,
        "chat_fast": 0.62,
        "base_latency_ms": 700,
        "price": (1.50, 6.00),
    },
    "nvidia_nim_tier_6": {
        "coding": 0.97,
        "reasoning": 0.94,
        "tool_use": 0.92,
        "chat": 0.88,
        "chat_fast": 0.50,
        "base_latency_ms": 2000,
        "price": (1.60, 7.00),
    },
    "openrouter": {
        "coding": 0.92,
        "reasoning": 0.89,
        "tool_use": 0.80,
        "chat": 0.84,
        "chat_fast": 0.55,
        "base_latency_ms": 4000,
        "price": (0.50, 0.50),
    },
    "pollinations": {
        "coding": 0.60,
        "reasoning": 0.65,
        "tool_use": 0.55,
        "chat": 0.80,
        "chat_fast": 0.40,
        "base_latency_ms": 5000,
        "price": (0.0, 0.0),
    },
    "local_nn": {
        "coding": 0.35,
        "reasoning": 0.40,
        "tool_use": 0.30,
        "chat": 0.75,
        "chat_fast": 0.75,
        "base_latency_ms": 200,
        "price": (0.0, 0.0),
    },
}

# Per-intent dimension weights: intent -> (dimension, weight) pairs.
_INTENT_DIMS: dict[str, list[tuple[str, float]]] = {
    "coding": [("coding", 1.0), ("tool_use", 0.5), ("reasoning", 0.4)],
    "reasoning": [("reasoning", 1.0), ("coding", 0.4), ("tool_use", 0.3)],
    "tool_use": [("tool_use", 1.0), ("reasoning", 0.4), ("coding", 0.3)],
    "automation": [("tool_use", 1.0), ("reasoning", 0.4), ("coding", 0.3)],
    "self_mod": [("coding", 0.9), ("tool_use", 0.6), ("reasoning", 0.4)],
    "chat": [("reasoning", 0.7), ("tool_use", 0.5), ("chat", 0.4)],
    # Low-effort chat: fast conversational replies are the whole point.
    "chat_fast": [("chat_fast", 1.0), ("chat", 0.3)],
}

# Scoring weights (named, no magic in the code path).
W_CAPABILITY = 0.5
W_LATENCY = 0.2
W_COST = 0.2
W_HEALTH = 0.1

# Hard eligibility gate: providers below this health are INVALID.
HEALTH_MIN = 30.0

# Latency bands (ms) -> factor; unknown latency is not penalized.
# Sub-second resolution lets low-effort routing tell 350ms chat from 900ms chat.
_LATENCY_BANDS = [
    (300, 1.00),
    (600, 0.99),
    (1000, 0.97),
    (3000, 0.94),
    (8000, 0.90),
    (20000, 0.80),
    (float("inf"), 0.70),
]

# When daily budget headroom drops below this fraction, expensive providers
# get a cost penalty (see score_candidates `budget_warning` flag).
BUDGET_WARNING_HEADROOM = 0.25
_COST_PENALTY_FACTOR = 0.7

# Cheap-classifier output contract: it MUST never contain a provider name.
CLASSIFIER_KEYS = ("intent", "fine_intent", "complexity", "tool_required", "confidence")


def capability_fit(intent: str, profile: dict[str, Any]) -> float:
    """Weighted fit of a provider profile against an intent (0..1).

    Never picks a provider — only produces a comparable number.
    """
    dims = _INTENT_DIMS.get(intent, _INTENT_DIMS["chat"])
    total_w = sum(w for _, w in dims)
    if total_w <= 0:
        return 0.5
    return sum(profile.get(dim, 0.5) * w for dim, w in dims) / total_w


def latency_factor(latency_ms: float | None) -> float:
    if latency_ms is None:
        return 1.0  # unknown latency: no penalty (do not guess)
    for band, factor in _LATENCY_BANDS:
        if latency_ms <= band:
            return factor
    return 0.7


def cost_factor(price: tuple[float, float] | None) -> float:
    """Relative-price factor: cheaper providers score higher.

    factor = 1 / (1 + ln(1 + price_ratio)) where price_ratio is this
    provider's price vs the cheapest known price. Free providers cap at 1.
    """
    if not price or (price[0] <= 0 and price[1] <= 0):
        return 1.0
    cheapest: float | None = None
    for p in PROVIDER_PROFILES.values():
        pp = p.get("price")
        if pp and (pp[0] > 0 or pp[1] > 0):
            ratio = pp[0] * 3 + pp[1]  # normalize: out tokens ~3x heavier
            if cheapest is None or ratio < cheapest:
                cheapest = ratio
    if cheapest is None:
        return 1.0
    ratio = price[0] * 3 + price[1]
    rel = max(ratio / cheapest, 1.0)
    return 1.0 / (1.0 + math.log1p(rel - 1.0))


def score_candidates(
    intent: str,
    candidates: list[dict[str, Any]],
    budget_warning: bool = False,
    weights: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Score candidates against an intent. Returns INVALID-first-free list.

    Each candidate dict supports:
      provider (str), health (float, default 100), latency_ms (float|None),
      available (bool, default True), price (tuple|None override)

    ``weights`` optionally overrides the global W_* scoring weights
    (e.g. latency-policy effort tiers). None = global defaults.

    Returns ordered list of dicts: {provider, score, components, status}
    where status is "eligible" or "INVALID" (with reason). INVALID entries
    keep their health/availability facts for telemetry but carry no score.
    """
    if weights:
        w_capability = weights.get("capability", W_CAPABILITY)
        w_latency = weights.get("latency", W_LATENCY)
        w_cost = weights.get("cost", W_COST)
        w_health = weights.get("health", W_HEALTH)
    else:
        w_capability, w_latency, w_cost, w_health = W_CAPABILITY, W_LATENCY, W_COST, W_HEALTH
    scored: list[dict[str, Any]] = []
    for cand in candidates:
        name = cand["provider"]
        profile = PROVIDER_PROFILES.get(name)
        if profile is None:
            profile = {**PROVIDER_PROFILES["pollinations"], "price": None}  # neutral priors
        price = cand.get("price") or profile.get("price")

        if cand.get("available") is False:
            scored.append(
                _entry(name, None, "INVALID", "unavailable", cand, price)
            )
            continue
        health = float(cand.get("health", 100.0))
        if health < HEALTH_MIN:
            scored.append(
                _entry(name, None, "INVALID", f"health {health:.0f} < {HEALTH_MIN:.0f}", cand, price)
            )
            continue

        fit = capability_fit(intent, profile)
        lat = latency_factor(cand.get("latency_ms"))
        cost = cost_factor(price)
        health_f = health / 100.0
        if budget_warning and price and price[0] + price[1] > 0:
            cost *= _COST_PENALTY_FACTOR

        score = (
            w_capability * fit + w_latency * lat + w_cost * cost + w_health * health_f
        )
        scored.append(
            _entry(
                name,
                round(score, 4),
                "eligible",
                None,
                cand,
                price,
                components={
                    "capability_fit": round(fit, 4),
                    "latency_factor": round(lat, 4),
                    "cost_factor": round(cost, 4),
                    "health_factor": round(health_f, 4),
                    "budget_warning": budget_warning,
                },
            )
        )

    eligible = [e for e in scored if e["status"] == "eligible"]
    eligible.sort(key=lambda e: (-e["score"], e["provider"]))
    invalid = [e for e in scored if e["status"] == "INVALID"]
    return eligible + invalid


def _entry(
    name: str,
    score: float | None,
    status: str,
    reason: str | None,
    cand: dict[str, Any],
    price,
    components: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "provider": name,
        "score": score,
        "status": status,
        "reason": reason,
        "components": components or {},
        "observed": {
            "health": cand.get("health", 100.0),
            "latency_ms": cand.get("latency_ms"),
            "available": cand.get("available") is not False,
        },
        "price": price,
    }


def parse_classifier_output(text: str) -> dict[str, Any] | None:
    """Parse the cheap classifier's JSON reply into a contract dict.

    The contract explicitly EXCLUDES provider names. Returns None on any
    parse failure or if the payload contains an unexpected key.
    """
    if not text:
        return None
    try:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        data = json_like_loads(text[start : end + 1])
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    unknown = set(data) - set(CLASSIFIER_KEYS)
    if unknown:
        return None
    for key in ("intent", "fine_intent"):
        if not isinstance(data.get(key), str) or not data[key]:
            return None
    result: dict[str, Any] = {"intent": data["intent"], "fine_intent": data.get("fine_intent")}
    try:
        result["complexity"] = int(data.get("complexity", 3)) if data.get("complexity") else 3
    except (TypeError, ValueError):
        result["complexity"] = 3
    result["tool_required"] = bool(data.get("tool_required"))
    try:
        conf = data.get("confidence")
        result["confidence"] = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        result["confidence"] = None
    return result


def json_like_loads(s: str) -> Any:
    import json

    return json.loads(s)
