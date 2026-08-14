#!/usr/bin/env python3
"""Explicit, foreground embedding-model migration for the Jarvis vector memory index.

This is the ONLY sanctioned way to migrate the Chroma collection. Importing
vector_memory never deletes/recreates/migrates anything implicitly; any mismatch
is logged as "deferred" instead. This command performs every stage with
verification and fails loudly (exit 1) if any stage fails.

Usage:
    python scripts/migrate_embeddings.py --mode nemo --yes
    python scripts/migrate_embeddings.py --mode local --dry-run

The tool sets JARVIS_EMBEDDING for its own process before importing the app
modules, so it always runs in the requested mode regardless of .env.

On any failure nothing is destroyed until the backup stage has succeeded, and
the restore command is printed (cp -R <backup>/vector_db ~/jarvis_vector_db).

--rebuild-from-sources: additive recovery mode (no model change, no delete).
Reconstructs missing records in the CURRENT index from ~/jarvis_watchlog.db
(only the event signatures proactive.py vectorizes), ~/.jarvis/logs/jarvis.jsonl
(excluding error rows), and SQLite as authority for facts/goals/summaries.
Snapshots the recovery base first, dedupes by id + document, reports full
statistics, and exits 1 with rollback instructions on any failure.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(backup_dir: str | None, msg: str) -> int:
    print(f"\nMIGRATION FAILED: {msg}")
    if backup_dir:
        print(f"Backup exists at: {backup_dir}")
        print(f"Restore with:     cp -R {backup_dir}/vector_db {os.path.expanduser('~')}/jarvis_vector_db")
    else:
        print("No destructive step ran; the source collection is untouched.")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["nemo", "local"], default=os.getenv("JARVIS_EMBEDDING", "nemo"))
    ap.add_argument("--yes", action="store_true", help="skip the interactive confirmation")
    ap.add_argument(
        "--force",
        action="store_true",
        help="re-migrate even if the stored model matches (recreates collection config)",
    )
    ap.add_argument("--dry-run", action="store_true", help="verify preconditions, change nothing")
    ap.add_argument(
        "--rebuild-from-sources",
        action="store_true",
        help="reconstruct missing records in the CURRENT index from watchlog.db + "
        "jarvis.jsonl + SQLite (no model change, additive only)",
    )
    args = ap.parse_args()

    os.environ["JARVIS_EMBEDDING"] = args.mode
    sys.path.insert(0, str(ROOT))

    import chromadb

    import vector_memory
    from config import VECTOR_DB_PATH
    from vector_memory import (
        COLLECTION_NAME,
        EMBED_BACKUP_ROOT,
        EMBEDDING_MODEL_NAME,
        JARVIS_EMBED_BATCH,
        JarvisEmbeddingFunction,
    )

    if args.rebuild_from_sources:
        return _rebuild(args, vector_memory, VECTOR_DB_PATH, COLLECTION_NAME, EMBED_BACKUP_ROOT, JARVIS_EMBED_BATCH)

    # Reuse vector_memory's own client (a second PersistentClient on the same
    # path races its background init thread). The collection open may raise a
    # deferred config conflict — the client itself is still initialized, and
    # plain get_collection bypasses the embedding-function validation.
    try:
        vector_memory._get_collection()
    except Exception:
        pass
    client = vector_memory._client
    target = EMBEDDING_MODEL_NAME
    backup_dir = None

    # ── Stage 1: verify mode/model + source collection ---------------------
    print(f"[1/9] Mode={args.mode}  target model={target}")
    print(f"      index path: {VECTOR_DB_PATH}")
    if not os.path.isdir(VECTOR_DB_PATH):
        return _fail(None, f"index path does not exist: {VECTOR_DB_PATH}")

    client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
    try:
        col = client.get_collection(name=COLLECTION_NAME)
    except Exception as e:
        return _fail(None, f"source collection '{COLLECTION_NAME}' not found: {e}")

    source_count = col.count()
    print(f"[2/9] Source collection '{COLLECTION_NAME}' exists: {source_count} entries")
    if source_count == 0:
        return _fail(None, "source collection is empty; nothing to migrate")

    actual_model = (col.metadata or {}).get("embedding_model", "unknown")
    print(f"[3/9] Stored embedding model: {actual_model}")
    if actual_model == target and not args.force:
        print(f"Already on '{target}' — nothing to migrate.")
        return 0

    # ── Stage 4: export -----------------------------------------------------
    print("[4/9] Exporting ids/documents/metadata...")
    try:
        export = col.get(include=["documents", "metadatas"])
        ids = export.get("ids", [])
        docs = export.get("documents", [])
        metas = export.get("metadatas", [])
    except Exception as e:
        return _fail(None, f"export failed: {e}")
    if len(ids) != source_count:
        return _fail(None, f"exported {len(ids)} ids but count() said {source_count} — aborting")
    print(f"      exported {len(ids)} entries")

    # ── Stage 5: timestamped backup BEFORE any destructive op ---------------
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(EMBED_BACKUP_ROOT, f"migration_{actual_model.replace('/', '_')}_{ts}")
    print(f"[5/9] Backup -> {dest}")
    try:
        os.makedirs(dest, exist_ok=True)
        shutil.copytree(VECTOR_DB_PATH, os.path.join(dest, "vector_db"), dirs_exist_ok=True)
        with open(os.path.join(dest, "snapshot.jsonl"), "w") as fh:
            for i in range(len(ids)):
                fh.write(
                    json.dumps(
                        {"id": ids[i], "document": docs[i] if docs else "", "metadata": metas[i] if metas else {}}
                    )
                    + "\n"
                )
        if os.path.isdir(os.path.join(dest, "vector_db")) and os.path.isfile(os.path.join(dest, "snapshot.jsonl")):
            backup_dir = dest
        else:
            return _fail(backup_dir, "backup files did not materialize — aborting before any destructive op")
    except Exception as e:
        return _fail(backup_dir, f"backup failed: {e}")

    if args.dry_run:
        print("\nDRY RUN: preconditions OK, backup verified. No changes made.")
        print(f"Backup dir (created during dry run): {backup_dir}")
        return 0

    if not args.yes:
        print(
            f"\nThis will DELETE and RE-CREATE '{COLLECTION_NAME}' ({source_count} entries) "
            f"re-embedding with '{target}'."
        )
        reply = input("Type 'migrate' to proceed: ").strip().lower()
        if reply != "migrate":
            print("Aborted by user. Source untouched.")
            return 0

    # ── Stage 6: re-embed in batches -----------------------------------------
    print(f"[6/9] Re-embedding {len(ids)} entries in batches of {JARVIS_EMBED_BATCH}...")
    ef = JarvisEmbeddingFunction()
    embeddings = []
    t0 = time.time()
    try:
        for start in range(0, len(ids), JARVIS_EMBED_BATCH):
            chunk = [d for d in docs[start : start + JARVIS_EMBED_BATCH]]
            vecs = ef(chunk)
            embeddings.extend(vecs)
            done = min(start + JARVIS_EMBED_BATCH, len(ids))
            print(f"      {done}/{len(ids)}  ({time.time() - t0:.1f}s)")
    except Exception as e:
        return _fail(backup_dir, f"re-embedding failed at batch: {e}")
    if len(embeddings) != len(ids):
        return _fail(backup_dir, f"embedded {len(embeddings)} vectors for {len(ids)} entries")

    # ── Stage 7: recreate collection ----------------------------------------
    # The new collection must be created WITH the app's JarvisEmbeddingFunction
    # config (name "jarvis_embedding") — creating it bare persists chroma's
    # "default" config, and vector_memory's get_or_create(embedding_function=...)
    # then raises an embedding-function conflict on every open.
    print("[7/9] Recreating collection...")
    try:
        client.delete_collection(name=COLLECTION_NAME)
        client.create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine", "embedding_model": target},
            embedding_function=ef,
        )
        col = client.get_collection(name=COLLECTION_NAME)
    except Exception as e:
        return _fail(backup_dir, f"recreate failed: {e}")

    try:
        for start in range(0, len(ids), JARVIS_EMBED_BATCH):
            col.add(
                ids=ids[start : start + JARVIS_EMBED_BATCH],
                documents=docs[start : start + JARVIS_EMBED_BATCH],
                metadatas=metas[start : start + JARVIS_EMBED_BATCH],
                embeddings=embeddings[start : start + JARVIS_EMBED_BATCH],
            )
    except Exception as e:
        return _fail(backup_dir, f"re-add failed: {e}")

    # ── Stage 8: verify -------------------------------------------------------
    print("[8/9] Verifying...")
    try:
        new_count = col.count()
        got_ids = set(col.get(include=[])["ids"])
    except Exception as e:
        return _fail(backup_dir, f"post-migration verification failed: {e}")

    if new_count != source_count:
        return _fail(backup_dir, f"count mismatch: source {source_count}, new {new_count}")
    if got_ids != set(ids):
        missing = len(set(ids) - got_ids)
        extra = len(got_ids - set(ids))
        return _fail(backup_dir, f"id set mismatch: missing {missing}, extra {extra}")

    try:
        sample = col.get(limit=1, include=["embeddings"])
        new_dim = len(sample["embeddings"][0])
        expected_dim = len(ef(["dimension check"])[0])
    except Exception as e:
        return _fail(backup_dir, f"dimension verification failed: {e}")
    if new_dim != expected_dim:
        return _fail(backup_dir, f"dimension mismatch: stored {new_dim}, expected {expected_dim}")

    # ── Stage 9: report --------------------------------------------------------
    print("[9/9] DONE.")
    print(f"  entries restored: {new_count} (exact match with source)")
    print(f"  dimensions: {new_dim}")
    print(f"  backup: {backup_dir}")
    print("Next steps: restart the server with the matching JARVIS_EMBEDDING,")
    print("            then run scripts/retrieval_eval.py to compare retrieval quality.")
    return 0


VECTORIZED_EVENTS = {
    "system": {"CPU spike", "High RAM usage", "Low disk space"},
    "network": {"Internet connection lost"},
    "weather": {"Rain incoming"},
    "files": {"Downloads folder large", "Desktop cluttered"},
}


def _is_vectorized_event(category: str, event: str) -> bool:
    if category in VECTORIZED_EVENTS and event in VECTORIZED_EVENTS[category]:
        return True
    if category == "calendar" and (event.startswith("Event in 15 min") or event.startswith("Event in 5 min")):
        return True
    if category == "apps" and (event.endswith(" opened") or event.endswith(" closed")):
        return True
    if category == "screen" and event.startswith("Notable content in"):
        return True
    return False


def _epoch(iso: str) -> float:
    return datetime.datetime.fromisoformat(iso).timestamp()


def _rebuild(args, chromadb, vector_db_path, collection_name, backup_root, batch_size) -> int:
    """Additive reconstruction of missing records into the CURRENT index.

    Sources (read-only): ~/jarvis_watchlog.db (system_event signatures),
    ~/.jarvis/logs/jarvis.jsonl (conversations), ~/jarvis_memory.db (facts/goals/
    summaries — already synced, acts as authority check). Snapshot before write.
    """
    if args.mode != "local":
        print("ERROR: --rebuild-from-sources must embed with the index's current model (local/MiniLM).")
        return 1

    from vector_memory import JarvisEmbeddingFunction

    if not os.path.isdir(vector_db_path):
        return _fail(None, f"index path does not exist: {vector_db_path}")
    import vector_memory

    try:
        vector_memory._get_collection()
    except Exception:
        pass
    client = vector_memory._client
    try:
        col = client.get_collection(name=collection_name)
    except Exception as e:
        return _fail(None, f"collection '{collection_name}' not found: {e}")

    old_count = col.count()
    stored_model = (col.metadata or {}).get("embedding_model", "unknown")
    print(f"[rebuild] Recovery base: {old_count} entries, model '{stored_model}' (mode={args.mode})")
    if old_count == 0:
        return _fail(None, "recovery base is empty — nothing to build on")

    # ── snapshot the current index before writing anything -------------------
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(backup_root, f"pre_rebuild_{stored_model.replace('/', '_')}_{ts}")
    print(f"[rebuild] Snapshot of recovery base -> {dest}")
    try:
        os.makedirs(dest, exist_ok=True)
        shutil.copytree(vector_db_path, os.path.join(dest, "vector_db"), dirs_exist_ok=True)
        export = col.get(include=["documents", "metadatas"])
        with open(os.path.join(dest, "snapshot.jsonl"), "w") as fh:
            for i in range(len(export["ids"])):
                fh.write(
                    json.dumps(
                        {
                            "id": export["ids"][i],
                            "document": export["documents"][i],
                            "metadata": export["metadatas"][i],
                        }
                    )
                    + "\n"
                )
        snap_rows = sum(1 for _ in open(os.path.join(dest, "snapshot.jsonl")))
        if not (os.path.isdir(os.path.join(dest, "vector_db")) and snap_rows == old_count):
            return _fail(dest, "snapshot unreadable or incomplete — aborting before any write")
        print(f"       snapshot verified: {snap_rows} entries")
    except Exception as e:
        return _fail(dest, f"snapshot failed: {e}")

    # The index's true epoch: every pre-incident record began 2026-08-07 21:12
    # (backup's earliest conversation/system_event timestamps). Records older
    # than that were never part of this index and are NOT reconstructed.
    # Reconstruction also ENDS at the incident (2026-08-13 18:45): anything
    # timestamped after it was written live into the recovery base already.
    WINDOW_START = "2026-08-07T21:12:00"
    REBUILD_END = "2026-08-13T18:45:00"

    existing_ids = set(export["ids"])
    existing_docs = {str(d).strip().lower() for d in export["documents"] if d}
    # The base index only covers its own window (index epoch -> Aug 9 00:07).
    # A candidate whose content matches a base doc is a true duplicate ONLY if
    # it falls inside that coverage window; the original stored one row per
    # request/event, including repeated identical texts, so content matches
    # outside the base window are NEW records and must be added.
    base_window = {
        "conversation": (None, None),
        "system_event": (None, None),
        "goal": (None, None),
        "fact": (None, None),
        "conversation_summary": (None, None),
    }
    for i, m in enumerate(export["metadatas"]):
        if not isinstance(m, dict):
            continue
        cat = m.get("category", "unknown")
        ts = m.get("created_at", "")
        if cat not in base_window or not ts:
            continue
        # Rows timestamped after the incident are LIVE writes (the server kept
        # running) — they must not extend the backup's real coverage window.
        if ts > REBUILD_END:
            continue
        lo, hi = base_window[cat]
        base_window[cat] = (ts if lo is None or ts < lo else lo, ts if hi is None or ts > hi else hi)

    def _within_base_window(cat: str, ts: str) -> bool:
        lo, hi = base_window.get(cat, (None, None))
        if not lo or not hi:
            return False
        return lo <= ts <= hi

    # ── build candidate records ----------------------------------------------
    candidates = []  # (id, doc, meta)
    discovered = {"conversation": 0, "system_event": 0, "sqlite_authority": 0}
    unreconstructable = {}

    home = os.path.expanduser("~")
    # conversations from jarvis.jsonl
    jlog = os.path.join(os.path.expanduser("~"), ".jarvis", "logs", "jarvis.jsonl")
    if os.path.exists(jlog):
        seen_req = set()
        err_rows = empty_replies = out_of_window = out_after_incident = 0
        for line in open(jlog):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            u, reply = r.get("user_message_preview") or "", r.get("reply_preview") or ""
            if r.get("error"):
                err_rows += 1
                continue
            if not u:
                empty_replies += 1
                continue
            if r["ts"] < WINDOW_START:
                out_of_window += 1
                continue
            if r["ts"] > REBUILD_END:
                out_after_incident += 1
                continue
            rid = r.get("request_id")
            if rid and rid in seen_req:
                continue
            if rid:
                seen_req.add(rid)
            discovered["conversation"] += 1
            candidates.append(
                (
                    f"conversation_{_epoch(r['ts']):.6f}",
                    f"User: {u} | Jarvis: {reply[:200]}",
                    {"category": "conversation", "created_at": r["ts"], "source": "jarvis.jsonl"},
                )
            )
        unreconstructable["jarvis.jsonl error rows (never were entries)"] = err_rows
        unreconstructable["jarvis.jsonl empty-user rows"] = empty_replies
        unreconstructable["jarvis.jsonl rows before index epoch (never in this index)"] = out_of_window
        unreconstructable["jarvis.jsonl rows after incident (already live in base)"] = out_after_incident
    else:
        print(f"  [rebuild] jarvis.jsonl not found: {jlog} (conversation rebuild skipped)")

    # system_event signatures from watchlog.db
    wlog = os.path.join(home, "jarvis_watchlog.db")
    if os.path.exists(wlog):
        import sqlite3

        conn = sqlite3.connect(wlog)
        rows = conn.execute("SELECT category, event, detail, created_at FROM events").fetchall()
        conn.close()
        non_sig = {}
        out_of_window = out_after_incident = 0
        for cat, ev, det, cat_ts in rows:
            if not _is_vectorized_event(cat, ev):
                non_sig[cat] = non_sig.get(cat, 0) + 1
                continue
            if cat_ts < WINDOW_START:
                out_of_window += 1
                continue
            if cat_ts > REBUILD_END:
                out_after_incident += 1
                continue
            doc = f"{cat}: {ev}"
            if det:
                doc += f" | {det[:200]}"
            discovered["system_event"] += 1
            candidates.append(
                (
                    f"system_event_{_epoch(cat_ts):.6f}",
                    doc,
                    {"category": "system_event", "created_at": cat_ts, "source": "watchlog.db"},
                )
            )
        unreconstructable["watchlog vectorized rows before index epoch"] = out_of_window
        unreconstructable["watchlog vectorized rows after incident (already live in base)"] = out_after_incident
        unreconstructable["watchlog non-vectorized rows (presence/startup briefings etc.)"] = sum(
            non_sig.values()
        )
    else:
        print(f"  [rebuild] watchlog.db not found: {wlog} (system_event rebuild skipped)")

    # SQLite authority: add any facts/goals/summaries missing from the index
    mdb = os.path.join(home, "jarvis_memory.db")
    if os.path.exists(mdb):
        import hashlib
        import sqlite3

        conn = sqlite3.connect(mdb)
        cur = conn.cursor()
        cur.execute("SELECT type, content, created_at FROM memories")
        mem_rows = cur.fetchall()
        cur.execute("SELECT summary, created_at FROM summaries")
        sum_rows = cur.fetchall()
        cur.execute("SELECT title, description, status, priority, progress_notes, created_at FROM goals")
        goal_rows = cur.fetchall()
        conn.close()
        for mtype, content, created_at in mem_rows:
            if content and content.strip().lower() not in existing_docs:
                discovered["sqlite_authority"] += 1
                candidates.append(
                    (
                        f"fact_{created_at}",
                        content,
                        {"category": mtype or "fact", "created_at": created_at, "source": "jarvis_memory.db"},
                    )
                )
        for summary, created_at in sum_rows:
            if summary and summary.strip().lower() not in existing_docs:
                discovered["sqlite_authority"] += 1
                candidates.append(
                    (
                        f"conversation_summary_{created_at}",
                        summary,
                        {"category": "conversation_summary", "created_at": created_at, "source": "jarvis_memory.db"},
                    )
                )
        for title, desc, status, priority, notes, created_at in goal_rows:
            parts = [f"Goal: {title}"]
            if desc and desc.strip():
                parts.append(desc.strip())
            parts.append(f"Status: {status}, Priority: {priority}")
            if notes and notes.strip():
                parts.append(f"Progress: {notes.strip()}")
            content = " | ".join(parts)
            if content and content.strip().lower() not in existing_docs:
                discovered["sqlite_authority"] += 1
                candidates.append(
                    (
                        f"goal_{hashlib.md5(title.encode()).hexdigest()[:12]}_{created_at}",
                        content,
                        {"category": "goal", "created_at": created_at, "source": "jarvis_memory.db"},
                    )
                )

    # ── dedupe: id collisions + doc duplicates --------------------------------
    # id collisions: deterministic ids already in the base (never happens for
    # conversation/system_event since add-time ids trail request timestamps,
    # but sqlite authority ids can collide).
    # doc duplicates: only skip when the candidate falls inside the base
    # index's own coverage window AND its text exists there; repeated identical
    # records outside that window are distinct rows in the original design and
    # are all kept.
    id_collisions = 0
    doc_dups = 0
    to_add = []
    for cid, doc, meta in candidates:
        if cid in existing_ids:
            id_collisions += 1
            continue
        if (
            _within_base_window(meta.get("category", ""), meta.get("created_at", ""))
            and doc.strip().lower() in existing_docs
        ):
            doc_dups += 1
            continue
        to_add.append((cid, doc, meta))

    print(f"[rebuild] discovered: {discovered}")
    print(f"[rebuild] id collisions skipped: {id_collisions} | doc duplicates skipped: {doc_dups}")
    print(f"[rebuild] to add: {len(to_add)}")

    if args.dry_run:
        print("\nDRY RUN: no changes made. Snapshot of recovery base kept for reference:")
        print(f"  {dest}")
        return 0

    if not args.yes:
        reply = input(f"Add {len(to_add)} entries to the live index? Type 'rebuild' to proceed: ").strip().lower()
        if reply != "rebuild":
            print("Aborted by user. Index untouched (snapshot kept).")
            return 0

    ef = JarvisEmbeddingFunction()
    added = 0
    try:
        for start in range(0, len(to_add), batch_size):
            chunk = to_add[start : start + batch_size]
            docs = [c[1] for c in chunk]
            vecs = ef(docs)
            col.add(
                ids=[c[0] for c in chunk],
                documents=docs,
                metadatas=[c[2] for c in chunk],
                embeddings=vecs,
            )
            added += len(chunk)
            print(f"       {added}/{len(to_add)} added")
    except Exception as e:
        print(f"REBUILD FAILED mid-write: {e}")
        print(f"Index may be partially updated. Snapshot for rollback: {dest}")
        print(f"Restore with: cp -R {dest}/vector_db ~/jarvis_vector_db")
        return 1

    final_count = col.count()
    expected = old_count + len(to_add)
    try:
        got_ids = set(col.get(include=[])["ids"])
    except Exception as e:
        print(f"REBUILD VERIFY FAILED: {e}. Snapshot: {dest}")
        return 1
    added_ids = {c[0] for c in to_add}
    missing = added_ids - got_ids
    if missing:
        print(f"REBUILD VERIFY FAILED: {len(missing)} added ids missing. Snapshot: {dest}")
        return 1
    if final_count != expected:
        # The live server writes memory rows concurrently (proactive monitors);
        # a small positive delta is expected and benign. MISSING ids are not.
        delta = final_count - expected
        verdict = "OK (concurrent live writes)" if delta > 0 else "FAILED"
        print(f"count {final_count} vs expected {expected} (delta {delta:+d}) -> {verdict}")
        if delta < 0:
            print(f"REBUILD VERIFY FAILED: index smaller than expected. Snapshot: {dest}")
            return 1

    dist = {}
    for m in col.get(include=["metadatas"])["metadatas"]:
        cat = (m or {}).get("category", "unknown") if isinstance(m, dict) else "unknown"
        dist[cat] = dist.get(cat, 0) + 1

    times = [
        m.get("created_at", "")
        for m in col.get(include=["metadatas"])["metadatas"]
        if isinstance(m, dict) and m.get("created_at")
    ]
    times.sort()
    print("\n=== REBUILD REPORT ===")
    print(f"old count (recovery base):   {old_count}")
    print(f"discovered:                  {sum(discovered.values())}")
    for k, v in discovered.items():
        print(f"  {k}: {v}")
    print(f"id collisions skipped:       {id_collisions}")
    print(f"doc duplicates skipped:      {doc_dups}")
    print(f"entries added:               {added}")
    print(f"final count:                 {final_count}")
    print(f"unreconstructable:           {unreconstructable}")
    print(f"category distribution:       {dict(sorted(dist.items(), key=lambda x: -x[1]))}")
    print(f"earliest record:             {times[0] if times else '-'}")
    print(f"latest record:               {times[-1] if times else '-'}")
    print(f"snapshot of recovery base:   {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
