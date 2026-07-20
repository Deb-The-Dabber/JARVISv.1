import pytest

from tests.helpers import assert_no_raw_json


@pytest.mark.integration
class TestBrowserTools:
    """Safari/Chrome automation via AppleScript."""

    def test_navigate(self, api):
        r = api.ask("open example.com in safari")
        assert r.status_code == 200
        data = r.json()
        assert "example.com" in data["reply"] or "opened" in data["reply"].lower()
        assert_no_raw_json(data["reply"])

    def test_new_tab(self, api):
        r = api.ask("open new tab in safari")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_current_url(self, api):
        api.ask("open example.com in safari")
        r = api.ask("what page am i on")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_back_forward(self, api):
        api.ask("open example.com in safari")
        api.ask("open github.com in safari")
        r = api.ask("go back")
        assert r.status_code == 200
        data = r.json()
        assert "example.com" in data["reply"] or "back" in data["reply"].lower()
        assert_no_raw_json(data["reply"])

    def test_search_in_browser(self, api):
        r = api.ask("search for python 3.13 in browser")
        assert r.status_code == 200
        data = r.json()
        assert "python" in data["reply"].lower()
        assert_no_raw_json(data["reply"])
