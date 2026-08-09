# ruff: noqa: E501 — template lines are intentionally long phrase lists.
"""Training data for the fine-grained specialist routers.

Sources:
1. Real labeled requests from ~/.jarvis/logs/jarvis.jsonl — request entries with
   non-empty tool_calls map to fine intents via taxonomy.yaml tool_to_intent.
2. Synthetic template generation per fine class (slots filled from vocabularies
   and expanded with polite prefixes/pronoun swaps to reach synth_per_class).
"""

import json
import os
import random
from pathlib import Path

import yaml

TAXONOMY_PATH = Path(__file__).resolve().parent.parent.parent / "taxonomy.yaml"
LOG_FILE = Path(os.path.expanduser("~/.jarvis/logs/jarvis.jsonl"))

BUCKETS = ("chat", "coding", "tool_use", "reasoning", "self_mod", "automation")

_taxonomy: dict | None = None


def get_taxonomy() -> dict:
    global _taxonomy
    if _taxonomy is None:
        with open(TAXONOMY_PATH) as f:
            _taxonomy = yaml.safe_load(f)
    return _taxonomy


def fine_classes(bucket: str) -> list[str]:
    return list(get_taxonomy()[bucket])


def all_fine_classes() -> dict[str, list[str]]:
    tax = get_taxonomy()
    return {b: list(tax[b]) for b in BUCKETS}


def tool_to_fine(tool_name: str) -> str | None:
    """Map a cleaned tool name to its fine intent via taxonomy.yaml."""
    return get_taxonomy().get("tool_to_intent", {}).get(tool_name)


# ── Real data: jarvis.jsonl request entries with tool_calls ──


def _clean_tool_name(raw: str) -> str:
    """Strip log-serialized args: 'get_weather_detailed:[]' → 'get_weather_detailed'."""
    name = raw.split(":[")[0].split(":")[0].strip()
    return name


def load_real_fine_examples(bucket: str) -> list[tuple[str, str]]:
    """Return [(text, fine_intent)] for a bucket, derived from tool_calls in the log.

    Only entries whose coarse intent equals the bucket AND whose first tool maps
    to a fine class of that bucket are used. Also returns entries for the
    'chat' bucket whose tool_calls map into chat classes (e.g. greet).
    """
    examples: list[tuple[str, str]] = []
    if not LOG_FILE.exists():
        return examples
    with open(LOG_FILE) as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") == "tool_call":
                continue
            coarse = entry.get("intent")
            text = (entry.get("user_message_preview") or entry.get("user_message") or "").strip()
            tcs = entry.get("tool_calls") or []
            if coarse != bucket or not text or len(text) < 2 or not tcs:
                continue
            for tc in tcs:
                if not isinstance(tc, str):
                    continue
                fine = tool_to_fine(_clean_tool_name(tc))
                if fine and fine in fine_classes(bucket):
                    examples.append((text, fine))
                    break
    return examples


# ── Synthetic templates ──

_PREFIXES = [
    "",
    "can you ",
    "please ",
    "could you ",
    "hey jarvis, ",
    "i need you to ",
    "would you ",
    "do me a favor and ",
]

