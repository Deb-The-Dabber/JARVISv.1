import threading
import time

_cache = {}
_lock = threading.Lock()
_hits = 0
_misses = 0


def get_cached(key: str) -> tuple:
    global _hits, _misses
    with _lock:
        if key in _cache:
            value, expiry = _cache[key]
            if time.time() < expiry:
                _hits += 1
                return (True, value)
            del _cache[key]
        _misses += 1
    return (False, None)


def set_cached(key: str, value, ttl_seconds: int):
    with _lock:
        _cache[key] = (value, time.time() + ttl_seconds)


def invalidate(key: str):
    with _lock:
        _cache.pop(key, None)


def clear_cache():
    global _cache, _hits, _misses
    with _lock:
        _cache.clear()
        _hits = 0
        _misses = 0


def get_cache_stats() -> dict:
    with _lock:
        return {
            "entries": len(_cache),
            "hits": _hits,
            "misses": _misses,
            "hit_ratio": round(_hits / (_hits + _misses), 3) if (_hits + _misses) > 0 else 0,
        }


def cache_result(ttl_seconds: int):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            cache_key = f"{fn.__name__}:{args}:{kwargs}"
            found, cached = get_cached(cache_key)
            if found:
                return cached
            result = fn(*args, **kwargs)
            set_cached(cache_key, result, ttl_seconds)
            return result
        return wrapper
    return decorator
