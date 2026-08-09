import datetime
import json
import os
import threading
import uuid

LOG_DIR = os.path.expanduser("~/.jarvis/logs")
LOG_FILE = os.path.join(LOG_DIR, "jarvis.jsonl")

_metrics_lock = threading.Lock()
# All metric keys must be pre-declared here
_metrics = {
    "requests_total": 0,
    "requests_by_provider": {},
    "requests_by_intent": {},
    "tokens_input_total": 0,
    "tokens_output_total": 0,
    "tokens_input_by_provider": {},
    "tokens_output_by_provider": {},
    "latency_seconds_total": 0.0,
    "latency_by_provider": {},
    "tool_calls_total": 0,
    "tool_errors_total": 0,
    "cache_hits_total": 0,
    "errors_total": 0,
    "errors_by_provider": {},
}

# Approximate pricing per 1M tokens (USD) — update as rates change
PROVIDER_PRICING = {
    "nemotron_ultra": {"input": 2.00, "output": 8.00},
    "nemotron_nano": {"input": 0.50, "output": 2.00},
    "deepseek": {"input": 0.50, "output": 2.00},
    "gemini": {"input": 0.15, "output": 0.60},
    "groq": {"input": 0.80, "output": 0.80},
    "openrouter": {"input": 0.50, "output": 0.50},
    "pollinations": {"input": 0.0, "output": 0.0},
}

_cost_lock = threading.Lock()
_cost_totals = {
    "cost_usd_total": 0.0,
    "cost_by_provider": {},
}


def _ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)


def _incr(counter: str, provider: str = None, amount=1):
    with _metrics_lock:
        if provider:
            # counter is already like "requests_by_provider"
            d = _metrics.setdefault(counter, {})
            d[provider] = d.get(provider, 0) + amount
        else:
            _metrics[counter] = _metrics.get(counter, 0) + amount


def _append_latency(provider: str, seconds: float):
    with _metrics_lock:
        d = _metrics.setdefault("latency_by_provider", {})
        if provider not in d:
            d[provider] = []
        d[provider].append(seconds)
        _metrics["latency_seconds_total"] += seconds


def generate_request_id() -> str:
    return uuid.uuid4().hex[:12]


def log_request(
    request_id: str,
    provider: str,
    model: str,
    user_message: str,
    reply: str,
    intent: str,
    tokens_input: int,
    tokens_output: int,
    latency_seconds: float,
    tool_calls: list,
    error: str = None,
):
    _ensure_log_dir()
    entry = {
        "ts": datetime.datetime.now().isoformat(),
        "request_id": request_id,
        "provider": provider,
        "model": model,
        "intent": intent,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "latency_seconds": round(latency_seconds, 3),
        "tool_calls": tool_calls,
        "error": error,
        "user_message_preview": user_message[:200],
        "reply_preview": reply[:200],
    }
    _incr("requests_total")
    _incr("requests_by_provider", provider)
    _incr("requests_by_intent", intent)
    _incr("tokens_input_total", amount=tokens_input)
    _incr("tokens_output_total", amount=tokens_output)
    _incr("tokens_input_by_provider", provider, tokens_input)
    _incr("tokens_output_by_provider", provider, tokens_output)
    _append_latency(provider, latency_seconds)
    if error:
        _incr("errors_total")
        _incr("errors_by_provider", provider)
    for tc in tool_calls:
        if isinstance(tc, dict) and tc.get("error"):
            _incr("tool_errors_total")
        else:
            _incr("tool_calls_total")

    _track_cost(provider, tokens_input, tokens_output)

    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def log_tool_call(request_id: str, tool_name: str, args: dict, result: str, error: str = None):
    entry = {
        "ts": datetime.datetime.now().isoformat(),
        "request_id": request_id,
        "type": "tool_call",
        "tool": tool_name,
        "args": args,
        "result_preview": str(result)[:200],
        "error": error,
    }
    _ensure_log_dir()
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def _track_cost(provider: str, tokens_input: int, tokens_output: int):
    pricing = PROVIDER_PRICING.get(provider)
    if not pricing:
        return
    cost = (tokens_input / 1_000_000) * pricing["input"]
    cost += (tokens_output / 1_000_000) * pricing["output"]
    if cost == 0:
        return
    with _cost_lock:
        _cost_totals["cost_usd_total"] += cost
        by_prov = _cost_totals.setdefault("cost_by_provider", {})
        by_prov[provider] = by_prov.get(provider, 0.0) + cost


def get_cost_summary() -> dict:
    with _cost_lock:
        return dict(_cost_totals)


def get_metrics_snapshot() -> dict:
    with _metrics_lock:
        total = _metrics.get("requests_total", 0) or 1
        latencies = _metrics.get("latency_by_provider", {})
        avg_latency = {}
        for prov, vals in latencies.items():
            if vals:
                avg_latency[prov] = round(sum(vals) / len(vals), 3)
        return {
            "requests_total": _metrics["requests_total"],
            "requests_by_provider": dict(_metrics.get("requests_by_provider", {})),
            "requests_by_intent": dict(_metrics.get("requests_by_intent", {})),
            "tokens_input_total": _metrics["tokens_input_total"],
            "tokens_output_total": _metrics["tokens_output_total"],
            "tokens_input_by_provider": dict(_metrics.get("tokens_input_by_provider", {})),
            "tokens_output_by_provider": dict(_metrics.get("tokens_output_by_provider", {})),
            "latency_avg_by_provider": avg_latency,
            "latency_avg_overall": round(_metrics["latency_seconds_total"] / total, 3),
            "tool_calls_total": _metrics["tool_calls_total"],
            "tool_errors_total": _metrics["tool_errors_total"],
            "cache_hits_total": _metrics["cache_hits_total"],
        }


def get_latest_logs(n: int = 50) -> list:
    _ensure_log_dir()
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE) as f:
            lines = f.readlines()
        return [json.loads(l) for l in lines[-n:]]
    except Exception:
        return []


def count_intents() -> dict:
    """Per-intent request counts from the persisted request log (survives restarts)."""
    _ensure_log_dir()
    counts = {}
    if not os.path.exists(LOG_FILE):
        return counts
    try:
        with open(LOG_FILE) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("type") == "tool_call":
                    continue
                intent = entry.get("intent")
                if intent:
                    counts[intent] = counts.get(intent, 0) + 1
    except OSError:
        pass
    return counts


def get_cost_report(days: int = 30) -> dict:
    cost = get_cost_summary()
    cost["estimated_daily"] = round(cost.get("cost_usd_total", 0) / max(days, 1), 4)
    cost["estimated_monthly"] = round(cost.get("estimated_daily", 0) * 30, 4)
    return cost
