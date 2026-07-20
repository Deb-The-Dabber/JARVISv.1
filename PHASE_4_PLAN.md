# Phase 4 Plan: Gap-by-Gap Fixes

## Overview
Phase 3 delivered 6 sub-phases (Observability, Plugins, Workflows, RAG, Triggers, Sandbox) — 197 tests pass. Phase 4 addresses 9 architectural gaps.

---

## 4.a — Self-Improvement / Continuous Learning Loop
**Files:** `brain.py`, `proactive.py`, `learner.py`, `procedural_memory.py`, `plugin_manager.py`, `terminal.py`, `server.py`, new `learner_loop.py`
**Plan:**
1. Add `LearningHook` in `brain.py` post-turn → extract (intent, tool_sequence, outcome) → `procedural_memory.save_pattern()`
2. New `learner_loop.py`: background job mines patterns → generates candidate workflows/triggers/plugins
3. Human-in-the-loop: `learner review` CLI + `GET /learner/candidates`, `POST /learner/approve`
4. On approve: auto-generate plugin YAML → `plugin_manager.install_from_path()`
5. API: `GET /learner/stats`, `POST /learner/feedback`

---

## 4.b — Autonomous Agent Framework
**Files:** `agent.py`, `brain.py`, `safety.py`, `terminal.py`, `server.py`
**Plan:**
1. Extend `Agent` class: `goal`, `plan[]`, `memory`, `tools`, `max_iterations`
2. ReAct loop: `think → act → observe → reflect` with JSON tool calls
3. `agent_spawn` tool (SAFE) — launch sub-agents with scoped permissions
4. Checkpoint every N steps to `procedural_memory`
5. CLI: `agent run "goal"`, `agent list`, `agent stop <id>`; API: `/agent/spawn`, `/agent/<id>/status`, `/agent/<id>/stop`

---

## 4.c — Evaluation & Regression Harness
**Files:** New `eval_runner.py`, `scripts/run_eval.py`, `tests/eval/golden_set.jsonl`, `jarvis_doctor.py`, `server.py`
**Plan:**
1. `tests/eval/golden_set.jsonl`: prompt, expected_tools, expected_keywords, max_cost, max_latency
2. `eval_runner.py`: runs cases → scores (tool accuracy, keyword recall, cost, latency)
3. `scripts/run_eval.py`: exits non-zero on regression
4. Store runs in `eval_runs/`; `jarvis_doctor.py` check: "eval last run < 24h"
5. API: `GET /eval/latest`, `GET /eval/history`

---

## 4.d — Knowledge Graph Auto-Extraction + Graph RAG
**Files:** `graph_memory.py`, `brain.py`, `rag_memory.py`, `memory.py`, `terminal.py`, `server.py`
**Plan:**
1. `extract_entities_relations(text)` in `graph_memory.py` (LLM or spaCy)
2. Hook in `brain.py` post-turn → upsert entities/relations
3. Hook in `rag_memory.py` ingestion → extract from docs
4. `hybrid_search(query)` in `memory.py`: vector top-K + graph 1-hop neighbors → rerank
5. CLI: `graph extract`, `graph neighbors`, `graph search`; API: `/graph/extract`, `/graph/neighbors`, `/graph/search`

---

## 4.e — Voice Quality & Reliability
**Files:** `config.py`, `stt.py`, `wakeword.py`, `tts.py`, `proactive.py`, `jarvis_doctor.py`, `scripts/train_wakeword.py`
**Plan:**
1. `VADConfig` in `config.py`: aggressiveness, min_silence_ms, speech_pad_ms
2. Expose in `stt.py` → tune Silero VAD
3. `scripts/train_wakeword.py` for custom Porcupine/OWW models
4. TTS fallback chain with quota-aware retry + exponential backoff + proactive alert
5. Doctor checks: mic SNR, wake word detection rate, TTS latency

---

## 4.f — Multi-Modal Input (Images, Docs, Video)
**Files:** `vision_tools.py`, `server.py`, `terminal.py`, `rag_memory.py`, `config.py`
**Plan:**
1. `analyze_image(path/url)`, `ocr_document(path)`, `analyze_video(path, timestamps)`
2. NVIDIA NIM / Gemini 2.5 Flash for image/video; Tesseract/EasyOCR for docs
3. API: `POST /vision/analyze` (multipart), `POST /vision/ocr`, `POST /vision/video`
4. CLI: `vision analyze`, `vision ocr`, `vision video`
5. RAG: auto-OCR PDFs/images during `index_folder`

---

## 4.g — Security Hardening
**Files:** `safety.py`, `jarvis_logger.py`, `proactive.py`, `jarvis_doctor.py`, `tools/__init__.py`, new `scripts/scan_deps.py`
**Plan:**
1. Capability tokens: `ToolPermission(capabilities=["fs:read:~/docs", "net:api:github.com"])`
2. Per-tool capability declarations in `TOOL_DEFINITIONS` → enforce at call time
3. Audit alerting: on `DENIED/BLOCKED` → proactive alert + webhook
4. Supply chain scan: `pip-audit` + `safety` in `jarvis_doctor.py`
5. Secrets scan: `git-secrets` / `truffleHog` in doctor

---

## 4.h — Performance: Latency-Aware Routing + Caching
**Files:** `brain.py`, `jarvis_logger.py`, `cache.py`, `server.py`, `config.py`
**Plan:**
1. Track per-provider latency (p50/p99) + error rate in logger metrics
2. Router: prefer fastest healthy provider for simple queries; reserve Nemotron for tool-heavy
3. Speculative execution: fire fast provider in parallel for known-simple intents
4. Semantic response cache: embedding of prompt → TTL by intent type
5. API: `GET /perf/providers`, `GET /perf/cache`

---

## 4.i — Mobile Push & Offline Queue
**Files:** New `push_notify.py`, `server.py`, `proactive.py`, `static/sw.js`, `static/index.html`
**Plan:**
1. `push_notify.py`: APNs (iOS) + FCM (Android) via Expo/OneSignal or direct
2. `POST /mobile/register` (token, platform)
3. Proactive alerts → push via `proactive.py` integration
4. Offline queue: `outbox` table in SQLite → background sync
5. Web UI: service worker for offline caching + background sync API

---

## Dependency Order
```
4.c (Eval) → validates all
4.a (Learning) → enables 4.b (Agents)
4.d (Graph) → feeds 4.a, 4.b, 4.f
4.g (Security) → hardens 4.a, 4.b, 4.h
4.h (Perf) → measures all
4.e (Voice) → independent
4.f (Multi-modal) → feeds 4.d
4.i (Mobile) → consumes 4.e, 4.g
```
**Suggested sprint order:** 4.c → 4.a → 4.d → 4.b → 4.g → 4.h → 4.e → 4.f → 4.i
