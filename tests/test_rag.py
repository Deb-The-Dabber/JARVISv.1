import os
import shutil
import tempfile
from pathlib import Path

import pytest
from dotenv import dotenv_values

# The rag tests read/write the REAL ~/jarvis_rag_db, which is a Nemo 2048-dim
# index. conftest pins local for offline determinism, so re-source the repo
# .env's embedding mode here — BEFORE rag_memory (and its embedder) is
# imported — so the embedder matches the live collection. No .env (CI) keeps
# the local fallback. dotenv_values leaves os.environ untouched, so the other
# conftest freezes stay intact.
_env_file = Path(__file__).resolve().parents[1] / ".env"
_env = dotenv_values(_env_file) if _env_file.exists() else {}
os.environ["JARVIS_EMBEDDING"] = _env.get("JARVIS_EMBEDDING") or os.getenv("JARVIS_EMBEDDING") or "local"

from rag_memory import (  # noqa: E402
    _bm25_search,
    _chunk_text,
    _format_citations,
    _read_file,
    _rerank,
    _rrf_fusion,
    _tokenize,
    _vector_search,
    index_folder,
    search_rag_structured,
)


class TestTokenization:
    def test_simple(self):
        assert _tokenize("Hello World") == ["hello", "world"]

    def test_lowercase(self):
        assert _tokenize("HELLO") == ["hello"]

    def test_punctuation(self):
        assert _tokenize("don't stop") == ["don", "t", "stop"]

    def test_empty(self):
        assert _tokenize("") == []


class TestChunking:
    def test_small_text(self):
        chunks = _chunk_text("hello world", chunk_words=500)
        assert len(chunks) == 1
        assert chunks[0] == "hello world"

    def test_overlap(self):
        text = " ".join(f"word{i}" for i in range(20))
        chunks = _chunk_text(text, chunk_words=10, overlap_words=3)
        assert len(chunks) >= 2

    def test_empty(self):
        assert _chunk_text("") == []


class TestReadFile:
    def test_txt(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("hello world")
            path = f.name
        try:
            content = _read_file(path)
            assert content == "hello world"
        finally:
            os.unlink(path)

    def test_md(self):
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w", delete=False) as f:
            f.write("# Title\ncontent")
            path = f.name
        try:
            content = _read_file(path)
            assert "# Title\ncontent" in content
        finally:
            os.unlink(path)

    def test_nonexistent(self):
        assert _read_file("/nonexistent/file.txt") == ""


class TestBM25:
    @pytest.fixture(autouse=True)
    def setup_bm25(self):
        from rag_memory import _set_bm25_test_data

        _set_bm25_test_data(
            [
                ("the cat sat on the mat", {"file_name": "doc1.txt"}),
                ("the dog played in the yard", {"file_name": "doc2.txt"}),
                ("cats and dogs are pets", {"file_name": "doc3.txt"}),
            ]
        )
        yield

    def test_bm25_search(self):
        results = _bm25_search("cat", n=5)
        assert len(results) >= 1
        assert "cat" in results[0]["text"]

    def test_bm25_relevance(self):
        cat_results = _bm25_search("cat mat", n=5)
        dog_results = _bm25_search("dog yard", n=5)
        assert cat_results[0]["score"] > 0
        assert dog_results[0]["score"] > 0

    def test_bm25_no_match(self):
        results = _bm25_search("xyznonexistent_12345", n=5)
        assert len(results) == 0

    def test_bm25_empty_query(self):
        results = _bm25_search("", n=5)
        assert results == []


class TestVectorSearch:
    def test_vector_returns_list(self):
        results = _vector_search("test", n=5)
        assert isinstance(results, list)


class TestRRFFusion:
    def test_fusion(self):
        vec = [
            {"text": "A", "metadata": {}, "score": 0.9},
            {"text": "B", "metadata": {}, "score": 0.8},
        ]
        bm = [
            {"text": "B", "metadata": {}, "score": 10},
            {"text": "C", "metadata": {}, "score": 5},
        ]
        fused = _rrf_fusion(vec, bm)
        assert len(fused) == 3
        texts = {r["text"] for r in fused}
        assert texts == {"A", "B", "C"}

    def test_dedup(self):
        vec = [{"text": "same", "metadata": {}, "score": 0.5}]
        bm = [{"text": "same", "metadata": {}, "score": 10}]
        fused = _rrf_fusion(vec, bm)
        assert len(fused) == 1
        assert fused[0]["text"] == "same"


class TestRerank:
    def test_rerank_no_reranker(self):
        results = [{"text": "test", "metadata": {}, "score": 0.5}]
        reranked = _rerank("query", results, top_n=5)
        assert len(reranked) == 1
        assert reranked[0]["text"] == "test"

    def test_rerank_returns_top_n(self):
        results = [{"text": f"doc{i}", "metadata": {}, "score": 0.5} for i in range(20)]
        reranked = _rerank("test", results, top_n=3)
        assert len(reranked) <= 3


class TestCitations:
    def test_format_citations(self):
        results = [
            {"text": "content A", "metadata": {"file_name": "a.txt"}, "score": 0.9},
            {"text": "content B", "metadata": {"file_name": "b.txt"}, "score": 0.8},
        ]
        formatted, citations = _format_citations(results)
        assert "[1]" in formatted
        assert "[2]" in formatted
        assert len(citations) == 2
        assert citations[0]["source"] == "a.txt"
        assert citations[1]["source"] == "b.txt"

    def test_same_source_dedup(self):
        results = [
            {"text": "content A1", "metadata": {"file_name": "a.txt"}, "score": 0.9},
            {"text": "content A2", "metadata": {"file_name": "a.txt"}, "score": 0.7},
        ]
        formatted, citations = _format_citations(results)
        assert formatted.count("[1]") == 2
        assert len(citations) == 2
        assert citations[0]["source"] == "a.txt"
        assert citations[1]["source"] == "a.txt"
        assert citations[0]["index"] == 1
        assert citations[1]["index"] == 1


class TestIndexFolder:
    @pytest.fixture
    def temp_docs(self):
        tmp = tempfile.mkdtemp()
        for i, content in enumerate(
            [
                "The cat sat on the mat",
                "Dogs love to play fetch",
                "Python is a programming language",
            ]
        ):
            with open(os.path.join(tmp, f"doc{i}.txt"), "w") as f:
                f.write(content)
        yield tmp
        shutil.rmtree(tmp, ignore_errors=True)

    def test_index_and_search(self, temp_docs):
        files, chunks = index_folder(temp_docs)
        assert files >= 3
        assert chunks >= 3

        results = search_rag_structured("cat", n_results=3)
        assert results["total"] >= 1

    def test_reindex_skips(self, temp_docs):
        files1, _ = index_folder(temp_docs)
        files2, _ = index_folder(temp_docs)
        assert files2 == 0  # all already indexed


class TestRagStats:
    def test_stats_structure(self):
        from rag_memory import get_rag_stats

        stats = get_rag_stats()
        assert "total_files" in stats
        assert "total_chunks" in stats
        assert "collection_name" in stats
