import pytest

from tests.helpers import assert_no_raw_json, env_unset


@pytest.mark.integration
class TestGroqFallback:
    """Groq should handle markdown JSON tool calls when Nemotron fails."""

    def test_groq_open_app(self, api):
        with env_unset("NVIDIA_NEMOTRON_API_KEY"):
            r = api.ask("open safari")
        assert r.status_code == 200
        data = r.json()
        assert data["reply"]
        assert_no_raw_json(data["reply"])
        assert "safari" in data["reply"].lower() or "opened" in data["reply"].lower()

    def test_groq_weather(self, api):
        with env_unset("NVIDIA_NEMOTRON_API_KEY"):
            r = api.ask("weather in Seattle")
        assert r.status_code == 200
        data = r.json()
        assert "°F" in data["reply"] or "°C" in data["reply"]
        assert_no_raw_json(data["reply"])

    def test_groq_web_search(self, api):
        with env_unset("NVIDIA_NEMOTRON_API_KEY"):
            r = api.ask("search web for python 3.14 release date")
        assert r.status_code == 200
        data = r.json()
        assert len(data["reply"]) > 50
        assert_no_raw_json(data["reply"])


@pytest.mark.integration
class TestOpenRouterFallback:
    """OpenRouter should handle markdown JSON when Nemotron + Groq fail."""

    def test_openrouter_weather(self, api):
        with env_unset("NVIDIA_NEMOTRON_API_KEY"), env_unset("GROQ_API_KEY"):
            r = api.ask("weather in Austin")
        assert r.status_code == 200
        data = r.json()
        assert "°F" in data["reply"] or "°C" in data["reply"]
        assert_no_raw_json(data["reply"])

    def test_openrouter_open_app(self, api):
        with env_unset("NVIDIA_NEMOTRON_API_KEY"), env_unset("GROQ_API_KEY"):
            r = api.ask("open safari")
        assert r.status_code == 200
        data = r.json()
        assert data["reply"]
        assert_no_raw_json(data["reply"])


@pytest.mark.integration
class TestDeepSeekCodingRoute:
    """DeepSeek should handle coding queries."""

    def test_deepseek_python_function(self, api):
        r = api.ask("write a python function that sorts a list")
        assert r.status_code == 200
        data = r.json()
        assert "def " in data["reply"] or "sort" in data["reply"].lower()
        assert_no_raw_json(data["reply"])

    def test_deepseek_run_python(self, api):
        r = api.ask("run python code that prints hello world")
        assert r.status_code == 200
        data = r.json()
        assert "hello world" in data["reply"].lower()
        assert_no_raw_json(data["reply"])


@pytest.mark.integration
class TestPollinationsEmergency:
    """Pollinations should work with no keys (text only)."""

    def test_pollinations_chat(self, api):
        keys_to_unset = [
            "NVIDIA_NEMOTRON_API_KEY", "GOOGLE_GENAI_API_KEY",
            "GROQ_API_KEY", "OPENROUTER_API_KEY", "KIMI_API_KEY",
            "DEEPSEEK_API_KEY",
        ]
        with env_unset("NVIDIA_NEMOTRON_API_KEY"):
            r = api.ask("hello, who are you?")
        assert r.status_code == 200
        data = r.json()
        assert len(data["reply"]) > 10
        assert_no_raw_json(data["reply"])
