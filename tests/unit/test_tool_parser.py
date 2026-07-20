from tool_parser import (
    parse_json_tool_calls,
    parse_markdown_json_tool_calls,
    parse_tool_call_tags,
    parse_xml_tool_calls,
    strip_json_tool_calls,
    strip_markdown_json_tool_calls,
    strip_tool_call_tags,
    strip_xml_tool_calls,
)


class TestXMLParser:
    def test_basic(self):
        calls = parse_xml_tool_calls('<tool_name>open_app</tool_name><tool_args>{"app_name":"Finder"}</tool_args>')
        assert calls == [("open_app", {"app_name": "Finder"})]

    def test_multi(self):
        text = '<tool_name>a</tool_name><tool_args>{}</tool_args><tool_name>b</tool_name><tool_args>{}</tool_args>'
        assert len(parse_xml_tool_calls(text)) == 2

    def test_none(self):
        assert parse_xml_tool_calls("hello") == []
        assert parse_xml_tool_calls("") == []
        assert parse_xml_tool_calls(None) == []

    def test_strip(self):
        text = 'before<tool_name>x</tool_name><tool_args>{}</tool_args>after'
        cleaned = strip_xml_tool_calls(text)
        assert "before" in cleaned
        assert "after" in cleaned
        assert "<tool_name>" not in cleaned

    def test_create_file_xml(self):
        text = '<tool_name>create_file</tool_name><tool_args>{"filename":"test.html","content":"hello"}</tool_args>'
        calls = parse_xml_tool_calls(text)
        assert calls == [("create_file", {"filename": "test.html", "content": "hello"})]


class TestMarkdownJSONParser:
    def test_exact_log_format(self):
        text = '```json{"name": "open_app", "arguments": {"app_name": "Weather"}}```'
        calls = parse_markdown_json_tool_calls(text)
        assert calls == [("open_app", {"app_name": "Weather"})]

    def test_multiline(self):
        text = '```json\n{"name": "web_search", "arguments": {"query": "test"}}\n```'
        calls = parse_markdown_json_tool_calls(text)
        assert calls == [("web_search", {"query": "test"})]

    def test_multiple_fences(self):
        text = '```json{"name": "a", "arguments": {}}```text```json{"name": "b", "arguments": {}}```'
        calls = parse_markdown_json_tool_calls(text)
        assert len(calls) == 2

    def test_tool_format(self):
        text = '```json{"tool": "get_weather", "arguments": {}}```'
        calls = parse_markdown_json_tool_calls(text)
        assert calls == [("get_weather", {})]

    def test_strip(self):
        text = 'before```json{"name":"x","arguments":{}}```after'
        assert strip_markdown_json_tool_calls(text) == "beforeafter"

    def test_none_empty(self):
        assert parse_markdown_json_tool_calls(None) == []
        assert parse_markdown_json_tool_calls("") == []


class TestBareJSONParser:
    def test_tool_calls_wrapper(self):
        text = '{"tool_calls": [{"name": "open_app", "arguments": {"app_name": "Finder"}}]}'
        calls = parse_json_tool_calls(text)
        assert calls == [("open_app", {"app_name": "Finder"})]

    def test_single_tool(self):
        text = '{"name": "web_search", "arguments": {"query": "hello world"}}'
        calls = parse_json_tool_calls(text)
        assert calls == [("web_search", {"query": "hello world"})]

    def test_array_format(self):
        text = '[{"name": "get_weather", "arguments": {}}, {"name": "open_app", "arguments": {"app_name": "Calendar"}}]'
        calls = parse_json_tool_calls(text)
        assert len(calls) == 2
        assert calls[0] == ("get_weather", {})
        assert calls[1] == ("open_app", {"app_name": "Calendar"})

    def test_tool_key(self):
        text = '{"tool": "scan_project_structure", "arguments": {}}'
        calls = parse_json_tool_calls(text)
        assert calls == [("scan_project_structure", {})]

    def test_tool_calls_not_list(self):
        text = '{"tool_calls": "invalid"}'
        calls = parse_json_tool_calls(text)
        assert calls == []

    def test_non_tool_json(self):
        text = '{"key": "value", "nested": {"a": 1}}'
        calls = parse_json_tool_calls(text)
        assert calls == []

    def test_none_empty(self):
        assert parse_json_tool_calls(None) == []
        assert parse_json_tool_calls("") == []
        assert parse_json_tool_calls("not json at all") == []

    def test_strip_tool_calls(self):
        text = '{"tool_calls": [{"name": "x", "arguments": {}}]}'
        assert strip_json_tool_calls(text) == ""

    def test_strip_regular_text(self):
        text = "Hello, how are you?"
        assert strip_json_tool_calls(text) == text


class TestToolCallTagParser:
    def test_basic(self):
        text = '<tool_call>function(scan_project_structure)</tool_call>'
        calls = parse_tool_call_tags(text)
        assert calls == [("scan_project_structure", {})]

    def test_multiline(self):
        text = '<tool_call>\nfunction(scan_project_structure)\nend function'
        calls = parse_tool_call_tags(text)
        assert calls == [("scan_project_structure", {})]

    def test_with_args(self):
        text = '<tool_call>function(open_app, app_name="Finder")</tool_call>'
        calls = parse_tool_call_tags(text)
        assert calls == [("open_app", {"app_name": "Finder"})]

    def test_no_tags(self):
        assert parse_tool_call_tags("hello") == []
        assert parse_tool_call_tags("") == []
        assert parse_tool_call_tags(None) == []

    def test_strip(self):
        text = 'before<tool_call>function(x)</tool_call>after'
        assert strip_tool_call_tags(text) == "beforeafter"

    def test_strip_multiline(self):
        text = 'hello\n<tool_call>\nfunction(x)\nend function\nworld'
        cleaned = strip_tool_call_tags(text)
        assert "hello" in cleaned
        assert "world" in cleaned
