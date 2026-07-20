import pytest

from tests.helpers import assert_no_raw_json


@pytest.mark.regression
class TestMemory:
    def test_remember_recall(self, api):
        api.ask("remember I like black coffee")
        r = api.ask("what do you know about me")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_forget(self, api):
        api.ask("remember test fact for forgetting 9876")
        r = api.ask("forget test fact for forgetting 9876")
        assert r.status_code == 200
        r2 = api.ask("what do you know about me")
        assert "test fact for forgetting" not in r2.json()["reply"].lower()

    def test_semantic_search(self, api):
        r = api.ask("search memory for coffee preferences")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])
