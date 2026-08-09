# JARVIS — AI Personal Assistant (macOS)

## Quick Start

```bash
# Terminal mode (default)
cd /Users/debasishbeura/Jarvis
source venv/bin/activate
./run_jarvis.sh              # or: python terminal.py
JARVIS_DEBUG=1 ./run_jarvis.sh  # enable [DEBUG] brain logs (also appends to ~/.jarvis/logs/debug.log)

# Server/API mode (mobile UI via Tailscale)
python server.py             # listens on :8000
```

Terminal modes: `m` (manual — press Enter to record or type), `w` (wake word — "Hey Jarvis"), `q` (quit).

## Dev Commands

```bash
# Lint (ruff)
ruff check .                  # catch errors
ruff check . --fix            # auto-fix
ruff format .                 # format whole project

# Test (pytest)
pytest                        # run all tests/
pytest -v                     # verbose
pytest tests/test_foo.py      # single file

# Regression gate (pre-merge)
pytest tests/regression/ -m "regression and not local"  # CI-safe (no display)
pytest tests/regression/                                 # full (needs display on macOS)

# Eval harness
python eval_runner.py tests/eval/golden_set.jsonl

# Fallback tests
pytest tests/test_provider_fallback.py -v
```

Testing stack: `pytest` + `ruff`. Config in `pyproject.toml` at root.

## Critical `.env` Keys

**Never set `GOOGLE_API_KEY`** — the GenAI SDK auto-detects it and overrides `GOOGLE_GENAI_API_KEY`.

- `GOOGLE_GENAI_API_KEY` — Gemini (primary, tool calling)
- `NVIDIA_API_KEY` — vision/screen analysis
- `NVIDIA_NEMOTRON_API_KEY` — Nemotron & NIM models
- `DEEPSEEK_API_KEY` — DeepSeek v4 (via NVIDIA NIM, NVIDIA key format)
- `GROQ_API_KEY`, `OPENROUTER_API_KEY` — fallback providers
- `ELEVENLABS_API_KEY` — TTS (free tier → Edge-TTS → macOS `say`; quota warning prints once/session)
- `EDGE_TTS_VOICE` — Microsoft Edge TTS voice (default: `en-US-JennyNeural`)
- `TAVILY_API_KEY` — web search
- `HUGGINGFACE_TOKEN` — embeddings/downloads

Constants in `config.py` (user info, paths, TTLs, models).

## Entrypoints

