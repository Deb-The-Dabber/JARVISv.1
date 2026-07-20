import pytest

from tests.helpers import assert_no_raw_json


@pytest.mark.integration
class TestVisionTools:
    """Vision tools using NVIDIA_API_KEY for screen analysis."""

    def test_read_screen(self, api):
        r = api.ask("what's on my screen")
        assert r.status_code == 200
        data = r.json()
        assert len(data["reply"]) > 20
        assert_no_raw_json(data["reply"])

    def test_summarize_screen(self, api):
        r = api.ask("summarize screen")
        assert r.status_code == 200
        data = r.json()
        assert len(data["reply"]) > 30
        assert_no_raw_json(data["reply"])

    def test_find_on_screen(self, api):
        r = api.ask("find the search bar on screen")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])


@pytest.mark.integration
class TestComputerTools:
    """Computer control tools (mouse, keyboard, screenshots)."""

    def test_screenshot(self, api):
        r = api.ask("take a screenshot")
        assert r.status_code == 200
        data = r.json()
        assert "screenshot" in data["reply"].lower() or "saved" in data["reply"].lower()
        assert_no_raw_json(data["reply"])

    def test_mouse_move_click(self, api):
        r = api.ask("move mouse to 500 400 and click")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_type_text(self, api):
        r = api.ask("type text hello from jarvis test")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_press_key(self, api):
        r = api.ask("press key enter")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_click_on_screen(self, api):
        r = api.ask("click the Safari icon on screen")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])
