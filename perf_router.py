import threading
import time

_router_lock = threading.Lock()
_provider_latency: dict[str, list[float]] = {}
_provider_errors: dict[str, int] = {}
_provider_requests: dict[str, int] = {}
_semantic_cache: dict[str, tuple[str, float]] = {}
_semantic_cache_hits = 0
_semantic_cache_misses = 0


def record_latency(provider: str, seconds: float):
    with _router_lock:
        if provider not in _provider_latency:
            _provider_latency[provider] = []
        _provider_latency[provider].append(seconds)
        if len(_provider_latency[provider]) > 100:
            _provider_latency[provider] = _provider_latency[provider][-100:]
        _provider_requests[provider] = _provider_requests.get(provider, 0) + 1


def record_error(provider: str):
    with _router_lock:
        _provider_errors[provider] = _provider_errors.get(provider, 0) + 1


def get_p50(provider: str) -> float:
    vals = sorted(_provider_latency.get(provider, []))
    if not vals:
        return 0.0
    return vals[len(vals) // 2]


def get_p99(provider: str) -> float:
    vals = sorted(_provider_latency.get(provider, []))
    if not vals:
        return 0.0
    return vals[int(len(vals) * 0.99)]


def get_error_rate(provider: str) -> float:
    reqs = _provider_requests.get(provider, 0)
    if reqs == 0:
        return 0.0
    return _provider_errors.get(provider, 0) / reqs


def get_fastest_provider(candidates: list[str]) -> str | None:
    best = None
    best_latency = float("inf")
    with _router_lock:
        for p in candidates:
            vals = _provider_latency.get(p, [])
            if vals:
                avg = sum(vals) / len(vals)
                if avg < best_latency:
                    best_latency = avg
                    best = p
        if not best and candidates:
            best = candidates[0]
    return best


def get_provider_stats() -> dict:
    with _router_lock:
        stats = {}
        all_providers = set(_provider_latency.keys()) | set(_provider_errors.keys())
        for p in sorted(all_providers):
            stats[p] = {
                "requests": _provider_requests.get(p, 0),
                "errors": _provider_errors.get(p, 0),
                "error_rate": round(get_error_rate(p), 3),
                "p50_latency": round(get_p50(p), 3),
                "p99_latency": round(get_p99(p), 3),
            }
        return stats


# ── Semantic cache ──

SIMPLE_INTENTS = {"weather", "system", "timer", "time"}


def is_simple_intent(intent: str) -> bool:
    return intent.lower() in SIMPLE_INTENTS


def _intent_to_ttl(intent: str, default_ttl: int = 60) -> int:
    ttl_map = {
        "weather": 300,
        "system": 60,
        "timer": 30,
        "chat": 300,
    }
    return ttl_map.get(intent, default_ttl)


def semantic_cache_key(prompt: str, intent: str) -> str:
    try:
        from vector_memory import get_embedding
        emb = get_embedding(prompt)
        emb_str = str(hash(tuple(emb)))
        return f"{intent}:{emb_str}"
    except Exception:
        return f"{intent}:{prompt.strip().lower()[:100]}"


def semantic_cache_get(prompt: str, intent: str) -> str | None:
    global _semantic_cache_hits, _semantic_cache_misses
    key = semantic_cache_key(prompt, intent)
    with _router_lock:
        if key in _semantic_cache:
            value, expiry = _semantic_cache[key]
            if time.time() < expiry:
                _semantic_cache_hits += 1
                return value
            del _semantic_cache[key]
        _semantic_cache_misses += 1
    return None


def semantic_cache_set(prompt: str, intent: str, response: str):
    key = semantic_cache_key(prompt, intent)
    ttl = _intent_to_ttl(intent)
    with _router_lock:
        _semantic_cache[key] = (response, time.time() + ttl)


def get_semantic_cache_stats() -> dict:
    with _router_lock:
        total = _semantic_cache_hits + _semantic_cache_misses
        return {
            "entries": len(_semantic_cache),
            "hits": _semantic_cache_hits,
            "misses": _semantic_cache_misses,
            "hit_ratio": round(_semantic_cache_hits / total, 3) if total > 0 else 0,
        }
