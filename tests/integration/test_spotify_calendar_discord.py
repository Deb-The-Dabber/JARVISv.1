import pytest

from tests.helpers import assert_no_raw_json


@pytest.mark.integration
class TestSpotifyCalendarDiscord:
    def test_spotify_current(self, api):
        r = api.ask("what's playing on spotify")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_spotify_play(self, api):
        r = api.ask("play song bohemian rhapsody on spotify")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_calendar_today(self, api):
        r = api.ask("what's on my calendar today")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_discord_open(self, api):
        r = api.ask("open discord general channel")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])
