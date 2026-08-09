import pytest

from tests.helpers import assert_no_raw_json


@pytest.mark.regression
class TestSafetyAudit:
    def test_safe_tool_no_confirm(self, api):
        r = api.ask("weather in Chicago")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_warning_tool_requires_confirm(self, api):
        r = api.ask("quit safari")
        assert r.status_code == 200
        data = r.json()
        assert_no_raw_json(data["reply"])

    def test_audit_endpoint(self, api):
        r = api.get("/audit")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert "logs" in data
        logs = data["logs"]
        assert isinstance(logs, list)
        valid_decisions = ["ALLOWED", "EXECUTED", "DENIED", "BLOCKED", "NEEDS_CONFIRMATION", "DENIED_BY_USER", "CONFIRMED_BY_USER"]
        for entry in logs:
            assert "decision" in entry, f"Missing 'decision' in entry: {entry}"
            assert entry["decision"] in valid_decisions, f"Unknown decision: {entry['decision']}"
