import pytest

from jarvis_logger import (
    _cost_totals,
    _metrics,
    generate_request_id,
    get_cost_summary,
    get_latest_logs,
    get_metrics_snapshot,
    log_request,
    log_tool_call,
)


def setup_function():
    _metrics["requests_total"] = 0
    _metrics["tokens_input_total"] = 0
    _metrics["tokens_output_total"] = 0
    _metrics["tool_calls_total"] = 0
    _metrics["tool_errors_total"] = 0
    _metrics["latency_seconds_total"] = 0.0
    _metrics["requests_by_provider"] = {}
    _metrics["requests_by_intent"] = {}
    _metrics["latency_by_provider"] = {}
    _cost_totals["cost_usd_total"] = 0.0
    _cost_totals["cost_by_provider"] = {}


def test_generate_request_id():
    rid = generate_request_id()
    assert isinstance(rid, str)
    assert len(rid) == 12


def test_request_id_unique():
    ids = {generate_request_id() for _ in range(100)}
    assert len(ids) == 100


def test_log_request_updates_metrics():
    log_request(
        request_id="test123",
        provider="nemotron_ultra",
        model="nemotron-3-ultra",
        user_message="hello",
        reply="hi",
        intent="chat",
        tokens_input=50,
        tokens_output=30,
        latency_seconds=1.5,
        tool_calls=["get_weather"],
    )
    m = get_metrics_snapshot()
    assert m["requests_total"] == 1
    assert m["tokens_input_total"] == 50
    assert m["tokens_output_total"] == 30
    assert m["tool_calls_total"] == 1
    assert m["requests_by_provider"]["nemotron_ultra"] == 1
    assert m["requests_by_intent"]["chat"] == 1


def test_log_request_with_error():
    log_request(
        request_id="err123",
        provider="groq",
        model="llama-3.3",
        user_message="test",
        reply="",
        intent="tool_use",
        tokens_input=10,
        tokens_output=0,
        latency_seconds=10.0,
        tool_calls=[],
        error="Rate limit exceeded",
    )
    m = get_metrics_snapshot()
    assert m["requests_total"] == 1


def test_log_tool_call():
    log_tool_call(
        request_id="tc123",
        tool_name="get_weather",
        args={"city": "Chicago"},
        result="72F, sunny",
    )
    logs = get_latest_logs(10)
    tool_entries = [l for l in logs if l.get("type") == "tool_call"]
    assert len(tool_entries) >= 1
    assert tool_entries[-1]["tool"] == "get_weather"


def test_cost_tracking():
    log_request(
        request_id="cost1",
        provider="nemotron_ultra",
        model="test",
        user_message="x",
        reply="y",
        intent="chat",
        tokens_input=1_000_000,
        tokens_output=0,
        latency_seconds=0.1,
        tool_calls=[],
    )
    c = get_cost_summary()
    assert c["cost_usd_total"] == pytest.approx(2.0, rel=0.01)
    assert "nemotron_ultra" in c["cost_by_provider"]


def test_multiple_requests():
    for i in range(5):
        log_request(
            request_id=f"multi_{i}",
            provider="deepseek",
            model="deepseek-v4",
            user_message=f"msg_{i}",
            reply=f"reply_{i}",
            intent="coding",
            tokens_input=100,
            tokens_output=50,
            latency_seconds=2.0,
            tool_calls=[],
        )
    m = get_metrics_snapshot()
    assert m["requests_total"] == 5
    assert m["tokens_input_total"] == 500
    assert m["tokens_output_total"] == 250
    assert m["latency_avg_overall"] == pytest.approx(2.0, rel=0.01)


def test_zero_cost_for_unknown_provider():
    log_request(
        request_id="free1",
        provider="pollinations",
        model="free",
        user_message="x",
        reply="y",
        intent="chat",
        tokens_input=1000,
        tokens_output=500,
        latency_seconds=0.5,
        tool_calls=[],
    )
    c = get_cost_summary()
    assert c["cost_usd_total"] == 0.0


def test_metrics_has_all_fields():
    m = get_metrics_snapshot()
    for field in [
        "requests_total",
        "requests_by_provider",
        "requests_by_intent",
        "tokens_input_total",
        "tokens_output_total",
        "latency_avg_by_provider",
        "latency_avg_overall",
        "tool_calls_total",
        "tool_errors_total",
    ]:
        assert field in m, f"Missing field: {field}"
