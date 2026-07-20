import threading
import time

from cache import (
    cache_result,
    clear_cache,
    get_cache_stats,
    get_cached,
    invalidate,
    set_cached,
)


def setup_function():
    clear_cache()


def test_set_and_get():
    set_cached("key1", "value1", 60)
    found, val = get_cached("key1")
    assert found is True
    assert val == "value1"


def test_get_missing():
    found, val = get_cached("nonexistent")
    assert found is False
    assert val is None


def test_expiry():
    set_cached("key1", "value1", ttl_seconds=0)
    time.sleep(0.01)
    found, val = get_cached("key1")
    assert found is False
    assert val is None


def test_invalidate():
    set_cached("key1", "value1", 60)
    invalidate("key1")
    found, val = get_cached("key1")
    assert found is False


def test_clear_cache():
    set_cached("a", 1, 60)
    set_cached("b", 2, 60)
    clear_cache()
    assert get_cached("a")[0] is False
    assert get_cached("b")[0] is False


def test_cache_stats():
    clear_cache()
    stats = get_cache_stats()
    assert stats["entries"] == 0
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["hit_ratio"] == 0.0

    get_cached("missing")
    set_cached("x", 1, 60)
    get_cached("x")

    stats = get_cache_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_ratio"] == 0.5


def test_cache_result_decorator():
    call_count = 0

    @cache_result(ttl_seconds=60)
    def expensive(x):
        nonlocal call_count
        call_count += 1
        return x * 2

    assert expensive(5) == 10
    assert call_count == 1
    assert expensive(5) == 10
    assert call_count == 1
    assert expensive(7) == 14
    assert call_count == 2


def test_concurrent_access():
    errors = []

    def worker():
        try:
            for i in range(50):
                set_cached(f"k{i}", i, 10)
                get_cached(f"k{i}")
                invalidate(f"k{i}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Concurrent errors: {errors}"
