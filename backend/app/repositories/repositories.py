"""Repository helpers — thin async data access used by services."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Document,
    EvaluationResult,
    Evidence,
    Message,
    ResearchSession,
    ResearchTask,
    Source,
    TraceEvent,
)


async def get_session(db: AsyncSession, research_id: str) -> ResearchSession | None:
    return await db.get(ResearchSession, research_id)


async def list_sessions(db: AsyncSession, limit: int = 30, offset: int = 0) -> list[ResearchSession]:
    # 置顶会话优先,其余按创建时间倒序
    result = await db.execute(
        select(ResearchSession)
        .order_by(ResearchSession.pinned.desc(), ResearchSession.created_at.desc())
        .limit(limit).offset(offset))
    return list(result.scalars().all())


async def set_pinned(db: AsyncSession, research_id: str, pinned: bool) -> ResearchSession | None:
    session = await db.get(ResearchSession, research_id)
    if session is None:
        return None
    session.pinned = pinned
    await db.commit()
    return session


async def delete_session(db: AsyncSession, research_id: str) -> bool:
    """删除会话及其全部关联数据;返回是否存在。"""
    session = await db.get(ResearchSession, research_id)
    if session is None:
        return False
    for model in (TraceEvent, Evidence, EvaluationResult, Source, ResearchTask, Message):
        await db.execute(delete(model).where(model.session_id == research_id))
    await db.delete(session)
    await db.commit()
    return True


async def session_tasks(db: AsyncSession, research_id: str) -> list[ResearchTask]:
    result = await db.execute(
        select(ResearchTask).where(ResearchTask.session_id == research_id)
        .order_by(ResearchTask.order_index))
    return list(result.scalars().all())


async def session_sources(db: AsyncSession, research_id: str) -> list[Source]:
    result = await db.execute(select(Source).where(Source.session_id == research_id)
                              .order_by(Source.created_at))
    return list(result.scalars().all())


async def session_evidence(db: AsyncSession, research_id: str) -> list[Evidence]:
    result = await db.execute(select(Evidence).where(Evidence.session_id == research_id)
                              .order_by(Evidence.created_at))
    return list(result.scalars().all())


async def session_traces(db: AsyncSession, research_id: str) -> list[TraceEvent]:
    result = await db.execute(
        select(TraceEvent).where(TraceEvent.session_id == research_id)
        .order_by(TraceEvent.created_at, TraceEvent.id))
    return list(result.scalars().all())


async def get_evaluation(db: AsyncSession, research_id: str) -> EvaluationResult | None:
    result = await db.execute(select(EvaluationResult)
                              .where(EvaluationResult.session_id == research_id))
    return result.scalar_one_or_none()


async def list_documents(db: AsyncSession) -> list[Document]:
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    return list(result.scalars().all())


async def trace_error_count(db: AsyncSession, research_id: str) -> int:
    result = await db.execute(
        select(func.count()).select_from(TraceEvent)
        .where(TraceEvent.session_id == research_id, TraceEvent.event_type == "ERROR"))
    return int(result.scalar() or 0)
