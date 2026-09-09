"""Shared pytest fixtures (offline — no network, no API key needed)."""

from __future__ import annotations

import pytest

from app.core.llm import get_embedding_provider, get_llm_provider
from app.observability.trace import ResearchEventBus
from app.rag.engine import RAGEngine

from tests.helpers import FakeRegistry  # noqa: F401 — re-exported for fixture typing


@pytest.fixture
def fake_registry() -> FakeRegistry:
    return FakeRegistry()


@pytest.fixture
def bus() -> ResearchEventBus:
    return ResearchEventBus(persist=None)


@pytest.fixture
def rag_pair():
    """(fresh session index, tiny pre-indexed KB) using deterministic mock embeddings."""
    import asyncio

    session_index = RAGEngine(get_embedding_provider(), get_llm_provider())
    kb_index = RAGEngine(get_embedding_provider(), get_llm_provider())
    asyncio.run(kb_index.ingest_text(
        "kb-doc-1",
        "Hybrid retrieval blends sparse BM25 signals with dense vector similarity. "
        "Reciprocal rank fusion (RRF) is a robust, parameter-light way to merge the "
        "two rankings. Cross-encoder rerankers then refine the top candidates. " * 6,
    ))
    return session_index, kb_index
