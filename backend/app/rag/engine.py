"""RAG Engine — ingestion pipeline + hybrid retrieval (vector + BM25 + RRF + rerank).

Pipeline:
    Query → rewrite → [vector search ‖ BM25] → RRF fusion → dedup → rerank → top-K
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.llm import EmbeddingProvider, LLMProvider
from app.rag.bm25 import BM25Index
from app.rag.chunker import Chunker
from app.rag.reranker import HeuristicReranker
from app.rag.vectorstore import InMemoryVectorStore, VectorRecord


@dataclass
class RetrievedChunk:
    id: str
    text: str
    score: float
    metadata: dict = field(default_factory=dict)


def reciprocal_rank_fusion(*rankings: list[str], k: int = 60) -> dict[str, float]:
    """Standard RRF: score(d) = Σ 1 / (k + rank_i(d))."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


class RAGEngine:
    def __init__(self, embedding: EmbeddingProvider, llm: LLMProvider | None = None,
                 *, chunk_size: int = 700, chunk_overlap: int = 120,
                 vector_top_k: int = 20, bm25_top_k: int = 20, rerank_top_k: int = 8):
        self.embedding = embedding
        self.llm = llm
        self.chunker = Chunker(chunk_size, chunk_overlap)
        self.vector_store = InMemoryVectorStore()
        self.bm25 = BM25Index()
        self.reranker = HeuristicReranker()
        self.vector_top_k = vector_top_k
        self.bm25_top_k = bm25_top_k
        self.rerank_top_k = rerank_top_k
        self._meta: dict[str, dict] = {}
        self._text_cache: dict[str, str] = {}

    # -- ingestion -------------------------------------------------------------

    async def ingest_text(self, document_id: str, text: str, metadata: dict | None = None) -> int:
        metadata = metadata or {"document_id": document_id}
        chunks = self.chunker.split(text, metadata={"document_id": document_id, **metadata})
        if not chunks:
            return 0
        texts = [c.text for c in chunks]
        vectors = await self.embedding.embed(texts)
        records = [
            VectorRecord(id=f"{document_id}::{c.index}", vector=vec, text=c.text,
                         metadata=c.metadata)
            for c, vec in zip(chunks, vectors)
        ]
        await self.vector_store.upsert(records)
        for rec in records:
            self.bm25.add(rec.id, rec.text)
            self._meta[rec.id] = rec.metadata
            self._text_cache[rec.id] = rec.text
        return len(records)

    async def delete_document(self, document_id: str) -> None:
        ids = [cid for cid, meta in self._meta.items()
               if meta.get("document_id") == document_id]
        await self.vector_store.delete(ids)
        for cid in ids:
            self.bm25.remove(cid)
            self._meta.pop(cid, None)
            self._text_cache.pop(cid, None)

    async def count(self) -> int:
        return await self.vector_store.count()

    # -- retrieval ---------------------------------------------------------------

    @staticmethod
    def rewrite_query(query: str) -> list[str]:
        """Lightweight deterministic query expansion (no LLM needed)."""
        base = query.strip()
        variants = [base]
        cleaned = re.sub(r"[？！?!。，,]", " ", base).strip()
        if cleaned and cleaned != base:
            variants.append(cleaned)
        words = cleaned.split()
        if len(words) > 3:
            variants.append(" ".join(words[:4]))
        return variants[:3]

    async def search(self, query: str, *, top_k: int | None = None,
                     filter_meta: dict | None = None) -> dict:
        top_k = top_k or self.rerank_top_k
        variants = self.rewrite_query(query)

        # vector retrieval over all query variants
        vector_hits: dict[str, float] = {}
        for v in variants:
            qvec = (await self.embedding.embed([v]))[0]
            for hit in await self.vector_store.search(qvec, top_k=self.vector_top_k,
                                                      filter_meta=filter_meta):
                vector_hits[hit.id] = max(vector_hits.get(hit.id, 0.0), hit.score)
        vector_ranking = [cid for cid, _ in
                          sorted(vector_hits.items(), key=lambda x: x[1], reverse=True)]

        # BM25 retrieval
        bm25_hits: dict[str, float] = {}
        for v in variants:
            for cid, score in self.bm25.search(v, top_k=self.bm25_top_k):
                bm25_hits[cid] = max(bm25_hits.get(cid, 0.0), score)
        bm25_ranking = [cid for cid, _ in
                        sorted(bm25_hits.items(), key=lambda x: x[1], reverse=True)]

        # RRF fusion
        fused = reciprocal_rank_fusion(vector_ranking, bm25_ranking)
        candidates: list[dict] = []
        seen_texts: set[str] = set()
        for cid, fscore in sorted(fused.items(), key=lambda x: x[1], reverse=True):
            text = self._get_text(cid)
            if not text:
                continue
            key = re.sub(r"\s+", "", text[:200])
            if key in seen_texts:  # duplicate removal
                continue
            seen_texts.add(key)
            candidates.append({
                "id": cid, "text": text, "fusion_score": fscore,
                "vector_score": vector_hits.get(cid, 0.0),
                "bm25_score": bm25_hits.get(cid, 0.0),
                "metadata": self._meta.get(cid, {}),
            })

        reranked = self.reranker.rerank(query, candidates, top_k=top_k)
        chunks = [RetrievedChunk(id=c["id"], text=c["text"], score=c["rerank_score"],
                                 metadata=c["metadata"]) for c in reranked]
        return {"query": query, "chunks": [c.__dict__ | {} for c in chunks],
                "vector_candidates": len(vector_ranking), "bm25_candidates": len(bm25_ranking),
                "fused_candidates": len(candidates)}

    def _get_text(self, cid: str) -> str:
        return self._text_cache.get(cid, "")

    async def build_context(self, chunks: list[RetrievedChunk], *, budget_chars: int = 6000) -> str:
        """Evidence block format used across agents: [E1] text (source meta)."""
        parts: list[str] = []
        used = 0
        for i, chunk in enumerate(chunks, start=1):
            header = f"[E{i}] {chunk.text}"
            meta = chunk.metadata or {}
            if meta.get("source_title"):
                header += f"\n(source: {meta['source_title']})"
            if used + len(header) > budget_chars and parts:
                break
            parts.append(header)
            used += len(header)
        return "\n\n".join(parts)
