# JARVIS Session Review — June 25, 2026

## 1. Session Summary

### Batch 1: Permission & Parser Regressions
| # | Problem | Root Cause | Fix |
|---|---------|------------|-----|
| 1 | `extract_entities_relations` called by Groq fallback on simple weather queries, causing permission prompt spam | Tool definition exposed via `GRAPH_DEFINITIONS` → `TOOL_DEFINITIONS` → all models | Removed from `GRAPH_DEFINITIONS`, added to `TOOL_PERMISSIONS` as SAFE |
| 2 | Nemotron outputs JSON tool calls as markdown code fences (`` ```json{"name":"open_app",...}``` ``) — not parsed, displayed raw to user | XML parser didn't handle markdown fences | Added `parse_markdown_json_tool_calls()` + `strip_markdown_json_tool_calls()` |

### Batch 2: Test Bugs + Self-Learning Parser Infrastructure
| # | Problem | Root Cause | Fix |
|---|---------|------------|-----|
| 3 | Test assertions failed: `/memories` returns `{"memories": list}` not bare list; `/audit` missing `NEEDS_CONFIRMATION` | Outdated test expectations after refactoring | Fixed assertions in `test_api.py`, `test_smoke.py` |
| 4 | Nemotron outputs raw `{"tool_calls": [...]}` JSON without markdown fences — not parsed | New Nemotron output variant | Added `parse_json_tool_calls()` / `strip_json_tool_calls()` for bare JSON |
| 5 | Nemotron outputs `<tool_call>function(name)</tool_call>` XML tag format — not parsed | New Nemotron output variant | Added `parse_tool_call_tags()` / `strip_tool_call_tags()` for `<tool_call>` format |
| 6 | Unknown future Nemotron formats silently dropped — no observability, no recovery path | No catch-all parser | Added `FormatDetector` class with auto-logging to `format_log.jsonl`, hot-reload of dynamic parsers from `./parsers/`, retrain CLI `python -m tool_parser` |

### Batch 3: Safety TTL + Edge-TTS + Test Scripts
| # | Problem | Root Cause | Fix |
|---|---------|------------|-----|
| 7 | Session confirmations (`_session_confirmed`) never expire — stale WARNING approvals persist forever | No TTL on session memory | Added `SAFETY_PENDING_TTL` (config.py, default 300s), expiry timestamps to `_session_confirmed` + `_pending_safe` + `pending_action`, background cleaner thread |
| 8 | Edge-TTS voice hardcoded as `"en-US-JennyNeural"` — no env config | No env var read in tts.py | Imported `EDGE_TTS_VOICE` + `EDGE_TTS_VOICES` from config.py, added voice validation fallback |
| 9 | Vision/Computer tools have no automated integration tests | Missing test scripts | Created `tests/scripts/test_vision.py` + `tests/scripts/test_computer.py` (NVIDIA API, `exit(1)` on failure) |

### Batch 4: macOS `ps` + `<tool_call>` JSON Format (New Issues)
| # | Problem | Root Cause | Status |
|---|---------|------------|--------|
| 10 | Nemotron generates `ps aux --sort=-%mem` (Linux-style) which fails on macOS `ps` | Model educated on Linux syntax; macOS `ps` has different flags | **Open** — model needs macOS-compatible command or an app-level tool |
| 11 | Nemotron outputs `<tool_call>\n{"name": "get_open_apps", "arguments": {}}` — `<tool_call>` tag with bare JSON inside, not `function(...)` format | Model generating hybrid format: tag wrapper + JSON body | **Open** — `parse_tool_call_tags` expects `function(name, args)` inside tag; `parse_json_tool_calls` expects entire text to be JSON |

---

## 2. Files Modified

### Batch 1-2 (Permission + Parser + Self-Learning)

