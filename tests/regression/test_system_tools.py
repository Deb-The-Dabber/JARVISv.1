import pytest

from tests.helpers import assert_no_raw_json


@pytest.mark.regression
class TestSystemTools:
    def test_system_info(self, api):
        r = api.ask("what's my system usage")
        assert r.status_code == 200
        data = r.json()
        assert "cpu" in data["reply"].lower() or "ram" in data["reply"].lower()
        assert_no_raw_json(data["reply"])

    def test_weather_detailed(self, api):
        r = api.ask("detailed weather")
        assert r.status_code == 200
        data = r.json()
        assert "°F" in data["reply"] or "°C" in data["reply"]
        # "humid" is a strict substring of "humidity" — tolerate LLM phrasing
        assert "humid" in data["reply"].lower()
        assert_no_raw_json(data["reply"])

    def test_web_search(self, api):
        r = api.ask("search web for python 3.13")
        assert r.status_code == 200
        data = r.json()
        assert len(data["reply"]) > 50
        assert_no_raw_json(data["reply"])

    def test_open_app(self, api):
        r = api.ask("open safari")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_timer(self, api):
        r = api.ask("set a timer called test for 2 seconds")
        assert r.status_code == 200
        data = r.json()
        assert "timer" in data["reply"].lower()
        assert_no_raw_json(data["reply"])

    def test_disk_usage(self, api):
        r = api.ask("disk usage")
        assert r.status_code == 200
        data = r.json()
        assert "gb" in data["reply"].lower() or "disk" in data["reply"].lower()
        assert_no_raw_json(data["reply"])
