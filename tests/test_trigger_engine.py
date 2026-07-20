import datetime
import os
import tempfile

import pytest

from trigger_engine import (
    _compute_next_fire,
    _cron_field_matches,
    _cron_matches,
    _parse_cron,
    _parse_interval,
    create_trigger,
    delete_trigger,
    disable_trigger,
    enable_trigger,
    fire_event,
    fire_trigger,
    get_trigger,
    get_trigger_history,
    init_db,
    list_triggers,
    update_trigger,
)

DB = tempfile.mktemp(suffix=".db")


def _patch_db():
    import trigger_engine as te

    te.DB_PATH = DB


@pytest.fixture(autouse=True)
def setup():
    _patch_db()
    init_db()
    yield
    if os.path.exists(DB):
        os.unlink(DB)


class TestIntervalParsing:
    def test_seconds(self):
        assert _parse_interval("30s") == 30
        assert _parse_interval("5 sec") == 5
        assert _parse_interval("10 seconds") == 10

    def test_minutes(self):
        assert _parse_interval("5m") == 300
        assert _parse_interval("1 min") == 60
        assert _parse_interval("10 minutes") == 600

    def test_hours(self):
        assert _parse_interval("2h") == 7200
        assert _parse_interval("1 hour") == 3600

    def test_days(self):
        assert _parse_interval("1d") == 86400
        assert _parse_interval("7 days") == 604800

    def test_bare_number(self):
        assert _parse_interval("42") == 42

    def test_invalid(self):
        with pytest.raises(ValueError):
            _parse_interval("abc")
        with pytest.raises(ValueError):
            _parse_interval("")


class TestCronParsing:
    def test_valid(self):
        expr = _parse_cron("0 8 * * *")
        assert len(expr) == 5

    def test_invalid_field_count(self):
        with pytest.raises(ValueError):
            _parse_cron("0 8 * *")

    def test_complex_expr(self):
        expr = _parse_cron("*/15 9-17 * * 1-5")
        assert expr == ["*/15", "9-17", "*", "*", "1-5"]


class TestCronFieldMatching:
    def test_wildcard(self):
        assert _cron_field_matches("*", 5) is True

    def test_single_value(self):
        assert _cron_field_matches("5", 5) is True
        assert _cron_field_matches("5", 4) is False

    def test_range(self):
        assert _cron_field_matches("9-17", 12) is True
        assert _cron_field_matches("9-17", 8) is False

    def test_step(self):
        assert _cron_field_matches("*/15", 0) is True
        assert _cron_field_matches("*/15", 15) is True
        assert _cron_field_matches("*/15", 16) is False
        assert _cron_field_matches("2/10", 2) is True
        assert _cron_field_matches("2/10", 12) is True

    def test_comma_separated(self):
        assert _cron_field_matches("1,3,5", 3) is True
        assert _cron_field_matches("1,3,5", 2) is False


class TestCronMatching:
    def test_full_expr(self):
        dt = datetime.datetime(2026, 6, 21, 8, 0)
        expr = _parse_cron("0 8 * * *")
        assert _cron_matches(expr, dt) is True

    def test_non_match(self):
        dt = datetime.datetime(2026, 6, 21, 8, 30)
        expr = _parse_cron("0 8 * * *")
        assert _cron_matches(expr, dt) is False

    def test_weekday(self):
        dt = datetime.datetime(2026, 6, 22, 9, 0)
        expr = _parse_cron("0 9 * * 0")
        assert _cron_matches(expr, dt) is False
        expr2 = _parse_cron("0 9 * * 1")
        assert _cron_matches(expr2, dt) is True


class TestNextFire:
    def test_interval(self):
        nf = _compute_next_fire("interval", "30m")
        assert nf is not None
        dt = datetime.datetime.fromisoformat(nf)
        diff = (dt - datetime.datetime.now()).total_seconds()
        assert abs(diff - 1800) < 10

    def test_once_future(self):
        nf = _compute_next_fire("once", "2099-01-01T00:00:00")
        assert nf == "2099-01-01T00:00:00"

    def test_once_past(self):
        nf = _compute_next_fire("once", "2020-01-01T00:00:00")
        assert nf is None

    def test_cron(self):
        nf = _compute_next_fire("cron", "0 8 * * *")
        assert nf is not None
        dt = datetime.datetime.fromisoformat(nf)
        assert dt.hour == 8
        assert dt.minute == 0