| File | Change | Lines |
|------|--------|-------|
| `graph_memory.py` | Removed `extract_entities_relations` from `GRAPH_DEFINITIONS` (kept in `GRAPH_TOOLS`) | 234–252 |
| `safety.py` | Added `"extract_entities_relations": SAFE` to `TOOL_PERMISSIONS` | 101 |
| `tool_parser.py` → `tool_parser/` | Refactored into package: `tool_parser/__init__.py`, `tool_parser/tool_parser.py`, `tool_parser/__main__.py` | Moved + expanded |
| `tool_parser/tool_parser.py` | Added `parse_json_tool_calls`, `parse_tool_call_tags`, `FormatDetector` class (with hot-reload, logging, retrain CLI) | 1–352 |
| `tool_parser/__init__.py` | Re-exports all public symbols from `tool_parser.tool_parser` | 1–18 |
| `tool_parser/__main__.py` | Retrain CLI: reads `format_log.jsonl`, clusters, generates dynamic parsers | 1–109 |
| `brain.py` | Replaced cascading `parse_*` calls with single `detect_and_parse()` in all 4 provider loops; added `FormatDetector` integration; updated error recovery path; added `import time` | ~15 locations |
| `tests/helpers.py` | `assert_no_raw_json` updated to catch `{"tool_calls": [...]}` and `<tool_call>` patterns | 23–34 |
| `tests/unit/test_tool_parser.py` | 15 new tests: 9 bare JSON + 6 tool_call tag | +45% |
| `parsers/` | New directory for auto-generated dynamic parser modules | 1 file |

### Batch 3 (Safety TTL + Edge-TTS + Test Scripts)

| File | Change | Lines |
|------|--------|-------|
| `config.py` | Added `SAFETY_PENDING_TTL` (env, default 300), `EDGE_TTS_VOICE` + `EDGE_TTS_VOICES`, `PARSERS_DIR`, `FORMAT_LOG_PATH` | ~15 |
| `safety.py` | `_session_confirmed` changed from `set` to `dict{tool: expiry}`; added `_clean_expired_confirmations()` background cleaner | ~20 |
| `brain.py` | Added `expires_at` to `pending_action` + `_pending_safe`; added `has_pending_action()`; updated `set_pending_safe`/`has_pending_safe` with TTL check; imported `SAFETY_PENDING_TTL` | ~15 |
| `tts.py` | Imported `EDGE_TTS_VOICE` + `EDGE_TTS_VOICES` from config.py; added voice validation with fallback | ~5 |
| `tests/scripts/test_vision.py` | Integration test for `read_screen`, `find_on_screen`, `summarize_screen` (NVIDIA API required) | Created |
| `tests/scripts/test_computer.py` | Integration test for `take_screenshot` (safe non-destructive test) | Created |

---

## 3. Test Results

### Batch 1 — Live API Tests (via FastAPI on localhost:8000)

| Test | Prompt | Result | Status |
|------|--------|--------|--------|
| Weather | `"weather in Chicago"` | "71°F, clear, 75% humidity" | ✅ |
| Open app | `"open weather app"` | "Done." (called `open_app`, no permission prompt) | ✅ |
| Run Python | `"run python code that prints hello world"` | `print("hello world")` executed | ✅ |
| Scan project | `"scan my project structure"` | "83 files across main dir, tools/, tests/..." | ✅ |
| Create file | `"create a file called test.html on my desktop with hello world in it"` | Model said "Done." but never called tool | ⚠️ Model quality |

### Batch 2 — Pytest Unit Tests (Post-Fix)

| Test Suite | Count | Result |
|------------|-------|--------|
| `tests/unit/` — all unit tests | 38 | ✅ All pass |
| `tests/regression/` — quick tests (25) + system_tools (6) | 31 | ✅ All pass |

### Batch 3 — Debug Live Session (JARVIS_DEBUG=1)