_CITIES = ["Chicago", "Tokyo", "Paris", "London", "New York", "Austin", "Denver", "Seattle", "Berlin", "Mumbai"]
_APPS = ["Safari", "Chrome", "Spotify", "Discord", "Finder", "Calendar", "Notes", "Terminal", "Photos", "Messages"]
_SONGS = ["bohemian rhapsody", "stairway to heaven", "imagine", "yesterday", "hotel california", "billie jean"]
_FILES = ["report.txt", "notes.md", "budget.csv", "resume.pdf", "todo.txt", "config.json", "data.csv"]
_DIRS = ["~/Downloads", "~/Documents", "~/Desktop", "~/Jarvis", "~/Projects", "~/Music"]
_TOOLS = ["screwdriver", "calculator", "clipboard", "compiler", "linter"]
_QUERIES = [
    "python 3.13 release",
    "best budget laptops 2026",
    "how to make sourdough",
    "cheap flights to Tokyo",
    "AI news this week",
    "latest mac mini specs",
    "electric car tax credit",
    "top rated headphones",
]
_CONTACTS = ["mom", "dad", "john", "sarah", "the team", "project group"]
_MESSAGES = [
    "i'll be late",
    "meeting moved to 3pm",
    "happy birthday",
    "see you tomorrow",
    "can you pick up milk",
    "send the report",
]
_REMINDERS = ["call john", "water the plants", "submit expense report", "book dentist", "pay rent", "backup laptop"]
_EVENTS = ["dentist appointment", "team standup", "dinner with sarah", "gym session", "project deadline"]
_STOCKS = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GOOG"]
_CRYPTO = ["bitcoin", "ethereum", "solana", "dogecoin"]
_URLS = ["https://example.com", "https://news.ycombinator.com", "https://github.com", "https://youtube.com"]
_TOPICS = ["the economy", "climate change", "neural networks", "quantum computing", "the stock market", "photosynthesis"]
_CONCEPTS = ["gravity", "machine learning", "inflation", "how batteries work", "the water cycle", "blockchain"]
_GOALS = ["run a marathon", "learn spanish", "save for a house", "write a book", "lose 10 pounds"]
_NEWS = ["technology", "finance", "world news", "sports", "science"]

# Bucket → fine class → list of template functions (takes rng, returns phrasing)
_TEMPLATES: dict[str, dict[str, list]] = {}

