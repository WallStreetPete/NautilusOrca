"""pgvector-backed memory of past experiments.

The store has two implementations:

- :class:`PgVectorMemory` — Postgres + pgvector for production
- :class:`InMemoryMemory` — Python dict + numpy cosine for tests & offline

Both implement :class:`MemoryStore`. :func:`make_memory_store` picks one based
on whether ``DATABASE_URL`` is reachable; the agent code never branches on the
backend.
"""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import numpy as np

from blackorca.config import get_settings
from blackorca.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class Lesson:
    id: str
    hypothesis: str
    result_summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class MemoryStore(ABC):
    @abstractmethod
    def add(self, lesson: Lesson) -> None: ...

    @abstractmethod
    def search(self, query_embedding: list[float], k: int = 5) -> list[Lesson]: ...

    @abstractmethod
    def all(self) -> list[Lesson]: ...


# ---------------------------------------------------------------------------
# In-memory fallback (also used for tests)
# ---------------------------------------------------------------------------


class InMemoryMemory(MemoryStore):
    def __init__(self) -> None:
        self._lessons: list[Lesson] = []

    def add(self, lesson: Lesson) -> None:
        self._lessons.append(lesson)

    def search(self, query_embedding: list[float], k: int = 5) -> list[Lesson]:
        if not self._lessons or not query_embedding:
            return list(self._lessons[:k])
        q = np.asarray(query_embedding, dtype=np.float32)
        scored: list[tuple[float, Lesson]] = []
        for lsn in self._lessons:
            if not lsn.embedding:
                continue
            v = np.asarray(lsn.embedding, dtype=np.float32)
            denom = (np.linalg.norm(q) * np.linalg.norm(v)) or 1.0
            scored.append((float(np.dot(q, v) / denom), lsn))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [lsn for _, lsn in scored[:k]]

    def all(self) -> list[Lesson]:
        return list(self._lessons)


# ---------------------------------------------------------------------------
# pgvector
# ---------------------------------------------------------------------------


class PgVectorMemory(MemoryStore):
    def __init__(self, dsn: str, dim: int = 1024) -> None:
        try:
            import psycopg
        except ImportError as e:
            raise RuntimeError(
                "psycopg not installed; `uv sync --extra pgvector`"
            ) from e
        self._psycopg = psycopg
        self.dsn = dsn
        self.dim = dim
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(
                f"""
                    CREATE TABLE IF NOT EXISTS agent_lessons (
                        id          TEXT PRIMARY KEY,
                        hypothesis  TEXT NOT NULL,
                        result      TEXT NOT NULL,
                        metadata    JSONB,
                        embedding   VECTOR({self.dim}),
                        created_at  TIMESTAMPTZ DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS agent_lessons_embed_idx
                        ON agent_lessons USING ivfflat (embedding vector_cosine_ops);
                    """
            )
            conn.commit()

    def add(self, lesson: Lesson) -> None:
        with self._psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agent_lessons (id, hypothesis, result, metadata, embedding) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (
                    lesson.id,
                    lesson.hypothesis,
                    lesson.result_summary,
                    json.dumps(lesson.metadata),
                    lesson.embedding,
                ),
            )
            conn.commit()

    def search(self, query_embedding: list[float], k: int = 5) -> list[Lesson]:
        with self._psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, hypothesis, result, metadata, embedding, created_at "
                "FROM agent_lessons ORDER BY embedding <=> %s::vector LIMIT %s",
                (query_embedding, k),
            )
            rows = cur.fetchall()
        return [
            Lesson(
                id=r[0],
                hypothesis=r[1],
                result_summary=r[2],
                metadata=r[3] or {},
                embedding=r[4],
                created_at=r[5],
            )
            for r in rows
        ]

    def all(self) -> list[Lesson]:
        with self._psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT id, hypothesis, result, metadata, embedding, created_at FROM agent_lessons"
            )
            rows = cur.fetchall()
        return [
            Lesson(
                id=r[0],
                hypothesis=r[1],
                result_summary=r[2],
                metadata=r[3] or {},
                embedding=r[4],
                created_at=r[5],
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_memory_store() -> MemoryStore:
    """Try pgvector; fall back to in-memory."""
    try:
        return PgVectorMemory(get_settings().database_url)
    except Exception as e:
        log.info("memory.fallback_in_memory", error=str(e))
        return InMemoryMemory()


def hash_embedding(text: str, dim: int = 1024) -> list[float]:
    """Deterministic, model-free embedding for tests & offline runs.

    Uses character-trigram hashing into ``dim`` buckets, then L2-normalizes.
    Not semantically meaningful, but stable.
    """
    vec = np.zeros(dim, dtype=np.float32)
    text = text.lower()
    for i in range(max(len(text) - 2, 0)):
        tri = text[i : i + 3]
        h = hash(tri) % dim
        vec[h] += 1.0
    norm = math.sqrt(float((vec * vec).sum())) or 1.0
    vec /= norm
    return vec.tolist()


def make_lesson(hypothesis: str, result_summary: str, **metadata: Any) -> Lesson:
    return Lesson(
        id=str(uuid4()),
        hypothesis=hypothesis,
        result_summary=result_summary,
        metadata=metadata,
        embedding=hash_embedding(hypothesis + " | " + result_summary),
    )


__all__ = [
    "InMemoryMemory",
    "Lesson",
    "MemoryStore",
    "PgVectorMemory",
    "hash_embedding",
    "make_lesson",
    "make_memory_store",
]