| Turn | Prompt | Result | Status |
|------|--------|--------|--------|
| 1 | `hello jarvis` | "Hello! How can I help you today?" | ✅ |
| 2 | `whats the weather today?` | "78°F, clear skies, 52% humidity..." | ✅ `[TOOL PARSED] nemotron:` |
| 3 | `whats eating up my RAM?` | "75% RAM usage..." + searched memory | ✅ |
| 4 | `whats taking up most of my memory?` | Permission prompt for `run_terminal_command` | ✅ |
| 5 | `yes` | Executed `ps aux --sort=-%mem` — **failed** (macOS flag) | ❌ Issue #10 |
| 6 | `what does that mean?` | Explained and asked for permission | ✅ |
| 7 | `yes` | Same `ps` command again — **same failure** (no macOS fix) | ❌ Issue #10 |
| 8 | `open weather` | Called `get_weather_detailed` — **returned weather, not app** | ⚠️ Misrouted |
| 9 | `open the weather app on my computer` | Called `open_app("Weather")` — **then described action** | ⚠️ Model explained instead of doing |
| 10 | `open the weather app on my computer` (repeat) | Semantic cache HIT — same bad response | ❌ Cache amplifying error |
| 11 | `open the weather app on my computer` (repeat) | "Done — the Weather app is now open." | ✅ |
| 12 | `open an app of your choice` | Opened Terminal | ✅ |
| 13 | `open an app thats not already opened` | **Returned raw `<tool_call>` JSON — not parsed** | ❌ Issue #11 |

---

## 4. Known Issues

### 4.1 `<tool_call>` + Bare JSON Format Not Parsed (New)
- **Format logged**: `format_log.jsonl` captured:
  ```json
  {"text": "<tool_call>\n{\"name\": \"get_open_apps\", \"arguments\": {}}", "provider": "nemotron_ultra"}
  ```
- **Problem**: Nemotron wraps tool calls in `<tool_call>` tag but fills it with JSON, not `function(name)` syntax. The `parse_tool_call_tags` regex expects `function(...)` after the tag, and `parse_json_tool_calls` requires the entire text to be valid JSON.
- **Impact**: Tool call is printed raw to user instead of executed.
- **Status**: **Open**. Need a parser that strips `<tool_call>` before JSON parsing, or a combined parser.

### 4.2 macOS `ps` Compatibility (New)
- **Problem**: Nemotron model is trained on Linux `ps` flags (`--sort=-%mem`) which don't work on macOS.
- **Impact**: Memory query tool fails after user approval. Same command repeated on retry (no adaptation to macOS).
- **Status**: **Open**. Either: (a) add macOS-aware system tool, or (b) harden the terminal tool to rewrite commands for macOS, or (c) prompt the model with macOS-specific examples.

### 4.3 Semantic Cache Amplifying Bad Responses (New)
- **Problem**: Repeat identical queries hit semantic cache and replay the same bad/stale response (e.g., model describing intent instead of executing).
- **Status**: **Open**. Cache should invalidate on tool-execution context changes, or have a per-turn TTL.

### 4.4 Model Quality: Nemotron Skips Tool Calls
- **Evidence**: `create_file` tool was available but Nemotron responded "Done." without invoking it.
- **Status**: Sporadic model behavior issue.

### 4.5 Fallback Provider Markdown JSON Integration (Untested Live)
- `_ask_openai_compatible` (Groq/OpenRouter/DeepSeek) has `detect_and_parse` integration but was **not live-tested** because Nemotron handled all queries.
- **Risk**: Fallback path might have edge cases.

### 4.6 `extract_entities_relations` Still in `TOOL_PERMISSIONS`
- Unused now that it's removed from `GRAPH_DEFINITIONS`, but harmless as SAFE-level permission.

### 4.7 Rate Limiting: OpenRouter & Groq Backing Off
- Both providers hit 429 rate limits after a few requests and are backed off for 600s.
- **Status**: Expected behavior; circuit breaker works. Monitor false positives.

---

## 5. Untested Feature Inventory

(Based on code audit of `tools/__init__.py` registry)

