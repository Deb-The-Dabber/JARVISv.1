import os

import config


def test_user_name():
    assert config.USER_NAME, "USER_NAME should not be empty"
    assert isinstance(config.USER_NAME, str)


def test_location():
    assert config.USER_CITY, "USER_CITY should not be empty"
    assert isinstance(config.USER_LAT, float)
    assert isinstance(config.USER_LON, float)
    assert -90 <= config.USER_LAT <= 90
    assert -180 <= config.USER_LON <= 180
    assert config.USER_TIMEZONE, "USER_TIMEZONE should not be empty"


def test_paths():
    assert config.HOME, "HOME should not be empty"
    assert os.path.isabs(config.HOME)
    assert config.JARVIS_DIR, "JARVIS_DIR should not be empty"
    # Paths should be under HOME
    assert config.MEMORY_DB_PATH.startswith(config.HOME)
    assert config.VECTOR_DB_PATH.startswith(config.HOME)
    assert config.AUDIT_DB_PATH.startswith(config.HOME)


def test_constants():
    assert config.SAMPLE_RATE == 16000
    assert config.RECORD_SAMPLE_RATE == 44100
    assert isinstance(config.GEMINI_DAILY_LIMIT, int)
    assert config.GEMINI_DAILY_LIMIT > 0
    assert isinstance(config.CACHE_WEATHER_TTL, int)
    assert isinstance(config.CACHE_SYSTEM_INFO_TTL, int)
    assert isinstance(config.CACHE_SEARCH_TTL, int)


def test_cache_ttls():
    assert config.CACHE_WEATHER_TTL >= 60
    assert config.CACHE_SYSTEM_INFO_TTL >= 30
    assert config.CACHE_SEARCH_TTL >= 30


def test_proactive_constants():
    assert config.PROACTIVE_CHECK_INTERVAL >= 5
    assert config.CPU_THRESHOLD == 80
    assert config.RAM_THRESHOLD == 85
    assert isinstance(config.MIN_SECONDS_BETWEEN_ALERTS, int)
    assert config.MIN_SECONDS_BETWEEN_ALERTS > 0


def test_default_browser():
    browser = os.getenv("JARVIS_DEFAULT_BROWSER", config.DEFAULT_BROWSER)
    assert browser, "DEFAULT_BROWSER should not be empty"


def test_screenshot_dirs():
    assert len(config.SCREENSHOT_DIRS) >= 2
    for d in config.SCREENSHOT_DIRS:
        assert d.startswith(config.HOME)


def test_supported_extensions():
    assert ".md" in config.SUPPORTED_EXTENSIONS
    assert ".txt" in config.SUPPORTED_EXTENSIONS
    assert ".pdf" in config.SUPPORTED_EXTENSIONS
    assert ".py" in config.SUPPORTED_EXTENSIONS
    assert ".js" in config.SUPPORTED_EXTENSIONS