_S = {
    "tool_use": {
        "app_open": [lambda r: f"open {r.choice(_APPS)}", lambda r: f"launch {r.choice(_APPS)}", lambda r: f"start {r.choice(_APPS)}", lambda r: f"open up {r.choice(_APPS)}", lambda r: f"fire up {r.choice(_APPS)}"],
        "app_close": [lambda r: f"quit {r.choice(_APPS)}", lambda r: f"close {r.choice(_APPS)}", lambda r: f"exit {r.choice(_APPS)}", lambda r: f"shut down {r.choice(_APPS)}"],
        "app_focus": [lambda r: f"focus {r.choice(_APPS)}", lambda r: f"switch to {r.choice(_APPS)}", lambda r: f"bring {r.choice(_APPS)} to the front", lambda r: f"go to {r.choice(_APPS)} window", lambda r: f"make {r.choice(_APPS)} the active app"],
        "browser_navigate": [lambda r: f"go to {r.choice(_URLS)}", lambda r: f"open {r.choice(_URLS)} in the browser", lambda r: f"navigate to {r.choice(_URLS)}", lambda r: f"browse to {r.choice(_URLS)}", lambda r: f"load {r.choice(_URLS)}"],
        "browser_search": [lambda r: f"search the web for {r.choice(_QUERIES)}", lambda r: f"search for {r.choice(_QUERIES)}", lambda r: f"look up {r.choice(_QUERIES)} online", lambda r: f"find {r.choice(_QUERIES)} on the internet", lambda r: f"web search {r.choice(_QUERIES)}", lambda r: f"google {r.choice(_QUERIES)}", lambda r: f"search online for {r.choice(_QUERIES)}", lambda r: f"look up {r.choice(_QUERIES)} on the web", lambda r: f"what does the internet say about {r.choice(_QUERIES)}", lambda r: f"research {r.choice(_QUERIES)} online"],
        "file_read": [lambda r: f"read {r.choice(_FILES)}", lambda r: f"show me the contents of {r.choice(_FILES)}", lambda r: f"open {r.choice(_FILES)} and read it", lambda r: f"display {r.choice(_FILES)}", lambda r: f"cat {r.choice(_FILES)}"],
        "file_write": [lambda r: f"write {r.choice(_FILES)}", lambda r: f"save {r.choice(_QUERIES)} to {r.choice(_FILES)}", lambda r: f"update {r.choice(_FILES)}", lambda r: f"append to {r.choice(_FILES)}", lambda r: f"create a note in {r.choice(_FILES)}"],
        "file_create": [lambda r: f"create a new file called {r.choice(_FILES)}", lambda r: f"make {r.choice(_FILES)}", lambda r: f"create {r.choice(_FILES)} in {r.choice(_DIRS)}", lambda r: f"new file named {r.choice(_FILES)}"],
        "file_list": [lambda r: f"list the files in {r.choice(_DIRS)}", lambda r: f"what's in {r.choice(_DIRS)}", lambda r: f"show my files in {r.choice(_DIRS)}", lambda r: f"open {r.choice(_DIRS)} in finder", lambda r: f"show {r.choice(_DIRS)} in the finder"],
        "file_search": [lambda r: f"search for {r.choice(_QUERIES)} in my files", lambda r: f"find files containing {r.choice(_QUERIES)}", lambda r: f"grep for {r.choice(_QUERIES)} in {r.choice(_DIRS)}", lambda r: f"search my documents for {r.choice(_QUERIES)}"],
        "sys_info": [lambda r: "what's my system usage", lambda r: "show me system info", lambda r: "how's my computer doing", lambda r: "what are my system stats", lambda r: "get system information", lambda r: "how much cpu and memory am i using"],
        "disk_usage": [lambda r: "how much disk space do i have", lambda r: "check disk usage", lambda r: "what's my storage situation", lambda r: "how full is my hard drive", lambda r: "show me disk space", lambda r: "what are my largest files"],
        "process_list": [lambda r: "what processes are running", lambda r: "show me running processes", lambda r: "top processes right now", lambda r: "what's eating my cpu", lambda r: "list the top processes"],
        "calendar_add": [lambda r: f"add {r.choice(_EVENTS)} to my calendar", lambda r: f"schedule {r.choice(_EVENTS)} for tomorrow", lambda r: f"put {r.choice(_EVENTS)} on my calendar", lambda r: f"create a calendar event for {r.choice(_EVENTS)}", lambda r: "book a meeting at 3pm tomorrow"],
        "calendar_get": [lambda r: "what's on my calendar today", lambda r: "show me my events", lambda r: "what meetings do i have today", lambda r: "what's my schedule for tomorrow", lambda r: "do i have anything on the calendar", lambda r: "show me my calendar", lambda r: "show my calendar", lambda r: "what does my calendar look like"],
        "message_send": [lambda r: f"text {r.choice(_CONTACTS)} that {r.choice(_MESSAGES)}", lambda r: f"send an imessage to {r.choice(_CONTACTS)} saying {r.choice(_MESSAGES)}", lambda r: f"message {r.choice(_CONTACTS)} on discord", lambda r: f"send a discord message to {r.choice(_CONTACTS)}: {r.choice(_MESSAGES)}", lambda r: f"imessage {r.choice(_CONTACTS)} {r.choice(_MESSAGES)}"],
        "spotify_control": [lambda r: f"play {r.choice(_SONGS)} on spotify", lambda r: "pause the music", lambda r: "skip to the next song", lambda r: "go back a song", lambda r: "turn the volume up", lambda r: "turn the volume down", lambda r: "play some music", lambda r: "start playing music on spotify", lambda r: "stop the music", lambda r: "what's playing right now"],
        "timer_set": [lambda r: "set a timer for 10 minutes", lambda r: f"set a timer called {r.choice(_CONTACTS)} for 5 minutes", lambda r: "start a 20 minute timer", lambda r: "timer for 15 minutes", lambda r: "set an alarm for 7am"],
        "timer_cancel": [lambda r: "cancel the timer", lambda r: "stop the timer", lambda r: "delete the countdown", lambda r: "kill the timer that's running"],
        "screen_describe": [lambda r: "what's on my screen", lambda r: "read my screen", lambda r: "summarize what's on screen", lambda r: "tell me what you see on my display", lambda r: "describe the current screen"],
        "weather_current": [lambda r: f"what's the weather in {r.choice(_CITIES)}", lambda r: f"what is the weather in {r.choice(_CITIES)}", lambda r: f"how is the weather in {r.choice(_CITIES)}", lambda r: f"weather in {r.choice(_CITIES)}", lambda r: "how's the weather outside", lambda r: "is it raining", lambda r: "what's the temperature right now", lambda r: f"current conditions in {r.choice(_CITIES)}", lambda r: f"weather right now in {r.choice(_CITIES)}"],
        "weather_detailed": [lambda r: f"give me the full forecast for {r.choice(_CITIES)}", lambda r: f"detailed weather report for {r.choice(_CITIES)}", lambda r: "what's the 7 day forecast", lambda r: "weather forecast for the weekend", lambda r: "how's the humidity and wind today"],
        "finance_quote": [lambda r: f"what's {r.choice(_STOCKS)} stock price", lambda r: f"get a quote for {r.choice(_STOCKS)}", lambda r: f"how's {r.choice(_CRYPTO)} doing", lambda r: f"{r.choice(_CRYPTO)} price now", lambda r: "eur to usd exchange rate", lambda r: f"what's {r.choice(_STOCKS)} trading at"],
        "reminders_manage": [lambda r: f"remind me to {r.choice(_REMINDERS)}", lambda r: f"set a reminder to {r.choice(_REMINDERS)}", lambda r: "what reminders do i have", lambda r: "show my reminders", lambda r: "mark my reminder as done", lambda r: "delete my reminders", lambda r: f"remind me about {r.choice(_REMINDERS)} at 5pm"],
        "gdrive_manage": [lambda r: "list my drive files", lambda r: "upload this file to drive", lambda r: "download the file from drive", lambda r: "share the doc on drive", lambda r: "create a folder in drive", lambda r: "search drive for the report"],
        "gsheets_manage": [lambda r: "create a spreadsheet", lambda r: "add this data to the sheet", lambda r: "update the budget sheet", lambda r: "show me the sheet values", lambda r: "append a row to the spreadsheet"],
        "gmail_manage": [lambda r: "search my email for invoices", lambda r: "send an email", lambda r: "show me that email from mom", lambda r: "check my mail for the confirmation", lambda r: "draft an email to the team"],
        "github_manage": [lambda r: "list my github repos", lambda r: "show open issues on this repo", lambda r: "create a github issue", lambda r: "search github code for this function", lambda r: "check the repo on github"],
        "knowledge_add": [lambda r: "remember that debasish likes dark chocolate", lambda r: "add to the knowledge graph that i work at acme", lambda r: "note that my brother lives in seattle", lambda r: "record that my favorite movie is inception"],
        "knowledge_query": [lambda r: "what do you know about my family", lambda r: "query the knowledge graph for my contacts", lambda r: "what facts do you have about debasish", lambda r: "check the knowledge graph for this person"],
        "memory_search": [lambda r: "search my memories for what i said about coffee", lambda r: "do you remember anything about my trip", lambda r: "search my notes for the meeting notes", lambda r: "find my past notes on this topic"],
        "recap_get": [lambda r: "give me a recap of my day", lambda r: "what did we do this week", lambda r: "recap my last few days", lambda r: "summarize what i've been working on"],
        "goals_manage": [lambda r: f"add a goal to {r.choice(_GOALS)}", lambda r: "what are my goals", lambda r: "update my goal status", lambda r: f"mark progress on {r.choice(_GOALS)}", lambda r: "set a next check for my goal"],
        "news_fetch": [lambda r: f"show me {r.choice(_NEWS)} headlines", lambda r: "what's in the news today", lambda r: f"get the top stories in {r.choice(_NEWS)}", lambda r: "fetch today's headlines", lambda r: f"any news on {r.choice(_TOPICS)}"],
        "shopping_search": [lambda r: "find a cheap coffee maker", lambda r: "search shopping for headphones under 100", lambda r: "what's the best price for a laptop stand", lambda r: "shop for running shoes"],
        "diagnostics": [lambda r: "what's wrong with my system", lambda r: "diagnose this issue", lambda r: "check provider health", lambda r: "why is my computer slow", lambda r: "run diagnostics on my setup"],
        "agents_manage": [lambda r: "spawn an agent to research this", lambda r: "what agents are running", lambda r: "check the agent status", lambda r: "list my agents"],
        "selfmod_code": [lambda r: "modify your own tool to do this", lambda r: "change your tool that handles files", lambda r: "update your calendar tool"],
        "api_keys": [lambda r: "save my api key", lambda r: "what keys do i have configured", lambda r: "list configured api keys", lambda r: "store the openai key"],
        "oauth_flow": [lambda r: "connect my google account", lambda r: "authorize google drive", lambda r: "log into github", lambda r: "set up gmail access", lambda r: "authenticate google sheets"],
        "project_scan": [lambda r: "scan the project structure", lambda r: "show me the layout of this repo", lambda r: "map out the codebase", lambda r: "what files are in the project"],
        "geo_code": [lambda r: "geocode this address", lambda r: "what's the coordinates of chicago", lambda r: "find the latitude of paris", lambda r: "reverse geocode this location"],
        "directions": [lambda r: "get directions to the airport", lambda r: "how do i get to downtown", lambda r: "directions to the nearest store"],
        "image_analyze": [lambda r: "analyze this image", lambda r: "what's in this picture", lambda r: "describe this photo", lambda r: "read the text in this image", lambda r: "extract the text from this screenshot"],
        "video_analyze": [lambda r: "analyze this video", lambda r: "what happens in this video", lambda r: "summarize this video content", lambda r: "describe the video"],
        "screenshot_take": [lambda r: "take a screenshot", lambda r: "capture the screen", lambda r: "screenshot my current window", lambda r: "grab a screenshot of the display"],
    },
    "coding": {
        "write_code": [lambda r: "write a python function to calculate fibonacci", lambda r: "write code that parses json", lambda r: "generate a script to rename files", lambda r: "code a web scraper", lambda r: "implement a sorting algorithm"],
        "debug_code": [lambda r: "fix this bug", lambda r: "debug this error", lambda r: "why is my code throwing an exception", lambda r: "fix the bug in my script", lambda r: "help me debug this traceback"],
        "improve_code": [lambda r: "refactor this code", lambda r: "optimize my script", lambda r: "make this code faster", lambda r: "clean up this function", lambda r: "improve the performance of this code"],
        "explain_code": [lambda r: "explain this code to me", lambda r: "what does this function do", lambda r: "walk me through this script", lambda r: "break down this code for me"],
        "run_tests": [lambda r: "run the tests", lambda r: "execute the test suite", lambda r: "check if tests pass", lambda r: "run pytest on my project"],
        "design_api": [lambda r: "design an api for this", lambda r: "what should the endpoints look like", lambda r: "design the api schema", lambda r: "plan the rest api structure"],
        "generate_docs": [lambda r: "write documentation for this module", lambda r: "generate docstrings", lambda r: "create a readme for the project", lambda r: "document this api"],
        "review_code": [lambda r: "review my code", lambda r: "do a code review", lambda r: "check my pull request", lambda r: "look over this diff"],
        "implement_feature": [lambda r: "add a feature to my app", lambda r: "implement the login flow", lambda r: "build a settings page", lambda r: "implement dark mode"],
        "write_script": [lambda r: "write a bash script to backup", lambda r: "create a shell script for this", lambda r: "write a script to organize files", lambda r: "make a script that monitors cpu"],
        "convert_lang": [lambda r: "convert this python to javascript", lambda r: "translate this code to typescript", lambda r: "rewrite this in go", lambda r: "port this function to rust"],
        "write_config": [lambda r: "write a config file for this", lambda r: "create a .env for the project", lambda r: "set up the config for my app", lambda r: "write a pyproject.toml"],
    },
    "chat": {
        "greet": [lambda r: "hello", lambda r: "hi", lambda r: "hey", lambda r: "good morning", lambda r: "good afternoon", lambda r: "howdy", lambda r: "what's up", lambda r: "yo"],
        "farewell": [lambda r: "goodbye", lambda r: "bye", lambda r: "see you later", lambda r: "good night", lambda r: "talk to you tomorrow", lambda r: "see ya"],
        "thanks": [lambda r: "thanks", lambda r: "thank you", lambda r: "appreciate it", lambda r: "thanks a lot", lambda r: "much obliged"],
        "joke": [lambda r: "tell me a joke", lambda r: "say something funny", lambda r: "give me a pun", lambda r: "make me laugh"],
        "small_talk": [lambda r: "how are you", lambda r: "how's it going", lambda r: "what's new", lambda r: "how was your day", lambda r: "what are you up to", lambda r: "nice weather today"],
        "remember_fact": [lambda r: "remember that i like black coffee", lambda r: "keep in mind that my birthday is in june", lambda r: "note that i prefer tea", lambda r: "don't forget i have a cat", lambda r: "remember i drive a tesla"],
        "recall_fact": [lambda r: "what do you know about me", lambda r: "do you remember my favorite color", lambda r: "what facts have you saved about me", lambda r: "what do you remember about me"],
        "ask_identity": [lambda r: "what's your name", lambda r: "who are you", lambda r: "what are you", lambda r: "what model are you", lambda r: "who made you"],
        "ask_capabilities": [lambda r: "what can you do", lambda r: "what are your capabilities", lambda r: "what tools do you have", lambda r: "explain your capabilities", lambda r: "what can you help me with"],
    },
    "reasoning": {
        "explain_concept": [lambda r: f"explain {r.choice(_CONCEPTS)}", lambda r: f"how does {r.choice(_CONCEPTS)} work", lambda r: f"what is {r.choice(_CONCEPTS)}", lambda r: f"explain {r.choice(_CONCEPTS)} in simple terms"],
        "compare_options": [lambda r: "compare python and javascript", lambda r: "which is better, mac or windows", lambda r: "compare these two approaches", lambda r: "what's the difference between sql and nosql"],
        "analyze_pros_cons": [lambda r: "pros and cons of electric cars", lambda r: "analyze the pros and cons of working remotely", lambda r: "what are the downsides of this plan", lambda r: "weigh the pros and cons of investing in crypto"],
        "design_strategy": [lambda r: "design a strategy to improve my productivity", lambda r: "what's the best approach to scale this app", lambda r: "plan a strategy for learning a language", lambda r: "how should i approach this project"],
        "why_question": [lambda r: "why is the sky blue", lambda r: "why does water boil at 100 degrees", lambda r: "why do we dream", lambda r: "why is the ocean salty", lambda r: "why does time feel faster as we age"],
        "how_question": [lambda r: "how do neural networks work", lambda r: "how does gravity affect time", lambda r: "how do i improve my memory", lambda r: "how does photosynthesis work"],
        "math_problem": [lambda r: "what is the square root of 144", lambda r: "solve for x: 2x + 5 = 15", lambda r: "what's 15 percent of 200", lambda r: "calculate the area of a circle with radius 5"],
        "logic_puzzle": [lambda r: "solve this logic puzzle", lambda r: "a man has 3 sons, each son has 2 children, how many grandchildren", lambda r: "if all bloops are roops and all roops are loopers, are all bloops loopers"],
        "decision_help": [lambda r: "should i switch to linux", lambda r: "help me decide between two job offers", lambda r: "is it worth buying a house now", lambda r: "what should i do about this situation"],
    },
    "self_mod": {
        "fix_own_code": [lambda r: "fix the bug in brain.py", lambda r: "debug the issue in your code", lambda r: "fix yourself, you're broken", lambda r: "there's a bug in your code, fix it", lambda r: "debug brain.py"],
        "add_feature": [lambda r: "add a new feature to yourself", lambda r: "give yourself the ability to do this", lambda r: "add a new tool to your skillset", lambda r: "improve yourself by adding this capability"],
        "update_config": [lambda r: "update your config file", lambda r: "change your settings", lambda r: "modify config.py", lambda r: "update the configuration for jarvis"],
        "improve_perf": [lambda r: "make yourself faster", lambda r: "optimize your code", lambda r: "improve your performance", lambda r: "make your responses quicker"],
        "read_own_code": [lambda r: "show me your code", lambda r: "what's your source code", lambda r: "list your modules", lambda r: "read me your source", lambda r: "show me brain.py"],
        "modify_tool": [lambda r: "modify your weather tool", lambda r: "change your spotify tool", lambda r: "update the browser tool", lambda r: "modify your own tool"],
    },
    "automation": {
        "schedule_task": [lambda r: "schedule this task for tomorrow", lambda r: "set up a scheduled task", lambda r: "automate this to run daily", lambda r: "schedule a reminder to run this weekly"],
        "create_workflow": [lambda r: "create a workflow that backs up my files", lambda r: "set up an automation to organize my downloads", lambda r: "build a workflow that checks my calendar each morning", lambda r: "create a routine for my morning briefing"],
        "monitor_resource": [lambda r: "monitor my system usage in the background", lambda r: "set up monitoring for disk space", lambda r: "watch my cpu usage and alert me", lambda r: "monitor the internet connection"],
        "organize_files": [lambda r: "automate organizing my downloads folder", lambda r: "set up a script that cleans my desktop", lambda r: "automatically sort my screenshots", lambda r: "organize my documents by type automatically"],
        "backup_data": [lambda r: "set up a daily backup automation", lambda r: "automate backing up my documents", lambda r: "create a workflow to backup my photos", lambda r: "schedule weekly backups"],
        "automate_reminders": [lambda r: "automate my reminders", lambda r: "set up automatic reminders for my meetings", lambda r: "create recurring reminders", lambda r: "automate reminding me to stand up"],
        "setup_cron": [lambda r: "set up a cron job", lambda r: "schedule this script on a cron", lambda r: "create a recurring job every monday", lambda r: "set up a scheduled script"],
    },
}

