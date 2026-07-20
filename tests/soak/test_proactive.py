import pytest


@pytest.mark.soak
class TestProactiveEngine:
    def test_priorities_endpoint(self, api):
        r = api.get("/priorities")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)

    def test_recap_endpoint(self, api):
        r = api.get("/recap")
        assert r.status_code == 200
        data = r.json()
        assert data is not None
