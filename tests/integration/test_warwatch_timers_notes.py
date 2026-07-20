import pytest

from tests.helpers import assert_no_raw_json


@pytest.mark.integration
class TestWarWatchTimersNotes:
    def test_warwatch_news(self, api):
        r = api.ask("get war news about ukraine")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_notes_search(self, api):
        r = api.ask("search my notes for project")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_knowledge_graph(self, api):
        r = api.ask("query my knowledge graph for Jarvis")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])
