import os

import pytest

from tests.helpers import assert_no_raw_json


@pytest.mark.regression
class TestFileTools:
    def test_create_file(self, api):
        r = api.ask("create a file called test_jarvis_api.txt on desktop with hello world")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])
        path = os.path.expanduser("~/Desktop/test_jarvis_api.txt")
        if os.path.exists(path):
            os.remove(path)

    def test_find_recent_screenshot(self, api):
        r = api.ask("find my latest screenshot")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_largest_files(self, api):
        r = api.ask("show largest files in downloads")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_organize_downloads(self, api):
        r = api.ask("organize downloads")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])
