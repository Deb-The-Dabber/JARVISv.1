import pytest

from safety import (
    SAFE,
    TOOL_PERMISSIONS,
    NeedsConfirmation,
    PermissionDenied,
    check_permission,
)


class TestSafetyPermissions:
    def test_extract_entities_relations_safe(self):
        assert TOOL_PERMISSIONS.get("extract_entities_relations") == SAFE

    def test_safe_tools_return_true(self):
        assert check_permission("get_weather_detailed", {}) is True
        assert check_permission("open_app", {"app_name": "Safari"}) is True
        assert check_permission("web_search", {"query": "test"}) is True

    def test_blocked_command_raises(self):
        with pytest.raises(PermissionDenied):
            check_permission("run_terminal_command", {"command": "rm -rf /"})

    def test_warning_tools_raise_needs_confirmation(self):
        with pytest.raises(NeedsConfirmation):
            check_permission("quit_app", {"app_name": "Safari"})

    def test_dangerous_tools_raise_needs_confirmation(self):
        with pytest.raises(NeedsConfirmation):
            check_permission("send_imessage", {})

    def test_unknown_tool_defaults_safe(self):
        # Unknown/plugin tools are SAFE by default
        assert check_permission("nonexistent_tool", {}) is True
