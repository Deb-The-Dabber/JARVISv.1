
import requests

from config import NEWSAPI_API_KEY

BASE = "https://newsapi.org/v2"


def fetch_top_headlines(category: str = "", country: str = "us", query: str = ""):
    """Fetch top headlines by category (business, tech, sports, etc.) or query."""
    params = {"apiKey": NEWSAPI_API_KEY, "country": country}
    if category:
        params["category"] = category
    if query:
        params["q"] = query
    try:
        resp = requests.get(f"{BASE}/top-headlines", params=params, timeout=10)
        data = resp.json()
        if data.get("status") != "ok":
            return f"NewsAPI error: {data.get('message', 'unknown')}"
        articles = data.get("articles", [])[:5]
        if not articles:
            return f"No top headlines found{f' for {query}' if query else ''}."
        lines = [f"Top headlines{f' in {category}' if category else ''}:".format()]
        for a in articles:
            title = a.get("title", "")
            source = a.get("source", {}).get("name", "")
            lines.append(f"- {title} ({source})")
        return "\n".join(lines)
    except Exception as e:
        return f"NewsAPI request failed: {e}"


def fetch_everything(query: str, from_date: str = "", language: str = "en"):
    """Search all news articles matching a query."""
    if not query:
        return "Query is required."
    params = {"apiKey": NEWSAPI_API_KEY, "q": query, "language": language, "pageSize": 5}
    if from_date:
        params["from"] = from_date
    try:
        resp = requests.get(f"{BASE}/everything", params=params, timeout=10)
        data = resp.json()
        if data.get("status") != "ok":
            return f"NewsAPI error: {data.get('message', 'unknown')}"
        articles = data.get("articles", [])[:5]
        if not articles:
            return f"No news found for '{query}'."
        lines = [f"News results for '{query}':"]
        for a in articles:
            title = a.get("title", "")
            source = a.get("source", {}).get("name", "")
            desc = a.get("description") or ""
            lines.append(f"- {title} ({source})")
            if desc:
                lines.append(f"  {desc[:120]}")
        return "\n".join(lines)
    except Exception as e:
        return f"NewsAPI request failed: {e}"


NEWS_TOOLS = {
    "fetch_top_headlines": fetch_top_headlines,
    "fetch_everything": fetch_everything,
}

NEWS_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "fetch_top_headlines",
            "description": "Fetch top news headlines by category or keyword. Pass category for curated headlines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Category (business, tech, sports, etc.)"},
                    "country": {"type": "string", "description": "Two-letter country code (default: us)"},
                    "query": {"type": "string", "description": "Keyword search within headlines"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_everything",
            "description": "Search all news articles matching a query. Use for specific topics, people, or events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (required)"},
                    "from_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "language": {"type": "string", "description": "Language code (default: en)"},
                },
                "required": ["query"],
            },
        },
    },
]