| File | Role |
|------|------|
| `terminal.py` | CLI: voice/text → brain → TTS, wake word loop, proactive engine |
| `server.py` | FastAPI :8000: `/ask`, `/ask-voice`, `/health`, `/system`, `/weather`, `/recap`, `/memories`, `/priorities`, `/audit`, `/brain/reset`, `/oauth/*`, `/learner/*`, `/inspect` |
| `brain.py` | Provider chain, tool calling, safety gating, tool definitions, intent router, circuit breaker, `_tool_call_names` tracking, `get_last_tool_calls()` |
| `jarvis_local_nn/` | From-scratch NumPy tiny tensor library + **two-stage intent router**. Stage 1: coarse 6-way router (MiniLM 384-dim → MLP 384→128→6), weights in `weights/intent_router.npz`. Stage 2: one specialist MLP per bucket (same arch → N fine classes, 89 total) in `weights/specialists/<bucket>.npz`, taxonomy in `taxonomy.yaml` (fine classes, tool→intent map, `execution_primitives` excluded from the classifier). Retrain coarse: `python -m jarvis_local_nn.training.train`; specialists: `python -m jarvis_local_nn.training.train_specialist --all`. Eval: `python -m jarvis_local_nn.training.evaluate` (golden set, scores coarse + fine via `expected_fine`). Calibrate: `python -m jarvis_local_nn.training.calibrate` (coarse per-intent gates) and `python -m jarvis_local_nn.training.calibrate_fine --all` (writes `weights/specialists/thresholds.json` per-class gates). Auto-retrain: `jarvis_local_nn/training/auto_retrain.py` — debounced (default 600s) background retrain triggered from `brain._on_tool_learned` when the learner adds a new tool (`JARVIS_AUTO_RETRAIN_ENABLED=0` off, `JARVIS_AUTO_RETRAIN_INTERVAL` window). Toggles: `JARVIS_LOCAL_INTENT_ENABLED=0` (router; independent of the MLX local-chat `JARVIS_LOCAL_ENABLED`); coarse gates: global `JARVIS_LOCAL_INTENT_CONFIDENCE=0.85` + per-intent `JARVIS_LOCAL_INTENT_CONFIDENCE_{CHAT,CODING,TOOL_USE,REASONING,SELF_MOD,AUTOMATION}`; fine gates: `weights/specialists/thresholds.json` + per-class `JARVIS_FINE_CONFIDENCE_<CLASS>` overrides (bucket defaults 0.85/0.90). Embeddings cached in `~/.jarvis/nn_cache/embeddings.npz` (keyed by text hash; incremental retrains embed only new entries). First call per process loads MiniLM (~8s), then 10-70ms/call; reuses vector_memory's embedder. Also acts as last-resort offline provider in `ask_with_tools` (`local_nn` canned reply + locally prefetched tool results). Runtime: `brain.classify_intent` fast-path → coarse bucket → `predict_fine_gated` (per-class gate; below gate the fine label is withheld and routing falls to the LLM) → exposed via `brain.get_last_fine_intent()`, consumed by `_FINE_PREFETCH` (weather_current/sys_info/disk_usage → safe no-arg tool prefetch) |
| `tools/` | 13+ modules: system, browser, spotify, discord, calendar, file, code, computer, vision, communication, **google_docs**, **google_slides**, **google_forms**, **inspect_tools** |
| `learner.py` | LLM code-gen learning: `trigger_learning()`, CRUD for learned tools, web API endpoints |
| `memory.py` | Vector (ChromaDB) + RAG + graph + associative memory |
| `proactive.py` | Background monitors → priority engine → spoken alerts |
| `safety.py` | Tool confirmation/blocking: `SAFE` (auto), `WARNING` (confirm), `DANGEROUS` (confirm), `BLOCKED` (deny) |
| `vector_memory.py` | ChromaDB with embedding model migration (export/re-embed on dimension change) |
| `file_sandbox.py` | File-write sandbox: stages create/write/append as diffs, approval before apply |
| `action_sandbox.py` | Universal action sandbox: previews (sandboxed run / intent), self-mod review, typed confirm |
| `eval_runner.py` | Eval harness: runs golden set through brain, measures intent/tool/keyword accuracy |
| `tests/mock_provider.py` | Deterministic mock LLM provider server (8 providers, rate limits, health scoring, fail injection) |
| `tests/conftest.py` | Pytest fixtures: `has_display`, `api`, `jarvis_server`, `mock_provider`, `mock_api`; `_free_port()`, `_stop_proc()` helpers |
| `tests/regression/test_regressions.py` | P0 regression tests: `TestFunctionCallingRegressions` (3) + `TestP0Regressions` (5) |
| `tests/test_provider_fallback.py` | Provider fallback chain tests (11 tests) |
| `.github/workflows/ci.yml` | CI/CD: lint (ruff), unit (pytest + Xvfb + mock provider), regression (real providers, secrets-gated) |
| `ci-requirements.txt` | Portable pip-only deps for CI (249 packages, no conda artifacts) |

## Capabilities

| Category | What Jarvis can do |
|----------|-------------------|
| **Chat** | Voice or text conversation, remembers context, semantic memory |
| **Weather** | Current conditions, detailed forecast (temp, humidity, wind, rain) |
| **Web** | Search, browse pages, open URLs in Safari/Chrome |
| **Apps** | Open, focus, quit any macOS app; list running apps |
| **Spotify** | Play/pause/skip, search and play songs |
| **Discord** | Open channels, send messages |
| **Calendar** | Read today's events, add new events |
| **System** | CPU/RAM/disk usage, disk space, open apps |
| **Files** | Find files, show largest, organize downloads, open in Finder |
| **Screen** | Read & summarize screen contents (vision) |
| **Computer** | Mouse move/click, type text, press keys, screenshot, click elements by description (vision) |
| **Terminal** | Run shell commands (dangerous ones require confirmation) |
| **iMessage** | Send messages (requires confirmation) |
| **Knowledge** | Query/add relationships in knowledge graph |
| **Notes** | Search personal notes via RAG |
| **Timers** | Set/cancel countdown timers with spoken alerts |
| **Memory** | Remember facts, forget them, semantic search |
| **Proactive** | Background monitoring for CPU, internet, calendar events |
| **Google Docs** | Create, read, update documents (OAuth) |
| **Google Slides** | Create, read, update presentations (OAuth) |
| **Google Forms** | Create, read, update forms/responses (OAuth) |
| **Inspect** | Query own tool inventory and capabilities |
| **Learner** | LLM-generated tool creation with CRUD API and web UI |

## Provider Chain (auto-failover)

```
User → Intent Router → Nemotron Ultra (primary) / DeepSeek (coding) → Fallbacks
```

| Tier | Provider | Role |
|------|----------|------|
| 1 | **Nemotron 3 Ultra** | Primary — tool-first + final response (tool calling + reasoning) |
| 2 | **DeepSeek v4** | Coding only — routed by intent classifier when code/script/bug keywords detected |
| 3 | **Gemini 2.5 Flash** | Fallback — excellent tool calling, used when Nemotron unavailable |
| 4 | **Groq llama-3.3-70b** | Fallback — full tools support via modern `tool_choice` format |
| 5 | **NVIDIA NIM Tier 5** | Llama 4 Maverick → MiniMax M2.7 (split blast radius) |
| 6 | **NVIDIA NIM Tier 6** | Qwen 3.5 (397B MoE) → Mistral Large 3 (split blast radius) |
| 7 | **DeepSeek v4** | Fallback — via NVIDIA NIM |
| 8 | **OpenRouter deepseek-r1** | Last-resort fallback |
| 9 | **Pollinations.ai** | No-key emergency fallback |