class TestCRUD:
    def test_create(self):
        t = create_trigger("test", "interval", "30m", "tool", "get_weather")
        assert t["name"] == "test"
        assert t["trigger_type"] == "interval"
        assert t["action_type"] == "tool"
        assert t["enabled"] == 1
        assert t["next_fire"] is not None

    def test_create_duplicate_name(self):
        create_trigger("dup", "interval", "30m", "tool", "get_weather")
        with pytest.raises(ValueError):
            create_trigger("dup", "interval", "1h", "tool", "get_weather")

    def test_get(self):
        t = create_trigger("gettest", "once", "2099-06-01T00:00:00", "workflow", "system_report")
        fetched = get_trigger(t["id"])
        assert fetched is not None
        assert fetched["name"] == "gettest"

    def test_get_nonexistent(self):
        assert get_trigger(999) is None

    def test_list(self):
        create_trigger("a", "interval", "30m", "tool", "get_weather")
        create_trigger("b", "once", "2099-01-01T00:00:00", "prompt", "hello")
        ts = list_triggers()
        assert len(ts) >= 2
        names = {t["name"] for t in ts}
        assert "a" in names
        assert "b" in names

    def test_list_enabled_only(self):
        create_trigger("ea", "interval", "30m", "tool", "get_weather")
        tb = create_trigger("eb", "interval", "1h", "tool", "get_weather")
        update_trigger(tb["id"], enabled=0)
        ts = list_triggers(enabled_only=True)
        names = {t["name"] for t in ts}
        assert "ea" in names
        assert "eb" not in names

    def test_update(self):
        t = create_trigger("upd", "interval", "30m", "tool", "get_weather")
        updated = update_trigger(t["id"], name="updated_name", description="new desc")
        assert updated["name"] == "updated_name"
        assert updated["description"] == "new desc"

    def test_delete(self):
        t = create_trigger("del", "interval", "30m", "tool", "get_weather")
        tid = t["id"]
        assert delete_trigger(tid) is True
        assert get_trigger(tid) is None

    def test_delete_nonexistent(self):
        assert delete_trigger(999) is False


class TestFire:
    def test_fire_tool(self):
        t = create_trigger("fire_tool", "once", "2099-01-01T00:00:00", "tool", "get_system_info")
        result = fire_trigger(t["id"])
        assert result["ok"] is True
        assert result["status"] == "done"
        assert result["duration_ms"] >= 0

    def test_fire_unknown_tool(self):
        t = create_trigger("fire_bad", "once", "2099-01-01T00:00:00", "tool", "nonexistent_tool_xyz")
        result = fire_trigger(t["id"])
        assert result["ok"] is False
        assert result["status"] == "error"

    def test_fire_disabled(self):
        t = create_trigger("fire_dis", "once", "2099-01-01T00:00:00", "tool", "get_system_info")
        update_trigger(t["id"], enabled=0)
        with pytest.raises(ValueError, match="disabled"):
            fire_trigger(t["id"])

    def test_fire_adds_history(self):
        t = create_trigger("fire_hist", "once", "2099-01-01T00:00:00", "tool", "get_system_info")
        fire_trigger(t["id"])
        history = get_trigger_history(t["id"])
        assert len(history) >= 1
        assert history[0]["trigger_id"] == t["id"]
        assert history[0]["status"] == "done"


class TestHistory:
    def test_history_empty(self):
        assert get_trigger_history(999) == []

    def test_history_all(self):
        t = create_trigger("hist_all", "once", "2099-01-01T00:00:00", "tool", "get_system_info")
        fire_trigger(t["id"])
        all_h = get_trigger_history(limit=100)
        assert len(all_h) >= 1


class TestEnableDisable:
    def test_disable(self):
        t = create_trigger("ed", "interval", "30m", "tool", "get_weather")
        updated = disable_trigger(t["id"])
        assert updated["enabled"] == 0

    def test_enable(self):
        t = create_trigger("en", "interval", "30m", "tool", "get_weather")
        disable_trigger(t["id"])
        updated = enable_trigger(t["id"])
        assert updated["enabled"] == 1


class TestEventTriggers:
    def test_fire_event(self):
        create_trigger("evt_test", "event", "my_event", "tool", "get_system_info", {}, "event test")
        results = fire_event("my_event")
        assert len(results) == 1
        assert results[0]["ok"] is True

    def test_fire_event_no_match(self):
        create_trigger("evt_nomatch", "event", "some_event", "tool", "get_system_info", {}, "event test")
        results = fire_event("other_event")
        assert len(results) == 0


class TestScheduler:
    def test_scheduler_creates_no_errors(self):
        from trigger_engine import start, stop

        start()
        assert True
        stop()


class TestNextFireUpdates:
    def test_fire_updates_next_fire_interval(self):
        t = create_trigger("nf_interval", "interval", "30s", "tool", "get_weather")
        before = t["next_fire"]
        fire_trigger(t["id"])
        after = get_trigger(t["id"])["next_fire"]
        assert after != before
        assert after is not None

    def test_fire_updates_fire_count(self):
        t = create_trigger("nf_count", "once", "2099-01-01T00:00:00", "tool", "get_weather")
        assert t["fire_count"] == 0
        fire_trigger(t["id"])
        assert get_trigger(t["id"])["fire_count"] == 1
        with pytest.raises(ValueError, match="disabled"):
            fire_trigger(t["id"])


class TestCronEdgeCases:
    def test_every_15_minutes(self):
        expr = _parse_cron("*/15 * * * *")
        for m in [0, 15, 30, 45]:
            dt = datetime.datetime(2026, 6, 21, 10, m)
            assert _cron_matches(expr, dt) is True
        for m in [7, 22, 37]:
            dt = datetime.datetime(2026, 6, 21, 10, m)
            assert _cron_matches(expr, dt) is False

    def test_weekday_restricted(self):
        mon = datetime.datetime(2026, 6, 22, 9, 0)
        sat = datetime.datetime(2026, 6, 27, 9, 0)
        expr = _parse_cron("0 9 * * 1-5")
        assert _cron_matches(expr, mon) is True
        assert _cron_matches(expr, sat) is False
