import os
import shutil
import subprocess
import time

import psutil
import requests

from cache import cache_result
from config import (
    CACHE_SYSTEM_INFO_TTL,
    CACHE_WEATHER_TTL,
    USER_CITY,
)

HOME = os.path.expanduser("~")

APP_ALIASES = {
    "safari": "Safari",
    "chrome": "Google Chrome",
    "firefox": "Firefox",
    "dia": "Dia",
    "spotify": "Spotify",
    "terminal": "Terminal",
    "notes": "Notes",
    "calendar": "Calendar",
    "messages": "Messages",
    "mail": "Mail",
    "maps": "Maps",
    "music": "Music",
    "photos": "Photos",
    "finder": "Finder",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "slack": "Slack",
    "discord": "Discord",
    "facetime": "FaceTime",
    "calculator": "Calculator",
    "settings": "System Preferences",
    "system preferences": "System Preferences",
    "antigravity": "Antigravity",
    "zoom": "zoom.us",
    "zoom.us": "zoom.us",
}


@cache_result(ttl_seconds=CACHE_SYSTEM_INFO_TTL)
def get_system_info():
    cpu = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage(HOME)
    return {
        "cpu_percent": cpu,
        "ram_used_gb": round(ram.used / 1024**3, 1),
        "ram_available_gb": round(ram.available / 1024**3, 1),
        "ram_total_gb": round(ram.total / 1024**3, 1),
        "ram_percent": ram.percent,
        "disk_free_gb": round(disk.free / 1024**3, 1),
        "disk_total_gb": round(disk.total / 1024**3, 1),
    }


