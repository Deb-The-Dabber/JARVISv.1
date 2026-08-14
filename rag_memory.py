import datetime
import math
import os
import re
import threading
from collections import Counter

from dotenv import load_dotenv

from vector_memory import JarvisEmbeddingFunction

load_dotenv()

RAG_DB_PATH = os.path.join(os.path.expanduser("~"), "jarvis_rag_db")
DEFAULT_COLLECTION = "rag_docs"
DEFAULT_FOLDER = os.path.expanduser(os.getenv("RAG_FOLDER", "~/Documents"))
SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".py", ".js", ".html", ".csv", ".json"}

_client = None
_collections = {}
_embedding_function = JarvisEmbeddingFunction()
_watchers = {}
_lock = threading.Lock()

# In-memory BM25 index
_bm25_index = {}
_bm25_docs = []
_bm25_avgdl = 0
_bm25_k1 = 1.5
_bm25_b = 0.75
_bm25_dirty = True

# Cross-encoder re-ranker (lazy-loaded)
_reranker = None
_reranker_lock = threading.Lock()


# ─────────────────────────────────────────────
# TOKENIZATION
# ─────────────────────────────────────────────
def _tokenize(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


# ─────────────────────────────────────────────
# BM25
# ─────────────────────────────────────────────
def _build_bm25_from_data(docs: list[tuple[str, dict]]):
    global _bm25_index, _bm25_docs, _bm25_avgdl, _bm25_dirty
    if not docs:
        _bm25_index = {}
        _bm25_docs = []
        _bm25_avgdl = 0
        return
    _bm25_docs = docs
    total_terms = 0
    df = Counter()
    doc_term_counts = []
    for doc_text, _ in _bm25_docs:
        tokens = _tokenize(doc_text)
        unique = set(tokens)
        for t in unique:
            df[t] += 1
        doc_term_counts.append(Counter(tokens))
        total_terms += len(tokens)
    n_docs = len(_bm25_docs)
    _bm25_avgdl = total_terms / max(n_docs, 1)
    _bm25_index = {
        "df": dict(df),
        "doc_term_counts": doc_term_counts,
        "n_docs": n_docs,
    }
    _bm25_dirty = False


def _rebuild_bm25_from_collection():
    try:
        collection = _get_collection()
        data = collection.get(include=["documents", "metadatas"])
        docs = data.get("documents", []) or []
        metas = data.get("metadatas", []) or []
    except Exception:
        _build_bm25_from_data([])
        return
    _build_bm25_from_data(list(zip(docs, metas)))


def _ensure_bm25():
    if _bm25_dirty:
        _rebuild_bm25_from_collection()


def _bm25_score(query_terms: list[str], doc_idx: int) -> float:
    doc_len = sum(_bm25_index["doc_term_counts"][doc_idx].values())
    n = _bm25_index["n_docs"]
    df = _bm25_index["df"]
    doc_tc = _bm25_index["doc_term_counts"][doc_idx]
    score = 0.0
    for term in query_terms:
        if term in doc_tc:
            tf = doc_tc[term]
            idf = math.log((n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5) + 1)
            score += idf * (tf * (_bm25_k1 + 1)) / (tf + _bm25_k1 * (1 - _bm25_b + _bm25_b * doc_len / _bm25_avgdl))
    return score


def _bm25_search(query: str, n: int = 20) -> list[dict]:
    _ensure_bm25()
    if not _bm25_index:
        return []
    query_terms = _tokenize(query)
    if not query_terms:
        return []
    scored = []
    for i in range(_bm25_index["n_docs"]):
        score = _bm25_score(query_terms, i)
        if score > 0:
            doc_text, meta = _bm25_docs[i]
            scored.append(
                {
                    "text": doc_text,
                    "metadata": meta,
                    "score": score,
                    "index": i,
                }
            )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:n]


