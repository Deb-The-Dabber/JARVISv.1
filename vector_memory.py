import datetime
import hashlib
import json
import os
import shutil
import threading
import time

from dotenv import load_dotenv

load_dotenv()

try:
    from config import JARVIS_EMBEDDING, JARVIS_EMBED_BATCH, JARVIS_EMBED_MAX_CHARS  # noqa: I001
except Exception:
    JARVIS_EMBEDDING = os.getenv("JARVIS_EMBEDDING", "nemo").lower().strip()
    JARVIS_EMBED_BATCH = int(os.getenv("JARVIS_EMBED_BATCH", "64"))
    JARVIS_EMBED_MAX_CHARS = int(os.getenv("JARVIS_EMBED_MAX_CHARS", "6000"))

VECTOR_DB_PATH = os.path.join(os.path.expanduser("~"), "jarvis_vector_db")

EMBEDDING_URL = "https://integrate.api.nvidia.com/v1/embeddings"
NEMO_EMBED_MODEL = "nvidia/nemotron-3-embed-1b"
EMBED_CACHE_MAX = 2048
EMBED_BACKUP_ROOT = os.path.join(os.path.expanduser("~"), ".jarvis", "embeddings_backup")

_client = None
_collection = None
_embedding_function = None
_lock = threading.RLock()
_embedding_mode_printed = False
_local_embedding_model = None
_embedding_failed = False
_repopulated = False
_repopulate_done = threading.Event()
_http_client = None
_embed_lru: dict[str, list] = {}


def _disable_tqdm_mp_lock() -> None:
    """Prevent tqdm from creating a multiprocessing.RLock for its write lock.

    tqdm's progress bar (e.g. MiniLM "Loading weights" bar) calls
    multiprocessing.RLock() at first render. That spawns the multiprocessing
    resource_tracker daemon, which can hang at interpreter exit on macOS
    (holds the inherited stderr pipe open -> process appears hung, with a
    "leaked semaphore objects" warning). The threading lock alone is
    sufficient for our single-process use.
    """
    try:
        import tqdm.std

        tqdm.std.TqdmDefaultWriteLock.mp_lock = None
    except Exception:
        pass


def _get_http_client():
    """Return the single persistent HTTP client for embeddings.

    Never create/close a client per request (macOS ENOBUFS): one keep-alive
    client is shared for the process lifetime.
    """
    global _http_client
    if _http_client is None:
        import httpx

        _http_client = httpx.Client(
            timeout=httpx.Timeout(60.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=4, max_connections=8),
        )
    return _http_client