| Module | Tools | Priority | Test Command |
|--------|-------|----------|-------------|
| **Spotify** | play, pause, next, previous, volume, current, play_song | Medium | `"play bohemian rhapsody on spotify"` |
| **Calendar** | get_events, add_event | Medium | `"what's on my calendar today"` |
| **Browser** | navigate, new_tab, close_tab, scroll, back, forward, reload, current_url, quick_search | High | `"open example.com in safari"` |
| **Discord** | open_channel, send_message, open_and_send | Low | `"open discord general channel"` |
| **iMessage** | send_imessage | Low | `"send imessage to [contact] saying test"` |
| **Vision** | read_screen, find_on_screen, summarize_screen, check_alerts, analyze_image, ocr_document, analyze_video | High | `"what's on my screen"` |
| **Computer** | move_and_click, type_text, press_key, take_screenshot, click_on_screen, run_terminal_command | High | `"take a screenshot"` |
| **Sandbox** | run_python_sandboxed, run_command_sandboxed | Low | `"run this python in sandbox: print(1+1)"` |
| **Memory** | remember, forget, semantic_search | Medium | `"remember I like black coffee"` |
| **Knowledge Graph** | query, add_to, extract | Medium | `"what do you know about Jarvis"` |
| **Files** | find_recent_screenshot, get_largest_files, organize_downloads, open_in_finder, create_file | High | `"organize my downloads"` |
| **WarWatch** | warwatch_news | Low | `"get war news about ukraine"` |
| **Timers** | set_timer, cancel_timer | Medium | `"set a timer called tea for 10 seconds"` |
| **Recap** | get_recap, get_recent_events | Low | `"what happened while I was away"` |
| **Notes (RAG)** | search_my_notes | Low | `"search my notes for"` |

Provider fallback paths to verify:
- Nemotron fails → Groq (markdown JSON parsing)
- Groq fails → DeepSeek (coding intent routing)
- All API providers fail → Pollinations.ai (emergency)

---

## 6. Architecture

### Tool Pipeline (Updated)

```
User Input → process() → Intent Router
  ├── Coding keywords?   → ask_deepseek()
  ├── Imperative command? → ask_nim_with_context()
  └── Default             → ask_with_tools() → Nemotron Ultra (primary)
                                    ↓ failover
                               Gemini 2.5 Flash
                                    ↓ failover
                                Groq → OpenRouter → Nemotron Nano → Pollinations

Each provider loop (simplified):
  response → structured function_call? → execute → continue
           → raw JSON (multi-line, single, naked) → execute → continue
           → FormatDetector.detect_and_parse():
               ├── parse_xml_tool_calls()
               ├── parse_markdown_json_tool_calls()
               ├── parse_json_tool_calls()
               ├── parse_tool_call_tags()
               └── dynamic parsers (hot-reloaded from ./parsers/)
                    if found → execute → continue
                    if not found → log to format_log.jsonl → text return

  plain text → _sanitize_assistant_text() → return
```

### FormatDetector Self-Learning Pipeline

```
Model output (unknown format)
         ↓
FormatDetector.detect_and_parse()
         ↓
  ┌─── Static parsers match? ──→ execute tool ──→ done
  │
  └─── Dynamic parsers match? ──→ execute tool ──→ done
  │
  └─── No match ──→ _log_failed_format() → format_log.jsonl
                                    ↓
                        python -m tool_parser (retrain CLI)
                                    ↓
                        1. Read format_log.jsonl
                        2. Cluster similar formats by prefix + structure
                        3. Generate parser_*.py in ./parsers/
                        4. FormatDetector reload() detects new files
                        5. Next call: new format is parsed
```

### Safety TTL Pipeline

```
mark_session_confirmed("run_terminal_command")
  → stores {tool: expiry_timestamp}       (ttl = SAFETY_PENDING_TTL, default 300s)
  → background cleaner every 60s purges expired entries

is_session_confirmed("run_terminal_command")
  → checks expiry; if expired → deletes & returns False
  → after TTL, tool requires re-confirmation even within session
```

### Safety Gating

```
_execute_tool() → check_permission() → ALLOWED / WARNING (confirm, session) / DANGEROUS (confirm, per-call) / BLOCKED (deny)
                → execute → log_audit(AUDIT_LOG)
```

### Provider Chain (9 Tiers)

