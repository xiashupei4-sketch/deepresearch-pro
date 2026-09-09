"""Unit tests — vector store index consistency (regression: upsert of existing ids)."""

import asyncio

import pytest

from app.rag.vectorstore import InMemoryVectorStore, VectorRecord


def _rec(id: str, seed: float) -> VectorRecord:
    return VectorRecord(id=id, vector=[seed, 1.0 - seed, 0.5], text=f"text-{id}",
                        metadata={"document_id": "d1"})


def test_upsert_new_and_search():
    store = InMemoryVectorStore()
    asyncio.run(store.upsert([_rec("a", 0.9), _rec("b", 0.1), _rec("c", 0.5)]))
    hits = asyncio.run(store.search([0.9, 0.1, 0.5], top_k=2))
    assert len(hits) == 2
    assert hits[0].id == "a"
    assert all(0.0 <= h.score <= 1.0 + 1e-6 for h in hits)
    assert hits[0].text == "text-a"


def test_upsert_existing_id_updates_in_place():
    """Regression: re-upserting an existing id must NOT shift list indices
    (previously caused IndexError in search)."""
    store = InMemoryVectorStore()
    asyncio.run(store.upsert([_rec("a", 0.9), _rec("b", 0.1)]))
    asyncio.run(store.upsert([_rec("a", 0.0)]))  # update in place + new vector dim check

    assert len(store._ids) == 2
    assert len(store._texts) == len(store._ids)
    assert len(store._metas) == len(store._ids)
    assert store._vectors is not None
    assert store._vectors.shape[0] == len(store._ids)
    assert store._index["a"] == store._ids.index("a")

    hits = asyncio.run(store.search([0.0, 1.0, 0.5], top_k=3))
    assert {h.id for h in hits} == {"a", "b"}
    assert hits[0].id == "a"
    assert hits[0].text == "text-a"


def test_delete_rebuilds_index():
    store = InMemoryVectorStore()
    asyncio.run(store.upsert([_rec("a", 0.9), _rec("b", 0.1), _rec("c", 0.5)]))
    asyncio.run(store.delete(["b"]))

    assert store._ids == ["a", "c"]
    assert store._index == {"a": 0, "c": 1}
    assert store._vectors is not None and store._vectors.shape[0] == 2
    # search must not raise and must not return deleted docs
    hits = asyncio.run(store.search([0.5, 0.5, 0.5], top_k=5))
    assert {h.id for h in hits} == {"a", "c"}


def test_delete_all_then_search_returns_empty():
    store = InMemoryVectorStore()
    asyncio.run(store.upsert([_rec("a", 0.9)]))
    asyncio.run(store.delete(["a"]))
    assert asyncio.run(store.search([0.5, 0.5, 0.5])) == []
    assert asyncio.run(store.count()) == 0


def test_search_with_meta_filter():
    store = InMemoryVectorStore()
    r1 = VectorRecord(id="a", vector=[0.9, 0.1, 0.5], text="ta",
                      metadata={"document_id": "d1"})
    r2 = VectorRecord(id="b", vector=[0.9, 0.1, 0.5], text="tb",
                      metadata={"document_id": "d2"})
    asyncio.run(store.upsert([r1, r2]))
    hits = asyncio.run(store.search([0.9, 0.1, 0.5], top_k=5,
                                    filter_meta={"document_id": "d2"}))
    assert [h.id for h in hits] == ["b"]


def test_upsert_empty_is_noop():
    store = InMemoryVectorStore()
    asyncio.run(store.upsert([]))
    assert asyncio.run(store.count()) == 0
