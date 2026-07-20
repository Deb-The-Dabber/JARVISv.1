import pytest

from tests.helpers import assert_no_raw_json


@pytest.mark.regression
class TestCodeTools:
    def test_run_python(self, api):
        r = api.ask("run python code that prints hello world")
        assert r.status_code == 200
        data = r.json()
        assert "hello world" in data["reply"].lower()
        assert_no_raw_json(data["reply"])

    def test_scan_project(self, api):
        r = api.ask("scan my project structure")
        assert r.status_code == 200
        data = r.json()
        assert "file" in data["reply"].lower() or "directory" in data["reply"].lower()
        assert_no_raw_json(data["reply"])

    def test_function_signatures(self, api):
        r = api.ask("get function signatures for tool_parser")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])
