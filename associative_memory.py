import datetime
import itertools
import os
import re
import sqlite3

DB_PATH = os.path.join(os.path.expanduser("~"), "jarvis_associations.db")

STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "could",
    "from",
    "have",
    "here",
    "into",
    "just",
    "like",
    "more",
    "need",
    "please",
    "should",
    "that",
    "the",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "your",
    "you",
    "jarvis",
    "user",
    "assistant",
    "there",
}


def _connect():
    return sqlite3.connect(DB_PATH)


def _init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_pairs (
                concept1 TEXT NOT NULL,
                concept2 TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                last_seen TEXT NOT NULL,
                PRIMARY KEY (concept1, concept2)
            )
        """)
        conn.commit()


def _extract_concepts(text: str) -> list:
    words = re.findall(r"\b[A-Za-z][A-Za-z0-9]{2,}\b", text)
    concepts = []
    seen = set()
    for word in words:
        concept = word.lower()
        if concept in STOPWORDS:
            continue
        if concept not in seen:
            seen.add(concept)
            concepts.append(concept)
    return concepts[:10]


def record_concepts(text: str):
    concepts = sorted(_extract_concepts(text))
    if len(concepts) < 2:
        return
    now = datetime.datetime.now().isoformat()
    with _connect() as conn:
        for concept1, concept2 in itertools.combinations(concepts, 2):
            conn.execute(
                """
                INSERT INTO concept_pairs (concept1, concept2, count, last_seen)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(concept1, concept2) DO UPDATE SET
                    count = count + 1,
                    last_seen = excluded.last_seen
            """,
                (concept1, concept2, now),
            )
        conn.commit()


def get_related_concepts(concept: str, limit: int = 5) -> list:
    c = concept.lower()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT CASE WHEN concept1 = ? THEN concept2 ELSE concept1 END AS related,
                   count
            FROM concept_pairs
            WHERE concept1 = ? OR concept2 = ?
            ORDER BY count DESC, last_seen DESC
            LIMIT ?
        """,
            (c, c, c, limit),
        ).fetchall()
    return rows


def build_association_context(text: str) -> str:
    lines = []
    for concept in _extract_concepts(text)[:5]:
        related = [r for r, count in get_related_concepts(concept) if count > 3]
        if related:
            lines.append(f"When you mention {concept}, you often discuss: {', '.join(related)}")
    return "\n".join(lines)


def get_association_stats() -> dict:
    with _connect() as conn:
        pairs = conn.execute("SELECT COUNT(*) FROM concept_pairs").fetchone()[0]
        concepts = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT concept1 AS concept FROM concept_pairs
                UNION
                SELECT concept2 AS concept FROM concept_pairs
            )
        """).fetchone()[0]
    return {"total_concepts": concepts, "total_pairs": pairs}


_init_db()