def get_top_processes(by: str = "memory", count: int = 10):
    metric = "memory" if (by or "").lower() not in ("cpu", "memory", "ram") else (by or "").lower()
    sort_key = "memory_percent" if metric in ("memory", "ram") else "cpu_percent"
    rows = []
    for proc in psutil.process_iter(["pid", "name", "memory_percent", "cpu_percent"]):
        try:
            info = proc.info
            rows.append(
                {
                    "pid": info.get("pid"),
                    "name": info.get("name") or "Unknown",
                    "memory_percent": float(info.get("memory_percent") or 0),
                    "cpu_percent": float(info.get("cpu_percent") or 0),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    rows.sort(key=lambda item: item[sort_key], reverse=True)
    lines = [f"Top processes by {'RAM' if sort_key == 'memory_percent' else 'CPU'}:"]
    for item in rows[: max(1, min(int(count or 10), 25))]:
        lines.append(f"{item['name']} (pid {item['pid']}): RAM {item['memory_percent']:.1f}%, CPU {item['cpu_percent']:.1f}%")
    return "\n".join(lines)


from tools.weather_fallback import weather_fallback_detailed


def get_weather(city=USER_CITY):
    try:
        resp = requests.get(f"https://wttr.in/{city}?format=3", timeout=10)
        return resp.text.strip()
    except Exception as e:
        return f"Couldn't fetch weather: {e}"


@cache_result(ttl_seconds=CACHE_WEATHER_TTL)
def get_weather_detailed():
    return weather_fallback_detailed()


def open_app(app_name: str):
    app = APP_ALIASES.get(app_name.lower().strip(), app_name)
    try:
        subprocess.run(["open", "-a", app], check=True)
        return f"Opened {app}."
    except subprocess.CalledProcessError:
        return f"Couldn't find {app}. Make sure it's installed."


def focus_app(app_name: str):
    """Bring an app to the foreground so screenshots and keystrokes target it."""
    app = APP_ALIASES.get(app_name.lower().strip(), app_name)
    script = f'tell application "{app}" to activate'
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return f"Couldn't focus {app}. {err[:120]}".strip()
    time.sleep(0.45)
    return f"Focused {app}."


def quit_app(app_name: str):
    script = f'tell application "{app_name}" to quit'
    subprocess.run(["osascript", "-e", script])
    return f"Quit {app_name}."


def get_open_apps():
    script = 'tell application "System Events" to get name of every process whose background only is false'
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    apps = [a.strip() for a in result.stdout.strip().split(",")]
    return f"Open apps: {', '.join(apps)}"


def disk_usage():
    total, used, free = shutil.disk_usage(HOME)
    gb = lambda b: b / (1024**3)
    return f"Disk: {gb(total):.0f}GB total, {gb(used):.0f}GB used, {gb(free):.0f}GB free."


def semantic_search_memory(query: str):
    from memory import semantic_search

    result = semantic_search(query)
    return result if result else "No relevant memories found."


def get_recap(hours: int = 8):
    from watchlog import build_recap

    return build_recap(hours)


def get_recent_events(hours: int = 2):
    from watchlog import get_events_since

    events = get_events_since(hours)
    if not events:
        return f"Nothing notable in the last {hours} hours."
    return "\n".join([f"[{e[3][11:16]}] {e[0]}: {e[1]}" for e in events])


import threading

_active_timers = {}


def set_timer(label: str, seconds: int):
    from tts import speak

    def _run():
        import time

        time.sleep(seconds)
        if label in _active_timers:
            del _active_timers[label]
            speak(f"Timer done! {label}")

    t = threading.Thread(target=_run, daemon=True)
    _active_timers[label] = t
    t.start()
    mins, secs = seconds // 60, seconds % 60
    parts = []
    if mins:
        parts.append(f"{mins} minute{'s' if mins > 1 else ''}")
    if secs:
        parts.append(f"{secs} second{'s' if secs > 1 else ''}")
    return f"Timer set for {' and '.join(parts)}."


def cancel_timer():
    if not _active_timers:
        return "No active timers."
    key = list(_active_timers.keys())[-1]
    del _active_timers[key]
    return f"Timer '{key}' cancelled."


def search_my_notes(query: str):
    """Search through user's personal notes and documents."""
    from rag_memory import search_rag

    return search_rag(query)


def query_my_knowledge_graph(entity: str):
    """Query relationships and connections about any person, project or concept."""
    from graph_memory import query_relationships

    return query_relationships(entity)


def add_to_knowledge_graph(entity1: str, relationship: str, entity2: str):
    """Add a relationship to the knowledge graph."""
    from graph_memory import add_entity, add_relationship

    add_entity(entity1, "concept")
    add_entity(entity2, "concept")
    add_relationship(entity1, relationship, entity2)
    return f"Added: {entity1} -> {relationship} -> {entity2}"


# def list_directory(path: str = "~/Jarvis") -> str:
#     import os
#     folder = os.path.expanduser(path)
#     if not os.path.exists(folder):
#         return f"Folder not found: {folder}"
#     files = os.listdir(folder)
#     return "\n".join(sorted(files)) if files else "Empty folder."


# ── WarWatch News ─────────────────────────────


def warwatch_news(query: str = "latest") -> str:
    """Fetch and summarize news from war-watch.com. Query can filter by topic (e.g. 'nuclear', 'iran', 'ukraine', 'china')."""
    url = "https://www.war-watch.com/feed"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return f"WarWatch returned status {resp.status_code}."
        html = resp.text
    except Exception as e:
        return f"Could not fetch WarWatch: {e}"

    # Parse article cards from HTML
    import re

    articles = []
    # Match article blocks: each has h3 title, p summary, span source, severity
    pattern = r'<article[^>]*>.*?<h3[^>]*>(.*?)</h3>.*?<p[^>]*>(.*?)</p>.*?<div class="font-mono[^"]*"[^>]*>([^<]*)<'
    matches = re.findall(pattern, html, re.DOTALL)
    for title, summary, source in matches[:15]:
        title = re.sub(r"<[^>]+>", "", title).strip()
        summary = re.sub(r"<[^>]+>", "", summary).strip()
        source = source.strip()
        articles.append({"title": title, "summary": summary[:200], "source": source})

    if not articles:
        return "No articles found from WarWatch feed."

    # Filter by query if not "latest"
    q = query.lower().strip()
    if q and q != "latest":
        filtered = [a for a in articles if q in a["title"].lower() or q in a["summary"].lower()]
        if filtered:
            articles = filtered
        # If no matches, keep all but note the filter

    lines = [f"WarWatch News ({query}):"]
    for a in articles[:8]:
        lines.append(f"• {a['title']}")
        lines.append(f"  {a['summary'][:120]} — {a['source']}")
    return "\n".join(lines)


# ── Exports ──────────────────────────────────
def save_api_key(key_name: str, key_value: str) -> str:
    """Save an API key to the .env file. Validates the key name and persists it."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    env_path = os.path.abspath(env_path)
    if not os.path.exists(env_path):
        return f".env not found at {env_path}"
    key = key_name.strip().upper().replace(" ", "_")
    with open(env_path) as f:
        lines = f.readlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={key_value}\n"
            found = True
            break
    if not found:
        lines.append(f"\n# ── {key_name} ──\n{key}={key_value}\n")
    with open(env_path, "w") as f:
        f.writelines(lines)
    return f"Saved {key} to .env"


def list_configured_keys(masked: bool = True) -> str:
    """List all configured API keys in .env. When masked=True, shows only first/last 4 chars."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    env_path = os.path.abspath(env_path)
    if not os.path.exists(env_path):
        return ".env not found"
    keys = []
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#") and not line.startswith("export "):
                k, v = line.split("=", 1)
                if v:
                    display = f"{v[:4]}...{v[-4:]}" if masked and len(v) > 12 else v
                    keys.append(f"  {k}={display}")
    return "Configured keys:\n" + "\n".join(sorted(keys)) if keys else "No keys configured."


SYSTEM_TOOLS = {
    "get_system_info": get_system_info,
    "get_top_processes": get_top_processes,
    "get_weather": get_weather,
    "get_weather_detailed": get_weather_detailed,
    "open_app": open_app,
    "focus_app": focus_app,
    "quit_app": quit_app,
    "get_open_apps": get_open_apps,
    "disk_usage": disk_usage,
    "semantic_search_memory": semantic_search_memory,
    "get_recap": get_recap,
    "get_recent_events": get_recent_events,
    "set_timer": set_timer,
    "cancel_timer": cancel_timer,
    "search_my_notes": search_my_notes,
    "query_my_knowledge_graph": query_my_knowledge_graph,
    "add_to_knowledge_graph": add_to_knowledge_graph,
    "warwatch_news": warwatch_news,
    "save_api_key": save_api_key,
    "list_configured_keys": list_configured_keys,
}

SYSTEM_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Get current CPU, RAM, and disk usage. Also provides system info including public IP address and battery/charging status. Use this for 'what's my ip', 'battery level', 'system usage' queries.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_processes",
            "description": "Get the top running macOS processes by RAM or CPU usage. Prefer this over shell ps commands for memory questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "by": {"type": "string", "description": "memory, ram, or cpu"},
                    "count": {"type": "integer", "description": "Number of processes to return"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get a short current weather summary for a city (default your location)",
            "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_detailed",
            "description": "Get detailed current weather including temp, humidity, wind, and rain chance. Uses your configured location.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open a Mac application",
            "parameters": {"type": "object", "properties": {"app_name": {"type": "string"}}, "required": ["app_name"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "focus_app",
            "description": "Bring an app to the foreground before screen vision or keyboard automation",
            "parameters": {"type": "object", "properties": {"app_name": {"type": "string"}}, "required": ["app_name"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quit_app",
            "description": "Quit a Mac application",
            "parameters": {"type": "object", "properties": {"app_name": {"type": "string"}}, "required": ["app_name"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_open_apps",
            "description": "Get list of currently open applications",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "disk_usage",
            "description": "Get disk space usage",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search_memory",
            "description": "Search long-term memory semantically by meaning",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recap",
            "description": "Get a recap of everything Jarvis monitored while user was away",
            "parameters": {"type": "object", "properties": {"hours": {"type": "integer"}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_events",
            "description": "Get recent events logged by Jarvis",
            "parameters": {"type": "object", "properties": {"hours": {"type": "integer"}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Set a timer that speaks when done",
            "parameters": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "seconds": {"type": "integer"}},
                "required": ["label", "seconds"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_timer",
            "description": "Cancel the most recent timer",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_my_notes",
            "description": "Search through user's personal notes and documents",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_my_knowledge_graph",
            "description": "Query relationships and connections about any person, project or concept",
            "parameters": {"type": "object", "properties": {"entity": {"type": "string"}}, "required": ["entity"]},
        },
    },
    # {"type":"function","function":{"name":"list_directory","description":"List files in a folder","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":[]}}},
    {
        "type": "function",
        "function": {
            "name": "add_to_knowledge_graph",
            "description": "Add a relationship to the user's knowledge graph",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity1": {"type": "string"},
                    "relationship": {"type": "string"},
                    "entity2": {"type": "string"},
                },
                "required": ["entity1", "relationship", "entity2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "warwatch_news",
            "description": "Fetch and summarize news from WarWatch (war-watch.com). Main news source for global conflicts, war zones, and geopolitics. Query filters by topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Topic to filter news by (e.g. 'nuclear', 'iran', 'ukraine', 'russia', 'china', 'middle east'). Default 'latest'."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_api_key",
            "description": "Save or update an API key in the .env configuration file. Use this when the user gives you a new API key. Never just narrate 'key saved' without calling this tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key_name": {"type": "string", "description": "Name of the key (e.g. WEATHERAPI_KEY, SERPAPI_KEY, NEWSAPI_KEY, OPENAI_API_KEY, GOOGLE_MAPS_API_KEY, ALPHA_VANTAGE_KEY)"},
                    "key_value": {"type": "string", "description": "The actual API key value"},
                },
                "required": ["key_name", "key_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_configured_keys",
            "description": "List all configured API keys from .env. Keys are masked by default (shows first/last 4 chars). Use this to verify what keys are configured.",
            "parameters": {
                "type": "object",
                "properties": {
                    "masked": {"type": "boolean", "description": "Whether to mask the key values (default: true)"},
                },
                "required": [],
            },
        },
    },
]
