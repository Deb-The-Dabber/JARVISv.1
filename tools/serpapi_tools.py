import requests

from config import SERPAPI_API_KEY

BASE = "https://serpapi.com/search"


def _search(params: dict) -> dict:
    params["api_key"] = SERPAPI_API_KEY
    resp = requests.get(BASE, params=params, timeout=15)
    return resp.json()


def search_web(query: str, location: str = "", num_results: int = 5, engine: str = "google"):
    """Search the web using SerpAPI (Google, Bing, DuckDuckGo, etc.)."""
    params = {"q": query, "engine": engine, "num": min(num_results, 10)}
    if location:
        params["location"] = location
    try:
        data = _search(params)
        results = data.get("organic_results", [])[:num_results]
        if not results:
            return f"No search results for '{query}'."
        lines = [f"Search results for '{query}' ({engine}):"]
        for r in results:
            title = r.get("title", "")
            link = r.get("link", "")
            snippet = r.get("snippet", "")
            lines.append(f"- {title}")
            lines.append(f"  {snippet}")
            lines.append(f"  {link}")
        return "\n".join(lines)
    except Exception as e:
        return f"SerpAPI search failed: {e}"


def search_news(query: str):
    """Search news articles via SerpAPI."""
    params = {"q": query, "engine": "google", "tbm": "nws", "num": 5}
    try:
        data = _search(params)
        results = data.get("news_results", [])[:5]
        if not results:
            return f"No news results for '{query}'."
        lines = [f"News results for '{query}':"]
        for r in results:
            title = r.get("title", "")
            source = r.get("source", "")
            snippet = r.get("snippet", "")
            lines.append(f"- {title} ({source})")
            if snippet:
                lines.append(f"  {snippet}")
        return "\n".join(lines)
    except Exception as e:
        return f"SerpAPI news search failed: {e}"


def search_shopping(query: str):
    """Search shopping/products via SerpAPI Google Shopping."""
    params = {"q": query, "engine": "google", "tbm": "shop", "num": 5}
    try:
        data = _search(params)
        results = data.get("shopping_results", [])[:5]
        if not results:
            return f"No shopping results for '{query}'."
        lines = [f"Shopping results for '{query}':"]
        for r in results:
            title = r.get("title", "")
            price = r.get("price", "")
            source = r.get("source", "")
            link = r.get("link", "")
            lines.append(f"- {title} - {price} ({source})")
            lines.append(f"  {link}")
        return "\n".join(lines)
    except Exception as e:
        return f"SerpAPI shopping search failed: {e}"


SERPAPI_TOOLS = {
    "search_web": search_web,
    "search_news": search_news,
    "search_shopping": search_shopping,
}

SERPAPI_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web via SerpAPI (Google, Bing, DuckDuckGo). Returns results with snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "location": {"type": "string", "description": "Location for localized results"},
                    "num_results": {"type": "integer", "description": "Number of results (max 10)"},
                    "engine": {"type": "string", "description": "Search engine: google, bing, duckduckgo"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "Search news articles via SerpAPI Google News.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "News search query"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_shopping",
            "description": "Search shopping/product listings via SerpAPI Google Shopping. Returns prices and sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Product search query"},
                },
                "required": ["query"],
            },
        },
    },
]
