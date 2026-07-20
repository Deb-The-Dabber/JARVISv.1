import os
import shutil
import tempfile

import pytest

from workflow_engine import (
    BUILTIN_WORKFLOWS,
    WORKFLOW_DIR,
    _interpolate,
    _resolve_args,
    get_run_detail,
    get_run_history,
    list_workflows,
    load_workflow,
    run_workflow,
)


class TestBuiltinWorkflows:
    def test_list_contains_builtins(self):
        wfs = list_workflows()
        names = {w["name"] for w in wfs}
        assert "research_and_save" in names
        assert "system_report" in names
        assert "code_review" in names

    def test_list_has_descriptions(self):
        for w in list_workflows():
            assert w.get("description")

    def test_load_builtin(self):
        wf = load_workflow("system_report")
        assert wf is not None
        assert wf["name"] == "system_report"

    def test_research_workflow_nodes(self):
        wf = load_workflow("research_and_save")
        assert len(wf["nodes"]) == 3
        assert wf["nodes"][0]["id"] == "search"
        assert wf["nodes"][1]["id"] == "summarize"
        assert wf["nodes"][2]["id"] == "save"

    def test_system_report_nodes(self):
        wf = load_workflow("system_report")
        assert len(wf["nodes"]) == 3
        # First two are parallel (no deps)
        assert wf["nodes"][0].get("depends_on") is None or wf["nodes"][0].get("depends_on") == []
        # Third depends on first two
        assert set(wf["nodes"][2].get("depends_on", [])) == {"sysinfo", "weather"}

    def test_load_nonexistent(self):
        assert load_workflow("definitely_does_not_exist") is None

    def test_builtin_tag(self):
        wfs = list_workflows()
        for w in wfs:
            if w["name"] in BUILTIN_WORKFLOWS:
                assert w.get("builtin") is True


class TestInterpolation:
    def test_basic_substitution(self):
        result = _interpolate("Hello {name}", {}, {"name": "World"})
        assert result == "Hello World"

    def test_output_substitution(self):
        result = _interpolate("Result: {search.output}", {"search.output": "found it"}, {})
        assert result == "Result: found it"

    def test_dotted_path_resolution(self):
        result = _interpolate("Node: {n.result}", {"n.result": "success"}, {})
        assert result == "Node: success"

    def test_multiple_vars(self):
        result = _interpolate("{a} and {b} and {a}", {"a": "x", "b": "y"}, {})
        assert result == "x and y and x"

    def test_missing_var_keeps_placeholder(self):
        result = _interpolate("Hello {missing}", {}, {})
        assert result == "Hello {missing}"

    def test_empty_template(self):
        assert _interpolate("", {}, {}) == ""

    def test_no_placeholders(self):
        assert _interpolate("plain text", {}, {}) == "plain text"


class TestResolveArgs:
    def test_simple_value(self):
        resolved = _resolve_args({"query": "hello {name}"}, {}, {"name": "World"})
        assert resolved["query"] == "hello World"

    def test_nested_dict(self):
        resolved = _resolve_args(
            {"nested": {"key": "val-{x}"}},
            {"x": "123"}, {}
        )
        assert resolved["nested"]["key"] == "val-123"

    def test_list_values(self):
        resolved = _resolve_args(
            {"items": ["{a}", "{b}"]},
            {"a": "1", "b": "2"}, {}
        )
        assert resolved["items"] == ["1", "2"]

    def test_non_string_passthrough(self):
        resolved = _resolve_args({"num": 42, "flag": True}, {}, {})
        assert resolved["num"] == 42
        assert resolved["flag"] is True


class TestRunHistory:
    def test_history_empty(self):
        history = get_run_history(5)
        assert isinstance(history, list)

    @pytest.mark.skip(reason="requires live API calls")
    def test_run_id_stored(self):
        r = run_workflow("system_report")
        assert "run_id" in r

    @pytest.mark.skip(reason="requires live API calls")
    def test_run_detail(self):
        r = run_workflow("system_report")
        detail = get_run_detail(r["run_id"])
        assert detail is not None
        assert detail["workflow"] == "system_report"

    @pytest.mark.skip(reason="requires live API calls")
    def test_run_detail_nodes(self):
        r = run_workflow("system_report")
        detail = get_run_detail(r["run_id"])
        assert "nodes" in detail


class TestWorkflowFileLoading:
    @pytest.fixture
    def temp_wf_dir(self):
        old = WORKFLOW_DIR
        tmp = tempfile.mkdtemp()
        import workflow_engine as we
        we.WORKFLOW_DIR = tmp
        yield tmp
        we.WORKFLOW_DIR = old
        shutil.rmtree(tmp, ignore_errors=True)

    def test_custom_yaml(self, temp_wf_dir):
        wf = {
            "name": "my_custom_workflow",
            "description": "Test custom workflow",
            "nodes": [
                {"id": "step1", "type": "tool_call", "tool": "get_weather_detailed", "args": {}}
            ],
        }
        import yaml
        with open(os.path.join(temp_wf_dir, "custom.yaml"), "w") as f:
            yaml.dump(wf, f)
        wfs = list_workflows()
        names = {w["name"] for w in wfs}
        assert "my_custom_workflow" in names

    def test_custom_in_list(self, temp_wf_dir):
        wf = {
            "name": "test_custom_listed",
            "description": "Listed workflow",
            "nodes": [{"id": "w", "type": "tool_call", "tool": "get_weather_detailed", "args": {}}],
        }
        import yaml
        with open(os.path.join(temp_wf_dir, "test.yaml"), "w") as f:
            yaml.dump(wf, f)
        wfs = list_workflows()
        names = {w["name"] for w in wfs}
        assert "test_custom_listed" in names
