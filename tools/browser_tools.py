import os
import subprocess
import time

import requests

from config import DEFAULT_BROWSER


def _applescript(script):
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip()


def _get_browser(text: str = ""):
    return "Safari" if "safari" in text.lower() else DEFAULT_BROWSER


def _activate_browser(browser: str):
    _applescript(f'tell application "{browser}" to activate')
    time.sleep(0.35)


def browser_navigate(url: str, browser: str = DEFAULT_BROWSER):
    if not url.startswith("http"):
        url = "https://" + url
    safe_url = url.replace("\\", "\\\\").replace('"', '\\"')
    _activate_browser(browser)
    if browser == "Safari":
        script = f'tell application "Safari" to set URL of current tab of front window to "{safe_url}"'
    else:
        script = (
            f'tell application "{browser}"\ntell front window to tell active tab to set URL to "{safe_url}"\nend tell'
        )
    _applescript(script)
    return f"Navigating to {url}."


def browser_quick_search(query: str, browser: str = DEFAULT_BROWSER):
    """Open in-app quick switcher (Cmd+K) — works for Discord web, Slack, etc."""
    safe = query.replace("\\", "\\\\").replace('"', '\\"')
    _activate_browser(browser)
    script = f'''tell application "System Events"
    keystroke "k" using command down
    delay 0.35
    keystroke "{safe}"
    delay 0.45
    keystroke return
end tell'''
    _applescript(script)
    return f"Quick-searched for '{query}' in {browser}."


def browser_new_tab(browser: str = DEFAULT_BROWSER):
    _activate_browser(browser)
    script = (
        'tell application "Safari" to make new tab at end of tabs of front window'
        if browser == "Safari"
        else f'tell application "{browser}" to tell front window to make new tab'
    )
    _applescript(script)
    return "Opened new tab."


def browser_close_tab(browser: str = DEFAULT_BROWSER):
    _activate_browser(browser)
    script = (
        'tell application "Safari" to close current tab of front window'
        if browser == "Safari"
        else f'tell application "{browser}" to tell front window to close active tab'
    )
    _applescript(script)
    return "Closed tab."


def browser_scroll(direction: str = "down", browser: str = DEFAULT_BROWSER):
    key = "125" if direction == "down" else "126"
    _activate_browser(browser)
    script = f'tell application "System Events"\nkey code {key}\nkey code {key}\nkey code {key}\nend tell'
    _applescript(script)
    return f"Scrolling {direction}."


def browser_back(browser: str = DEFAULT_BROWSER):
    _activate_browser(browser)
    _applescript('tell application "System Events" to keystroke "[" using command down')
    return "Going back."


def browser_forward(browser: str = DEFAULT_BROWSER):
    _activate_browser(browser)
    _applescript('tell application "System Events" to keystroke "]" using command down')
    return "Going forward."


def browser_reload(browser: str = DEFAULT_BROWSER):
    _activate_browser(browser)
    _applescript('tell application "System Events" to keystroke "r" using command down')
    return "Reloading."


def browser_current_url(browser: str = DEFAULT_BROWSER):
    script = (
        'tell application "Safari" to return URL of current tab of front window'
        if browser == "Safari"
        else f'tell application "{browser}" to return URL of active tab of front window'
    )
    out, _ = _applescript(script)
    return f"You're on: {out}" if out else "Couldn't read URL."


def web_search(query: str, search_depth: str = "basic") -> str:
    """Search the web using Tavily (structured) as primary, DuckDuckGo as fallback."""
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    if tavily_key:
        try:
            depth = "advanced" if search_depth == "advanced" else "basic"
            resp = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query, "search_depth": depth, "max_results": 5, "include_answer": True},
                timeout=10,
            )
            data = resp.json()
            parts = []
            answer = data.get("answer", "")
            if answer:
                parts.append(f"Answer: {answer[:500]}")
            for r in data.get("results", [])[:5]:
                title = r.get("title", "")
                content = r.get("content", "")[:300]
                url = r.get("url", "")
                parts.append(f"• {title}: {content} ({url})")
            if parts:
                return "\n".join(parts)
        except Exception:
            pass
    return _duckduckgo_search(query)


def _duckduckgo_search(query: str) -> str:
    """Fallback web search using DuckDuckGo's instant answer API."""
    try:
        resp = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            timeout=10,
        )
        data = resp.json()
        parts = []
        abstract = data.get("AbstractText", "")
        if abstract:
            parts.append(abstract[:500])
        for topic in data.get("RelatedTopics", [])[:3]:
            text = topic.get("Text", "") if isinstance(topic, dict) else ""
            if text:
                parts.append(text[:300])
        answer = data.get("Answer", "")
        if answer:
            parts.append(f"Answer: {answer[:300]}")
        if not parts:
            html_resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            from html.parser import HTMLParser
            class _LinkParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.results = []
                    self._capture = False
                def handle_starttag(self, tag, attrs):
                    attrs_dict = dict(attrs)
                    if tag == "a" and "result__a" in attrs_dict.get("class", ""):
                        self._capture = True
                def handle_data(self, data):
                    if self._capture:
                        self.results.append(data.strip())
                        self._capture = False
            parser = _LinkParser()
            parser.feed(html_resp.text)
            parts = parser.results[:5] if parser.results else ["Could not search: no results"]
        return "\n".join(parts[:5])
    except Exception as e:
        return f"Search failed: {e}"


BROWSER_TOOLS = {
    "browser_navigate": browser_navigate,
    "browser_quick_search": browser_quick_search,
    "browser_new_tab": browser_new_tab,
    "browser_close_tab": browser_close_tab,
    "browser_scroll": browser_scroll,
    "browser_back": browser_back,
    "browser_forward": browser_forward,
    "browser_reload": browser_reload,
    "browser_current_url": browser_current_url,
    "web_search": web_search,
}

BROWSER_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate browser to a URL (activates the browser first)",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}, "browser": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_quick_search",
            "description": "Use Cmd+K quick switcher in the browser (Discord/Slack channel search). Activates browser first.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "browser": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_new_tab",
            "description": "Open a new browser tab",
            "parameters": {"type": "object", "properties": {"browser": {"type": "string"}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close_tab",
            "description": "Close the current browser tab",
            "parameters": {"type": "object", "properties": {"browser": {"type": "string"}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": "Scroll the browser up or down",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "description": "'up' or 'down'"},
                    "browser": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_back",
            "description": "Go back in browser history",
            "parameters": {"type": "object", "properties": {"browser": {"type": "string"}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_forward",
            "description": "Go forward in browser history",
            "parameters": {"type": "object", "properties": {"browser": {"type": "string"}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_reload",
            "description": "Reload the current page",
            "parameters": {"type": "object", "properties": {"browser": {"type": "string"}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_current_url",
            "description": "Get the current page URL",
            "parameters": {"type": "object", "properties": {"browser": {"type": "string"}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using Tavily (primary) with DuckDuckGo fallback. Returns structured results with answer, title, content, and URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                    "search_depth": {"type": "string", "description": "'basic' (faster) or 'advanced' (more thorough)", "enum": ["basic", "advanced"]},
                },
                "required": ["query"],
            },
        },
    },
]
