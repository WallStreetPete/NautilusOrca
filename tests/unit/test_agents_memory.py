"""Memory store + embedding helper tests (no API keys required)."""

from __future__ import annotations

from blackorca.agents.memory import InMemoryMemory, hash_embedding, make_lesson


def test_hash_embedding_deterministic() -> None:
    a = hash_embedding("nvda earnings surprise positive")
    b = hash_embedding("nvda earnings surprise positive")
    assert a == b


def test_hash_embedding_distinguishes_different_text() -> None:
    a = hash_embedding("nvda earnings surprise positive")
    c = hash_embedding("amd supply constraint negative")
    assert a != c


def test_memory_search_recovers_similar() -> None:
    mem = InMemoryMemory()
    mem.add(make_lesson("nvda earnings surprise positive", "sharpe 1.2"))
    mem.add(make_lesson("amd supply constraint negative", "sharpe 0.1"))
    mem.add(make_lesson("nvda h100 demand surging", "sharpe 1.0"))
    q = hash_embedding("nvda earnings surprise")
    results = mem.search(q, k=2)
    assert len(results) == 2
    # The top result should mention nvda earnings
    assert "nvda" in results[0].hypothesis.lower()


def test_memory_search_empty() -> None:
    mem = InMemoryMemory()
    assert mem.search([0.1, 0.2, 0.3]) == []