# Merge static + generated into _TEMPLATES with slot fills
_EXTRA_FILLS = {
    "tool_use": lambda r, cls: None,
}


def build_templates(bucket: str, rng: random.Random) -> dict[str, list[str]]:
    """Return {fine_class: [phrasings]} — base templates × prefixes, ≥ ~40 each."""
    out = {}
    for cls, fns in _S[bucket].items():
        phrasings = set()
        for fn in fns:
            base = fn(rng)
            for prefix in _PREFIXES:
                phrasings.add((prefix + base).strip())
                phrasings.add((prefix + base).strip().capitalize())
        # pronoun swap variety
        extras = set(phrasings)
        for p in list(phrasings):
            extras.add(p.replace("my ", "the "))
            extras.add(p.replace("my ", "our "))
            extras.add(p.replace(" i ", " we "))
        out[cls] = sorted(extras)
    return out


def build_dataset(
    bucket: str,
    synth_per_class: int = 50,
    seed: int = 0,
    include_real: bool = True,
) -> tuple[list[str], list[str]]:
    """Return (texts, fine_intents) for one bucket.

    Real examples first (deduped), then synthetic samples capped at
    synth_per_class per fine class.
    """
    rng = random.Random(seed)
    classes = fine_classes(bucket)
    texts: list[str] = []
    intents: list[str] = []
    seen = set()

    if include_real:
        for text, fine in load_real_fine_examples(bucket):
            if text in seen:
                continue
            seen.add(text)
            texts.append(text)
            intents.append(fine)

    templates = build_templates(bucket, rng)
    for cls in classes:
        pool = templates.get(cls, [])
        rng.shuffle(pool)
        for t in pool[:synth_per_class]:
            if t in seen:
                continue
            seen.add(t)
            texts.append(t)
            intents.append(cls)
    return texts, intents
