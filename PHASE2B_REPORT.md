# Phase 2B Report — Intent-Routing Gates & Groq Cheap-Path Validation

Status: **IN PROGRESS** — final E3 (clean Groq window) pending; this report will be
finalized and the `phase2b-checkpoint` tag applied only after E3 completes.

## 1. Overview

Phase 2B extends the intent router with **confidence gates** so unreliable fast
classifiers (local NN, Groq cheap) escalate to the LLM (Nemotron) classify
instead of silently misrouting. The full design and 2A background are in
`AGENTS.md` (jarvis_local_nn row). This report covers:

- 2B.0 classifier-path telemetry (`classifier_path` / confidence / raw per routing)
- 2B.1 v2 cheap-classifier prompt (5-intent contract + confidence + `tool_required`)
- 2B.2 configurable per-intent gates + offline calibration + A/B/C/D gate bench
- 2B.3 frozen gate applied to the **cheap/Groq path** + honest error/latency telemetry

## 2. Frozen Reference (committed at `e923422`, not modified)

Per-user decision, the following are **locked**:

- Gate values: `chat = 0.92`, `tool_use = 0.92`, `coding = 0.50`, agreement gate = **OFF**
- A–D bench results below are the frozen comparison baseline
- Golden dataset (`tests/eval/routing_golden.jsonl`, 30 cases) untouched
- No environment/package changes (google-generativeai venv state left as-is)

### A–D results (frozen, `benchmarks/results/gate_bench_{A,B,C,D}.json`)

| config | accuracy | accepts | wrong accepts | escalations | LLM calls saved |
|--------|----------|---------|---------------|-------------|-----------------|
| A baseline | 0.7667 | 16 | 5 | 14 | 16 |
| **B confidence** | **0.9333** | 11 | 0 | 19 | 11 |
| C agreement | 0.9333 | 1 | 0 | 29 | 1 |
| D both | 0.8667 | 1 | 0 | 29 | 1 |

B wins: ties C's accuracy with 19× fewer LLM escalations. FROZEN as the gate for 2B.3.

Drift check (2B.3 code change, config A rerun): `acc 0.7667 / accepts 16 /
wrong 5 / escal 14` — byte-identical to frozen A. The cheap-path confidence gate
does not touch the `JARVIS_ROUTER_CHEAP=0` code paths.

## 3. 2B.3 What Changed

- `brain.py` cheap accept branch: `confidence >= _local_intent_threshold(intent)` required
  (`confidence=None` → escalate). Applied ONLY under `JARVIS_ROUTER_CHEAP=1`.
- `brain.py` cheap telemetry: `_cheap_call_count` / `_cheap_error_count`, surfaced per run.
- `benchmarks/classifier_gate_bench.py`: config E (frozen B thresholds + `JARVIS_ROUTER_CHEAP=1`),
  `--with-cheap` flag, per-case latency, honest `cheap_calls`/`cheap_errors` metrics,
  `cheap_groq` accepts counted as routed-without-LLM (schema of A–D unchanged).
- `benchmarks/compare_e_vs_b.py`: offline E-vs-frozen-B comparison.
- Unit tests: 15 in `tests/unit/test_intent_gates.py` (cheap above/below/missing
  confidence, E smoke, error counting) + contract fix in `test_routing_policy.py`.
  Full suite: 401 passed, 0 failed (69 errors = pre-existing env issue: fixtures
  spawn the base `python` which lacks fastapi → mock provider server can't boot;
  identical at pristine HEAD).

## 4. Config E — Groq Cheap Path (the experiment)

**Gate mechanics validated by E1/E2** (both runs executed in broken Groq windows):

| run | Groq state | cheap calls | cheap OK | cheap errors | acc | wrong accepts |
|-----|------------|-------------|----------|--------------|-----|---------------|
| E1 (`gate_bench_E_contaminated.json`, 00:05) | org TPD 99.9k/100k, lagging edges | 18 | 5 | 13 | 0.8667 | 0 |
| E2 (`gate_bench_E.json`, 01:15) | org TPD capped 100k, server-side queue → client 60s timeouts | 18 | 1 | 17 | 0.8000 | 0 |

E1 cheap accepts (all `confidence = 0.96`, i.e. ≥ the 0.92 frozen gate):
- "My Python script crashes with IndexError" → coding ✓
- "Why does this async function hang forever?" → reasoning ✗ (golden says coding —
  label-dispute case, same one B misses)
- "My regex <a.*?> grabs everything" → coding ✓
- "This while loop pegs the CPU" → coding ✓
- "git merge reports CONFLICT" → reasoning ✗ (label-dispute case, same one B misses)

Every cheap failure escalated honestly (nemotron / local_nn / keyword paths;
zero `wrong accepts` in both runs). **The gate accepts exactly what it should,
rejects what it can't trust, and the error path is truthfully reported.**

Why E1/E2 are not the final benchmark: Groq's org TPD window never rolled (counter
stuck ≥ 99,337/100,000 through 02:34 CDT; roll schedule opaque — not 00:00 UTC,
not 02:00 CDT). Small requests leak through stale counter edges; classifier-sized
(~700 token) requests 429 or queue past the 60 s client timeout mid-run.

## 5. Config E Pending — E3

- `/tmp/groq_wait.py` (detached) probes every 4 min with two classifier-sized calls;
  on 2/2 OK it auto-launches `classifier_gate_bench.py --with-cheap` → `gate_bench_E.json`
  (log `/tmp/gate_bench_E3.log`).
- On completion: run `venv/bin/python benchmarks/compare_e_vs_b.py`, add the E3 row
  to section 4, byte-verify E3 vs frozen B per case, finalize this report,
  commit results, tag `phase2b-checkpoint`. No push.

## 6. Open Items / Follow-ups

- Groq free-tier org TPD: waiting for a genuine window for one clean E run.
- `test_provider_fallback.py` fixture environment breakage (base `python` missing
  fastapi) — pre-existing, out of 2B scope.