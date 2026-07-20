#!/usr/bin/env python3
"""Test the <tool_call> + bare JSON parser."""

from tool_parser.tool_parser import parse_tool_call_json_tags

# The exact format from the test log that failed
text = '<tool_call>\n{"name": "get_open_apps", "arguments": {}}'
result = parse_tool_call_json_tags(text)

print("Input:", repr(text))
print("Result:", result)
print("Expected:", [("get_open_apps", {})])
print("Match:", result == [("get_open_apps", {})])

# Test with no newline
text2 = '<tool_call>{"name": "open_app", "arguments": {"app_name": "Weather"}}</tool_call>'
result2 = parse_tool_call_json_tags(text2)
print(f"\nInput: {repr(text2)}")
print("Result:", result2)
print("Expected: [(" + repr("open_app") + ", " + repr({"app_name": "Weather"}) + ")]")
print("Match:", result2 == [("open_app", {"app_name": "Weather"})])
