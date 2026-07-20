from config import (
    CACHE_SEARCH_TTL,
    CACHE_SYSTEM_INFO_TTL,
    CACHE_WEATHER_TTL,
    USER_LAT,
    USER_LON,
    USER_NAME,
    USER_TIMEZONE,
)


class TestConfig:
    def test_user_constants(self):
        assert USER_NAME == "Debasish"
        assert isinstance(USER_LAT, float)
        assert isinstance(USER_LON, float)
        assert USER_TIMEZONE == "America/Chicago"

    def test_cache_ttls_positive(self):
        assert CACHE_WEATHER_TTL > 0
        assert CACHE_SYSTEM_INFO_TTL > 0
        assert CACHE_SEARCH_TTL > 0