| Tier | Provider | Tool Format | Notes |
|------|----------|-------------|-------|
| 1 | Nemotron 3 Ultra | `function_call` + XML + Markdown JSON + bare JSON + `<tool_call>` + FormatDetector | Primary; 4-loop tool execution |
| 2 | DeepSeek v4 | Modern `tool_calls` + FormatDetector | Coding-only via intent router |
| 3 | Gemini 2.5 Flash | Native `function_call` + FormatDetector | Fallback with 3-loop retry |
| 4 | Groq (llama-3.3-70b) | Modern `tool_calls` + FormatDetector | Via `_ask_openai_compatible` |
| 5 | NVIDIA Nemotron Nano | Same as Groq | Via `_ask_openai_compatible` |
| 7 | OpenRouter deepseek-r1 | Same as Groq | Via `_ask_openai_compatible` |
| 8 | Pollinations.ai | No tool support | Text-only emergency |
| 9 | HuggingFace | Embeddings only | Not a chat provider |

---

## 7. Immediate Next Steps

1. **Fix `<tool_call>` + bare JSON format** — Add a combined parser: strip `<tool_call>` wrapper, then parse JSON. Integrate into `FormatDetector`.
2. **Fix macOS `ps` command** — Add a system-level tool `get_top_processes(by="memory", count=10)` or rewrite commands for macOS before execution.
3. **Harden semantic cache** — Add per-turn TTL or context-based invalidation.
4. **Live-test fallback providers** — Force Nemotron to fail (unset key), verify Groq/OpenRouter handle tool calls correctly.
5. **Test Vision + Computer tools** — Most impactful untested modules.
6. **Test Browser tools** — Verify AppleScript automation end-to-end.
7. **Create automated regression script** — `tests/test_regression.py` with server API validation.
8. **Test TTS fallback chain** — ElevenLabs → Edge-TTS → macOS `say`.
9. **Run retrain CLI** — `python -m tool_parser` to generate dynamic parser from captured `format_log.jsonl`.

### Full Systematic Test Matrix (From TEST_PLAN.md)
```
[ ] Preconditions (venv, permissions)
[ ] 1.1 Terminal mode startup
[ ] 1.2 API mode startup
[ ] 2.0 Core chat + TTS
[ ] 3.0 Mic / STT (manual record + wake word)
[ ] 4.0 Memory features (remember/forget/search)
[ ] 5.1 System tools (CPU/RAM/disk/timers)
[ ] 5.2 Weather + Web search
[ ] 5.3 Spotify
[ ] 5.4 Calendar
[ ] 5.5 File tools (screenshots, organize, create)
[ ] 5.6 Browser tools
[ ] 5.7 Communication (iMessage)
[ ] 5.8 Vision tools (screen read/analyze)
[ ] 5.9 Computer tools (mouse/keyboard/terminal)
[ ] 5.10 Sandbox tools
[ ] 6.0 Safety + Audit (WARNING/DANGEROUS/BLOCKED)
[ ] 7.0 Proactive engine idle test
[ ] 8.0 API endpoint smoke test
[ ] 9.0 Function-calling regression focus
[ ] 10.0 Debug toggle (ON/OFF)
[ ] 11.0 Pass criteria
```

---

## 8. Tool Registry Architecture

All tools flow through `tools/__init__.py`:

```
Each module (e.g. system_tools.py) exports:
  SYSTEM_TOOLS   = {"get_weather": get_weather, ...}   → runtime callable
  SYSTEM_DEFINITIONS = [{"type":"function", "function": {...}}, ...] → model-facing schema

tools/__init__.py merges:
  TOOL_REGISTRY  = SYSTEM_TOOLS + SPOTIFY_TOOLS + ... + GRAPH_TOOLS
  TOOL_DEFINITIONS = SYSTEM_DEFINITIONS + SPOTIFY_DEFINITIONS + ... + GRAPH_DEFINITIONS
```

**Key insight**: A tool is only callable if it's in both:
1. `TOOL_REGISTRY` — so `_execute_tool()` can find it
2. `TOOL_DEFINITIONS` — so the model knows about it and can call it

`extract_entities_relations` was removed from `GRAPH_DEFINITIONS` (step 2) but kept in `GRAPH_TOOLS` (step 1) — so it's still callable via terminal command but not offered to models.

---