# ─────────────────────────────────────────────
# VECTOR SEARCH
# ─────────────────────────────────────────────
def _vector_search(query: str, n: int = 20) -> list[dict]:
    try:
        collection = _get_collection()
        if collection.count() == 0:
            return []
        results = collection.query(
            query_embeddings=[_embedding_function([query])[0]],
            n_results=min(n, collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        items = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            items.append(
                {
                    "text": doc,
                    "metadata": meta,
                    "score": 1 - dist,
                }
            )
        return items
    except Exception:
        return []


# ─────────────────────────────────────────────
# HYBRID SEARCH (RRF)
# ─────────────────────────────────────────────
def _rrf_fusion(vector_results: list[dict], bm25_results: list[dict], k: int = 60) -> list[dict]:
    ranks = {}
    for rank, item in enumerate(vector_results):
        text = item["text"]
        ranks[text] = ranks.get(text, 0) + 1 / (k + rank + 1)
    for rank, item in enumerate(bm25_results):
        text = item["text"]
        ranks[text] = ranks.get(text, 0) + 1 / (k + rank + 1)
    merged = []
    seen = set()
    for item in vector_results + bm25_results:
        text = item["text"]
        if text not in seen:
            seen.add(text)
            merged.append(
                {
                    "text": text,
                    "metadata": item["metadata"],
                    "score": ranks.get(text, 0),
                }
            )
    merged.sort(key=lambda x: x["score"], reverse=True)
    return merged


# ─────────────────────────────────────────────
# RE-RANKER
# ─────────────────────────────────────────────
def _get_reranker():
    global _reranker
    if _reranker is None:
        with _reranker_lock:
            if _reranker is None:
                try:
                    from sentence_transformers import CrossEncoder

                    model = os.getenv("JARVIS_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
                    _reranker = CrossEncoder(model, automodel_args={"torch_dtype": "float16"})
                    print(f"  Reranker loaded: {model}")
                except Exception as e:
                    print(f"  Reranker unavailable: {e}")
                    _reranker = False
    return _reranker if _reranker is not False else None


def _rerank(query: str, results: list[dict], top_n: int = 5) -> list[dict]:
    reranker = _get_reranker()
    if not reranker or not results:
        return results[:top_n]
    pairs = [(query, r["text"]) for r in results]
    try:
        scores = reranker.predict(pairs, show_progress_bar=False)
        for i, score in enumerate(scores):
            results[i]["rerank_score"] = float(score)
        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    except Exception:
        pass
    return results[:top_n]


# ─────────────────────────────────────────────
# CITATION FORMATTING
# ─────────────────────────────────────────────
def _format_citations(results: list[dict]) -> tuple[str, list[dict]]:
    citations = []
    seen_sources = {}
    for r in results:
        meta = r.get("metadata") or {}
        source = meta.get("file_name", "unknown")
        if source not in seen_sources:
            seen_sources[source] = len(seen_sources) + 1
        idx = seen_sources[source]
        citations.append({"source": source, "index": idx, "text": r["text"][:300]})

    lines = []
    for r in results:
        meta = r.get("metadata") or {}
        source = meta.get("file_name", "unknown")
        idx = seen_sources[source]
        score = round(r.get("rerank_score", r.get("score", 0)), 3)
        lines.append(f"[{idx}] ({source}, score={score}): {r['text'][:900]}")

    return "\n\n".join(lines), citations


# ─────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────
def _get_collection(collection_name: str = DEFAULT_COLLECTION):
    global _client, _bm25_dirty
    with _lock:
        if collection_name in _collections:
            return _collections[collection_name]
        import chromadb

        os.makedirs(RAG_DB_PATH, exist_ok=True)
        if _client is None:
            _client = chromadb.PersistentClient(path=RAG_DB_PATH)
        try:
            collection = _client.get_collection(name=collection_name)
        except Exception:
            collection = None
        if collection is not None:
            try:
                peek = collection.peek(limit=1, include=["embeddings"])
                stored = peek.get("embeddings") or []
                if stored:
                    expected_dim = len(_embedding_function(["dimension check"])[0])
                    if len(stored[0]) != expected_dim:
                        print(
                            f"  RAG collection dimension mismatch "
                            f"({len(stored[0])} -> {expected_dim}), migration deferred."
                        )
                        print("  Re-embed rag_docs explicitly before switching embedding modes.")
            except Exception:
                pass
        if collection is None:
            collection = _client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        _collections[collection_name] = collection
        return collection


def _read_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            pass
        try:
            from tools.vision_tools import ocr_document

            return ocr_document(path)
        except Exception:
            return ""
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"):
        try:
            from tools.vision_tools import ocr_document

            return ocr_document(path)
        except Exception:
            return ""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _chunk_text(text: str, chunk_words: int = 500, overlap_words: int = 50):
    words = text.split()
    if not words:
        return []
    chunks = []
    step = max(1, chunk_words - overlap_words)
    for start in range(0, len(words), step):
        chunk = " ".join(words[start : start + chunk_words]).strip()
        if chunk:
            chunks.append(chunk)
        if start + chunk_words >= len(words):
            break
    return chunks


def _file_is_indexed(collection, file_path: str, modified_date: str) -> bool:
    try:
        result = collection.get(
            where={"$and": [{"file_path": file_path}, {"modified_date": modified_date}]},
            limit=1,
        )
        return bool(result.get("ids"))
    except Exception:
        return False


def index_folder(folder_path: str, collection_name: str = DEFAULT_COLLECTION):
    folder = os.path.expanduser(folder_path)
    collection = _get_collection(collection_name)
    indexed_files = 0
    indexed_chunks = 0

    for root, _, files in os.walk(folder):
        if ".git" in root.split(os.sep):
            continue
        for file_name in files:
            ext = os.path.splitext(file_name)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            file_path = os.path.join(root, file_name)
            try:
                modified_date = datetime.datetime.fromtimestamp(os.path.getmtime(file_path)).isoformat()
            except Exception:
                continue

            if _file_is_indexed(collection, file_path, modified_date):
                continue

            text = _read_file(file_path)
            chunks = _chunk_text(text)
            if not chunks:
                continue

            ids = []
            metadatas = []
            for i, _ in enumerate(chunks):
                ids.append(f"{file_path}:{modified_date}:{i}")
                metadatas.append(
                    {
                        "file_path": file_path,
                        "file_name": file_name,
                        "modified_date": modified_date,
                        "chunk_index": i,
                    }
                )

            embeddings = _embedding_function(chunks)
            collection.add(
                documents=chunks,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids,
            )
            indexed_files += 1
            indexed_chunks += len(chunks)

    if indexed_files:
        global _bm25_dirty
        _bm25_dirty = True
        _rebuild_bm25_from_collection()
    return indexed_files, indexed_chunks


def search_rag(query: str, n_results: int = 5) -> str:
    try:
        collection = _get_collection(DEFAULT_COLLECTION)
        if collection.count() == 0:
            return (
                "No documents indexed. RAG_FOLDER is "
                f"'{DEFAULT_FOLDER}'. Add files there or run '/ingest <path>' to index."
            )

        vector_results = _vector_search(query, n=n_results * 4)
        bm25_results = _bm25_search(query, n=n_results * 4)
        fused = _rrf_fusion(vector_results, bm25_results)
        reranked = _rerank(query, fused, top_n=n_results)

        if not reranked:
            return "No relevant document chunks found."

        formatted, citations = _format_citations(reranked)
        return formatted
    except Exception as e:
        return f"RAG search failed: {e}"


def search_rag_structured(query: str, n_results: int = 5) -> dict:
    try:
        collection = _get_collection(DEFAULT_COLLECTION)
        if collection.count() == 0:
            return {"results": [], "total": 0}

        vector_results = _vector_search(query, n=n_results * 4)
        bm25_results = _bm25_search(query, n=n_results * 4)
        fused = _rrf_fusion(vector_results, bm25_results)
        reranked = _rerank(query, fused, top_n=n_results)

        return {
            "results": [
                {
                    "text": r["text"][:500],
                    "source": r["metadata"].get("file_name", "unknown"),
                    "file_path": r["metadata"].get("file_path", ""),
                    "score": round(r.get("rerank_score", r.get("score", 0)), 3),
                }
                for r in reranked
            ],
            "total": len(reranked),
        }
    except Exception as e:
        return {"error": str(e), "results": []}


def prune_stale_entries(days: int = 90):
    collection = _get_collection(DEFAULT_COLLECTION)
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).isoformat()
    try:
        data = collection.get(include=["metadatas"])
        ids_to_delete = []
        for doc_id, meta in zip(data.get("ids", []), data.get("metadatas", [])):
            if meta and meta.get("modified_date", "") < cutoff:
                ids_to_delete.append(doc_id)
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
            _rebuild_bm25_from_collection()
        return len(ids_to_delete)
    except Exception:
        return 0


def watch_folder(folder_path: str):
    folder = os.path.expanduser(folder_path)
    if folder in _watchers:
        return

    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    class RagHandler(FileSystemEventHandler):
        def on_created(self, event):
            if not event.is_directory:
                threading.Thread(target=index_folder, args=(folder,), daemon=True).start()

        def on_modified(self, event):
            if not event.is_directory:
                threading.Thread(target=index_folder, args=(folder,), daemon=True).start()

    observer = Observer()
    observer.schedule(RagHandler(), folder, recursive=True)
    observer.daemon = True
    observer.start()
    _watchers[folder] = observer


def _set_bm25_test_data(docs: list[tuple[str, dict]]):
    """Directly populate BM25 index (testing only)."""
    _build_bm25_from_data(docs)


def get_rag_stats() -> dict:
    try:
        collection = _get_collection(DEFAULT_COLLECTION)
        data = collection.get(include=["metadatas"])
        files = {meta.get("file_path") for meta in data.get("metadatas", []) if meta and meta.get("file_path")}
        return {
            "total_files": len(files),
            "total_chunks": collection.count(),
            "collection_name": DEFAULT_COLLECTION,
            "folder_path": DEFAULT_FOLDER,
            "bm25_ready": not _bm25_dirty,
        }
    except Exception as e:
        return {
            "total_files": 0,
            "total_chunks": 0,
            "collection_name": DEFAULT_COLLECTION,
            "folder_path": DEFAULT_FOLDER,
            "error": str(e),
        }
