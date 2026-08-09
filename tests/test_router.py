import os

# These are keyword-routing unit tests — make them deterministic. The local NN
# fast-path and LLM-first classification have their own coverage
# (tests/unit/test_local_nn.py, tests/eval/golden_set.jsonl); letting them run
# here makes results depend on provider health and live LLM responses.
os.environ["JARVIS_LOCAL_INTENT_ENABLED"] = "0"
os.environ["JARVIS_LLM_FIRST"] = "0"

from brain import CODING_KEYWORDS, TOOL_USE_KEYWORDS, classify_intent


class TestCoding:
    def test_fix_bug(self):
        assert classify_intent("fix this python bug") == "coding"

    def test_write_script(self):
        assert classify_intent("write a python script") == "coding"

    def test_implement(self):
        assert classify_intent("implement a fibonacci function") == "coding"

    def test_debug(self):
        assert classify_intent("debug this error traceback") == "coding"

    def test_design_api(self):
        assert classify_intent("design an API for this") == "coding"

    def test_bare_file_reference(self):
        assert classify_intent("brain.py line 10") == "coding"

    def test_refactor(self):
        assert classify_intent("refactor the code in brain.py") == "self_mod"

    def test_run_python(self):
        assert classify_intent("run a python script") == "coding"


class TestToolUse:
    def test_open_app(self):
        assert classify_intent("open safari") == "tool_use"

    def test_weather(self):
        assert classify_intent("weather in chicago") == "tool_use"

    def test_search(self):
        assert classify_intent("search web for python 3.13") == "tool_use"

    def test_find(self):
        assert classify_intent("find python documentation") == "tool_use"

    def test_timer(self):
        assert classify_intent("set a timer for 10 seconds") == "tool_use"

    def test_system_usage(self):
        assert classify_intent("whats my system usage") == "tool_use"

    def test_calendar(self):
        assert classify_intent("get my calendar events") == "tool_use"

    def test_create(self):
        assert classify_intent("create a new directory") == "tool_use"

    def test_screen(self):
        assert classify_intent("summarize my screen") == "tool_use"

    def test_file_read(self):
        assert classify_intent("read file brain.py and show me line 10") == "tool_use"

    def test_forecast(self):
        assert classify_intent("whats the forecast") == "tool_use"

    def test_memory_app(self):
        assert classify_intent("check my email") == "tool_use"

    def test_disk_space(self):
        assert classify_intent("how much disk space do i have") == "tool_use"


class TestChat:
    def test_greeting(self):
        assert classify_intent("hello how are you") == "chat"

    def test_simple_hello(self):
        assert classify_intent("hello") == "chat"

    def test_joke(self):
        assert classify_intent("tell me a joke") == "chat"

    def test_knowledge(self):
        assert classify_intent("what do you know about me") == "chat"

    def test_good_morning(self):
        assert classify_intent("good morning") == "chat"

    def test_memory(self):
        assert classify_intent("remember I like coffee") == "chat"


class TestReasoning:
    def test_why_question(self):
        assert classify_intent("why is the sky blue") == "reasoning"

    def test_how_do(self):
        assert classify_intent("how do neural nets work") == "reasoning"

    def test_explain(self):
        assert classify_intent("explain transformers") == "reasoning"

    def test_meaning(self):
        assert classify_intent("what is the meaning of life") == "reasoning"

    def test_compare(self):
        assert classify_intent("compare these two approaches") == "reasoning"


class TestSelfMod:
    def test_read_and_fix(self):
        assert classify_intent("read brain.py and fix it") == "self_mod"

    def test_browser_tools_bug(self):
        assert classify_intent("fix the bug in tools/browser_tools.py") == "self_mod"

    def test_refactor_own_code(self):
        assert classify_intent("refactor the code in brain.py") == "self_mod"


class TestKeywordSets:
    def test_coding_keywords(self):
        assert "python" in CODING_KEYWORDS
        assert "debug" in CODING_KEYWORDS
        assert "bug" in CODING_KEYWORDS
        assert "implment" not in CODING_KEYWORDS

    def test_tool_keywords(self):
        assert "open" in TOOL_USE_KEYWORDS
        assert "weather" in TOOL_USE_KEYWORDS
        assert "browse" in TOOL_USE_KEYWORDS
        assert "click" in TOOL_USE_KEYWORDS