## 9. Provider Testing Cheat Sheet

### Force a specific provider path

| Goal | Method |
|------|--------|
| Test Groq fallback | Temporarily unset `NVIDIA_NEMOTRON_API_KEY` in `.env` |
| Test DeepSeek coding route | `JARVIS_USE_CODING_PROVIDER=1` or include coding keywords |
| Test Pollinations emergency | Unset all API keys except Pollinations |
| Test XML parsing | `curl` with prompt that triggers `<tool_name>` format |
| Test Markdown JSON parsing | Observe `[DEBUG] [TOOL PARSED] nemotron:` in logs |
| Test bare JSON parsing | Observe `[DEBUG] [TOOL PARSED] nemotron:` in logs (falls through FormatDetector) |
| Test self-learning retrain | Run `python -m tool_parser` after unknown format logged to `format_log.jsonl` |

### Debug log monitoring

Watch for these patterns:

```
[DEBUG] [Router] Intent: tool_use            → model is being asked to call a tool
[DEBUG] [Router] Nemotron Ultra primary       → which provider was chosen
[DEBUG] [Nemotron Ultra] Tool: open_app({...})→ structured function_call detected
[DEBUG] [TOOL PARSED] nemotron: fn(args)      → FormatDetector parsed the tool call
[DEBUG] [TOOL EXECUTED] {fn_name}             → tool ran successfully
[DEBUG] [Nemotron Ultra] Raw JSON tool:       → inline raw JSON parser matched
[DEBUG] [TOOL EXECUTED] open_app              → tool ran successfully
[DEBUG] [Nemotron Ultra] Text response        → plain text returned (no tool)
[DEBUG] [Router] Semantic cache HIT           → cached response replayed
[DEBUG] Backing off provider {name} for 600s. → rate-limited, circuit breaker active
```

---

## 10. Sanitization Pipeline

In `_sanitize_assistant_text()` (brain.py:592–621), text goes through these stages in order:

```
1. Strip <think>...</think> reasoning blocks         (DeepSeek/NIM)
2. Strip <tool_name>...</tool_name> XML markup        (XML parser)
3. Strip ```json{...}``` markdown fences              (Markdown JSON parser)
4. Strip standalone {"name":..., "arguments":...}      (raw JSON tool call)
5. Strip .tool_call function(args)                     (Nemotron dot-notation)
6. Strip NIM JSON arrays: [{"type": "tool", ...}]     (NIM format)
7. Strip <tool_call>function(name)</tool_call>         (tool_call tag format)
8. Strip <tool_call>{"name":..., "arguments":...}</tool_call> (hybrid tag+JSON — **not yet implemented**)
9. Convert Python repr blobs: [{'type':'text',...}]   (DeepSeek artifact)
```

If a step detects a tool call, the text is stripped to empty and the tool is executed in the provider loop (via `FormatDetector`) instead.

---

## 11. Eval / Regression Infrastructure

| Resource | Location | Purpose |
|----------|----------|---------|
| `TEST_PLAN.md` | Root | Manual regression checklist |
| `tests/` | Root | Pytest test directory |
| `tests/unit/` | Root | 38 unit tests (tool_parser, cache, config, safety) |
| `tests/regression/` | Root | 31 regression tests (25 quick + 6 system_tools) |
| `tests/scripts/test_vision.py` | Root | Vision integration test (NVIDIA API) |
| `tests/scripts/test_computer.py` | Root | Computer integration test (screenshot) |
| `eval_runs/` | Root | Historical evaluation run outputs |
| `AGENTS.md` | Root | Dev commands, config, quick reference |
| `REVIEW.md` | Root | This file — session history + audit |
| `PHASE_4_PLAN.md` | Root | Architectural roadmap |
| `parsers/format_log.jsonl` | Root | Auto-logged unknown tool-call formats for retraining |

