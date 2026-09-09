"""Memory system — working / short-term / long-term.

* Working memory  : the live LangGraph ResearchState (not persisted as memory).
* Short-term      : per-session messages (DB `messages` table).
* Long-term       : distilled, importance-scored facts (DB `memories`), searchable
                    by embedding similarity — never a dump of the whole conversation.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm import EmbeddingProvider
from app.models.models import MemoryRecord, Message


class MemoryService:
    def __init__(self, embedding: EmbeddingProvider):
        self.embedding = embedding

    # -- short-term -------------------------------------------------------------

    async def add_message(self, session: AsyncSession, research_id: str, role: str,
                          content: str, agent: str | None = None) -> None:
        session.add(Message(research_id := research_id and session_id_placeholder(
            research_id), role=role, agent=agent, content=content[:8000]))

    async def recent_messages(self, session: AsyncSession, research_id: str,
                              limit: int = 20) -> list[Message]:
        result = await session.execute(
            select(Message).where(Message.session_id == research_id)
            .order_by(Message.created_at.desc()).limit(limit))
        return list(reversed(result.scalars().all()))

    # -- long-term ----------------------------------------------------------------

    async def remember(self, session: AsyncSession, content: str, *, user_id: str | None = None,
                       research_id: str | None = None, type: str = "fact",
                       importance: float = 0.5) -> MemoryRecord:
        vec = (await self.embedding.embed([content]))[0]
        record = MemoryRecord(user_id=user_id, session_id=research_id, type=type,
                              content=content[:2000], importance=importance, embedding=vec)
        session.add(record)
        return record

    async def recall(self, session: AsyncSession, query: str, *, top_k: int = 3,
                     min_importance: float = 0.0) -> list[MemoryRecord]:
        result = await session.execute(
            select(MemoryRecord).where(MemoryRecord.importance >= min_importance))
        records = result.scalars().all()
        if not records:
            return []
        qvec = (await self.embedding.embed([query]))[0]
        scored: list[tuple[float, MemoryRecord]] = []
        for r in records:
            if not r.embedding:
                continue
            score = _cosine(qvec, r.embedding)
            scored.append((score * 0.8 + r.importance * 0.2, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]

    @staticmethod
    def extract_memory_candidates(query: str, report: str) -> list[tuple[str, float]]:
        """Rule-based extractor — distills durable facts from a finished research."""
        candidates: list[tuple[str, float]] = []
        if len(query) > 15:
            candidates.append((f"User research interest: {query[:300]}", 0.8))
        for line in report.splitlines():
            line = line.strip()
            if line.startswith("## ") and line != "## Research Report":
                candidates.append((f"Report section produced: {line[3:]}", 0.3))
        return candidates[:4]


def _cosine(a: list[float], b: list[float]) -> float:
    import numpy as np

    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    denom = (np.linalg.norm(va) * np.linalg.norm(vb)) or 1.0
    return float(np.dot(va, vb) / denom)