## Gotchas

| Issue | Why | Mitigation |
|-------|-----|------------|
| `Error querying device -1` | No default mic | `terminal.py` auto-picks first working input |
| ElevenLabs quota | Free tier exhausted | Prints once/session, falls back to Edge-TTS → `say` |
| ChromaDB dimension error | Embedding model changed | Auto-migrates: export → recreate → re-embed |
| Wake word unresponsive | Mic permission lost | Check System Settings → Privacy → Microphone |
| Any 503 on Gemini | `GOOGLE_API_KEY` set to non-Google key | Delete it from `.env` — keep only `GOOGLE_GENAI_API_KEY` |
| Stale :8000 process | Previous server didn't shut down cleanly | `_free_port()` in conftest.py kills it automatically |
| Mock provider refused | Port 18889 in use | `_free_port()` kills stale mock server processes |

## macOS Permissions

- **Accessibility**: System Settings → Privacy & Security → Accessibility → Terminal (or app running Python)
- **Microphone**: Privacy → Microphone
- **Calendar, Contacts, Spotify, Messages**: needed for respective tool modules

## Safety & Audit

- `safety.py` gates tools: `quit_app`, `send_imessage`, `run_terminal_command` require confirm
- `/audit` endpoint logs: `ALLOWED` / `EXECUTED` / `DENIED` / `BLOCKED` decisions
- Confirmation state persists per session
- File/computer tools (`create_file`, `write_file`, `move_and_click`, etc.) upgraded from `WARNING` to `SAFE`
- **File sandbox** (`file_sandbox.py`): all writes via `create_file` / `write_file` / `append_file` are staged as diffs and printed to the terminal; the write only happens after the user says yes (or `POST /confirm`). No discards it. View pending diff via `GET /files/pending`. Disable with `JARVIS_FILE_SANDBOX=0`; `JARVIS_EVAL_MODE` bypasses it
- **Action sandbox** (`action_sandbox.py`, default on): every dangerous action runs in a sandbox FIRST, the outcome is shown, then the user decides whether to proceed for real
  - Terminal/Python (`run_terminal_command`, `run_python`, `run_python_sandboxed`, `run_command_sandboxed`) → real OS-sandboxed run, output shown (`[Jarvis Sandbox] Preview`). `run_python` / `run_terminal_command` execute **outside** the sandbox after approval; the `*_sandboxed` variants stay sandboxed. Blocked patterns (`rm -rf /` etc.) are rejected before any preview runs
  - Browser/computer/mail/drive/docs/goals tools → intent preview ("what WOULD happen") before running
  - First approval per session → later calls preview + auto-proceed after 3s unless cancelled (`auto_proceed`); non-tty (API) auto-proceeds immediately
  - **Self-modification review** (`modify_own_tool` or writes to protected files — brain.py, safety.py, server.py, tools/ etc.): static analysis (syntax, size delta ≤ 50%, critical symbols like `def process(` must survive), always-on isolated dry run, then **typed confirmation** (`confirm self-modify <file>` in terminal, or `POST /confirm` with that text) — never auto-proceeds. Backup to `/tmp/jarvis_sandbox_backups` (24h), auto-rollback on post-apply failure, tool registry reloaded in place. `JARVIS_PROTECTED_FILES` adds extra protected paths (comma-separated)
  - View pending: `GET /actions/pending` (`self_mod` / `file_write` / `confirm` types). Disable with `JARVIS_ACTION_SANDBOX=0`; `JARVIS_EVAL_MODE=1` bypasses (set in `tests/conftest.py` for regression fixtures)
- `/brain/reset` clears pending safe state, conversation history, and context

## Quick Test

Quickest way to sanity-check Jarvis. Run terminal, choose `m`, type these:

| Prompt | Expected behavior |
|--------|------------------|
| `weather` | Spoken + printed temp, humidity, conditions |
| `open safari` | Safari launches |
| `search web for python 3.13` | Returns web results |
| `what's my system usage` | CPU, RAM, disk |
| `remember I like black coffee` | Saves to memory |
| `what do you know about me` | Recalls saved facts |
| `set a timer called tea for 10 seconds` | Speaks "Timer done!" after 10s |

Full regression checklist at `TEST_PLAN.md`.

```bash
source venv/bin/activate && python terminal.py
# Choose 'm' and try any prompt above
```

API smoke test:
```bash
curl http://localhost:8000/health && echo ""
curl http://localhost:8000/system && echo ""
```

