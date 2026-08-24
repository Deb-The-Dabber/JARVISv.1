#!/usr/bin/env python3
"""Retrieval benchmark: same corpus + queries, compare embedding backends.

Run against the same collection before (MiniLM) and after (nemotron-3-embed-1b)
a re-embed migration, then --compare the two result files.

Usage:
    JARVIS_EMBEDDING=local python scripts/retrieval_eval.py --out results_minilm.json
    JARVIS_EMBEDDING=nemo  python scripts/retrieval_eval.py --out results_nemo.json
    python scripts/retrieval_eval.py --compare results_minilm.json results_nemo.json

The mode you pass must MATCH the collection's stored embedding model; the script
never triggers a migration. Optional --queries file: one query per line.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

DEFAULT_QUERIES = [
    "coffee preferences",
    "what system events happened on my Mac",
    "apps I usually have open",
    "my goals and priorities",
    "conversations about the weather",
    "screen content I saw recently",
    "music or spotify habits",
    "project planning notes",
    "black coffee",
    "recent conversation summaries",
    "timers and reminders",
    "where do I work",
]


def run(mode: str, queries: list[str], out: Path) -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import vector_memory  # noqa: F401  (import-time env already set by caller)
    from vector_memory import search_vector_memory

    results = []
    for q in queries:
        t0 = time.time()
        hits = search_vector_memory(q, n_results=5)
        latency = round(time.time() - t0, 3)
        results.append(
            {
                "query": q,
                "latency_ms": round(latency * 1000),
                "hits": [
                    {"doc": doc[:200], "score": score, "category": cat}
                    for doc, cat, _date, score in hits
                ],
            }
        )
        print(f"{latency:7.3f}s  {q[:60]:60s} -> {len(hits)} hits")

    out.write_text(json.dumps({"mode": mode, "results": results}, indent=2))
    print(f"\nwrote {out}")
    return 0


def compare(a: Path, b: Path) -> int:
    ra = json.loads(Path(a).read_text())
    rb = json.loads(Path(b).read_text())
    assert len(ra["results"]) == len(rb["results"]), "result sets differ in query count"
    print(f"{'query':44s} {'overlap@5':>9s} {'latA':>6s} {'latB':>6s}  scoreA scoreB")
    overlaps = []
    lats_a, lats_b, scores_a, scores_b = [], [], [], []
    for x, y in zip(ra["results"], rb["results"]):
        da = [h["doc"] for h in x["hits"]]
        db = [h["doc"] for h in y["hits"]]
        if not da and not db:
            overlap = 1.0
        elif not da or not db:
            overlap = 0.0
        else:
            overlap = len(set(da) & set(db)) / max(len(set(da)), len(set(db)))
        overlaps.append(overlap)
        lats_a.append(x["latency_ms"])
        lats_b.append(y["latency_ms"])
        scores_a.append(x["hits"][0]["score"] if x["hits"] else 0.0)
        scores_b.append(y["hits"][0]["score"] if y["hits"] else 0.0)
        print(
            f"{x['query'][:44]:44s} {overlap:9.2f} "
            f"{x['latency_ms']:6.0f} {y['latency_ms']:6.0f}  "
            f"{scores_a[-1]:.3f} {scores_b[-1]:.3f}"
        )
    print("\n--- aggregate ---")
    print(f"overlap@5 mean: {statistics.fmean(overlaps):.3f}")
    print(
        f"median latency: {ra['mode']} {statistics.median(lats_a):.0f}ms | "
        f"{rb['mode']} {statistics.median(lats_b):.0f}ms"
    )
    print(
        f"median top-1 score: {ra['mode']} {statistics.median(scores_a):.3f} | "
        f"{rb['mode']} {statistics.median(scores_b):.3f}"
    )
    print("note: scores are mode-specific; compare overlap, not absolute scores.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["local", "nemo"], help="embedding mode for THIS run")
    ap.add_argument("--out", type=Path, default=Path("retrieval_results.json"))
    ap.add_argument("--queries", type=Path, help="file with one query per line (default: built-in set)")
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"), help="compare two result files")
    args = ap.parse_args()

    if args.compare:
        return compare(Path(args.compare[0]), Path(args.compare[1]))
    if not args.mode:
        ap.error("--mode required unless --compare is used")
    queries = DEFAULT_QUERIES
    if args.queries:
        queries = [line.strip() for line in args.queries.read_text().splitlines() if line.strip()]
    return run(args.mode, queries, args.out)


if __name__ == "__main__":
    sys.exit(main())
