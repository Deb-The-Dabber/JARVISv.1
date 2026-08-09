import datetime
import hashlib
import os
import shutil
import threading

from dotenv import load_dotenv

load_dotenv()

VECTOR_DB_PATH = os.path.join(os.path.expanduser("~"), "jarvis_vector_db")

_client = None
_collection = None
_embedding_function = None
_lock = threading.RLock()
_embedding_mode_printed = False
_local_embedding_model = None
_embedding_failed = False
_repopulated = False
_repopulate_done = threading.Event()


def _get_embedding(text: str) -> list:
    """Get embedding using local all-MiniLM-L6-v2 (Phase 2.2: MiniLM-only)."""
    global _embedding_mode_printed, _local_embedding_model, _embedding_failed

    if _embedding_failed:
        raise RuntimeError("Embedding service unavailable")

    try:
        if _local_embedding_model is None:
            from sentence_transformers import SentenceTransformer

            _local_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        if not _embedding_mode_printed:
            print("  Embeddings: all-MiniLM-L6-v2 (384-dim)")
            _embedding_mode_printed = True
        return _local_embedding_model.encode(text).tolist()
    except Exception as e:
        _embedding_failed = True
        raise RuntimeError(f"Embedding service unavailable: {e}")


class JarvisEmbeddingFunction:
    def __init__(self):
        pass

    def name(self):
        return "jarvis_embedding"

    def __call__(self, input):
        """Embed a list of texts using the new embedding service."""
        texts = list(input)
        embeddings = []
        for text in texts:
            try:
                embedding = _get_embedding(text)
                embeddings.append(embedding)
            except Exception:
                raise
        return embeddings


COLLECTION_NAME = "jarvis_mini"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


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
        for item in old_data:
            try:
                doc = item["document"]
                meta = item["metadata"]
                doc_id = item["id"]
                new_col.add(
                    documents=[doc],
                    metadatas=[meta],
                    ids=[doc_id],
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

        for attempt in range(2):
            try:
                _collection = _client.get_or_create_collection(
                    name=COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine", "embedding_model": expected_model},
                    embedding_function=_embedding_function,
                )
                actual_model = _collection.metadata.get("embedding_model", "") if _collection.metadata else ""
                if actual_model and actual_model != expected_model:
                    print(f"  Embedding model changed ({actual_model} -> {expected_model}). Migrating...")
                    _collection = _reset_collection()
                break
            except Exception as e:
                if _should_reset_collection(e):
                    print("  Vector memory DB corrupted, dropping and recreating.")
                    _collection = _drop_and_reopen()
                else:
                    if attempt == 0 and "no such table" in str(e).lower():
                        print("  Vector memory DB has missing tables, dropping and recreating.")
                        _drop_and_reopen()
                        continue
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
    attempt_reset = False
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
        if not attempt_reset and _should_reset_collection(e):
            attempt_reset = True
            print("  Vector memory embedding dimension mismatch detected during add, recreating collection.")
            _reset_collection()
            return add_to_vector_memory(content, category=category, metadata=metadata)
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
            print("  Vector memory embedding dimension mismatch detected during search, recreating collection.")
            _reset_collection()
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

        _local_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _local_embedding_model


# Initialize in background so startup isn't blocked
def _init_background():
    try:
        _get_collection()
    except Exception as e:
        print(f"  Vector memory init error: {e}")


threading.Thread(target=_init_background, daemon=True).start()
