"""Retriever Agent — hybrid retrieval over collected pages + local knowledge base."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.agent import BaseAgent, AgentContext
from app.rag.engine import RAGEngine, RetrievedChunk
from app.tools.web_search import _strip_html


class RetrieverAgent(BaseAgent):
    """Builds a per-session ephemeral index from the pages the Researcher collected,
    then runs hybrid retrieval (vector + BM25 + RRF + rerank) against it and the
    global knowledge base."""

    name = "Retriever"
    system_prompt = "Retriever agent: hybrid retrieval over session corpus and local KB."
    timeout = 90

    def __init__(self, llm, session_index: RAGEngine, kb_index: RAGEngine):
        super().__init__(llm, tools=None)
        self.session_index = session_index
        self.kb_index = kb_index

    async def ingest_pages(self, ctx: AgentContext, pages: list[dict]) -> list[dict]:
        """Ingest collected pages into the session index; returns registered sources.

        page: {"title": str, "url": str|None, "content": str, "source_type": str}
        """
        sources: list[dict] = []
        for page in pages:
            title = (page.get("title") or "untitled").strip()[:300]
            url = page.get("url")
            content = page.get("content") or ""
            if len(content.strip()) < 40:
                continue
            source_type = page.get("source_type") or ("web" if url else "local")
            domain = urlparse(url).netloc if url else "local"
            source_id = _hash_id(url or title)
            sources.append({"id": source_id, "title": title, "url": url,
                            "source_type": source_type, "domain": domain})
            await self.session_index.ingest_text(
                source_id, _strip_html(content) if "<" in content else content,
                metadata={"source_id": source_id, "source_title": title, "url": url,
                          "source_type": source_type})
        await self.trace(ctx, "TASK_END", output_summary=f"已索引 {len(sources)} 个来源")
        return sources

    async def retrieve(self, ctx: AgentContext, query: str, *, top_k: int = 8) -> dict:
        """Hybrid search across session index + KB; returns evidence-ready chunks."""
        session_res = await self.session_index.search(query, top_k=top_k)
        kb_res = await self.kb_index.search(query, top_k=max(2, top_k // 2))
        chunks: list[RetrievedChunk] = [
            RetrievedChunk(id=c["id"], text=c["text"], score=c["score"], metadata=c["metadata"])
            for c in session_res["chunks"]]
        chunks += [RetrievedChunk(id=f"kb::{c['id']}", text=c["text"], score=c["score"],
                                  metadata=c["metadata"]) for c in kb_res["chunks"]]
        chunks.sort(key=lambda c: c.score, reverse=True)
        chunks = chunks[:top_k]
        await self.trace(ctx, "TASK_END",
                         output_summary=(f"检索到会话 {len(session_res['chunks'])} 条 + "
                                         f"知识库 {len(kb_res['chunks'])} 条证据片段"))
        return {"chunks": [{"id": c.id, "text": c.text, "score": c.score,
                            "metadata": c.metadata} for c in chunks]}


def _hash_id(seed: str) -> str:
    import hashlib

    return "src-" + hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]


def _clean(text: str) -> str:  # re-exported helper for callers
    return re.sub(r"\s+", " ", text).strip()