### Running a regression test
```python
# tests/test_regression.py — template for API-based testing
import requests

BASE = "http://localhost:8000"

def test_weather():
    r = requests.post(f"{BASE}/ask", json={"text": "weather in chicago"})
    assert r.status_code == 200
    assert "°F" in r.json()["reply"]

def test_open_app():
    r = requests.post(f"{BASE}/ask", json={"text": "open safari"})
    assert r.status_code == 200
    assert r.json()["reply"]  # non-empty

def test_api_health():
    r = requests.get(f"{BASE}/health")
    assert r.status_code == 200
```

Run with: `pytest tests/test_regression.py -v`

### Retrain CLI
```bash
python -m tool_parser        # reads format_log.jsonl, clusters, generates parser
python -m pytest tests/unit/ -v  # verify all 38 tests pass
```

---

## 12. Environment Config Quick Reference

| Variable | Purpose | If Missing |
|----------|---------|------------|
| `NVIDIA_NEMOTRON_API_KEY` | Primary Nemotron 3 Ultra | Falls back to Gemini → Groq → ... |
| `GOOGLE_GENAI_API_KEY` | Gemini 2.5 Flash (NOT `GOOGLE_API_KEY`) | Gemini tier skipped |
| `GROQ_API_KEY` | Groq fallback | Groq tier skipped |
| `TAVILY_API_KEY` | Web search | `web_search` returns error |
| `NVIDIA_API_KEY` | Vision / screen analysis | `read_screen` returns "unavailable" |
| `ELEVENLABS_API_KEY` | TTS (primary) | Falls back to Edge-TTS → macOS `say` |
| `EDGE_TTS_VOICE` | Edge-TTS voice (default `en-US-JennyNeural`) | Falls back to default |
| `SAFETY_PENDING_TTL` | Session confirmation expiry in seconds (default `300`) | 300s |
| `JARVIS_DEBUG` | Debug logs (default `1`) | Run with `0` to suppress |

**WARNING**: Never set `GOOGLE_API_KEY` — the GenAI SDK auto-detects it and overrides `GOOGLE_GENAI_API_KEY`, breaking Gemini.

---

## 13. Key File Index

| File | Role | Lines |
|------|------|-------|
| `brain.py` | Provider chain, tool calling, intent router, FormatDetector integration | ~2179 |
| `tool_parser/tool_parser.py` | XML + Markdown JSON + bare JSON + tool_call tag parsers; FormatDetector class | 352 |
| `tool_parser/__init__.py` | Re-exports all public symbols from package | 18 |
| `tool_parser/__main__.py` | Retrain CLI: `python -m tool_parser` | 109 |
| `safety.py` | Tool permission gating + audit + session TTL | ~510 |
| `config.py` | User info, paths, TTLs, model names, EDGE_TTS_VOICES | ~200 |
| `terminal.py` | CLI entry point, scheduler, wake word | 626 |
| `server.py` | FastAPI server | 734 |
| `tts.py` | TTS chain: ElevenLabs → Edge-TTS → macOS `say` | ~236 |
| `code_tools.py` | Code/file read/write/run/scan/search tools | ~210 |
| `file_tools.py` | File management (organize, create, find) | 156 |
| `system_tools.py` | Weather, apps, timers, news, web search | 492 |
| `vision_tools.py` | Screen reading, image analysis, OCR | 344 |
| `computer_tools.py` | Mouse, keyboard, screenshots, terminal | 210 |
| `browser_tools.py` | Safari/Chrome automation (AppleScript) | 209 |
| `spotify_tools.py` | Spotify control (AppleScript) | 68 |
| `calendar_tools.py` | Apple Calendar read/add | 60 |
| `discord_tools.py` | Discord web automation | 141 |
| `communication_tools.py` | iMessage send | 26 |
| `sandbox_tools.py` | Sandboxed Python + shell | 89 |
| `graph_memory.py` | Knowledge graph (entities/relationships) | 255 |
| `memory.py` | Vector memory (ChromaDB) | ~300 |
| `proactive.py` | Background monitors → spoken alerts | 505 |
| `parsers/format_log.jsonl` | Auto-logged unknown formats for retraining | ~1 entry |
| `tests/scripts/test_vision.py` | Vision integration test | ~35 |
| `tests/scripts/test_computer.py` | Computer integration test | ~30 |
