from cache import _cache, cache_result


class TestCache:
    def teardown_method(self):
        _cache.clear()

    def test_basic_caching(self):
        calls = []

        @cache_result(ttl_seconds=10)
        def fn(x):
            calls.append(x)
            return x * 2

        assert fn(5) == 10
        assert calls == [5]
        assert fn(5) == 10
        assert calls == [5]

    def test_different_args(self):
        calls = []

        @cache_result(ttl_seconds=10)
        def fn(x):
            calls.append(x)
            return x * 2

        assert fn(5) == 10
        assert fn(7) == 14
        assert calls == [5, 7]

    def test_ttl_expiry(self):
        @cache_result(ttl_seconds=0)
        def fn(x):
            return x * 2

        assert fn(5) == 10
        assert fn(5) == 10

    def test_none_result(self):
        calls = []

        @cache_result(ttl_seconds=10)
        def fn():
            calls.append(1)
            return None

        assert fn() is None
        assert fn() is None
        assert len(calls) == 1
