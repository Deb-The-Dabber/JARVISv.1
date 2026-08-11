# Phase 2A Report — Remove DeepSeek Route, Policy Routing + Cheap Classifier

**Date**: 2026-08-11
**Checkpoint commit**: `eedb009` — tag `phase2a-checkpoint`
**Rollback point**: tag `phase2a-pre` (parent of `eedb009`)
**Status**: ✅ Complete. `phase2a-checkpoint` frozen; Phase 2B not started.

---

## 1. What Changed (2A.0–2A.4)

| Step | Change |
|------|--------|
| 2A.0 | Removed the dedicated DeepSeek v4 primary/coding route and the NIM DeepSeek fallback tier (`DEEPSEEK_MODEL`/`DEEPSEEK_API_KEY` constants, `ask_deepseek`, status rows, docstrings). Env key kept for `.env` compatibility; no longer read by `brain.py`. |
| 2A.1 | New `routing_policy.py`: provider profiles scored by capability fit / observed latency / cost / health; hard gates (unavailable or health < 30 → invalid); deterministic tie-breaks; classifier-output parsing that rejects provider keys. Toggle: `JARVIS_ROUTER_POLICY` (default off). |
| 2A.2 | Policy-aware primary selection — when policy is off, primary = Nemotron Ultra for all tool/LLM-first work with **no LLM round-trip** (the old selector burned a second classify call). |
| 2A.3 | Fallback chain ordered by policy score when enabled; legacy health-sort preserved when disabled. |
| 2A.4 | `JARVIS_ROUTER_CHEAP` (default off): fast Groq JSON classify before Nemotron when the message isn't tool-y, plus `routing_policy_ordered` telemetry (`~/.jarvis/logs/decisions.jsonl`). |

Provider chain after 2A (7 tiers): Nemotron 3 Ultra → Gemini 2.5 Flash → Groq llama-3.3-70b → NIM Tier 5 → NIM Tier 6 → OpenRouter deepseek-r1 → Pollinations.ai.

## 2. Benchmark Results (30-case golden set, `tests/eval/routing_golden.jsonl`)

Harness: `benchmarks/coding_routing_bench.py` (subprocess-per-case, 270s hard kill, HF offline, tool/speech silenced). AFTER run used `JARVIS_ROUTER_POLICY=1 JARVIS_ROUTER_CHEAP=1` with a static health seed and an isolated Gemini usage counter (live count was capped at 12/10 on run day).

| Metric | BEFORE | AFTER | Δ |
|--------|--------|-------|---|
| pass_rate | 0.556 | 0.633 | +0.077 |
| intent_accuracy | 0.722 | 0.633 | **−0.089** |
| provider_class_match_rate | 0.000 | 0.500 | +0.500 |
| fallback_rate | 0.000 | 0.000 | +0.000 |
| avg_intent_latency_ms | 19511 | 7458 | −12054 |
| avg_routing_latency_ms | 86513 | 9210 | −77303 |
| avg_total_latency_ms | 125916 | 35872 | −90044 |
| p95_total_latency_ms | 233561 | 96657 | −136905 |
| avg_cost_usd | 0.000744 | 0.000725 | −0.000019 |
| cost_usd_total | 0.013397 | 0.021740 | +0.008343 |
| stall kills (errors) | **12** | **0** | −12 |

Full tables/JSON: `benchmarks/results/before_2a.json`, `benchmarks/results/after_2a.json`; `python benchmarks/compare_bench.py before_2a after_2a` regenerates the table.

### Interpretation

- **Stall kills 12 → 0** is the headline architectural win. BEFORE, NIM endpoint stalls (C-level SSL reads that bypass SDK timeouts, immune to SIGALRM via EINTR-retry) blocked the main thread until the 270s kill.
- **Latency**: intent 19.5→7.5s (cheap classifier + no primary-select round-trip), routing 86.5→9.2s (no dead-provider walk), total −71%, p95 −59%.
- **Intent accuracy −0.089 is the acknowledged tradeoff** of always-on cheap classification (no confidence gate), and the central Phase 2B problem (see §4).

## 3. Known Accuracy Regression Cases

| Case | Golden intent | Cheap-classifier result | Effect |
|------|---------------|-------------------------|--------|
| 25 (URL shortener) | coding | reasoning | wrong route |
| 26 (file upload) | coding | tool_use | wrong route |
| 30 (chat sentinel) | chat | nemotron route took it | class mismatch (still passed) |
| 12, 19 | coding | local_nn hollow pass (keyword recall, not in pass gate) | cosmetic |

Suspects: Groq JSON classifier boundary behavior, 1200-char truncation, no confidence/ambiguity gate, no fallback escalation to the stronger classifier.

## 4. Phase 2B Success Criteria (pre-registered)

1. Stall kills: remain **0**
2. Total latency: **≤ 35.9s** (Phase 2A), ideally lower
3. Intent accuracy: **improve substantially** from 0.633
4. Class match: **> 0.5**
5. Pass rate: **> 0.633**
6. Existing unit / router / fallback gates remain green
7. No regression in tool selection

Leading candidate architecture (proposed, not implemented): confidence-gated cheap classifier — fast route on confident predictions, escalate to Nemotron classify on ambiguity, preserving the 7.5s intent latency for the confident majority.

## 5. Environmental Findings (not code regressions)

| Issue | Evidence |
|-------|----------|
| Nemotron stalls on this network (SSL read blocks main thread, timeouts ignored) | 12/30 BEFORE kills; reproduced standalone (bare /ask hung >200s) |
| NVIDIA NIM Tier 5/6: 410 Gone | live API responses |
| OpenRouter: 404 (dead free model) | live API responses |
| Pollinations: 402 Payment Required | live API responses |
| Groq: `TypeError: expected string or bytes-like object, got 'dict'` when called with tools | fallback log, not reproduced in isolation (2B scope) |
| Gemini daily cap (12/10) | live usage file |
| `~/.jarvis/provider_health.json` collapsed to one row (sparse in-memory dict clobbered across processes) | file forensics; bench now isolates a static seed |
| Eval-mode LLM wrote real files during bench (e.g., `find_duplicates.py`) | safety finding; artifacts deleted; `JARVIS_EVAL_MODE` behavior to review |

**Real-provider regression gate** (`tests/regression/ -m "regression and not local"`): 5 failures on run day (4× "every cloud provider is unreachable", 1× empty reply). All reproduced on pristine `phase2a-pre` code + standalone stale/eco failures → environmental, not Phase 2A. Re-run when providers recover (e.g., post-Gemini-cap-reset).

## 6. Pre-existing Test Issues Surfaced During Validation (fixed separately)

- `tests/test_safety.py::test_tool_permission_levels` — asserted `browser_navigate`/`browser_current_url` = SAFE; safety.py deliberately groups all browser tools WARNING. Test fixed, safety table untouched.
- `tests/test_session_permission.py` — standalone script mis-collected by pytest (`test_result` helper → "fixture 'name' not found"); excluded via `collect_ignore`.
- Fallback-suite order flake (`test_fallback_to_gemini_on_nemotron_failure`, `test_health_score_drops_on_failure`) — `mock_api` fixture could silently talk to a stale 8002 server; fixture now frees the port and fails loudly if its own process is gone.

## 7. Rollback

```bash
git checkout phase2a-pre        # code
# or, to revert just the implementation commit:
git revert eedb009
```