import datetime

import requests

from config import ALPHA_VANTAGE_API_KEY, ALPHA_VANTAGE_DAILY_LIMIT

BASE = "https://www.alphavantage.co/query"

_usage_today = 0
_last_reset_date = datetime.date.today()


def _check_rate_limit() -> bool:
    """Return True if under daily limit, False if exceeded."""
    global _usage_today, _last_reset_date
    today = datetime.date.today()
    if today != _last_reset_date:
        _usage_today = 0
        _last_reset_date = today
    if _usage_today >= ALPHA_VANTAGE_DAILY_LIMIT:
        return False
    return True


def _get(params: dict) -> dict | str:
    global _usage_today
    if not _check_rate_limit():
        return f"Alpha Vantage daily limit ({ALPHA_VANTAGE_DAILY_LIMIT}) reached. Try again tomorrow."
    params["apikey"] = ALPHA_VANTAGE_API_KEY
    try:
        resp = requests.get(BASE, params=params, timeout=10)
        data = resp.json()
        _usage_today += 1
        if "Note" in data and "API call frequency" in data["Note"]:
            return f"Alpha Vantage rate limited: {data['Note'][:200]}"
        return data
    except Exception as e:
        return f"Alpha Vantage request failed: {e}"


def get_stock_quote(symbol: str):
    """Get real-time stock quote for a symbol."""
    data = _get({"function": "GLOBAL_QUOTE", "symbol": symbol.upper()})
    if isinstance(data, str):
        return data
    quote = data.get("Global Quote", {})
    if not quote:
        return f"No quote data found for '{symbol}'."
    return (
        f"{symbol.upper()}: ${quote.get('05. price', 'N/A')} "
        f"(change: {quote.get('10. change percent', 'N/A')}) "
        f"high: ${quote.get('03. high', 'N/A')} "
        f"low: ${quote.get('04. low', 'N/A')} "
        f"volume: {quote.get('06. volume', 'N/A')}"
    )


def get_stock_time_series(symbol: str, interval: str = "daily"):
    """Get historical time series for a stock symbol."""
    interval_map = {
        "daily": {"fn": "TIME_SERIES_DAILY", "key": "Time Series (Daily)"},
        "weekly": {"fn": "TIME_SERIES_WEEKLY", "key": "Weekly Time Series"},
        "monthly": {"fn": "TIME_SERIES_MONTHLY", "key": "Monthly Time Series"},
    }
    spec = interval_map.get(interval, interval_map["daily"])
    data = _get({"function": spec["fn"], "symbol": symbol.upper(), "outputsize": "compact"})
    if isinstance(data, str):
        return data
    series = data.get(spec["key"], {})
    if not series:
        return f"No time series data found for '{symbol}'."
    dates = sorted(series.keys(), reverse=True)[:5]
    lines = [f"{symbol.upper()} {interval} prices (last {len(dates)} periods):"]
    for d in dates:
        entry = series[d]
        close = entry.get("4. close", "N/A")
        volume = entry.get("5. volume", "N/A")
        lines.append(f"  {d}: close ${close} volume {volume}")
    return "\n".join(lines)


def get_forex_rate(from_currency: str, to_currency: str):
    """Get real-time exchange rate between two currencies."""
    params = {"function": "CURRENCY_EXCHANGE_RATE", "from_currency": from_currency.upper(), "to_currency": to_currency.upper()}
    data = _get(params)
    if isinstance(data, str):
        return data
    rate = data.get("Realtime Currency Exchange Rate", {})
    if not rate:
        return f"No forex rate found for {from_currency}/{to_currency}."
    return f"{from_currency.upper()}/{to_currency.upper()}: {rate.get('5. Exchange Rate', 'N/A')} (bid: {rate.get('8. Bid Price', 'N/A')} ask: {rate.get('9. Ask Price', 'N/A')})"


def get_crypto_quote(symbol: str):
    """Get real-time cryptocurrency quote in USD."""
    data = _get({"function": "CURRENCY_EXCHANGE_RATE", "from_currency": symbol.upper(), "to_currency": "USD"})
    if isinstance(data, str):
        return data
    rate = data.get("Realtime Currency Exchange Rate", {})
    if not rate:
        return f"No crypto data found for '{symbol}'."
    return f"{symbol.upper()}/USD: ${rate.get('5. Exchange Rate', 'N/A')}"


FINANCE_TOOLS = {
    "get_stock_quote": get_stock_quote,
    "get_stock_time_series": get_stock_time_series,
    "get_forex_rate": get_forex_rate,
    "get_crypto_quote": get_crypto_quote,
}

FINANCE_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_stock_quote",
            "description": "Get real-time stock quote (price, change, high, low, volume). Rate-limited.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock symbol (e.g. AAPL, MSFT, GOOGL)"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_time_series",
            "description": "Get historical time series (daily/weekly/monthly) for a stock symbol.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Stock symbol"},
                    "interval": {"type": "string", "description": "daily, weekly, or monthly"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_forex_rate",
            "description": "Get real-time exchange rate between two currencies (e.g. USD to EUR).",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_currency": {"type": "string", "description": "Source currency code (e.g. USD)"},
                    "to_currency": {"type": "string", "description": "Target currency code (e.g. EUR)"},
                },
                "required": ["from_currency", "to_currency"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_crypto_quote",
            "description": "Get real-time cryptocurrency quote in USD (e.g. BTC, ETH).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Cryptocurrency symbol (e.g. BTC, ETH, SOL)"},
                },
                "required": ["symbol"],
            },
        },
    },
]
