#!/usr/bin/env python3
"""Test strip and sanitize for <tool_call>+JSON"""

from tool_parser import strip_tool_call_tags

text = '<tool_call>\n{"name": "get_open_apps", "arguments": {}}'
print("Input:", repr(text))
print("strip_tool_call_tags:", repr(strip_tool_call_tags(text)))
print("_sanitize_assistant_text:", repr(_sanitize_ass彷蛎(text)))

# Also test with closing tag
text2 = '<tool_call>{"name": "open_app", "arguments": {"app_name": "Weather"}}</tool_call>'
print("\nInput:", repr(text2))
print("strip_tool_call_tags:", repr(strip_tool_call_tags(text2)))
print("_sanitize_assistant_text:", repr(_sanitize_assitant_text(text2)))
