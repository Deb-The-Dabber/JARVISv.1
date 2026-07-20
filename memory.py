import datetime
import os
import sqlite3

from config import MAX_EXPLICIT_MEMORIES, MAX_SEMANTIC_MEMORIES

DB_PATH = os.path.join(os.path.expanduser("~"), "jarvis_memory.db")

def _connect():
    return sqlite3.connect(DB_PATH)

def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

def save_memory(content: str, type: str = "fact"):
    """Save to both SQLite and vector memory."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO memories (type, content, created_at) VALUES (?, ?, ?)",
            (type, content, datetime.datetime.now().isoformat())
        )
        conn.commit()
    # Also add to vector memory
    try:
        from vector_memory import add_to_vector_memory
        add_to_vector_memory(content, category=type)
    except Exception as e:
        print(f"  Vector memory save error: {e}")

def get_all_memories():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT type, content, created_at FROM memories "
            "ORDER BY created_at DESC"
        ).fetchall()
    return rows

def forget_memory(keyword: str):
    """Delete from both SQLite and vector memory."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM memories WHERE content LIKE ?",
            (f"%{keyword}%",)
        )
        conn.commit()
    try:
        from vector_memory import delete_from_vector_memory
        delete_from_vector_memory(keyword)
    except Exception:
        pass

def prune_old_memories(days: int = 30):
    """Delete memories older than `days` from both SQLite and vector memory."""
    cutoff = (
        datetime.datetime.now() - datetime.timedelta(days=days)
    ).isoformat()
    with _connect() as conn:
        deleted = conn.execute(
            "DELETE FROM memories WHERE created_at < ?", (cutoff,)
        ).rowcount
        conn.commit()
    try:
        from vector_memory import prune_vector_memory
        prune_vector_memory(days=days)
    except Exception:
        pass
    if deleted:
        print(f"  Pruned {deleted} memories older than {days} days.")
    return deleted


def save_summary(summary: str):
    """Save conversation summary to both stores."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO summaries (summary, created_at) VALUES (?, ?)",
            (summary, datetime.datetime.now().isoformat())
        )
        conn.commit()
    try:
        from vector_memory import add_to_vector_memory
        add_to_vector_memory(summary, category="conversation_summary")
    except Exception:
        pass

def get_recent_summaries(limit: int = 5):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT summary, created_at FROM summaries "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return rows

def semantic_search(query: str) -> str:
    """Search memories by meaning using vector memory."""
    try:
        from vector_memory import search_vector_memory
        results = search_vector_memory(query, n_results=5)
        if not results:
            return ""
        parts = []
        for content, category, created_at, score in results:
            date = created_at[:10] if created_at else ""
            parts.append(f"[{date}] {content}")
        return "\n".join(parts)
    except Exception:
        return ""

def build_memory_block() -> str:
    """Build memory block for system prompt — SQLite facts."""
    memories = get_all_memories()
    summaries = get_recent_summaries(MAX_SEMANTIC_MEMORIES)
    block = ""
    if memories:
        block += "\nExplicit memories:\n"
        for mtype, content, created_at in memories[:MAX_EXPLICIT_MEMORIES]:
            date = created_at[:10]
            block += f"  - [{date}] {content}\n"
    if summaries:
        block += "\nRecent conversation summaries:\n"
        for summary, created_at in summaries:
            date = created_at[:10]
            block += f"  - [{date}] {summary}\n"
    return block if block else "\n(No memories yet.)"


def build_semantic_memory_block(query: str) -> str:
    """Build semantically relevant memory block for a specific query, token-capped."""
    try:
        from vector_memory import build_semantic_context
        result = build_semantic_context(query)
        if not result:
            return ""
        if len(result) > 4000:
            result = result[:4000] + "..."
        return result
    except Exception:
        return ""

init_db()
