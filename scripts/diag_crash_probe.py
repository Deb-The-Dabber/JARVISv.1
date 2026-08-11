#!/usr/bin/env python3
"""Diagnostic probe: binary-search the real-API crash location.

Runs progressive stages with faulthandler enabled, prints a marker BEFORE
each stage (flushed), and a completion marker after. If the process dies
mid-run, the last printed marker identifies the failing stage, and
faulthandler dumps the traceback.

Usage:
  JARVIS_INSTRUMENTATION=1 venv/bin/python scripts/diag_crash_probe.py [stage]

Stages (run progressively to STAGE, or all if omitted):
  import      -> import brain
  memory      -> load vector memory / ChromaDB
  embeddings  -> prewarm MiniLM embedder
  providers   -> initialize provider clients
  inference   -> one real provider call
  process     -> brain.process("hello")
"""

from __future__ import annotations

import faulthandler
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

faulthandler.enable()
faulthandler.dump_traceback_later(180, exit=True)  # watchdog for hangs

_target = sys.argv[1] if len(sys.argv) > 1 else "process"
STAGES = ["import", "memory", "embeddings", "providers", "inference", "process"]
_stage_idx = STAGES.index(_target)


def mark(msg: str) -> None:
    print(f"[PROBE:{_target}] {msg}", flush=True)


def run(stage: str) -> None:
    if STAGES.index(stage) > _stage_idx:
        return
    mark(f"BEGIN {stage}")
    t0 = time.time()
    try:
        if stage == "import":
            import brain  # noqa: F401
        elif stage == "memory":
            from vector_memory import _get_collection

            col = _get_collection()
            mark(f"chroma collection: {col}")
        elif stage == "embeddings":
            from vector_memory import get_local_embedding_model

            emb = get_local_embedding_model()
            emb.encode(["probe embedding warmup text"])
        elif stage == "providers":
            import brain

            client = brain._get_client()
            mark(f"client={'OK' if client else 'NONE'}")
            mark(f"primary provider: {getattr(brain, '_primary_provider_name', '?')}")
        elif stage == "inference":
            import brain

            reply = brain.ask_nim_with_context("Say OK", [])
            mark(f"reply: {str(reply)[:80]!r}")
        elif stage == "process":
            import brain

            reply = brain.process("hello")
            mark(f"process reply: {str(reply)[:120]!r}")
    except Exception as e:
        mark(f"STAGE {stage} ERROR: {type(e).__name__}: {e}")
        mark(f"END {stage} (error after {time.time() - t0:.1f}s)")
        return
    mark(f"END {stage} ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    mark(f"python={sys.version.split()[0]} instrumentation={os.getenv('JARVIS_INSTRUMENTATION', '1')}")
    for s in STAGES:
        if STAGES.index(s) <= _stage_idx:
            run(s)
    mark("ALL STAGES COMPLETE")