def _remote_embed(texts: list[str]) -> list:
    """Embed texts via NVIDIA NIM nemotron-3-embed-1b (2048-dim)."""
    import httpx

    key = (os.getenv("NVIDIA_NEMOTRON_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("NVIDIA_NEMOTRON_API_KEY not set for embeddings")
    client = _get_http_client()
    out: list = []
    for start in range(0, len(texts), JARVIS_EMBED_BATCH):
        batch = [t[:JARVIS_EMBED_MAX_CHARS] for t in texts[start : start + JARVIS_EMBED_BATCH]]
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                r = client.post(
                    EMBEDDING_URL,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={"model": NEMO_EMBED_MODEL, "input": batch},
                )
                if r.status_code == 200:
                    data = sorted(r.json()["data"], key=lambda v: v["index"])
                    out.extend(d["embedding"] for d in data)
                    break
                last_err = RuntimeError(f"embedding HTTP {r.status_code}: {r.text[:120]}")
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise last_err
            except httpx.HTTPError as e:
                last_err = e
                time.sleep(1.0 + attempt)
        else:
            raise last_err or RuntimeError("embedding request failed")
    return out


def _cached_embed(text: str) -> list:
    """Remote embed with a small in-memory LRU (repeated queries are free)."""
    h = hashlib.md5(text.encode("utf-8")).hexdigest()
    vec = _embed_lru.get(h)
    if vec is not None:
        return vec
    vec = _remote_embed([text])[0]
    if len(_embed_lru) >= EMBED_CACHE_MAX:
        _embed_lru.clear()
    _embed_lru[h] = vec
    return vec


def _get_embedding(text: str) -> list:
    """Get embedding using the configured backend (nemotron-3-embed-1b or local MiniLM)."""
    global _embedding_mode_printed, _local_embedding_model, _embedding_failed

    if _embedding_failed:
        raise RuntimeError("Embedding service unavailable")

    try:
        if JARVIS_EMBEDDING == "local":
            return _local_embed(text)
        if not _embedding_mode_printed:
            print(f"  Embeddings: {NEMO_EMBED_MODEL} (2048-dim, remote)")
            _embedding_mode_printed = True
        return _cached_embed(text)
    except Exception as e:
        _embedding_failed = True
        raise RuntimeError(f"Embedding service unavailable: {e}")


def _local_embed(text: str) -> list:
    """Local all-MiniLM-L6-v2 path (384-dim), used for offline/CI and the NN router core."""
    global _embedding_mode_printed, _local_embedding_model
    if _local_embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _disable_tqdm_mp_lock()
        _local_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    if not _embedding_mode_printed:
        print("  Embeddings: all-MiniLM-L6-v2 (384-dim)")
        _embedding_mode_printed = True
    return _local_embedding_model.encode(text).tolist()


class JarvisEmbeddingFunction:
    def __init__(self):
        pass

    def name(self):
        return "jarvis_embedding"

    def __call__(self, input):
        """Embed a list of texts using the new embedding service (batched remote)."""
        texts = list(input)
        if not texts:
            return []
        if JARVIS_EMBEDDING == "local":
            return [_get_embedding(t) for t in texts]
        out: list[tuple[int, list]] = []
        todo: list[tuple[int, str]] = []
        for i, t in enumerate(texts):
            h = hashlib.md5(t.encode("utf-8")).hexdigest()
            v = _embed_lru.get(h)
            if v is not None:
                out.append((i, v))
            else:
                todo.append((i, t))
        if todo:
            vecs = _remote_embed([t for _, t in todo])
            for (i, t), v in zip(todo, vecs):
                h = hashlib.md5(t.encode("utf-8")).hexdigest()
                if len(_embed_lru) >= EMBED_CACHE_MAX:
                    _embed_lru.clear()
                _embed_lru[h] = v
                out.append((i, v))
        out.sort(key=lambda x: x[0])
        return [v for _, v in out]


COLLECTION_NAME = "jarvis_mini"
EMBEDDING_MODEL_NAME = NEMO_EMBED_MODEL if JARVIS_EMBEDDING == "nemo" else "all-MiniLM-L6-v2"


def _current_embedding_name() -> str:
    return EMBEDDING_MODEL_NAME


def _should_reset_collection(error: Exception) -> bool:
    if not error:
        return False
    msg = str(error).lower()
    return (
        "collection expecting embedding with dimension" in msg
        or "an embedding function already exists in the collection configuration" in msg
        or "embedding function conflict" in msg
        or "no such table" in msg
    )


def _defer_migration(reason: str):
    """Log that a migration is needed without performing any destructive action.

    Importing vector_memory must never delete/recreate/migrate a collection
    implicitly (background threads / smoke tests / module init included).
    Deferred migrations are done explicitly via scripts/migrate_embeddings.py.
    """
    try:
        os.makedirs(EMBED_BACKUP_ROOT, exist_ok=True)
        with open(os.path.join(EMBED_BACKUP_ROOT, "deferred_migration.log"), "a") as fh:
            fh.write(f"[{datetime.datetime.now().isoformat()}] {reason}\n")
    except Exception:
        pass
    print(f"  [Migration deferred] {reason}")
    print("  Run explicitly: python scripts/migrate_embeddings.py --mode nemo|local --yes")


def _export_collection_data(col):
    try:
        all_data = col.get(include=["documents", "metadatas", "embeddings"])
        ids = all_data.get("ids", [])
        docs = all_data.get("documents", [])
        metas = all_data.get("metadatas", [])
        embs = all_data.get("embeddings", [])
        if not ids:
            return []
        exported = []
        for i in range(len(ids)):
            exported.append(
                {
                    "id": ids[i],
                    "document": docs[i] if docs and i < len(docs) else "",
                    "metadata": metas[i] if metas and i < len(metas) else {},
                    "embedding": embs[i] if embs and i < len(embs) else None,
                }
            )
        print(f"  Exported {len(exported)} existing vector entries for migration.")
        return exported
    except Exception as e:
        print(f"  Could not export via API: {e}")
        # Fallback: direct SQLite extraction
        try:
            import sqlite3

            chroma_db = os.path.join(VECTOR_DB_PATH, "chroma.sqlite3")
            if not os.path.exists(chroma_db):
                return []
            conn = sqlite3.connect(chroma_db)
            c = conn.cursor()
            c.execute("""
                SELECT e.embedding_id, em.string_value, em2.string_value
                FROM embeddings e
                JOIN embedding_metadata em ON e.id = em.id AND em.key = 'documents'
                JOIN embedding_metadata em2 ON e.id = em2.id AND em2.key = 'category'
            """)
            rows = c.fetchall()
            conn.close()
            if not rows:
                return []
            exported = []
            for row in rows:
                exported.append(
                    {
                        "id": row[0],
                        "document": row[1] or "",
                        "metadata": {"category": row[2] or "memory"} if row[2] else {},
                        "embedding": None,
                    }
                )
            print(f"  Exported {len(exported)} entries via SQLite fallback.")
            return exported
        except Exception as e2:
            print(f"  SQLite fallback also failed: {e2}")
            return []


def _snapshot_collection(old_collection, old_data: list) -> str:
    """Copy the old index dir + export.jsonl before migration, for immediate rollback."""
    try:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        old_model = "unknown"
        try:
            if old_collection is not None and old_collection.metadata:
                old_model = old_collection.metadata.get("embedding_model", "unknown") or "unknown"
        except Exception:
            pass
        dest = os.path.join(EMBED_BACKUP_ROOT, f"{old_model.replace('/', '_')}_{ts}")
        os.makedirs(dest, exist_ok=True)
        if os.path.isdir(VECTOR_DB_PATH):
            shutil.copytree(VECTOR_DB_PATH, os.path.join(dest, "vector_db"), dirs_exist_ok=True)
        with open(os.path.join(dest, "snapshot.jsonl"), "w") as fh:
            for item in old_data:
                fh.write(
                    json.dumps(
                        {"id": item["id"], "document": item["document"], "metadata": item["metadata"]}
                    )
                    + "\n"
                )
        print(f"  Pre-migration snapshot: {dest} ({len(old_data)} entries)")
        return dest
    except Exception as e:
        print(f"  Snapshot warning (proceeding without backup): {e}")
        return ""


def _reset_collection():
    global _client, _collection, _embedding_function

    old_collection = None
    old_data = []
    if _client is not None:
        try:
            old_collection = _client.get_collection(name=COLLECTION_NAME)
        except Exception:
            pass
    if old_collection is not None:
        try:
            old_data = _export_collection_data(old_collection)
        except Exception:
            old_data = []
    _snapshot_collection(old_collection, old_data)

    try:
        if _client is not None:
            _client.delete_collection(name=COLLECTION_NAME)
    except Exception as e:
        print(f"  Vector memory reset warning: could not delete mismatched collection: {e}")

    _collection = None
    _client = None
    _embedding_function = JarvisEmbeddingFunction()
    try:
        if os.path.isdir(VECTOR_DB_PATH):
            shutil.rmtree(VECTOR_DB_PATH)
    except Exception as e:
        print(f"  Vector memory reset warning: could not remove DB path: {e}")

    new_col = _get_collection()

    if old_data:
        migrated = 0
        for start in range(0, len(old_data), JARVIS_EMBED_BATCH):
            items = old_data[start : start + JARVIS_EMBED_BATCH]
            try:
                new_col.add(
                    documents=[item["document"] for item in items],
                    metadatas=[item["metadata"] for item in items],
                    ids=[item["id"] for item in items],
                )
                migrated += len(items)
            except Exception:
                for item in items:
                    try:
                        new_col.add(
                            documents=[item["document"]],
                            metadatas=[item["metadata"]],
                            ids=[item["id"]],
                        )
                        migrated += 1
                    except Exception:
                        pass
        print(f"  Migrated {migrated}/{len(old_data)} entries to new embedding model.")
    return new_col


def _drop_and_reopen():
    global _client, _collection
    _client = None
    _collection = None
    try:
        if os.path.isdir(VECTOR_DB_PATH):
            shutil.rmtree(VECTOR_DB_PATH)
    except Exception:
        pass
    return _get_collection()


def _get_collection():
    global _client, _collection, _embedding_function, _repopulated
    if _collection is not None and _repopulated:
        return _collection
    with _lock:
        if _collection is not None:
            return _collection
        import chromadb

        os.makedirs(VECTOR_DB_PATH, exist_ok=True)
        _client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
        _embedding_function = JarvisEmbeddingFunction()

        expected_model = _current_embedding_name()

        try:
            _collection = _client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine", "embedding_model": expected_model},
                embedding_function=_embedding_function,
            )
            actual_model = _collection.metadata.get("embedding_model", "") if _collection.metadata else ""
            if actual_model and actual_model != expected_model:
                _defer_migration(
                    f"index is '{actual_model}', runtime expects '{expected_model}' "
                    f"(JARVIS_EMBEDDING={JARVIS_EMBEDDING})."
                )
        except Exception as e:
            if _should_reset_collection(e):
                _defer_migration(f"collection access issue: {e}. Not auto-recreating.")
            raise
        count = _collection.count()
        if count == 0 and not _repopulated:
            repopulate_from_sqlite()
            _repopulated = True
            count = _collection.count()
        _repopulate_done.set()
        print(f"  Vector memory loaded ({count} entries).")
        return _collection


def _embed(texts: list[str]) -> list:
    global _embedding_function
    if _embedding_function is None:
        _embedding_function = JarvisEmbeddingFunction()
    return _embedding_function(texts)


def add_to_vector_memory(content: str, category: str = "memory", metadata: dict = None):
    """Add any text to vector memory."""
    try:
        col = _get_collection()
        doc_id = f"{category}_{datetime.datetime.now().timestamp()}"
        meta = {
            "category": category,
            "created_at": datetime.datetime.now().isoformat(),
        }
        if metadata:
            meta.update(metadata)
        embedding = _embed([content])[0]
        col.add(documents=[content], embeddings=[embedding], metadatas=[meta], ids=[doc_id])
        return True
    except Exception as e:
        if _should_reset_collection(e):
            _defer_migration(
                f"add_to_vector_memory hit a mismatch ({e}); entry not added, no automatic reset."
            )
            return False
        print(f"  Vector memory add error: {e}")
        return False


def search_vector_memory(query: str, n_results: int = 5, category: str = None) -> list:
    """
    Semantic search — finds memories by meaning not keywords.
    Returns list of (content, category, date, score) tuples.
    """
    if not _repopulate_done.is_set():
        if not _repopulate_done.wait(timeout=20):
            print("  Vector memory still warming up, search may return incomplete results.")
    try:
        col = _get_collection()
        if col.count() == 0:
            return []

        where = {"category": category} if category else None
        n = min(n_results, col.count())
        if n == 0:
            return []

        results = col.query(
            query_embeddings=[_embed([query])[0]],
            n_results=n,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        output = []
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        distances = results["distances"][0]

        for doc, meta, dist in zip(docs, metas, distances):
            score = 1 - dist  # Convert distance to similarity
            if score > 0.3:  # Only return reasonably similar results
                output.append((doc, meta.get("category", "unknown"), meta.get("created_at", ""), round(score, 3)))

        return output
    except Exception as e:
        if _should_reset_collection(e):
            _defer_migration(
                f"search_vector_memory hit a mismatch ({e}); returning empty, no automatic reset."
            )
            return []
        print(f"  Vector search error: {e}")
        return []


def build_semantic_context(query: str) -> str:
    """
    Build a context block of semantically relevant memories
    to inject into the system prompt.
    """
    results = search_vector_memory(query, n_results=8)
    if not results:
        return ""

    lines = ["Semantically relevant memories:"]
    for content, category, created_at, score in results:
        date = created_at[:10] if created_at else "unknown"
        lines.append(f"  [{date}][{category}] {content}")

    return "\n".join(lines)


def get_vector_memory_stats() -> dict:
    """Get stats about the vector memory database."""
    try:
        col = _get_collection()
        return {
            "total_entries": col.count(),
            "db_path": VECTOR_DB_PATH,
        }
    except Exception as e:
        return {"error": str(e)}


def delete_from_vector_memory(keyword: str) -> int:
    """Delete entries containing a keyword — queries ALL documents."""
    try:
        col = _get_collection()
        all_data = col.get(include=["documents"])
        ids = all_data.get("ids", [])
        docs = all_data.get("documents", [])
        ids_to_delete = []
        for i, doc in enumerate(docs):
            if doc and keyword.lower() in doc.lower():
                ids_to_delete.append(ids[i])
        if ids_to_delete:
            col.delete(ids=ids_to_delete)
        return len(ids_to_delete)
    except Exception as e:
        print(f"  Vector delete error: {e}")
        return 0


def repopulate_from_sqlite():
    """Repopulate vector memory from SQLite jarvis_memory.db.

    Returns number of entries added. Safe to call repeatedly (skips duplicates).
    """
    sqlite_path = os.path.join(os.path.expanduser("~"), "jarvis_memory.db")
    if not os.path.exists(sqlite_path):
        return 0
    try:
        import sqlite3

        conn = sqlite3.connect(sqlite_path)
        c = conn.cursor()
        c.execute("SELECT type, content, created_at FROM memories ORDER BY created_at DESC")
        memories = c.fetchall()
        c.execute("SELECT summary, created_at FROM summaries ORDER BY created_at DESC")
        summaries = c.fetchall()
        c.execute("""
            SELECT title, description, status, priority, progress_notes, created_at
            FROM goals ORDER BY created_at DESC
        """)
        goals_rows = c.fetchall()
        conn.close()
    except Exception as e:
        print(f"  Could not read SQLite memories for repopulation: {e}")
        return 0

    if not memories and not summaries and not goals_rows:
        return 0

    try:
        col = _get_collection()
    except Exception:
        return 0

    existing_set = set()
    try:
        all_data = col.get(include=["documents"])
        existing_docs = all_data.get("documents", []) or []
        existing_set = {d.strip().lower() for d in existing_docs if d}
    except Exception:
        pass

    added = 0
    for mtype, content, created_at in memories:
        if content and content.strip().lower() not in existing_set:
            try:
                doc_id = f"fact_{created_at}"
                meta = {
                    "category": mtype or "fact",
                    "created_at": created_at,
                }
                embedding = _embed([content])[0]
                col.add(
                    documents=[content],
                    embeddings=[embedding],
                    metadatas=[meta],
                    ids=[doc_id],
                )
                added += 1
                existing_set.add(content.strip().lower())
            except Exception:
                pass

    for summary, created_at in summaries:
        if summary and summary.strip().lower() not in existing_set:
            try:
                doc_id = f"conversation_summary_{created_at}"
                meta = {
                    "category": "conversation_summary",
                    "created_at": created_at,
                }
                embedding = _embed([summary])[0]
                col.add(
                    documents=[summary],
                    embeddings=[embedding],
                    metadatas=[meta],
                    ids=[doc_id],
                )
                added += 1
                existing_set.add(summary.strip().lower())
            except Exception:
                pass

    for title, desc, status, priority, notes, created_at in goals_rows:
        content_parts = [f"Goal: {title}"]
        if desc and desc.strip():
            content_parts.append(desc.strip())
        content_parts.append(f"Status: {status}, Priority: {priority}")
        if notes and notes.strip():
            content_parts.append(f"Progress: {notes.strip()}")
        content = " | ".join(content_parts)
        if content and content.strip().lower() not in existing_set:
            try:
                doc_id = f"goal_{hashlib.md5(title.encode()).hexdigest()[:12]}_{created_at}"
                meta = {
                    "category": "goal",
                    "created_at": created_at,
                    "goal_status": status,
                    "goal_priority": priority,
                }
                embedding = _embed([content])[0]
                col.add(
                    documents=[content],
                    embeddings=[embedding],
                    metadatas=[meta],
                    ids=[doc_id],
                )
                added += 1
                existing_set.add(content.strip().lower())
            except Exception:
                pass

    if added:
        print(f"  Repopulated {added} entries from SQLite.")
    return added


# Short aliases kept for callers that use the older/simple memory API names.
add = add_to_vector_memory
search = search_vector_memory
delete = delete_from_vector_memory
build_semantic_context = build_semantic_context
get_embedding = _get_embedding


def _ensure_populated():
    global _repopulated, _repopulate_done
    if _repopulated:
        _repopulate_done.set()
        return
    try:
        _get_collection()
    except Exception as e:
        print(f"  Vector memory repopulation error: {e}")


def prewarm_minilm():
    """Eagerly load the local sentence-transformers model at startup (Phase 1.2)."""
    global _local_embedding_model
    try:
        from sentence_transformers import SentenceTransformer

        _disable_tqdm_mp_lock()
        _local_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        if not _embedding_mode_printed:
            print("  Local embeddings: all-MiniLM-L6-v2 (pre-warmed)")
    except Exception as e:
        print(f"  Failed to pre-warm MiniLM: {e}")


def get_local_embedding_model():
    """Return the shared all-MiniLM-L6-v2 embedder (loading it on first use)."""
    global _local_embedding_model
    if _local_embedding_model is None:
        from sentence_transformers import SentenceTransformer

        _disable_tqdm_mp_lock()
        _local_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _local_embedding_model


# Initialize in background so startup isn't blocked
def _init_background():
    try:
        _get_collection()
    except Exception as e:
        print(f"  Vector memory init error: {e}")


threading.Thread(target=_init_background, daemon=True).start()
