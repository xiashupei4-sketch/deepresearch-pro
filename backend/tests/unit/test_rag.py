"""Unit tests — RAG fusion, reranking, mock embeddings, and engine e2e search."""

import asyncio

from app.core.llm import HashingEmbeddingProvider, get_llm_provider
from app.rag.bm25 import BM25Index
from app.rag.engine import RAGEngine, reciprocal_rank_fusion


def test_rrf_fusion_prefers_docs_present_in_all_rankings():
    fused = reciprocal_rank_fusion(["a", "b", "c"], ["b", "a", "d"])
    # "a" and "b" appear in both; they must outrank docs seen once
    assert fused["a"] > fused["c"]
    assert fused["b"] > fused["d"]
    top2 = {k for k, _ in sorted(fused.items(), key=lambda x: x[1], reverse=True)[:2]}
    assert top2 == {"a", "b"}


def test_bm25_ranks_relevant_doc_first():
    bm25 = BM25Index()
    bm25.add("d1", "hybrid retrieval combines bm25 and dense vectors")
    bm25.add("d2", "cross encoder reranking improves precision")
    bm25.add("d3", "knowledge graphs store entities and relations")
    hits = bm25.search("hybrid retrieval bm25", top_k=2)
    assert hits[0][0] == "d1"


def test_hashing_embedding_is_deterministic_and_normalized():
    emb = HashingEmbeddingProvider(dim=64)
    v1, v2 = asyncio.run(emb.embed(["hello world", "hello world"]))
    assert v1 == v2
    assert abs(sum(x * x for x in v1) - 1.0) < 1e-6


def test_engine_hybrid_search_finds_kb_content():
    """End-to-end engine search: ingest → hybrid query → relevant chunk returned."""
    engine = RAGEngine(HashingEmbeddingProvider(dim=128), get_llm_provider())
    asyncio.run(engine.ingest_text(
        "doc-1",
        "Reciprocal rank fusion merges BM25 and vector rankings robustly. " * 10,
    ))
    asyncio.run(engine.ingest_text(
        "doc-2",
        "Cross-encoder rerankers refine the top retrieved candidates. " * 10,
    ))
    res = asyncio.run(engine.search("reciprocal rank fusion bm25", top_k=3))
    assert res["chunks"], "expected at least one chunk"
    top_text = res["chunks"][0]["text"].lower()
    assert "reciprocal rank fusion" in top_text or "bm25" in top_text
    assert res["vector_candidates"] > 0 and res["bm25_candidates"] > 0


def test_engine_delete_document_removes_all_chunks():
    engine = RAGEngine(HashingEmbeddingProvider(dim=128))
    asyncio.run(engine.ingest_text("doc-1", "alpha beta gamma. " * 30))
    n = asyncio.run(engine.count())
    assert n > 0
    asyncio.run(engine.delete_document("doc-1"))
    assert asyncio.run(engine.count()) == 0
    res = asyncio.run(engine.search("alpha beta", top_k=3))
    assert res["chunks"] == []


def test_build_context_respects_budget_and_labels():
    from app.rag.engine import RetrievedChunk

    engine = RAGEngine(HashingEmbeddingProvider(dim=64))
    chunks = [
        RetrievedChunk(id="c1", text="x" * 100, score=0.9,
                       metadata={"source_title": "Doc A"}),
        RetrievedChunk(id="c2", text="y" * 100, score=0.8, metadata={}),
    ]
    ctx = asyncio.run(engine.build_context(chunks, budget_chars=1000))
    assert ctx.startswith("[E1]")
    assert "[E2]" in ctx
    assert "Doc A" in ctx
