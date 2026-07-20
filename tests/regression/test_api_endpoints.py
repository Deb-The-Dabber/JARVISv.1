import pytest


@pytest.mark.regression
class TestAPIEndpoints:
    """Verify all API endpoints return valid JSON."""

    ENDPOINTS = [
        ("/health", {"status": "online"}),
        ("/system", {"cpu_percent": (int, float)}),
        ("/memories", {"memories": list}),
        ("/priorities", dict),
        ("/audit", {"logs": list}),
    ]

    @pytest.mark.parametrize("endpoint,expected", ENDPOINTS)
    def test_get_endpoint(self, api, endpoint, expected):
        r = api.get(endpoint)
        assert r.status_code == 200, f"{endpoint} returned {r.status_code}"
        data = r.json()
        if isinstance(expected, dict):
            for key, typ in expected.items():
                assert key in data, f"{endpoint} missing {key}"
                if isinstance(typ, tuple):
                    assert isinstance(data[key], typ), f"{endpoint}.{key} type mismatch: {type(data[key])}"
                elif isinstance(typ, type):
                    assert isinstance(data[key], typ), f"{endpoint}.{key} expected {typ}, got {type(data[key])}"
        elif expected == list:
            assert isinstance(data, list), f"{endpoint} expected list, got {type(data)}"
        elif expected == dict:
            assert isinstance(data, dict), f"{endpoint} expected dict, got {type(data)}"

    def test_ask_endpoint(self, api):
        r = api.ask("weather in Chicago")
        assert r.status_code == 200
        data = r.json()
        assert "reply" in data
        assert "transcription" in data
        assert len(data["reply"]) > 10
